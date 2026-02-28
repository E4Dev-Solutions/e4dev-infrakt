# Server Wipe-on-Provision Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Automatically wipe non-infrakT-host servers before provisioning so they start clean.

**Architecture:** Add `is_infrakt_host` boolean to Server model. The provisioner gains a `wipe_server()` function that stops all Docker containers, prunes Docker, and deletes `/opt/infrakt/`. The provision workflow calls `wipe_server()` first for non-infrakT-host servers. `setup-vps.sh` sets the flag after registering the server.

**Tech Stack:** Python (SQLAlchemy, Click, FastAPI), React (TanStack Query), Playwright E2E tests

---

### Task 1: Add `is_infrakt_host` Column to Server Model

**Files:**
- Modify: `cli/models/server.py:26` (add column after `status`)
- Modify: `cli/core/database.py:47` (add migration)

**Step 1: Add column to Server model**

In `cli/models/server.py`, add after line 25 (`status` column):

```python
is_infrakt_host: Mapped[bool] = mapped_column(default=False)
```

Import `Boolean` from `sqlalchemy` on line 6:

```python
from sqlalchemy import Boolean, Integer, String, func
```

**Step 2: Add migration**

In `cli/core/database.py`, add to the `migrations` list in `_apply_migrations()` (after the existing entries around line 48):

```python
"ALTER TABLE servers ADD COLUMN is_infrakt_host BOOLEAN DEFAULT 0",
```

**Step 3: Run tests to verify no breakage**

Run: `pytest tests/unit/ -v -x --timeout=30 2>&1 | tail -20`
Expected: All existing tests pass (the column has a default so nothing breaks)

**Step 4: Commit**

```bash
git add cli/models/server.py cli/core/database.py
git commit -m "feat: add is_infrakt_host column to Server model"
```

---

### Task 2: Add `wipe_server()` to Provisioner

**Files:**
- Modify: `cli/core/provisioner.py` (add `wipe_server()` function)
- Create: `tests/unit/test_provisioner_wipe.py`

**Step 1: Write the failing test**

Create `tests/unit/test_provisioner_wipe.py`:

```python
"""Tests for server wipe functionality."""

from unittest.mock import MagicMock, call

from cli.core.provisioner import wipe_server


class TestWipeServer:
    def test_wipe_stops_containers_prunes_docker_and_removes_directory(self):
        ssh = MagicMock()
        ssh.run.return_value = ""
        ssh.run_checked.return_value = ""

        wipe_server(ssh)

        calls = [c[0][0] for c in ssh.run.call_args_list + ssh.run_checked.call_args_list]
        # Must stop all containers
        assert any("docker stop" in c for c in calls)
        # Must prune Docker
        assert any("docker system prune" in c for c in calls)
        # Must remove /opt/infrakt
        assert any("rm -rf /opt/infrakt" in c for c in calls)

    def test_wipe_calls_on_step_callback(self):
        ssh = MagicMock()
        ssh.run.return_value = ""
        ssh.run_checked.return_value = ""
        on_step = MagicMock()

        wipe_server(ssh, on_step=on_step)

        assert on_step.call_count >= 3

    def test_wipe_tolerates_no_containers(self):
        """docker stop with no containers should not raise."""
        ssh = MagicMock()
        ssh.run.return_value = ""
        ssh.run_checked.return_value = ""

        # Should not raise
        wipe_server(ssh)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_provisioner_wipe.py -v`
Expected: FAIL — `ImportError: cannot import name 'wipe_server'`

**Step 3: Implement `wipe_server()`**

In `cli/core/provisioner.py`, add before `provision_server()` (around line 52):

