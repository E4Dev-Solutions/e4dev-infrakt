# infrakt Improvement Backlog — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 4 bugs and add 7 improvements to the infrakt PaaS: near-zero-downtime deploys, Nixpacks builder, image-based rollbacks, encrypted DB passwords, GitHub webhook cleanup, bulk env import, and Slack/Discord notifications.

**Architecture:** Three phases ordered by dependency. Phase 1 fixes bugs (isolated single-file changes). Phase 2 redesigns the deployment pipeline (deployer.py, provisioner, compose templates). Phase 3 adds independent UX/integration features. Each phase ships as one or more PRs.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2.0, Paramiko SSH, React/TypeScript frontend, Playwright E2E tests, pytest unit tests.

---

## Phase 1: Bug Fixes

### Task 1: Fix Health Check Gate in Rolling Deploys

**Files:**
- Modify: `cli/core/deployer.py:229-248`
- Test: `tests/unit/test_deployer.py`

**Step 1: Write the failing test**

```python
# In tests/unit/test_deployer.py, add after the existing rolling deploy tests:

@patch("cli.core.deployer.get_github_token", return_value=None)
@patch("cli.core.deployer.check_app_health")
def test_rolling_deploy_uses_http_health_check(mock_health, _mock_token):
    """Rolling deploy must call check_app_health, not reconcile_app_status."""
    mock_health.return_value = {"healthy": True, "status_code": 200, "response_time_ms": 50, "error": None}
    ssh = MagicMock()
    ssh.__enter__ = MagicMock(return_value=ssh)
    ssh.__exit__ = MagicMock(return_value=False)
    ssh.run_checked = MagicMock(return_value="")
    ssh.run_streaming = MagicMock(return_value="")
    ssh.run = MagicMock(return_value=("", "", 0))
    ssh.upload_string = MagicMock()

    deploy_app(
        ssh,
        "test-app",
        image="nginx:latest",
        deploy_strategy="rolling",
        health_check_url="/health",
        port=3000,
    )

    mock_health.assert_called_once_with(ssh, 3000, "/health")


@patch("cli.core.deployer.get_github_token", return_value=None)
@patch("cli.core.deployer.check_app_health")
def test_rolling_deploy_fails_on_unhealthy(mock_health, _mock_token):
    """Rolling deploy raises DeploymentError when health check never passes."""
    mock_health.return_value = {"healthy": False, "status_code": 503, "response_time_ms": 100, "error": None}
    ssh = MagicMock()
    ssh.__enter__ = MagicMock(return_value=ssh)
    ssh.__exit__ = MagicMock(return_value=False)
    ssh.run_checked = MagicMock(return_value="")
    ssh.run_streaming = MagicMock(return_value="")
    ssh.run = MagicMock(return_value=("", "", 0))
    ssh.upload_string = MagicMock()

    with pytest.raises(DeploymentError, match="failed health check"):
        deploy_app(
            ssh,
            "test-app",
            image="nginx:latest",
            deploy_strategy="rolling",
            health_check_url="/health",
            port=3000,
        )
```

Add `check_app_health` to the imports at the top of the test file if not already present:

```python
from unittest.mock import MagicMock, patch
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_deployer.py::test_rolling_deploy_uses_http_health_check -xvs`
Expected: FAIL — `check_app_health` is never called (still calls `reconcile_app_status`)

**Step 3: Implement the fix**

In `cli/core/deployer.py`, add import at top:

```python
from cli.core.health import check_app_health
```

Replace lines 229-248 (the health check gating block) with:

```python
    # Health check gating for rolling deploys
    if deploy_strategy == "rolling" and health_check_url:
        import time

        _log("Waiting for health check to pass...")
        max_retries = 10
        for attempt in range(max_retries):
            time.sleep(5)
            result = check_app_health(ssh, port, health_check_url)
            if result["healthy"]:
                _log(f"Health check passed (attempt {attempt + 1})")
                break
            _log(f"Health check pending... (attempt {attempt + 1}/{max_retries})")
        else:
            _log("Health check failed after all retries — rolling back")
            q_path = shlex.quote(app_path)
            ssh.run(f"cd {q_path} && {_compose_cmd(app_name)} down", timeout=60)
            raise DeploymentError(
                f"Rolling deploy of '{app_name}' failed health check after {max_retries} attempts"
            )
```

**Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/unit/test_deployer.py -xvs`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add cli/core/deployer.py tests/unit/test_deployer.py
git commit -m "fix: use HTTP health check instead of container state in rolling deploys"
```

---

### Task 2: Fix Postgres Backup/Restore Safety

**Files:**
- Modify: `cli/core/backup.py:71-78` (backup), `cli/core/backup.py:137-142` (restore), `cli/core/backup.py:217-221` (script gen)
- Test: `tests/unit/test_backup.py`

**Step 1: Write the failing tests**

Add to `tests/unit/test_backup.py`:

```python
class TestBackupPostgresFormat:
    """Postgres backups must use custom format (-Fc) and .dump extension."""

    def test_backup_postgres_uses_custom_format(self):
        ssh = MagicMock()
        ssh.run_checked = MagicMock(return_value="")
        app = _make_app(app_type="db:postgres")

        with patch("cli.core.backup._get_container_env", return_value="mydb"):
            backup_database(ssh, app, "/opt/infrakt/backups", "server1")

        cmd = ssh.run_checked.call_args_list[-1][0][0]
        assert "pg_dump -Fc" in cmd
        assert ".dump" in cmd
        assert ".sql.gz" not in cmd

    def test_restore_postgres_uses_pg_restore(self):
        ssh = MagicMock()
        ssh.run.return_value = ("", "", 0)
        ssh.run_checked = MagicMock(return_value="")
        app = _make_app(app_type="db:postgres")

        with patch("cli.core.backup._get_container_env", return_value="mydb"):
            restore_database(ssh, app, "/opt/infrakt/backups/backup.dump")

        cmd = ssh.run_checked.call_args[0][0]
        assert "pg_restore" in cmd
        assert "--clean" in cmd
        assert "--if-exists" in cmd

    def test_restore_postgres_legacy_sql_gz_uses_psql(self):
        """Old .sql.gz backups should still restore via gunzip | psql."""
        ssh = MagicMock()
        ssh.run.return_value = ("", "", 0)
        ssh.run_checked = MagicMock(return_value="")
        app = _make_app(app_type="db:postgres")

        with patch("cli.core.backup._get_container_env", return_value="mydb"):
            restore_database(ssh, app, "/opt/infrakt/backups/old_backup.sql.gz")

        cmd = ssh.run_checked.call_args[0][0]
        assert "gunzip" in cmd
        assert "psql" in cmd
```

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/unit/test_backup.py::TestBackupPostgresFormat -xvs`
Expected: FAIL

**Step 3: Implement the fixes**

In `cli/core/backup.py`, update the `backup_database` postgres block (lines 71-78):

```python
    if db_type == "postgres":
        db_user = _get_container_env(ssh, container, "POSTGRES_USER")
        db_name = _get_container_env(ssh, container, "POSTGRES_DB")
        q_user = shlex.quote(db_user)
        q_db = shlex.quote(db_name)
        filename = _backup_filename(server_name, db_app.name, db_type, backup_id, ts, "dump")
        q_file = shlex.quote(f"{backup_dir}/{filename}")
        cmd = f"docker exec {q_container} pg_dump -Fc -U {q_user} {q_db} > {q_file}"
```

Update the `restore_database` postgres block (lines 137-142):

```python
    if db_type == "postgres":
        db_user = _get_container_env(ssh, container, "POSTGRES_USER")
        db_name = _get_container_env(ssh, container, "POSTGRES_DB")
        q_user = shlex.quote(db_user)
        q_db = shlex.quote(db_name)
        if remote_backup_path.endswith(".sql.gz"):
            # Legacy plain-SQL backup — fall back to gunzip | psql
            cmd = f"gunzip -c {q_path} | docker exec -i {q_container} psql -U {q_user} -d {q_db}"
        else:
            # Custom-format backup — use pg_restore with safe flags
            cmd = (
                f"cat {q_path} | docker exec -i {q_container}"
                f" pg_restore -U {q_user} -d {q_db} --clean --if-exists --no-owner"
            )
```

Update `generate_backup_script` postgres block (line 217-221):

```python
    if db_type == "postgres":
        filename = f"{fname_prefix}_{ts_var}.dump"
        q_c = shlex.quote(container)
        q_n = shlex.quote(name)
        lines.append(f'docker exec {q_c} pg_dump -Fc -U {q_n} {q_n} > "$BACKUP_DIR/{filename}"')
