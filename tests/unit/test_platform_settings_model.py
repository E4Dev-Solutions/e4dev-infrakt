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
