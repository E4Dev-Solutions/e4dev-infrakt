from cli.core.proxy_manager import _build_caddyfile, _parse_caddyfile


def test_build_caddyfile():
    entries = [("api.example.com", 8001), ("app.example.com", 8002)]
    content = _build_caddyfile(entries)
    assert "api.example.com" in content
    assert "reverse_proxy localhost:8001" in content
    assert "app.example.com" in content
    assert "reverse_proxy localhost:8002" in content


def test_parse_caddyfile():
    content = """# Managed by infrakt
api.example.com {
    reverse_proxy localhost:8001
}

app.example.com {
    reverse_proxy localhost:8002
}
"""
    entries = _parse_caddyfile(content)
    assert ("api.example.com", 8001) in entries
    assert ("app.example.com", 8002) in entries


def test_roundtrip():
    original = [("a.com", 3000), ("b.com", 4000)]
    content = _build_caddyfile(original)
    parsed = _parse_caddyfile(content)
    assert sorted(parsed) == sorted(original)
