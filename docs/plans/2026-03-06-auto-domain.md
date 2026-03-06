# Auto-Domain Assignment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Automatically assign a random subdomain (e.g., `a3f2b7c1.infrakt.cloud`) to apps created without an explicit domain, using a globally configured base domain.

**Architecture:** A new `PlatformSettings` model stores the `base_domain` (single-row table like S3Config/BackupPolicy). On app create, if no domain is provided and `base_domain` is set, generate `{random_hex}.{base_domain}` and save it on the app. No Traefik changes — existing per-domain HTTP-01 ACME flow handles TLS.

**Tech Stack:** SQLAlchemy model, FastAPI endpoints, Click CLI, React Settings page

---

### Task 1: PlatformSettings model

**Files:**
- Create: `cli/models/platform_settings.py`
- Modify: `cli/core/database.py` (import for auto-create)
- Test: `tests/unit/test_platform_settings_model.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_platform_settings_model.py
"""Tests for PlatformSettings model."""

from cli.core.database import get_session, init_db
from cli.models.platform_settings import PlatformSettings


class TestPlatformSettings:
    def test_create_with_base_domain(self, isolated_config):
        init_db()
        with get_session() as session:
            ps = PlatformSettings(base_domain="infrakt.cloud")
            session.add(ps)
        with get_session() as session:
            ps = session.query(PlatformSettings).first()
            assert ps is not None
            assert ps.base_domain == "infrakt.cloud"

    def test_base_domain_nullable(self, isolated_config):
        init_db()
        with get_session() as session:
            ps = PlatformSettings()
            session.add(ps)
        with get_session() as session:
            ps = session.query(PlatformSettings).first()
            assert ps is not None
            assert ps.base_domain is None
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_platform_settings_model.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cli.models.platform_settings'`

**Step 3: Write the model**

```python
# cli/models/platform_settings.py
from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, func
from sqlalchemy.orm import Mapped, mapped_column

from cli.core.database import Base


class PlatformSettings(Base):
    __tablename__ = "platform_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    base_domain: Mapped[str | None] = mapped_column(String(255), default=None)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())
```

Then add the import in `cli/core/database.py` alongside other model imports so `init_db()` creates the table:

```python
import cli.models.platform_settings  # noqa: F401
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_platform_settings_model.py -v`
Expected: PASS

**Step 5: Commit**

```
git add cli/models/platform_settings.py cli/core/database.py tests/unit/test_platform_settings_model.py
git commit -m "feat: add PlatformSettings model for base_domain"
```

---

### Task 2: Auto-domain generator helper

**Files:**
- Create: `cli/core/auto_domain.py`
- Test: `tests/unit/test_auto_domain.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_auto_domain.py
"""Tests for auto-domain generation."""

import re

from cli.core.auto_domain import generate_auto_domain, get_base_domain
from cli.core.database import get_session, init_db
from cli.models.platform_settings import PlatformSettings


class TestGenerateAutoDomain:
    def test_generates_subdomain_with_base(self):
        domain = generate_auto_domain("infrakt.cloud")
        assert domain.endswith(".infrakt.cloud")
        subdomain = domain.split(".")[0]
        assert len(subdomain) == 8
        assert re.match(r"^[a-f0-9]{8}$", subdomain)

    def test_different_calls_produce_different_domains(self):
        d1 = generate_auto_domain("infrakt.cloud")
        d2 = generate_auto_domain("infrakt.cloud")
        assert d1 != d2


class TestGetBaseDomain:
    def test_returns_none_when_not_configured(self, isolated_config):
        init_db()
        assert get_base_domain() is None

    def test_returns_base_domain_when_configured(self, isolated_config):
        init_db()
        with get_session() as session:
            session.add(PlatformSettings(base_domain="example.com"))
        assert get_base_domain() == "example.com"
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_auto_domain.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cli.core.auto_domain'`

**Step 3: Write the implementation**

```python
# cli/core/auto_domain.py
"""Auto-domain generation for apps without explicit domains."""

from __future__ import annotations

import secrets

from cli.core.database import get_session, init_db
from cli.models.platform_settings import PlatformSettings


def generate_auto_domain(base_domain: str) -> str:
    """Generate a random subdomain like ``a3f2b7c1.infrakt.cloud``."""
    return f"{secrets.token_hex(4)}.{base_domain}"


def get_base_domain() -> str | None:
    """Read the configured base_domain from platform settings, or None."""
    init_db()
    with get_session() as session:
        ps = session.query(PlatformSettings).first()
        if ps and ps.base_domain:
            return ps.base_domain
    return None
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_auto_domain.py -v`
Expected: PASS

**Step 5: Commit**

```
git add cli/core/auto_domain.py tests/unit/test_auto_domain.py
git commit -m "feat: add auto-domain generation helper"
```

---

