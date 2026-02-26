from cli.core.database import get_session, init_db
from cli.models.github_integration import GitHubIntegration
from cli.models.app import App
from cli.models.server import Server


def test_github_integration_create_and_read():
    init_db()
    with get_session() as session:
        gi = GitHubIntegration(
            token_encrypted="fernet-encrypted-token",
            github_username="testuser",
        )
        session.add(gi)
        session.flush()
        assert gi.id is not None
        assert gi.github_username == "testuser"
    with get_session() as session:
        gi = session.query(GitHubIntegration).first()
        assert gi is not None
        assert gi.token_encrypted == "fernet-encrypted-token"


def test_app_has_webhook_fields():
    init_db()
    with get_session() as session:
        srv = Server(name="test-srv", host="1.2.3.4", user="root", port=22, status="active")
        session.add(srv)
        session.flush()
        app = App(
            name="test-app", server_id=srv.id, port=3000, status="stopped",
            app_type="git", webhook_secret="secret123", auto_deploy=True,
        )
        session.add(app)
        session.flush()
        assert app.webhook_secret == "secret123"
        assert app.auto_deploy is True


def test_app_auto_deploy_defaults_true():
    init_db()
    with get_session() as session:
        srv = Server(name="test-srv2", host="1.2.3.5", user="root", port=22, status="active")
        session.add(srv)
        session.flush()
        app = App(name="test-app2", server_id=srv.id, port=3000, status="stopped", app_type="git")
        session.add(app)
        session.flush()
        assert app.auto_deploy is True