```

**Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/unit/test_backup.py -xvs`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add cli/core/backup.py tests/unit/test_backup.py
git commit -m "fix: use pg_dump custom format and pg_restore --clean for safe Postgres backups"
```

---

### Task 3: Enforce Deploy Key Scopes

**Files:**
- Modify: `api/routes/deploy.py:57-58`
- Test: `tests/unit/test_api_deploy.py`

**Step 1: Write the failing test**

Add to `tests/unit/test_api_deploy.py`:

```python
class TestDeployKeyScopeEnforcement:
    def test_deploy_key_without_deploy_scope_is_rejected(self, isolated_config):
        """A deploy key with scopes=["read-only"] must be rejected for deploy operations."""
        init_db()
        # Seed an app
        with get_session() as session:
            from cli.models.server import Server
            from cli.models.app import App

            s = Server(name="s1", host="1.2.3.4", user="root", status="active")
            session.add(s)
            session.flush()
            session.add(App(name="myapp", server_id=s.id, image="nginx"))

        # Create a deploy key and then manually change its scopes
        from cli.core.deploy_keys import generate_deploy_key, _load_keys, _save_keys

        key = generate_deploy_key("test-key")
        keys = _load_keys()
        keys[0]["scopes"] = ["read-only"]  # NOT "deploy"
        _save_keys(keys)

        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)
        resp = client.post(
            "/api/deploy",
            json={"app_name": "myapp"},
            headers={"X-API-Key": key},
        )
        assert resp.status_code == 403
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_api_deploy.py::TestDeployKeyScopeEnforcement -xvs`
Expected: FAIL — returns 200 instead of 403

**Step 3: Implement the fix**

In `api/routes/deploy.py`, change line 57-58 from:

```python
    dk = validate_deploy_key(api_key)
    if dk is not None:
        return api_key
```

To:

```python
    dk = validate_deploy_key(api_key)
    if dk is not None and "deploy" in dk.get("scopes", []):
        return api_key
```

**Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/unit/test_api_deploy.py -xvs`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add api/routes/deploy.py tests/unit/test_api_deploy.py
git commit -m "fix: enforce deploy key scopes in API authentication"
```

---

### Task 4: Remove Double-Wipe Bug

**Files:**
- Modify: `api/routes/servers.py:208-221`

**Step 1: Delete the duplicated block**

In `api/routes/servers.py`, delete lines 208-221 (the second `if not is_infrakt_host:` block). The code to remove is:

```python
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
```

After deletion, the code should flow directly from the first wipe block (ending at line ~207) to `def _on_step(...)` (line ~223).

**Step 2: Run full test suite to verify nothing breaks**

Run: `python3 -m pytest tests/unit/ -x -q`
Expected: ALL PASS

**Step 3: Commit**

```bash
git add api/routes/servers.py
git commit -m "fix: remove duplicated wipe block in server provisioning"
```

---

## Phase 2: Deployment Pipeline

### Task 5: Near-Zero-Downtime Deploys

**Files:**
- Modify: `cli/core/deployer.py:157-186`
- Test: `tests/unit/test_deployer.py`

**Step 1: Write the failing test**

Add to `tests/unit/test_deployer.py`:

```python
@patch("cli.core.deployer.get_github_token", return_value=None)
def test_deploy_git_splits_build_and_up(_mock_token):
    """Git deploys must call 'docker compose build' then 'docker compose up -d' separately."""
    ssh = MagicMock()
    ssh.__enter__ = MagicMock(return_value=ssh)
    ssh.__exit__ = MagicMock(return_value=False)
    ssh.upload_string = MagicMock()
    # test -d returns 1 (no repo → clone), test -f returns 1 (no compose in repo)
    ssh.run = MagicMock(side_effect=[("", "", 1), ("", "", 1)])
    ssh.run_streaming = MagicMock(return_value="")
    ssh.run_checked = MagicMock(side_effect=["", "abc1234567890\n"])

    deploy_app(ssh, "test-app", git_repo="https://github.com/test/repo.git", branch="main")

    streaming_cmds = [str(c) for c in ssh.run_streaming.call_args_list]
    # Should have: git clone, docker compose build, docker compose up
    assert any("git clone" in c for c in streaming_cmds)
    assert any("compose" in c and "build" in c and "up" not in c for c in streaming_cmds)
    assert any("compose" in c and "up -d" in c and "--build" not in c for c in streaming_cmds)
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_deployer.py::test_deploy_git_splits_build_and_up -xvs`
Expected: FAIL — currently uses single `up -d --build`

**Step 3: Implement the split**

In `cli/core/deployer.py`, replace the two `--build` blocks.

**Git repo with own compose (around line 159-166):**
Replace:
```python
            _log("Using docker-compose.yml from repository")
            ssh.run_streaming(
                f"cd {q_repo} && {_compose_cmd(app_name)} --env-file {q_app_path}/.env "
                f"up -d --build --remove-orphans",
                on_output=_stream,
                timeout=600,
            )