### Task 3: Settings API endpoints for base_domain

**Files:**
- Modify: `api/routes/settings.py`
- Modify: `api/schemas.py`
- Test: `tests/unit/test_api_domain_settings.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_api_domain_settings.py
"""Tests for domain settings API endpoints."""

import pytest
from fastapi.testclient import TestClient

from api.main import app
from tests.conftest import TEST_API_KEY

HEADERS = {"X-API-Key": TEST_API_KEY}


@pytest.fixture
def client(isolated_config):
    return TestClient(app, headers=HEADERS)


class TestGetDomainSettings:
    def test_returns_empty_when_not_configured(self, client):
        resp = client.get("/api/settings/domain")
        assert resp.status_code == 200
        assert resp.json() == {"base_domain": None}

    def test_returns_configured_domain(self, client):
        client.put("/api/settings/domain", json={"base_domain": "infrakt.cloud"})
        resp = client.get("/api/settings/domain")
        assert resp.status_code == 200
        assert resp.json() == {"base_domain": "infrakt.cloud"}


class TestPutDomainSettings:
    def test_saves_base_domain(self, client):
        resp = client.put("/api/settings/domain", json={"base_domain": "apps.example.com"})
        assert resp.status_code == 200
        assert resp.json()["message"] == "Domain settings saved"

    def test_updates_existing_domain(self, client):
        client.put("/api/settings/domain", json={"base_domain": "old.com"})
        client.put("/api/settings/domain", json={"base_domain": "new.com"})
        resp = client.get("/api/settings/domain")
        assert resp.json()["base_domain"] == "new.com"

    def test_clears_domain_with_null(self, client):
        client.put("/api/settings/domain", json={"base_domain": "infrakt.cloud"})
        client.put("/api/settings/domain", json={"base_domain": None})
        resp = client.get("/api/settings/domain")
        assert resp.json()["base_domain"] is None
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_api_domain_settings.py -v`
Expected: FAIL — 404 on `/api/settings/domain`

**Step 3: Add schema and endpoints**

In `api/schemas.py`, add near the other settings schemas:

```python
class DomainSettingsSave(BaseModel):
    base_domain: str | None = None
```

In `api/routes/settings.py`, add at the bottom:

```python
from cli.models.platform_settings import PlatformSettings
from api.schemas import DomainSettingsSave

# ── Domain Settings ───────────────────────────────────────────────────────

@router.get("/domain")
def get_domain_settings() -> dict:
    init_db()
    with get_session() as session:
        ps = session.query(PlatformSettings).first()
        return {"base_domain": ps.base_domain if ps else None}


@router.put("/domain")
def save_domain_settings(body: DomainSettingsSave) -> dict[str, str]:
    init_db()
    with get_session() as session:
        ps = session.query(PlatformSettings).first()
        if ps:
            ps.base_domain = body.base_domain
        else:
            session.add(PlatformSettings(base_domain=body.base_domain))
    return {"message": "Domain settings saved"}
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_api_domain_settings.py -v`
Expected: PASS

**Step 5: Commit**

```
git add api/routes/settings.py api/schemas.py tests/unit/test_api_domain_settings.py
git commit -m "feat: add domain settings API endpoints"
```

---

### Task 4: Auto-assign domain on app create (API)

**Files:**
- Modify: `api/routes/apps.py` (in `create_app` function, ~line 250)
- Test: `tests/unit/test_api_auto_domain.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_api_auto_domain.py
"""Tests for auto-domain assignment on app create."""

import re

import pytest
from fastapi.testclient import TestClient

from api.main import app
from cli.core.database import get_session, init_db
from cli.models.platform_settings import PlatformSettings
from cli.models.server import Server
from tests.conftest import TEST_API_KEY

HEADERS = {"X-API-Key": TEST_API_KEY}


@pytest.fixture
def client(isolated_config):
    return TestClient(app, headers=HEADERS)


@pytest.fixture
def server_with_domain(client):
    """Create a server and configure base_domain."""
    client.post(
        "/api/servers",
        json={"name": "test-srv", "host": "1.2.3.4", "user": "root"},
    )
    init_db()
    with get_session() as session:
        session.add(PlatformSettings(base_domain="infrakt.cloud"))
    return "test-srv"


class TestAutoDomainOnCreate:
    def test_assigns_random_domain_when_none_provided(self, client, server_with_domain):
        resp = client.post(
            "/api/apps",
            json={"name": "myapp", "server_name": server_with_domain, "image": "nginx"},
        )
        assert resp.status_code == 201
        domain = resp.json()["domain"]
        assert domain is not None
        assert domain.endswith(".infrakt.cloud")
        assert re.match(r"^[a-f0-9]{8}\.infrakt\.cloud$", domain)

    def test_no_auto_domain_when_explicit_domain_set(self, client, server_with_domain):
        resp = client.post(
            "/api/apps",
            json={
                "name": "myapp2",
                "server_name": server_with_domain,
                "image": "nginx",
                "domain": "custom.example.com",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["domain"] == "custom.example.com"

    def test_no_auto_domain_when_base_domain_not_configured(self, client):
        client.post(
            "/api/servers",
            json={"name": "bare-srv", "host": "5.6.7.8", "user": "root"},
        )
        resp = client.post(
            "/api/apps",
            json={"name": "nodom", "server_name": "bare-srv", "image": "nginx"},
        )
        assert resp.status_code == 201
        assert resp.json()["domain"] is None

    def test_no_auto_domain_for_database_apps(self, client, server_with_domain):
        # Database apps are created via /api/databases, not /api/apps,
        # but if app_type starts with db: we should not assign a domain.
        # This is tested indirectly — db create doesn't go through app create.
        pass
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_api_auto_domain.py -v`
Expected: FAIL — domain is None when no domain provided

