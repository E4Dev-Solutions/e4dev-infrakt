"""Tests for the 'app' CLI command group (create, list, deploy, stop, destroy, etc.)."""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from cli.core.database import get_session, init_db
from cli.main import cli
from cli.models.app import App
from cli.models.server import Server


@pytest.fixture
def runner():
    return CliRunner()


def _seed_server(name="test-server", host="1.2.3.4", user="root"):
    """Insert a server record into the isolated DB and return it."""
    init_db()
    with get_session() as session:
        srv = Server(name=name, host=host, user=user, port=22, status="active")
        session.add(srv)
    return name


def _seed_app(server_name="test-server", app_name="my-app", status="stopped"):
    """Insert a server + app record and return the app name."""
    _seed_server(server_name)
    init_db()
    with get_session() as session:
        srv = session.query(Server).filter(Server.name == server_name).first()
        a = App(name=app_name, server_id=srv.id, port=3000, app_type="git", status=status)
        session.add(a)
    return app_name


# ---------------------------------------------------------------------------
# app create
# ---------------------------------------------------------------------------

class TestAppCreate:
    def test_create_succeeds_with_valid_server(self, runner, isolated_config):
        _seed_server("prod")
        result = runner.invoke(cli, [
            "app", "create",
            "--server", "prod",
            "--name", "web-api",
            "--port", "8080",
        ])
        assert result.exit_code == 0
        assert "web-api" in result.output

    def test_create_stores_app_in_database(self, runner, isolated_config):
        _seed_server("prod")
        runner.invoke(cli, [
            "app", "create",
            "--server", "prod",
            "--name", "stored-app",
        ])
        init_db()
        with get_session() as session:
            app_obj = session.query(App).filter(App.name == "stored-app").first()
            found = app_obj is not None
            status = app_obj.status if app_obj else None
        assert found
        assert status == "stopped"

    def test_create_fails_when_server_not_found(self, runner, isolated_config):
        result = runner.invoke(cli, [
            "app", "create",
            "--server", "nonexistent",
            "--name", "my-app",
        ])
        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "nonexistent" in result.output

    def test_create_fails_on_duplicate_app_name(self, runner, isolated_config):
        _seed_server("prod")
        runner.invoke(cli, ["app", "create", "--server", "prod", "--name", "dup-app"])
        result = runner.invoke(cli, ["app", "create", "--server", "prod", "--name", "dup-app"])
        assert result.exit_code != 0
        assert "already exists" in result.output

    def test_create_with_git_repo_sets_type(self, runner, isolated_config):
        _seed_server("prod")
        runner.invoke(cli, [
            "app", "create",
            "--server", "prod",
            "--name", "git-app",
            "--git", "https://github.com/example/repo.git",
        ])
        init_db()
        with get_session() as session:
            app_obj = session.query(App).filter(App.name == "git-app").first()
            app_type = app_obj.app_type if app_obj else None
            git_repo = app_obj.git_repo if app_obj else None
        assert app_type == "git"
        assert git_repo == "https://github.com/example/repo.git"

    def test_create_with_image_sets_type(self, runner, isolated_config):
        _seed_server("prod")
        runner.invoke(cli, [
            "app", "create",
            "--server", "prod",
            "--name", "img-app",
            "--image", "nginx:latest",
        ])
        init_db()
        with get_session() as session:
            app_obj = session.query(App).filter(App.name == "img-app").first()
            app_type = app_obj.app_type if app_obj else None
            image = app_obj.image if app_obj else None
        assert app_type == "image"
        assert image == "nginx:latest"

    def test_create_with_domain_stores_domain(self, runner, isolated_config):
        _seed_server("prod")
        runner.invoke(cli, [
            "app", "create",
            "--server", "prod",
            "--name", "domain-app",
            "--domain", "api.example.com",
        ])
        init_db()
        with get_session() as session:
            app_obj = session.query(App).filter(App.name == "domain-app").first()
            domain = app_obj.domain if app_obj else None
        assert domain == "api.example.com"

    def test_create_without_source_defaults_to_compose_type(self, runner, isolated_config):
        _seed_server("prod")
        runner.invoke(cli, [
            "app", "create",
            "--server", "prod",
            "--name", "compose-app",
        ])
        init_db()
        with get_session() as session:
            app_obj = session.query(App).filter(App.name == "compose-app").first()
            app_type = app_obj.app_type if app_obj else None
        assert app_type == "compose"


