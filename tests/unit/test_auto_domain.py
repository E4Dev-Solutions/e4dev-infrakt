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