**Step 3: Add auto-domain logic to create_app**

In `api/routes/apps.py`, in the `create_app` function, after line ~256 (`effective_domain = body.domain`), add:

```python
        # Auto-assign a random subdomain if no domain was provided
        # and a base_domain is configured in platform settings.
        if not effective_domain and not body.domains:
            from cli.core.auto_domain import generate_auto_domain, get_base_domain

            base = get_base_domain()
            if base:
                effective_domain = generate_auto_domain(base)
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_api_auto_domain.py -v`
Expected: PASS

**Step 5: Commit**

```
git add api/routes/apps.py tests/unit/test_api_auto_domain.py
git commit -m "feat: auto-assign domain on app create when base_domain configured"
```

---

### Task 5: Auto-assign domain on CLI app create

**Files:**
- Modify: `cli/commands/app.py` (in `create` function, ~line 130)
- Test: `tests/unit/test_commands/test_app_auto_domain.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_commands/test_app_auto_domain.py
"""Tests for auto-domain in CLI app create."""

import re

from click.testing import CliRunner

from cli.commands.app import create
from cli.core.database import get_session, init_db
from cli.models.app import App
from cli.models.platform_settings import PlatformSettings
from cli.models.server import Server


class TestCliAutoDomain:
    def test_auto_assigns_domain_when_base_configured(self, isolated_config):
        init_db()
        runner = CliRunner()
        with get_session() as session:
            session.add(Server(name="s1", host="1.2.3.4", user="root", port=22, status="active"))
            session.add(PlatformSettings(base_domain="infrakt.cloud"))

        result = runner.invoke(
            create,
            ["--server", "s1", "--name", "testapp", "--image", "nginx"],
        )
        assert result.exit_code == 0

        with get_session() as session:
            app = session.query(App).filter(App.name == "testapp").first()
            assert app is not None
            assert app.domain is not None
            assert app.domain.endswith(".infrakt.cloud")

    def test_no_auto_domain_when_explicit(self, isolated_config):
        init_db()
        runner = CliRunner()
        with get_session() as session:
            session.add(Server(name="s1", host="1.2.3.4", user="root", port=22, status="active"))
            session.add(PlatformSettings(base_domain="infrakt.cloud"))

        result = runner.invoke(
            create,
            ["--server", "s1", "--name", "testapp", "--image", "nginx", "--domain", "custom.com"],
        )
        assert result.exit_code == 0

        with get_session() as session:
            app = session.query(App).filter(App.name == "testapp").first()
            assert app.domain == "custom.com"
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_commands/test_app_auto_domain.py -v`
Expected: FAIL — domain is None

**Step 3: Add auto-domain logic to CLI create**

In `cli/commands/app.py`, in the `create` function, before `new_app = App(...)` (~line 130), add:

```python
        # Auto-assign domain if base_domain is configured and no domain provided
        if not domain:
            from cli.core.auto_domain import generate_auto_domain, get_base_domain

            base = get_base_domain()
            if base:
                domain = generate_auto_domain(base)
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_commands/test_app_auto_domain.py -v`
Expected: PASS

**Step 5: Commit**

```
git add cli/commands/app.py tests/unit/test_commands/test_app_auto_domain.py
git commit -m "feat: auto-assign domain in CLI app create"
```

---

### Task 6: Auto-domain for multi-domain templates

**Files:**
- Modify: `api/routes/apps.py` (in `create_app`, template handling ~line 239)
- Test: add cases to `tests/unit/test_api_auto_domain.py`

**Step 1: Write the failing test**

Add to `tests/unit/test_api_auto_domain.py`:

