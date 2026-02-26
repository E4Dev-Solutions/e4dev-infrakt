import yaml

from cli.core.proxy_manager import (
    _build_domain_config,
    _conf_path,
    _sanitize_domain,
    add_domain,
    list_domains,
    remove_domain,
)


def test_sanitize_domain():
    assert _sanitize_domain("myapp.example.com") == "myapp-example-com"
    assert _sanitize_domain("api.example.com") == "api-example-com"
    assert _sanitize_domain("a.b.c.d") == "a-b-c-d"
    assert _sanitize_domain("simple") == "simple"


def test_conf_path():
    assert _conf_path("myapp.example.com") == "/opt/infrakt/traefik/conf.d/myapp-example-com.yml"
    assert _conf_path("api.example.com") == "/opt/infrakt/traefik/conf.d/api-example-com.yml"


def test_build_domain_config_structure():
    content = _build_domain_config("myapp.example.com", 3000)
    data = yaml.safe_load(content)

    # Check routers
    routers = data["http"]["routers"]
    assert "myapp-example-com" in routers
    assert "myapp-example-com-http" in routers

    # Check HTTPS router
    https_router = routers["myapp-example-com"]
    assert https_router["rule"] == "Host(`myapp.example.com`)"
    assert https_router["entryPoints"] == ["websecure"]
    assert https_router["tls"]["certResolver"] == "letsencrypt"

    # Check HTTP router
    http_router = routers["myapp-example-com-http"]
    assert http_router["rule"] == "Host(`myapp.example.com`)"
    assert http_router["entryPoints"] == ["web"]

    # Check services
    services = data["http"]["services"]
    assert "svc-myapp-example-com" in services
    lb = services["svc-myapp-example-com"]["loadBalancer"]
    assert lb["servers"] == [{"url": "http://host.docker.internal:3000"}]
    assert lb["passHostHeader"] is True


def test_add_domain_writes_config(mock_ssh):
    add_domain(mock_ssh, "api.example.com", 8001)

    # Verify upload_string was called with the correct path
    mock_ssh.upload_string.assert_called_once()
    args = mock_ssh.upload_string.call_args
    content = args[0][0]
    path = args[0][1]

    assert path == "/opt/infrakt/traefik/conf.d/api-example-com.yml"

    # Verify the content is valid YAML with correct structure
    data = yaml.safe_load(content)
    assert "http" in data
    assert "routers" in data["http"]
    assert "services" in data["http"]
    assert "http://host.docker.internal:8001" in content


def test_remove_domain_calls_rm(mock_ssh):
    remove_domain(mock_ssh, "api.example.com")
    mock_ssh.run_checked.assert_called_once_with(
        "rm -f /opt/infrakt/traefik/conf.d/api-example-com.yml"
    )


def test_list_domains_parses_configs(mock_ssh):
    # Mock ls to return two config files
    mock_ssh.run.return_value = (
        "/opt/infrakt/traefik/conf.d/api-example-com.yml\n"
        "/opt/infrakt/traefik/conf.d/app-example-com.yml\n",
        "",
        0,
    )

    # Mock read_remote_file to return valid configs
    config1 = _build_domain_config("api.example.com", 8001)
    config2 = _build_domain_config("app.example.com", 8002)
    mock_ssh.read_remote_file.side_effect = [config1, config2]

    entries = list_domains(mock_ssh)
    assert ("api.example.com", 8001) in entries
    assert ("app.example.com", 8002) in entries


def test_list_domains_empty(mock_ssh):
    mock_ssh.run.return_value = ("", "", 1)
    entries = list_domains(mock_ssh)
    assert entries == []