# ---------------------------------------------------------------------------
# app list
# ---------------------------------------------------------------------------

class TestAppList:
    def test_list_shows_no_apps_message_when_empty(self, runner, isolated_config):
        result = runner.invoke(cli, ["app", "list"])
        assert result.exit_code == 0
        assert "No apps" in result.output

    def test_list_shows_created_apps(self, runner, isolated_config):
        _seed_server("prod")
        runner.invoke(cli, ["app", "create", "--server", "prod", "--name", "listed-app"])
        result = runner.invoke(cli, ["app", "list"])
        assert result.exit_code == 0
        assert "listed-app" in result.output

    def test_list_shows_server_name_in_output(self, runner, isolated_config):
        _seed_server("staging")
        runner.invoke(cli, ["app", "create", "--server", "staging", "--name", "svc"])
        result = runner.invoke(cli, ["app", "list"])
        assert "staging" in result.output

    def test_list_filtered_by_server_shows_only_matching(self, runner, isolated_config):
        _seed_server("prod")
        _seed_server("staging", host="2.2.2.2")
        runner.invoke(cli, ["app", "create", "--server", "prod", "--name", "prod-app"])
        runner.invoke(cli, ["app", "create", "--server", "staging", "--name", "stage-app"])
        result = runner.invoke(cli, ["app", "list", "--server", "prod"])
        assert result.exit_code == 0
        assert "prod-app" in result.output
        assert "stage-app" not in result.output

    def test_list_shows_multiple_apps(self, runner, isolated_config):
        _seed_server("prod")
        for name in ("alpha", "beta", "gamma"):
            runner.invoke(cli, ["app", "create", "--server", "prod", "--name", name])
        result = runner.invoke(cli, ["app", "list"])
        for name in ("alpha", "beta", "gamma"):
            assert name in result.output


# ---------------------------------------------------------------------------
# app deploy
# ---------------------------------------------------------------------------

class TestAppDeploy:
    def test_deploy_succeeds_with_mocked_ssh(self, runner, isolated_config):
        _seed_app("prod", "deploy-me")
        with patch("cli.commands.app.SSHClient") as mock_cls, \
             patch("cli.commands.app.deploy_app", return_value="build log"), \
             patch("cli.commands.app.status_spinner"):
            mock_ssh = MagicMock()
            mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
            mock_ssh.__exit__ = MagicMock(return_value=False)
            mock_ssh.run.return_value = ("", "", 0)
            mock_cls.from_server.return_value = mock_ssh

            result = runner.invoke(cli, ["app", "deploy", "deploy-me"])

        assert result.exit_code == 0
        assert "deploy-me" in result.output

    def test_deploy_fails_when_app_not_found(self, runner, isolated_config):
        result = runner.invoke(cli, ["app", "deploy", "ghost-app"])
        assert result.exit_code != 0

    def test_deploy_updates_app_status_to_running_on_success(self, runner, isolated_config):
        _seed_app("prod", "status-app")
        with patch("cli.commands.app.SSHClient") as mock_cls, \
             patch("cli.commands.app.deploy_app", return_value="ok"), \
             patch("cli.commands.app.status_spinner"):
            mock_ssh = MagicMock()
            mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
            mock_ssh.__exit__ = MagicMock(return_value=False)
            mock_ssh.run.return_value = ("", "", 0)
            mock_cls.from_server.return_value = mock_ssh
            runner.invoke(cli, ["app", "deploy", "status-app"])

        init_db()
        with get_session() as session:
            app_obj = session.query(App).filter(App.name == "status-app").first()
            status = app_obj.status if app_obj else None
        assert status == "running"

    def test_deploy_sets_app_status_to_error_on_failure(self, runner, isolated_config):
        _seed_app("prod", "fail-app")
        with patch("cli.commands.app.SSHClient") as mock_cls, \
             patch("cli.commands.app.deploy_app", side_effect=Exception("boom")), \
             patch("cli.commands.app.status_spinner"):
            mock_ssh = MagicMock()
            mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
            mock_ssh.__exit__ = MagicMock(return_value=False)
            mock_ssh.run.return_value = ("", "", 0)
            mock_cls.from_server.return_value = mock_ssh
            result = runner.invoke(cli, ["app", "deploy", "fail-app"])

        assert result.exit_code != 0
        init_db()
        with get_session() as session:
            app_obj = session.query(App).filter(App.name == "fail-app").first()
            status = app_obj.status if app_obj else None
        assert status == "error"