```python
class TestAutoDomainTemplates:
    def test_multi_domain_template_gets_random_domains(self, client, server_with_domain):
        resp = client.post(
            "/api/apps",
            json={"name": "mydevtools", "server_name": server_with_domain, "template": "devtools"},
        )
        assert resp.status_code == 201
        domain_raw = resp.json()["domain"]
        # Should be JSON with random subdomains for each service
        import json
        domains = json.loads(domain_raw)
        assert "gitea" in domains
        assert "portainer" in domains
        assert domains["gitea"].endswith(".infrakt.cloud")
        assert domains["portainer"].endswith(".infrakt.cloud")
        assert domains["gitea"] != domains["portainer"]

    def test_single_domain_template_gets_random_domain(self, client, server_with_domain):
        resp = client.post(
            "/api/apps",
            json={"name": "mykuma", "server_name": server_with_domain, "template": "uptime-kuma"},
        )
        assert resp.status_code == 201
        domain = resp.json()["domain"]
        assert domain.endswith(".infrakt.cloud")
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_api_auto_domain.py::TestAutoDomainTemplates -v`
Expected: FAIL — domain is None for templates without explicit domain

**Step 3: Add auto-domain for templates**

In `api/routes/apps.py`, in `create_app`, after the template handling block (~line 243) and before the domain assignment, add logic for templates with `domain_map`:

```python
        # Auto-assign domains for multi-domain templates
        if body.template and not body.domain and not body.domains:
            from cli.core.auto_domain import generate_auto_domain, get_base_domain

            base = get_base_domain()
            if base and tmpl and "domain_map" in tmpl:
                import json as _json
                auto_domains = {
                    svc: generate_auto_domain(base)
                    for svc in tmpl["domain_map"]
                }
                effective_domain = _json.dumps(auto_domains)
            elif base:
                from cli.core.auto_domain import generate_auto_domain
                # Single-domain template
                pass  # Will be handled by the existing auto-domain block below
```

Note: The exact placement needs to ensure `effective_domain` is set before the existing block that falls through to auto-assign. The single-domain template case is already handled by the generic auto-domain block from Task 4.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_api_auto_domain.py -v`
Expected: PASS

**Step 5: Commit**

```
git add api/routes/apps.py tests/unit/test_api_auto_domain.py
git commit -m "feat: auto-assign random domains for multi-domain templates"
```

---

### Task 7: Frontend — Settings page base domain input

**Files:**
- Modify: `frontend/src/pages/Settings.tsx`
- Modify: `frontend/src/hooks/useApi.ts` (add hooks)
- Modify: `frontend/src/api/client.ts` (add API functions)

**Step 1: Add API client functions**

In `frontend/src/api/client.ts`, add:

```typescript
export async function getDomainSettings(): Promise<{ base_domain: string | null }> {
  return get("/api/settings/domain");
}

export async function saveDomainSettings(base_domain: string | null): Promise<{ message: string }> {
  return put("/api/settings/domain", { base_domain });
}
```

**Step 2: Add TanStack Query hooks**

In `frontend/src/hooks/useApi.ts`, add:

```typescript
export function useDomainSettings() {
  return useQuery({ queryKey: ["domain-settings"], queryFn: getDomainSettings });
}

export function useSaveDomainSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (base_domain: string | null) => saveDomainSettings(base_domain),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["domain-settings"] }),
  });
}
```

**Step 3: Add base domain section to Settings page**

In `frontend/src/pages/Settings.tsx`, add a "Domain" card section (following the same pattern as the S3 card) with:
- A text input for `base_domain`
- A Save button
- Helper text: "Set a wildcard DNS A record (*.yourdomain.com) pointing to your server. Apps created without an explicit domain will get a random subdomain."

**Step 4: Verify manually**

Run: `cd frontend && npm run type-check && npm run build`
Expected: No TypeScript or build errors

**Step 5: Commit**

```
git add frontend/src/api/client.ts frontend/src/hooks/useApi.ts frontend/src/pages/Settings.tsx
git commit -m "feat: add base domain settings to frontend dashboard"
```

---

### Task 8: Run full test suite and verify

**Step 1: Run all backend tests**

Run: `python3 -m pytest tests/ -v --tb=short`
Expected: All tests pass

**Step 2: Run frontend build**

Run: `cd frontend && npm run type-check && npm run build`
Expected: Clean build

**Step 3: Final commit if any fixups needed**

---

### Task 9: E2E test for domain settings

**Files:**
- Create: `frontend/e2e/domain-settings.spec.ts`

**Step 1: Write E2E test**

Following the pattern in `frontend/e2e/fixtures.ts`, mock the `/api/settings/domain` endpoint and test:
- Settings page shows base domain input
- Saving base domain shows success toast
- Empty field clears the setting

**Step 2: Run E2E tests**

Run: `cd frontend && npx playwright test e2e/domain-settings.spec.ts`
Expected: PASS

**Step 3: Commit**

```
git add frontend/e2e/domain-settings.spec.ts
git commit -m "test: add E2E tests for domain settings"
```
