"""Tests for auto-domain in CLI app create."""

from click.testing import CliRunner

from cli.core.database import get_session, init_db
from cli.main import cli
from cli.models.app import App
from cli.models.platform_settings import PlatformSettings
from cli.models.server import Server


class TestCliAutoDomain:
    def test_auto_assigns_domain_when_base_configured(self, isolated_config):
        """When base_domain is set and no --domain provided, auto-assign domain."""
        init_db()
        runner = CliRunner()
        with get_session() as session:
            session.add(Server(name="s1", host="1.2.3.4", user="root", port=22, status="active"))
            session.add(PlatformSettings(base_domain="infrakt.cloud"))

        result = runner.invoke(
            cli,
            [
                "app",
                "create",
                "--server",
                "s1",
                "--name",
                "testapp",
                "--image",
                "nginx",
            ],
        )
        assert result.exit_code == 0

        with get_session() as session:
            app = session.query(App).filter(App.name == "testapp").first()
            assert app is not None
            assert app.domain is not None
            assert app.domain.endswith(".infrakt.cloud")

    def test_no_auto_domain_when_explicit(self, isolated_config):
        """When --domain is provided, don't auto-assign."""
        init_db()
        runner = CliRunner()
        with get_session() as session:
            session.add(Server(name="s1", host="1.2.3.4", user="root", port=22, status="active"))
            session.add(PlatformSettings(base_domain="infrakt.cloud"))

        result = runner.invoke(
            cli,
            [
                "app",
                "create",
                "--server",
                "s1",
                "--name",
                "testapp",
                "--image",
                "nginx",
                "--domain",
                "custom.com",
            ],
        )
        assert result.exit_code == 0

        with get_session() as session:
            app = session.query(App).filter(App.name == "testapp").first()
            assert app.domain == "custom.com"

    def test_no_auto_domain_when_base_not_configured(self, isolated_config):
        """When base_domain is not set, don't auto-assign."""
        init_db()
        runner = CliRunner()
        with get_session() as session:
            session.add(Server(name="s1", host="1.2.3.4", user="root", port=22, status="active"))
            # No PlatformSettings record created

        result = runner.invoke(
            cli,
            [
                "app",
                "create",
                "--server",
                "s1",
                "--name",
                "testapp",
                "--image",
                "nginx",
            ],
        )
        assert result.exit_code == 0

        with get_session() as session:
            app = session.query(App).filter(App.name == "testapp").first()
            assert app.domain is None