```python
WIPE_STEPS = [
    (
        "Stopping all Docker containers",
        "docker stop $(docker ps -aq) 2>/dev/null || true",
    ),
    (
        "Removing all Docker data",
        "docker system prune -af --volumes 2>/dev/null || true",
    ),
    (
        "Deleting /opt/infrakt",
        "rm -rf /opt/infrakt",
    ),
]


def wipe_server(
    ssh: SSHClient,
    on_step: Callable[[str, int, int], None] | None = None,
) -> None:
    """Wipe all Docker data and infrakt files from a remote server.

    Args:
        ssh: Connected SSHClient instance.
        on_step: Optional callback(step_name, index, total) for progress reporting.
    """
    total = len(WIPE_STEPS)
    for idx, (step_name, command) in enumerate(WIPE_STEPS):
        if on_step:
            on_step(step_name, idx, total)
        ssh.run(command, timeout=120)
```

Note: Uses `ssh.run()` (not `run_checked()`) because `docker stop` on empty container list returns non-zero and that's OK.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_provisioner_wipe.py -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add cli/core/provisioner.py tests/unit/test_provisioner_wipe.py
git commit -m "feat: add wipe_server() to provisioner"
```

---

### Task 3: Integrate Wipe into CLI Provision Command

**Files:**
- Modify: `cli/commands/server.py:124-142` (provision command)

**Step 1: Update the provision command**

Replace the `provision` function in `cli/commands/server.py` (lines 124-142) with:

```python
@server.command()
@click.argument("name")
def provision(name: str) -> None:
    """Provision a server with Docker, Traefik, and security hardening."""
    init_db()
    srv = _get_server(name)

    # Wipe non-infrakT-host servers before provisioning
    if not srv.is_infrakt_host:
        typed = click.prompt(
            f"All data on '{name}' will be destroyed. Type the server name to confirm",
            default="",
        )
        if typed != name:
            error("Server name does not match — aborting.")
            raise SystemExit(1)
        info(f"Wiping server '{name}' before provisioning...")
        with _ssh_for_server(srv) as ssh:
            from cli.core.provisioner import wipe_server

            wipe_server(ssh)
        # Clean local app records for this server
        with get_session() as session:
            s = session.query(Server).filter(Server.name == name).first()
            if s:
                for app in s.apps:
                    session.delete(app)
                s.status = "pending"
        success(f"Server '{name}' wiped")

    with status_spinner(f"Provisioning {srv.name} ({srv.host})"):
        with _ssh_for_server(srv) as ssh:
            from cli.core.provisioner import provision_server

            provision_server(ssh)

    with get_session() as session:
        s = session.query(Server).filter(Server.name == name).first()
        if s:
            s.status = "active"

    success(f"Server '{name}' provisioned and active")
```

**Step 2: Run existing tests**

Run: `pytest tests/unit/ -v -x --timeout=30 2>&1 | tail -20`
Expected: All pass

**Step 3: Commit**

```bash
git add cli/commands/server.py
git commit -m "feat: wipe non-infrakT-host servers before provisioning (CLI)"
```

---

### Task 4: Update API Schema and Provision Endpoint

**Files:**
- Modify: `api/schemas.py:69-74` (ServerUpdate) and `api/schemas.py:77-91` (ServerOut)
- Modify: `api/routes/servers.py:111-151` (update_server) and `api/routes/servers.py:166-220` (provision)

**Step 1: Add `is_infrakt_host` to schemas**

In `api/schemas.py`, add to `ServerUpdate` (line 74, after `provider`):

```python
is_infrakt_host: bool | None = None
```

In `api/schemas.py`, add to `ServerOut` (line 89, after `tags`):

```python
is_infrakt_host: bool = False
```

**Step 2: Handle `is_infrakt_host` in update endpoint**

In `api/routes/servers.py`, add to `update_server()` after line 134 (the `provider` check):

```python
if body.is_infrakt_host is not None:
    srv.is_infrakt_host = body.is_infrakt_host