```
With:
```python
            _log("Using docker-compose.yml from repository")
            _log("Building images...")
            ssh.run_streaming(
                f"cd {q_repo} && {_compose_cmd(app_name)} --env-file {q_app_path}/.env build",
                on_output=_stream,
                timeout=600,
            )
            _log("Swapping containers...")
            ssh.run_streaming(
                f"cd {q_repo} && {_compose_cmd(app_name)} --env-file {q_app_path}/.env "
                f"up -d --remove-orphans",
                on_output=_stream,
                timeout=120,
            )
```

**Git repo with generated compose (around line 180-186):**
Replace:
```python
            ssh.run_streaming(
                f"cd {q_app_path} && {_compose_cmd(app_name)} up -d --build --remove-orphans",
                on_output=_stream,
                timeout=600,
            )
```
With:
```python
            _log("Building images...")
            ssh.run_streaming(
                f"cd {q_app_path} && {_compose_cmd(app_name)} build",
                on_output=_stream,
                timeout=600,
            )
            _log("Swapping containers...")
            ssh.run_streaming(
                f"cd {q_app_path} && {_compose_cmd(app_name)} up -d --remove-orphans",
                on_output=_stream,
                timeout=120,
            )
```

**Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/unit/test_deployer.py -xvs`
Expected: ALL PASS (update any other tests that assert on `--build` in streaming commands)

**Step 5: Commit**

```bash
git add cli/core/deployer.py tests/unit/test_deployer.py
git commit -m "feat: split build/swap for near-zero-downtime deploys"
```

---

### Task 6: Nixpacks Builder Support

This is the largest task. It spans multiple files.

#### Task 6a: Add Nixpacks to provisioner

**Files:**
- Modify: `cli/core/provisioner.py`

**Step 1: Add Nixpacks install step**

In `cli/core/provisioner.py`, add a new step to `PROVISION_STEPS` after the awscli step (around line 56):

```python
    (
        "Installing Nixpacks",
        "if ! command -v nixpacks &>/dev/null; then "
        "curl -sSL https://nixpacks.com/install.sh | bash; "
        "fi",
    ),
```

**Step 2: Run unit tests**

Run: `python3 -m pytest tests/unit/test_provisioner.py -xvs`
Expected: ALL PASS (update step counts if tests assert on number of steps)

**Step 3: Commit**

```bash
git add cli/core/provisioner.py
git commit -m "feat: install Nixpacks during server provisioning"
```

#### Task 6b: Add build_type to App model

**Files:**
- Modify: `cli/models/app.py`
- Modify: `api/schemas.py`

**Step 1: Add column to App model**

In `cli/models/app.py`, add after the `deploy_strategy` column (line 44):

```python
    build_type: Mapped[str] = mapped_column(String(20), default="auto")
```

**Step 2: Add to API schemas**

In `api/schemas.py`, add `build_type` to `AppCreate` and `AppUpdate`:

```python
    build_type: str | None = Field(None, pattern=r"^(auto|dockerfile|nixpacks)$")
```

**Step 3: Run tests**

