from cli.core.database import get_session, init_db
from cli.models.server import Server


def test_init_db_creates_tables(isolated_config):
    init_db()
    with get_session() as session:
        servers = session.query(Server).all()
        assert servers == []


def test_add_and_query_server(isolated_config):
    init_db()
    with get_session() as session:
        session.add(Server(name="test-srv", host="1.2.3.4"))

    with get_session() as session:
        srv = session.query(Server).filter(Server.name == "test-srv").first()
        assert srv is not None
        assert srv.host == "1.2.3.4"
        assert srv.port == 22
        assert srv.user == "root"
        assert srv.status == "inactive"