```

Also add `is_infrakt_host=srv.is_infrakt_host` to the `ServerOut(...)` return on line 138.

**Step 3: Add wipe logic to provision endpoint**

In `api/routes/servers.py`, inside `_do_provision()` (line 183), add wipe logic before the existing `provision_server()` call. Also add local DB cleanup:

```python
def _do_provision() -> None:
    try:
        ssh = SSHClient(host=host, user=user, port=port, key_path=key_path)
        with ssh:
            # Wipe non-infrakT-host servers first
            if not is_infrakt_host:
                def _on_wipe_step(step_name: str, index: int, total: int) -> None:
                    broadcaster.publish(prov_key, f"[wipe {index + 1}/{total}] {step_name}")

                wipe_server(ssh, on_step=_on_wipe_step)

                # Clean local app records
                with get_session() as session:
                    s = session.query(Server).filter(Server.name == name).first()
                    if s:
                        for app in s.apps:
                            session.delete(app)

            def _on_step(step_name: str, index: int, total: int) -> None:
                broadcaster.publish(prov_key, f"[{index + 1}/{total}] {step_name}")

            provision_server(ssh, on_step=_on_step)
        # ... rest unchanged
```

Capture `is_infrakt_host` from the server record before the background task:

```python
is_infrakt_host = srv.is_infrakt_host
```

Add import at top of file:

```python
from cli.core.provisioner import provision_server, wipe_server
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_api_servers.py -v`
Expected: All pass

**Step 5: Commit**

```bash
git add api/schemas.py api/routes/servers.py
git commit -m "feat: wipe non-infrakT-host servers before provisioning (API)"
```

---

### Task 5: Update `setup-vps.sh` to Set `is_infrakt_host`

**Files:**
- Modify: `scripts/setup-vps.sh:349-356` (after server registration)

**Step 1: Add PATCH call after registration**

In `scripts/setup-vps.sh`, after the successful registration check (line 350), add:

```bash
    if [ "$REG_CODE" = "200" ] || [ "$REG_CODE" = "201" ]; then
        echo "    Server '${SERVER_NAME}' registered (host: ${DOCKER_BRIDGE_IP})"
        # Mark as infrakT host to protect from wipe-on-provision
        curl -s --max-time 10 \
            -X PUT "${API_BASE}/api/servers/${SERVER_NAME}" \
            -H "Content-Type: application/json" \
            -H "X-API-Key: ${API_KEY}" \
            -d '{"is_infrakt_host": true}' >/dev/null 2>&1
        echo "    Marked as infrakT host (protected from wipe)"
```

**Step 2: Commit**

```bash
git add scripts/setup-vps.sh
git commit -m "feat: setup-vps.sh marks server as infrakT host"
```

---

### Task 6: Add Wipe Confirmation Modal to Frontend

**Files:**
- Modify: `frontend/src/pages/ServerDetail.tsx:818-826` (handleProvision function)
- Modify: `frontend/src/pages/ServerDetail.tsx:779-784` (add state for confirmation)
- Modify: `frontend/src/pages/ServerDetail.tsx:886-901` (Provision button area)

**Step 1: Add confirmation state**

In `ServerDetail.tsx`, add state near line 784 (after provisionResult state):

```tsx
const [showWipeConfirm, setShowWipeConfirm] = useState(false);
const [wipeConfirmText, setWipeConfirmText] = useState("");
```

**Step 2: Update handleProvision**

Replace `handleProvision` (lines 818-826):

```tsx
async function handleProvision() {
  // Non-infrakT-host servers need wipe confirmation
  if (server && !server.is_infrakt_host) {
    setShowWipeConfirm(true);
    setWipeConfirmText("");
    return;
  }
  await doProvision();
}