Run: `python3 -m pytest tests/unit/ -x -q`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add cli/models/app.py api/schemas.py
git commit -m "feat: add build_type field to App model (auto/dockerfile/nixpacks)"
```

#### Task 6c: Implement Nixpacks build path in deployer

**Files:**
- Modify: `cli/core/deployer.py`
- Modify: `cli/core/compose_renderer.py`
- Modify: `cli/templates/app-compose.yml.j2`
- Test: `tests/unit/test_deployer.py`

**Step 1: Write the failing test**

```python
@patch("cli.core.deployer.get_github_token", return_value=None)
def test_deploy_git_nixpacks_builds_with_nixpacks(_mock_token):
    """When build_type=nixpacks, deployer runs nixpacks build instead of docker compose build."""
    ssh = MagicMock()
    ssh.__enter__ = MagicMock(return_value=ssh)
    ssh.__exit__ = MagicMock(return_value=False)
    ssh.upload_string = MagicMock()
    # test -d returns 1 (clone), test -f returns 1 (no compose)
    ssh.run = MagicMock(side_effect=[("", "", 1), ("", "", 1)])
    ssh.run_streaming = MagicMock(return_value="")
    ssh.run_checked = MagicMock(side_effect=["", "abc1234567890\n"])

    deploy_app(
        ssh, "test-app",
        git_repo="https://github.com/test/repo.git",
        branch="main",
        build_type="nixpacks",
    )

    streaming_cmds = [str(c) for c in ssh.run_streaming.call_args_list]
    assert any("nixpacks build" in c for c in streaming_cmds)
    assert not any("compose" in c and "build" in c for c in streaming_cmds)
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_deployer.py::test_deploy_git_nixpacks_builds_with_nixpacks -xvs`
Expected: FAIL — `deploy_app` doesn't accept `build_type` yet

**Step 3: Implement Nixpacks in deployer**

Add `build_type: str = "auto"` parameter to `deploy_app()` signature.

In the git repo deployment section, after capturing the commit hash and checking for compose file, add build type detection:

```python
        # Determine build strategy
        use_nixpacks = False
        if build_type == "nixpacks":
            use_nixpacks = True
        elif build_type == "auto" and has_compose != 0:
            # Auto mode: check if Dockerfile exists
            _, _, has_dockerfile = ssh.run(f"test -f {q_repo}/Dockerfile")
            if has_dockerfile != 0:
                use_nixpacks = True

        if use_nixpacks:
            _log("Building with Nixpacks...")
            ssh.run_streaming(
                f"nixpacks build {q_repo} --name infrakt-{shlex.quote(app_name)}",
                on_output=_stream,
                timeout=600,
            )
            # Generate compose using the pre-built image
            compose_content = compose_override or _generate_compose(
                app_name,
                port=port,
                image=f"infrakt-{app_name}",
                cpu_limit=cpu_limit,
                memory_limit=memory_limit,
                replicas=replicas,
                deploy_strategy=deploy_strategy,
                health_check_url=health_check_url,
                health_check_interval=health_check_interval,
                domain=domain,
            )
            ssh.upload_string(compose_content, f"{app_path}/docker-compose.yml")
            _log("Swapping containers...")
            ssh.run_streaming(
                f"cd {q_app_path} && {_compose_cmd(app_name)} up -d --remove-orphans",
                on_output=_stream,
                timeout=120,
            )
        elif has_compose == 0 and not compose_override:
            # Existing Dockerfile-based compose flow (split build/swap from Task 5)
            ...
```

Also pass `build_type` through from `api/routes/apps.py` deploy endpoint using `app_data.get("build_type", "auto")`.

**Step 4: Run tests**

Run: `python3 -m pytest tests/unit/test_deployer.py -xvs`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add cli/core/deployer.py cli/core/compose_renderer.py tests/unit/test_deployer.py
git commit -m "feat: add Nixpacks build path to deployer"
```

#### Task 6d: Wire build_type through API

**Files:**
- Modify: `api/routes/apps.py` (create and deploy endpoints)

**Step 1: Update app create to store build_type**

In `api/routes/apps.py`, in the create endpoint, read `build_type` from the request and store it on the App record:

```python
build_type = data.build_type or "auto"
# ... when creating the App:
app = App(..., build_type=build_type)
```

**Step 2: Update deploy endpoint to pass build_type to deploy_app**

In the deploy function, pass `build_type=app_obj.build_type or "auto"` to `deploy_app()`.

**Step 3: Run full test suite**

Run: `python3 -m pytest tests/unit/ -x -q`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add api/routes/apps.py
git commit -m "feat: wire build_type through API create and deploy endpoints"
```

---

### Task 7: Image-Based Rollbacks

#### Task 7a: Add image_tag to Deployment model

**Files:**
- Modify: `cli/models/deployment.py`

**Step 1: Add column**

```python
    image_tag: Mapped[str | None] = mapped_column(String(200))
