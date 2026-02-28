# SSH Key Upload Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow users to upload SSH private key files via the web UI and select managed keys when adding servers.

**Architecture:** New `POST /api/keys/upload` multipart endpoint calls existing `import_key()`. Settings page gets an "Upload Key" button/modal. Add Server modal replaces the text `ssh_key_path` input with a dropdown of managed keys plus "Upload new..." option.

**Tech Stack:** FastAPI (UploadFile, Form), React, TanStack Query, Playwright E2E

---

### Task 1: Backend upload endpoint

**Files:**
- Modify: `api/routes/keys.py:42-68` (add new endpoint after `create_key`)
- Test: `tests/unit/test_key_upload.py` (create)

**Step 1: Write the failing test**

Create `tests/unit/test_key_upload.py`:

```python
"""Tests for SSH key upload endpoint."""

from pathlib import Path
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient


@pytest.fixture
def client(isolated_config):
    from api.main import app
    return TestClient(app)


@pytest.fixture
def api_key(isolated_config):
    from cli.core.config import INFRAKT_HOME
    key_path = INFRAKT_HOME / "api_key.txt"
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_text("test-api-key")
    return "test-api-key"


@pytest.fixture
def ed25519_key_bytes():
    """Generate a valid Ed25519 private key in PEM format."""
    private_key = Ed25519PrivateKey.generate()
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption(),
    )


def test_upload_valid_key(client, api_key, ed25519_key_bytes):
    resp = client.post(
        "/api/keys/upload",
        headers={"X-API-Key": api_key},
        data={"name": "my-uploaded-key"},
        files={"file": ("id_ed25519", ed25519_key_bytes, "application/octet-stream")},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "my-uploaded-key"
    assert body["key_type"] == "ed25519"
    assert body["fingerprint"].startswith("SHA256:")
    assert body["public_key"].startswith("ssh-ed25519")


def test_upload_duplicate_name(client, api_key, ed25519_key_bytes):
    client.post(
        "/api/keys/upload",
        headers={"X-API-Key": api_key},
        data={"name": "dup-key"},
        files={"file": ("id_ed25519", ed25519_key_bytes, "application/octet-stream")},
    )
    resp = client.post(
        "/api/keys/upload",
        headers={"X-API-Key": api_key},
        data={"name": "dup-key"},
        files={"file": ("id_ed25519", ed25519_key_bytes, "application/octet-stream")},
    )
    assert resp.status_code == 409


def test_upload_invalid_file(client, api_key):
    resp = client.post(
        "/api/keys/upload",
        headers={"X-API-Key": api_key},
        data={"name": "bad-key"},
        files={"file": ("id_ed25519", b"not a real key", "application/octet-stream")},
    )
    assert resp.status_code == 400


def test_upload_too_large(client, api_key):
    big_content = b"x" * 20_000  # 20KB, over the 10KB limit
    resp = client.post(
        "/api/keys/upload",
        headers={"X-API-Key": api_key},
        data={"name": "big-key"},
        files={"file": ("id_ed25519", big_content, "application/octet-stream")},
    )
    assert resp.status_code == 400
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_key_upload.py -v`
Expected: FAIL (404 — endpoint doesn't exist)

**Step 3: Write minimal implementation**

In `api/routes/keys.py`, add after the existing `create_key` endpoint (line ~68):

```python
from fastapi import UploadFile, File, Form
import tempfile

@router.post("/upload", response_model=SSHKeyOut, status_code=201)
async def upload_key(
    name: str = Form(..., min_length=1, max_length=100),
    file: UploadFile = File(...),
) -> SSHKeyOut:
    """Upload an existing SSH private key file."""
    from cli.core.key_manager import import_key

    init_db()

    # Validate name
    import re
    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$", name):
        raise HTTPException(400, "Invalid key name")

    # Check duplicate
    with get_session() as session:
        existing = session.query(SSHKey).filter(SSHKey.name == name).first()
        if existing:
            raise HTTPException(409, f"SSH key '{name}' already exists")

    # Read and validate size
    content = await file.read()
    if len(content) > 10_240:  # 10KB max
        raise HTTPException(400, "Key file too large (max 10KB)")

    # Write to temp file and import
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".key") as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        private_path, fingerprint = import_key(name, tmp_path)
        public_key = get_public_key(private_path)
    except Exception as exc:
        raise HTTPException(400, f"Invalid SSH key file: {exc}")
    finally:
        tmp_path.unlink(missing_ok=True)

    # Save to DB
    with get_session() as session:
        ssh_key = SSHKey(
            name=name,
            fingerprint=fingerprint,
            key_type="ed25519",
            public_key=public_key,
            key_path=str(private_path),
        )
        session.add(ssh_key)
        session.flush()
        return _ssh_key_out(ssh_key)
```

Add these imports at top of `api/routes/keys.py`:

```python
import re
import tempfile
from pathlib import Path
from fastapi import UploadFile, File, Form
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_key_upload.py -v`
Expected: PASS (all 4 tests)

**Step 5: Run full test suite + lint**

Run: `pytest tests/unit/ -v && ruff check . && ruff format --check .`
Expected: All pass

**Step 6: Commit**

```bash
git add api/routes/keys.py tests/unit/test_key_upload.py
git commit -m "feat: add POST /api/keys/upload endpoint for SSH key file upload"
```

---

### Task 2: Frontend API client + hook for upload

**Files:**
- Modify: `frontend/src/api/client.ts:615-621` (add `upload` to `keysApi`)
- Modify: `frontend/src/hooks/useApi.ts:551-576` (add `useUploadSSHKey` hook)

**Step 1: Add upload function to keysApi**

In `frontend/src/api/client.ts`, add an `upload` method to `keysApi` (after line 617):

```typescript
export const keysApi = {
  list: (): Promise<SSHKey[]> => get("/keys"),
  generate: (name: string): Promise<SSHKey> => post("/keys", { name }),
  upload: async (name: string, file: File): Promise<SSHKey> => {
    const formData = new FormData();
    formData.append("name", name);
    formData.append("file", file);
    const res = await fetch(`${BASE}/keys/upload`, {
      method: "POST",
      headers: { "X-API-Key": getApiKey() },
      body: formData,
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `Upload failed (${res.status})`);
    }
    return res.json();
  },
  delete: (name: string): Promise<void> => del(`/keys/${name}`),
  deploy: (name: string, serverName: string): Promise<{ message: string }> =>
    post(`/keys/${name}/deploy`, { server_name: serverName }),
};
```

Note: We can't use the `post()` helper because it sends `Content-Type: application/json`. Multipart file upload needs `FormData` with no explicit Content-Type header (browser sets boundary automatically).

Check where `BASE` and `getApiKey()` are defined — they should already be accessible in client.ts. If `BASE` is not exported, use whatever base URL constant the file uses.

**Step 2: Add useUploadSSHKey hook**

In `frontend/src/hooks/useApi.ts`, add after `useGenerateSSHKey` (~line 559):

```typescript
export function useUploadSSHKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ name, file }: { name: string; file: File }) =>
      keysApi.upload(name, file),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.keys });
    },
  });
}
```

**Step 3: Run type check**

Run: `cd frontend && npx tsc --noEmit`
Expected: Clean (no errors)

**Step 4: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/hooks/useApi.ts
git commit -m "feat: add keysApi.upload() and useUploadSSHKey hook"
```

---

### Task 3: Upload Key modal on Settings page

**Files:**
- Modify: `frontend/src/pages/Settings.tsx`

**Step 1: Add state for upload modal**

At `Settings.tsx:94` (near the existing SSH key state), add:

```typescript
const uploadKey = useUploadSSHKey();
const [showUploadKeyModal, setShowUploadKeyModal] = useState(false);
const [uploadKeyName, setUploadKeyName] = useState("");
const [uploadKeyFile, setUploadKeyFile] = useState<File | null>(null);
```

Import `useUploadSSHKey` from `@/hooks/useApi` (add to existing import).
Import `Upload` from `lucide-react` (add to existing import).

**Step 2: Add upload handler**

After the existing `handleGenerateKey` function (~line 131), add:

```typescript
async function handleUploadKey(e: React.FormEvent) {
  e.preventDefault();
  if (!uploadKeyName.trim() || !uploadKeyFile) return;
  try {
    await uploadKey.mutateAsync({ name: uploadKeyName.trim(), file: uploadKeyFile });
    toast.success(`SSH key "${uploadKeyName.trim()}" uploaded.`);
    setShowUploadKeyModal(false);
    setUploadKeyName("");
    setUploadKeyFile(null);
  } catch (err) {
    toast.error(err instanceof Error ? err.message : "Failed to upload key.");
  }
}
```

**Step 3: Add Upload Key button**

Replace the single "Generate Key" button at line ~330-336 with a button group:

```tsx
<div className="flex shrink-0 items-center gap-2">
  <button
    onClick={() => setShowUploadKeyModal(true)}
    className="flex items-center gap-2 rounded-lg border border-zinc-600 bg-zinc-700 px-4 py-2 text-sm font-medium text-zinc-300 transition-colors hover:bg-zinc-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500"
  >
    <Upload size={16} aria-hidden="true" />
    Upload Key
  </button>
  <button
    onClick={() => setShowGenerateKeyModal(true)}
    className="flex items-center gap-2 rounded-lg bg-orange-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-orange-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500"
  >
    <Plus size={16} aria-hidden="true" />
    Generate Key
  </button>
</div>
```

**Step 4: Add Upload Key modal**

After the existing Generate Key modal markup, add:

```tsx
<Modal open={showUploadKeyModal} onClose={() => setShowUploadKeyModal(false)} title="Upload SSH Key">
  <form onSubmit={(e) => void handleUploadKey(e)} className="space-y-4">
    <div>
      <label htmlFor="upload-key-name" className="mb-1.5 block text-xs font-medium text-zinc-300">
        Key Name <span className="text-red-400">*</span>
      </label>
      <input
        id="upload-key-name"
        type="text"
        required
        value={uploadKeyName}
        onChange={(e) => setUploadKeyName(e.target.value)}
        placeholder="my-server-key"
        className="w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none"
      />
    </div>
    <div>
      <label htmlFor="upload-key-file" className="mb-1.5 block text-xs font-medium text-zinc-300">
        Private Key File <span className="text-red-400">*</span>
      </label>
      <input
        id="upload-key-file"
        type="file"
        required
        onChange={(e) => setUploadKeyFile(e.target.files?.[0] ?? null)}
        className="w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 file:mr-3 file:rounded-md file:border-0 file:bg-zinc-600 file:px-3 file:py-1 file:text-sm file:text-zinc-300 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none"
      />
    </div>
    <div className="flex justify-end gap-3 pt-2">
      <button
        type="button"
        onClick={() => setShowUploadKeyModal(false)}
        className="rounded-lg border border-zinc-600 bg-zinc-700 px-4 py-2 text-sm font-medium text-zinc-300 transition-colors hover:bg-zinc-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500"
      >
        Cancel
      </button>
      <button
        type="submit"
        disabled={!uploadKeyName.trim() || !uploadKeyFile || uploadKey.isPending}
        className="flex items-center gap-2 rounded-lg bg-orange-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-orange-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500 disabled:opacity-50"
      >
        {uploadKey.isPending && <Loader2 size={14} className="animate-spin" aria-hidden="true" />}
        Upload
      </button>
    </div>
  </form>
</Modal>
```

**Step 5: Run type check and dev server**

Run: `cd frontend && npx tsc --noEmit`
Expected: Clean

**Step 6: Commit**

```bash
git add frontend/src/pages/Settings.tsx
git commit -m "feat: add Upload Key button and modal to Settings page"
```

---

### Task 4: Key picker dropdown on Add Server modal

**Files:**
- Modify: `frontend/src/pages/Servers.tsx`

**Step 1: Add key data and upload state**

At the top of the `Servers` component (~line 150), add:

```typescript
const { data: sshKeys = [] } = useSSHKeys();
const uploadKey = useUploadSSHKey();
const [showUploadKeyInline, setShowUploadKeyInline] = useState(false);
const [inlineKeyName, setInlineKeyName] = useState("");
const [inlineKeyFile, setInlineKeyFile] = useState<File | null>(null);
```

Import `useSSHKeys` and `useUploadSSHKey` from `@/hooks/useApi` (add to existing import).
Import `Upload` from `lucide-react` (add to existing import).

**Step 2: Replace ssh_key_path text input with dropdown**

Replace the SSH Key Path `<div>` block (lines ~346-363) with:

```tsx
{/* SSH Key */}
<div>
  <label
    htmlFor="server-key"
    className="mb-1.5 block text-xs font-medium text-zinc-300"
  >
    SSH Key
  </label>
  <div className="flex gap-2">
    <select
      id="server-key"
      name="ssh_key_path"
      value={form.ssh_key_path ?? ""}
      onChange={handleChange}
      className="flex-1 rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none"
    >
      <option value="">None (use SSH agent)</option>
      {sshKeys.map((k) => (
        <option key={k.id} value={`~/.infrakt/keys/${k.name}`}>
          {k.name}
        </option>
      ))}
    </select>
    <button
      type="button"
      onClick={() => setShowUploadKeyInline(true)}
      title="Upload a key"
      className="rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-400 transition-colors hover:bg-zinc-600 hover:text-orange-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500"
    >
      <Upload size={16} aria-hidden="true" />
    </button>
  </div>
</div>
```

**Step 3: Add inline upload handler**

Add this function in the Servers component:

```typescript
async function handleInlineUpload(e: React.FormEvent) {
  e.preventDefault();
  if (!inlineKeyName.trim() || !inlineKeyFile) return;
  try {
    await uploadKey.mutateAsync({ name: inlineKeyName.trim(), file: inlineKeyFile });
    // Auto-select the newly uploaded key
    setForm((prev) => ({ ...prev, ssh_key_path: `~/.infrakt/keys/${inlineKeyName.trim()}` }));
    setShowUploadKeyInline(false);
    setInlineKeyName("");
    setInlineKeyFile(null);
  } catch (err) {
    // Show error via toast if available, or alert
    alert(err instanceof Error ? err.message : "Failed to upload key.");
  }
}
```

**Step 4: Add inline upload modal**

After the Add Server `</Modal>`, add:

```tsx
<Modal open={showUploadKeyInline} onClose={() => setShowUploadKeyInline(false)} title="Upload SSH Key">
  <form onSubmit={(e) => void handleInlineUpload(e)} className="space-y-4">
    <div>
      <label htmlFor="inline-key-name" className="mb-1.5 block text-xs font-medium text-zinc-300">
        Key Name <span className="text-red-400">*</span>
      </label>
      <input
        id="inline-key-name"
        type="text"
        required
        value={inlineKeyName}
        onChange={(e) => setInlineKeyName(e.target.value)}
        placeholder="my-server-key"
        className="w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none"
      />
    </div>
    <div>
      <label htmlFor="inline-key-file" className="mb-1.5 block text-xs font-medium text-zinc-300">
        Private Key File <span className="text-red-400">*</span>
      </label>
      <input
        id="inline-key-file"
        type="file"
        required
        onChange={(e) => setInlineKeyFile(e.target.files?.[0] ?? null)}
        className="w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 file:mr-3 file:rounded-md file:border-0 file:bg-zinc-600 file:px-3 file:py-1 file:text-sm file:text-zinc-300 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none"
      />
    </div>
    <div className="flex justify-end gap-3 pt-2">
      <button
        type="button"
        onClick={() => setShowUploadKeyInline(false)}
        className="rounded-lg border border-zinc-600 bg-zinc-700 px-4 py-2 text-sm font-medium text-zinc-300 transition-colors hover:bg-zinc-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500"
      >
        Cancel
      </button>
      <button
        type="submit"
        disabled={!inlineKeyName.trim() || !inlineKeyFile || uploadKey.isPending}
        className="flex items-center gap-2 rounded-lg bg-orange-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-orange-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500 disabled:opacity-50"
      >
        {uploadKey.isPending && <Loader2 size={14} className="animate-spin" aria-hidden="true" />}
        Upload
      </button>
    </div>
  </form>
</Modal>
```

**Step 5: Run type check**

Run: `cd frontend && npx tsc --noEmit`
Expected: Clean

**Step 6: Commit**

```bash
git add frontend/src/pages/Servers.tsx
git commit -m "feat: replace SSH key path input with managed key dropdown on Add Server"
```

---

### Task 5: E2E tests for SSH key upload

**Files:**
- Modify: `frontend/e2e/fixtures.ts` (add upload route mock)
- Modify: `frontend/e2e/ssh-keys.spec.ts` (add upload tests)
- Modify: `frontend/e2e/servers.spec.ts` (add key picker tests)

**Step 1: Add upload route mock to fixtures**

In `frontend/e2e/fixtures.ts`, find the `**/api/keys` route handler (~line 696-713). The existing POST handler returns a generated key. Add a handler for `**/api/keys/upload` before it:

```typescript
// In mockApi(), add before the existing /api/keys route:
await page.route("**/api/keys/upload", async (route) => {
  if (route.request().method() === "POST") {
    return route.fulfill({
      status: 201,
      json: {
        id: 100,
        name: "uploaded-key",
        fingerprint: "SHA256:uploadedkey1234567890uploadedkey123456",
        key_type: "ed25519",
        public_key: "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI... uploaded-key",
        created_at: new Date().toISOString(),
      },
    });
  }
  return route.continue();
});
```

**Step 2: Write E2E tests for upload on Settings page**

Add to `frontend/e2e/ssh-keys.spec.ts`:

```typescript
// ─── Upload Key modal ──────────────────────────────────────────────────────

test("Upload Key button is visible", async ({ page }) => {
  await expect(
    page.getByRole("button", { name: "Upload Key" }),
  ).toBeVisible();
});

test("Upload Key button opens modal", async ({ page }) => {
  await page.getByRole("button", { name: "Upload Key" }).click();
  await expect(
    page.getByRole("heading", { name: "Upload SSH Key" }),
  ).toBeVisible();
});

test("Upload modal has name input and file input", async ({ page }) => {
  await page.getByRole("button", { name: "Upload Key" }).click();
  await expect(page.getByLabel(/Key Name/)).toBeVisible();
  await expect(page.getByLabel(/Private Key File/)).toBeVisible();
});

test("Upload button is disabled when fields are empty", async ({ page }) => {
  await page.getByRole("button", { name: "Upload Key" }).click();
  const submitBtn = page.locator("form").getByRole("button", { name: "Upload" });
  await expect(submitBtn).toBeDisabled();
});

test("Cancel closes Upload Key modal", async ({ page }) => {
  await page.getByRole("button", { name: "Upload Key" }).click();
  await expect(
    page.getByRole("heading", { name: "Upload SSH Key" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(
    page.getByRole("heading", { name: "Upload SSH Key" }),
  ).not.toBeVisible();
});
```

**Step 3: Write E2E tests for key picker on Add Server**

Add to `frontend/e2e/servers.spec.ts`:

```typescript
test("Add Server modal shows SSH Key dropdown with managed keys", async ({ page }) => {
  await page.getByRole("button", { name: /Add Server/i }).click();
  const keySelect = page.getByLabel("SSH Key");
  await expect(keySelect).toBeVisible();
  // Should have "None" + managed keys
  await expect(keySelect.locator("option")).toHaveCount(3); // None + prod-key + staging-key
});

test("Add Server modal has upload key button", async ({ page }) => {
  await page.getByRole("button", { name: /Add Server/i }).click();
  await expect(page.getByTitle("Upload a key")).toBeVisible();
});
```

**Step 4: Run E2E tests**

Run: `cd frontend && npx playwright test ssh-keys.spec.ts servers.spec.ts --reporter=list`
Expected: All pass

**Step 5: Commit**

```bash
git add frontend/e2e/fixtures.ts frontend/e2e/ssh-keys.spec.ts frontend/e2e/servers.spec.ts
git commit -m "test: add E2E tests for SSH key upload and key picker"
```

---

### Task 6: Final verification

**Step 1: Run full backend test suite**

Run: `pytest -v`
Expected: All pass

**Step 2: Run lint + format**

Run: `ruff check . && ruff format --check .`
Expected: Clean

**Step 3: Run type check**

Run: `cd frontend && npx tsc --noEmit`
Expected: Clean

**Step 4: Run full E2E suite**

Run: `cd frontend && npx playwright test --reporter=list`
Expected: All pass

**Step 5: Run production build**

Run: `cd frontend && npm run build`
Expected: Clean build