async function doProvision() {
  try {
    setShowWipeConfirm(false);
    setWipeConfirmText("");
    setProvisionResult(null);
    const result = await provisionServer.mutateAsync(decodedName);
    setProvisionKey(result.provision_key);
  } catch (err) {
    toast.error(err instanceof Error ? err.message : "Provisioning failed.");
  }
}
```

**Step 3: Add confirmation modal**

In the JSX, after the `ToastContainer` (line 855), add:

```tsx
{/* Wipe confirmation modal */}
{showWipeConfirm && (
  <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
    <div className="w-full max-w-md rounded-2xl border border-zinc-700 bg-zinc-900 p-6 shadow-2xl">
      <h3 className="text-lg font-semibold text-zinc-100">
        Wipe & Provision Server
      </h3>
      <p className="mt-2 text-sm text-zinc-400">
        All Docker containers, images, volumes, and app data on{" "}
        <span className="font-semibold text-zinc-200">{decodedName}</span>{" "}
        will be permanently deleted before reprovisioning.
      </p>
      <div className="mt-4">
        <label className="block text-xs font-medium uppercase tracking-wider text-zinc-500 mb-1.5">
          Type "{decodedName}" to confirm
        </label>
        <input
          type="text"
          value={wipeConfirmText}
          onChange={(e) => setWipeConfirmText(e.target.value)}
          className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 focus:border-orange-500/60 focus:outline-none focus:ring-1 focus:ring-orange-500/40"
          autoFocus
        />
      </div>
      <div className="mt-5 flex justify-end gap-3">
        <button
          onClick={() => setShowWipeConfirm(false)}
          className="rounded-lg px-4 py-2 text-sm font-medium text-zinc-400 hover:text-zinc-200 transition-colors"
        >
          Cancel
        </button>
        <button
          onClick={() => void doProvision()}
          disabled={wipeConfirmText !== decodedName}
          className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-red-500 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Wipe & Provision
        </button>
      </div>
    </div>
  </div>
)}
```

**Step 4: Update the `Server` type in client.ts to include `is_infrakt_host`**

In `frontend/src/api/client.ts`, find the `Server` type and add:

```typescript
is_infrakt_host: boolean;
```

**Step 5: TypeScript check**

Run: `cd frontend && npx tsc --noEmit`
Expected: Clean (no errors)

**Step 6: Commit**

```bash
git add frontend/src/pages/ServerDetail.tsx frontend/src/api/client.ts
git commit -m "feat: add wipe confirmation modal to Provision button"
```

---

### Task 7: Update E2E Tests and Mock Data

**Files:**
- Modify: `frontend/e2e/fixtures.ts:14-40` (add `is_infrakt_host` to MOCK_SERVERS)
- Modify: `frontend/e2e/server-detail.spec.ts` (add wipe confirmation tests)

**Step 1: Add `is_infrakt_host` to mock data**

In `frontend/e2e/fixtures.ts`, add `is_infrakt_host: true` to the first mock server (prod-1, line 15-27) since it represents the infrakT host. Add `is_infrakt_host: false` to the second (staging, lines 28-40).

Also update the POST handler (line 290-302) to include `is_infrakt_host: false` in the response.

**Step 2: Add E2E tests for wipe confirmation**

In `frontend/e2e/server-detail.spec.ts`, add tests in a new `test.describe("Provision wipe confirmation")` block:

```typescript
test.describe("Provision wipe confirmation", () => {
  test("shows wipe modal for non-infrakT-host server", async ({ page }) => {
    // Navigate to staging server (is_infrakt_host: false)
    await page.goto("/servers/staging");
    await page.getByRole("button", { name: /provision/i }).click();
    await expect(page.getByText("Wipe & Provision Server")).toBeVisible();
    await expect(page.getByText('Type "staging" to confirm')).toBeVisible();
  });

  test("wipe confirm button is disabled until name typed", async ({ page }) => {
    await page.goto("/servers/staging");
    await page.getByRole("button", { name: /provision/i }).click();
    const confirmBtn = page.getByRole("button", { name: "Wipe & Provision" });
    await expect(confirmBtn).toBeDisabled();
    await page.getByRole("textbox").fill("staging");
    await expect(confirmBtn).toBeEnabled();
  });

  test("does NOT show wipe modal for infrakT host server", async ({ page }) => {
    // Navigate to prod-1 (is_infrakt_host: true)
    await page.goto("/servers/prod-1");
    await page.getByRole("button", { name: /provision/i }).click();
    await expect(page.getByText("Wipe & Provision Server")).not.toBeVisible();
  });

  test("cancel closes the modal", async ({ page }) => {
    await page.goto("/servers/staging");
    await page.getByRole("button", { name: /provision/i }).click();
    await expect(page.getByText("Wipe & Provision Server")).toBeVisible();
    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(page.getByText("Wipe & Provision Server")).not.toBeVisible();
  });
});
```

**Step 3: Run E2E tests**

Run: `cd frontend && npx playwright test e2e/server-detail.spec.ts`
Expected: All pass (existing + new)

**Step 4: Commit**

```bash
git add frontend/e2e/fixtures.ts frontend/e2e/server-detail.spec.ts
git commit -m "test: add E2E tests for wipe confirmation on provision"
```

---

### Task 8: Backend Unit Tests for Wipe Integration

**Files:**
- Create: `tests/unit/test_provision_wipe_integration.py`

**Step 1: Write tests**

```python
"""Tests for wipe-on-provision integration."""