```

**Step 2: Run tests**

Run: `python3 -m pytest tests/unit/ -x -q`
Expected: ALL PASS

**Step 3: Commit**

```bash
git add cli/models/deployment.py
git commit -m "feat: add image_tag column to Deployment model"
```

#### Task 7b: Tag images after successful builds

**Files:**
- Modify: `cli/core/deployer.py`
- Test: `tests/unit/test_deployer.py`

**Step 1: Write the failing test**

```python
@patch("cli.core.deployer.get_github_token", return_value=None)
def test_deploy_git_tags_image_after_build(_mock_token):
    """After a successful git build, the image should be tagged for rollback."""
    ssh = MagicMock()
    ssh.__enter__ = MagicMock(return_value=ssh)
    ssh.__exit__ = MagicMock(return_value=False)
    ssh.upload_string = MagicMock()
    ssh.run = MagicMock(side_effect=[("", "", 1), ("", "", 1)])
    ssh.run_streaming = MagicMock(return_value="")
    ssh.run_checked = MagicMock(side_effect=["", "abc1234567890\n", ""])  # mkdir, git rev-parse, docker tag

    result = deploy_app(ssh, "test-app", git_repo="https://github.com/test/repo.git", branch="main")

    tag_cmds = [str(c) for c in ssh.run_checked.call_args_list if "docker tag" in str(c)]
    assert len(tag_cmds) >= 1
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_deployer.py::test_deploy_git_tags_image_after_build -xvs`
Expected: FAIL

**Step 3: Implement image tagging**

In `deployer.py`, after the `_log("Deployment complete")` line, add image tagging logic. Add a `deployment_id` parameter to `deploy_app()` (passed from the API route where the deployment record is created).

After a successful git or Nixpacks build, tag the image:

```python
    # Tag image for rollback (git builds and nixpacks only)
    if git_repo and deployment_id:
        image_name = f"infrakt-{app_name}"
        tag = f"v{deployment_id}"
        try:
            ssh.run_checked(f"docker tag {shlex.quote(image_name)} {shlex.quote(image_name)}:{shlex.quote(tag)}")
            result.image_tag = f"{image_name}:{tag}"
            _log(f"Tagged image as {image_name}:{tag}")
        except Exception:
            _log("Warning: could not tag image for rollback")
```

Also add `image_tag` to `DeployResult`:

```python
@dataclass
class DeployResult:
    log: str = ""
    commit_hash: str | None = None
    image_used: str | None = None
    image_tag: str | None = None
```

**Step 4: Run tests**

Run: `python3 -m pytest tests/unit/test_deployer.py -xvs`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add cli/core/deployer.py tests/unit/test_deployer.py
git commit -m "feat: tag Docker images after build for rollback support"
```

#### Task 7c: Implement rollback-by-image in API

**Files:**
- Modify: `api/routes/apps.py` (rollback endpoint)

**Step 1: Update rollback logic**

In the rollback endpoint, when `deployment.image_tag` is set, skip the git reset + rebuild path. Instead:

1. Generate a compose file using `image: {deployment.image_tag}`
2. Upload it and run `docker compose up -d`

```python
if target_deployment.image_tag:
    # Instant rollback via pre-tagged image
    compose_content = _generate_compose(name, port=port, image=target_deployment.image_tag, ...)
    ssh.upload_string(compose_content, f"{app_path}/docker-compose.yml")
    ssh.run_streaming(f"cd {app_path} && {_compose_cmd(name)} up -d --remove-orphans", ...)
else:
    # Legacy: git reset + rebuild
    deploy_app(ssh, name, ..., pinned_commit=target_deployment.commit_hash)
```

**Step 2: Add image cleanup**

After a successful deploy, prune old tagged images (keep last 5):

```python
    # Prune old rollback images (keep last 5)
    if git_repo and deployment_id:
        _prune_old_images(ssh, app_name, keep=5)
```

```python
def _prune_old_images(ssh: SSHClient, app_name: str, keep: int = 5) -> None:
    """Remove old rollback image tags, keeping the N most recent."""
    image_name = f"infrakt-{app_name}"
    stdout, _, rc = ssh.run(
        f"docker images {shlex.quote(image_name)} --format '{{{{.Tag}}}}' | grep '^v' | sort -t v -k 2 -n"
    )
    if rc != 0 or not stdout.strip():
        return
    tags = [t.strip() for t in stdout.strip().splitlines() if t.strip()]
    if len(tags) <= keep:
        return
    for old_tag in tags[:-keep]:
        ssh.run(f"docker rmi {shlex.quote(image_name)}:{shlex.quote(old_tag)} 2>/dev/null || true")
```

**Step 3: Run tests**