# ---------------------------------------------------------------------------
# app stop
# ---------------------------------------------------------------------------

class TestAppStop:
    def test_stop_succeeds_with_mocked_ssh(self, runner, isolated_config):
        _seed_app("prod", "running-app", status="running")
        with patch("cli.commands.app.SSHClient") as mock_cls, \
             patch("cli.commands.app.stop_app"), \
             patch("cli.commands.app.status_spinner"):
            mock_ssh = MagicMock()
            mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
            mock_ssh.__exit__ = MagicMock(return_value=False)
            mock_cls.from_server.return_value = mock_ssh
            result = runner.invoke(cli, ["app", "stop", "running-app"])

        assert result.exit_code == 0
        assert "running-app" in result.output

    def test_stop_updates_app_status_to_stopped(self, runner, isolated_config):
        _seed_app("prod", "to-stop", status="running")
        with patch("cli.commands.app.SSHClient") as mock_cls, \
             patch("cli.commands.app.stop_app"), \
             patch("cli.commands.app.status_spinner"):
            mock_ssh = MagicMock()
            mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
            mock_ssh.__exit__ = MagicMock(return_value=False)
            mock_cls.from_server.return_value = mock_ssh
            runner.invoke(cli, ["app", "stop", "to-stop"])

        init_db()
        with get_session() as session:
            app_obj = session.query(App).filter(App.name == "to-stop").first()
            status = app_obj.status if app_obj else None
        assert status == "stopped"

    def test_stop_fails_when_app_not_found(self, runner, isolated_config):
        result = runner.invoke(cli, ["app", "stop", "ghost"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# app destroy
# ---------------------------------------------------------------------------

class TestAppDestroy:
    def test_destroy_with_force_removes_app_from_database(self, runner, isolated_config):
        _seed_app("prod", "doomed-app")
        with patch("cli.commands.app.SSHClient") as mock_cls, \
             patch("cli.commands.app.destroy_app"), \
             patch("cli.commands.app.status_spinner"):
            mock_ssh = MagicMock()
            mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
            mock_ssh.__exit__ = MagicMock(return_value=False)
            mock_cls.from_server.return_value = mock_ssh
            result = runner.invoke(cli, ["app", "destroy", "doomed-app", "--force"])

        assert result.exit_code == 0
        init_db()
        with get_session() as session:
            app_obj = session.query(App).filter(App.name == "doomed-app").first()
        assert app_obj is None

    def test_destroy_prints_success_message(self, runner, isolated_config):
        _seed_app("prod", "bye-app")
        with patch("cli.commands.app.SSHClient") as mock_cls, \
             patch("cli.commands.app.destroy_app"), \
             patch("cli.commands.app.status_spinner"):
            mock_ssh = MagicMock()
            mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
            mock_ssh.__exit__ = MagicMock(return_value=False)
            mock_cls.from_server.return_value = mock_ssh
            result = runner.invoke(cli, ["app", "destroy", "bye-app", "--force"])

        assert "bye-app" in result.output

    def test_destroy_fails_when_app_not_found(self, runner, isolated_config):
        result = runner.invoke(cli, ["app", "destroy", "ghost", "--force"])
        assert result.exit_code != 0

    def test_destroy_without_force_prompts_confirmation(self, runner, isolated_config):
        _seed_app("prod", "careful-app")
        # Provide 'n' to decline the confirmation prompt
        runner.invoke(cli, ["app", "destroy", "careful-app"], input="n\n")
        # Should abort and not destroy the app
        init_db()
        with get_session() as session:
            app_obj = session.query(App).filter(App.name == "careful-app").first()
        assert app_obj is not None