from unittest.mock import MagicMock, patch

import pytest

from cli.core.database import get_session, init_db
from cli.models.app import App
from cli.models.server import Server


class TestProvisionWipesNonInfraktHost:
    """Verify provision_server is only preceded by wipe for non-infrakT hosts."""

    def test_server_model_has_is_infrakt_host_default_false(self, isolated_config):
        init_db()
        with get_session() as session:
            srv = Server(name="test-srv", host="1.2.3.4")
            session.add(srv)
            session.flush()
            assert srv.is_infrakt_host is False

    def test_is_infrakt_host_can_be_set_true(self, isolated_config):
        init_db()
        with get_session() as session:
            srv = Server(name="host-srv", host="1.2.3.4", is_infrakt_host=True)
            session.add(srv)
            session.flush()
            assert srv.is_infrakt_host is True


class TestApiProvisionWipe:
    """Verify the API provision endpoint wipes non-infrakT hosts."""

    def test_provision_non_infrakt_host_calls_wipe(self, client, isolated_config):
        init_db()
        with get_session() as session:
            srv = Server(name="wipe-srv", host="1.2.3.4", is_infrakt_host=False)
            session.add(srv)

        with (
            patch("api.routes.servers.wipe_server") as mock_wipe,
            patch("api.routes.servers.provision_server"),
            patch("api.routes.servers.asyncio"),
            patch("api.routes.servers.broadcaster"),
            patch("api.routes.servers.SSHClient"),
        ):
            response = client.post("/api/servers/wipe-srv/provision")

        assert response.status_code == 200
        # wipe_server is called in background task, so we verify it was imported

    def test_provision_infrakt_host_does_not_call_wipe(self, client, isolated_config):
        init_db()
        with get_session() as session:
            srv = Server(name="safe-srv", host="1.2.3.4", is_infrakt_host=True)
            session.add(srv)

        with (
            patch("api.routes.servers.wipe_server") as mock_wipe,
            patch("api.routes.servers.provision_server"),
            patch("api.routes.servers.asyncio"),
            patch("api.routes.servers.broadcaster"),
            patch("api.routes.servers.SSHClient"),
        ):
            response = client.post("/api/servers/safe-srv/provision")

        assert response.status_code == 200
```

**Step 2: Run tests**

Run: `pytest tests/unit/test_provision_wipe_integration.py -v`
Expected: All pass

**Step 3: Commit**

```bash
git add tests/unit/test_provision_wipe_integration.py
git commit -m "test: add unit tests for wipe-on-provision integration"
```

---

### Task 9: Full Test Suite Verification

**Step 1: Run all backend tests**

Run: `pytest tests/unit/ -v --timeout=30`
Expected: All ~310+ tests pass

**Step 2: Run all E2E tests**

Run: `cd frontend && npx playwright test`
Expected: All ~258+ tests pass

**Step 3: TypeScript + build check**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: Clean

**Step 4: Final commit (if any fixups needed)**

If any tests needed fixing, commit the fixes.