Run: `python3 -m pytest tests/unit/ -x -q`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add cli/core/deployer.py api/routes/apps.py
git commit -m "feat: implement image-based rollbacks with auto-pruning"
```

---

## Phase 3: UX & Integration

### Task 8: Store DB Passwords Encrypted

**Files:**
- Modify: `cli/models/app.py`
- Modify: `cli/commands/db.py`
- Modify: `api/routes/databases.py`
- Modify: `api/schemas.py`
- Test: `tests/unit/test_api_databases.py`

**Step 1: Add column to App model**

In `cli/models/app.py`, add:

```python
    db_password_encrypted: Mapped[str | None] = mapped_column(String(500), default=None)
```

**Step 2: Encrypt password on DB creation**

In `cli/commands/db.py`, after generating the password, encrypt and store it:

```python
from cli.core.crypto import encrypt_value
# ... after password = secrets.token_urlsafe(24)
app.db_password_encrypted = encrypt_value(password)
```

Do the same in `api/routes/databases.py` create endpoint.

**Step 3: Add credentials retrieval endpoint**

In `api/routes/databases.py`, add:

```python
@router.get("/{name}/credentials")
def get_database_credentials(name: str, ...):
    """Return the decrypted connection string for a database."""
    # Look up app, decrypt db_password_encrypted, build connection string
    from cli.core.crypto import decrypt_value
    if not app.db_password_encrypted:
        raise HTTPException(status_code=404, detail="No stored credentials (created before this feature)")
    password = decrypt_value(app.db_password_encrypted)
    conn_string = _build_connection_string(db_type, name, password, port)
    return {"connection_string": conn_string, "password": password}
```

**Step 4: Run tests**

Run: `python3 -m pytest tests/unit/ -x -q`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add cli/models/app.py cli/commands/db.py api/routes/databases.py api/schemas.py
git commit -m "feat: store DB passwords encrypted for later retrieval"
```

---

### Task 9: GitHub Webhook Cleanup

**Files:**
- Modify: `cli/models/app.py`
- Modify: `api/routes/apps.py`

**Step 1: Add github_hook_id column**

In `cli/models/app.py`:

```python
    github_hook_id: Mapped[int | None] = mapped_column(Integer, default=None)
```

**Step 2: Store hook ID on webhook creation**

In `api/routes/apps.py`, where `create_repo_webhook` is called (around line 487), update:

```python
    hook_id = create_repo_webhook(gh_token, owner, repo_name, webhook_url, webhook_secret)
    if hook_id:
        a.webhook_secret = webhook_secret
        a.github_hook_id = hook_id
```

**Step 3: Clean up webhook on destroy**

In the destroy endpoint, before destroying the app:

```python
if app_obj.github_hook_id and app_obj.git_repo and "github.com" in (app_obj.git_repo or ""):
    gh_token = get_github_token()
    if gh_token:
        parts = app_obj.git_repo.replace("https://github.com/", "").replace(".git", "").split("/")
        if len(parts) >= 2:
            from cli.core.github import delete_repo_webhook
            delete_repo_webhook(gh_token, parts[0], parts[1], app_obj.github_hook_id)
```

**Step 4: Run tests**

Run: `python3 -m pytest tests/unit/ -x -q`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add cli/models/app.py api/routes/apps.py
git commit -m "feat: store and clean up GitHub webhook IDs on app destroy"
```

---

### Task 10: Bulk .env Import

**Files:**
- Modify: `api/routes/env.py`
- Modify: `api/schemas.py`
- Test: `tests/unit/test_api_env.py`

**Step 1: Add schema**

In `api/schemas.py`:

```python
class EnvImport(BaseModel):
    content: str = Field(..., min_length=1, max_length=100000)
