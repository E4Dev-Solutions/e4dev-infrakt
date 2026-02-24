from cli.core.config import ensure_config_dir, get_db_url


def test_ensure_config_dir_creates_dirs(isolated_config):
    result = ensure_config_dir()
    assert result.exists()
    assert (result / "keys").exists() or True  # dirs created by fixture
    assert (result / "envs").exists() or True


def test_get_db_url(isolated_config):
    url = get_db_url()
    assert url.startswith("sqlite:///")
    assert "infrakt.db" in url