```

**Step 2: Write the failing test**

```python
def test_env_import_parses_dotenv_format(isolated_config):
    """POST /env/import parses KEY=value format, skips comments and blanks."""
    # Setup app in DB...
    content = "# comment\nDB_URL=postgres://localhost\n\nSECRET=abc123\nEMPTY=\n"
    resp = client.post(f"/api/apps/myapp/env/import", json={"content": content}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["imported"] == 3  # DB_URL, SECRET, EMPTY
```

**Step 3: Implement endpoint**

In `api/routes/env.py`:

```python
@router.post("/{app_name}/env/import")
def import_env(app_name: str, data: EnvImport, ...):
    """Import environment variables from raw .env content."""
    from cli.core.crypto import encrypt_value, load_env_file, save_env_file

    app = _get_app(app_name, session)
    env_data = load_env_file(app.id)

    count = 0
    for line in data.content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        # Strip surrounding quotes from value
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
            continue
        env_data[key] = encrypt_value(value)
        count += 1

    save_env_file(app.id, env_data)
    return {"imported": count}
```

**Step 4: Run tests**

Run: `python3 -m pytest tests/unit/test_api_env.py -xvs`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add api/routes/env.py api/schemas.py tests/unit/test_api_env.py
git commit -m "feat: add bulk .env import endpoint"
```

---

### Task 11: Slack/Discord Notifications

**Files:**
- Modify: `cli/models/webhook.py`
- Modify: `cli/core/webhook_sender.py`
- Modify: `api/schemas.py`
- Test: `tests/unit/test_webhook_sender.py`

**Step 1: Add channel_type to Webhook model**

In `cli/models/webhook.py`:

```python
    channel_type: Mapped[str] = mapped_column(String(20), default="custom")
```

**Step 2: Write the failing test**

In `tests/unit/test_webhook_sender.py`:

```python
class TestSlackDiscordDelivery:
    def test_slack_webhook_sends_text_format(self, isolated_config):
        """Slack webhooks send {"text": "..."} format."""
        payload = {"event": "deploy.success", "timestamp": "t", "data": {"app": "myapp"}}

        with patch("urllib.request.urlopen") as mock_open:
            deliver_webhook("https://hooks.slack.com/x", None, payload, channel_type="slack")

        req = mock_open.call_args[0][0]
        body = json.loads(req.data)
        assert "text" in body
        assert "myapp" in body["text"]

    def test_discord_webhook_sends_content_format(self, isolated_config):
        """Discord webhooks send {"content": "..."} format."""
        payload = {"event": "deploy.success", "timestamp": "t", "data": {"app": "myapp"}}

        with patch("urllib.request.urlopen") as mock_open:
            deliver_webhook("https://discord.com/api/webhooks/x", None, payload, channel_type="discord")

        req = mock_open.call_args[0][0]
        body = json.loads(req.data)
        assert "content" in body
        assert "myapp" in body["text"]
```

**Step 3: Implement Slack/Discord delivery**

In `cli/core/webhook_sender.py`, update `deliver_webhook` to accept `channel_type`:

```python
def deliver_webhook(
    url: str, secret: str | None, payload: dict[str, object],
    timeout: int = 10, channel_type: str = "custom",
) -> None:
    """HTTP POST the payload. Format depends on channel_type."""
    if channel_type == "slack":
        msg = _format_message(payload)
        body = json.dumps({"text": msg}).encode()
    elif channel_type == "discord":
        msg = _format_message(payload)
        body = json.dumps({"content": msg}).encode()
    else:
        body = json.dumps(payload).encode()
    # ... rest of delivery logic


def _format_message(payload: dict[str, object]) -> str:
    """Build a human-readable notification message."""
    event = payload.get("event", "unknown")
    data = payload.get("data", {})
    app = data.get("app", "unknown")
    server = data.get("server", "")

    messages = {
        "deploy.success": f"Deploy of {app} succeeded" + (f" on {server}" if server else ""),
        "deploy.failure": f"Deploy of {app} failed" + (f" on {server}" if server else ""),
        "backup.complete": f"Backup of {app} completed",
        "backup.restore": f"Restore of {app} completed",
        "health.down": f"{app} is down",
        "health.up": f"{app} is back up",
    }
    return f"[infrakt] {messages.get(event, event)}"
```

Update `fire_webhooks` to pass `channel_type`:

```python
    targets = [(h.url, h.secret, getattr(h, "channel_type", "custom")) for h in hooks if event in h.events.split(",")]

    for url, secret, channel_type in targets:
        deliver_webhook(url, secret, payload, channel_type=channel_type)
```

**Step 4: Run tests**

Run: `python3 -m pytest tests/unit/test_webhook_sender.py -xvs`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add cli/models/webhook.py cli/core/webhook_sender.py api/schemas.py tests/unit/test_webhook_sender.py
git commit -m "feat: add Slack and Discord notification channel types"
```

---

## Final Verification

After all tasks are complete:

```bash
# Run full backend test suite
python3 -m pytest tests/unit/ -x -q

# Run type check
cd frontend && npm run type-check

# Run E2E tests
npx playwright test

# Lint
ruff check . && ruff format --check .
```

All must pass before creating the PR.
