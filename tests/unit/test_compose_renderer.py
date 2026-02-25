"""Tests for cli/core/compose_renderer.py — render_app_compose and render_db_compose."""

from __future__ import annotations

import yaml

from cli.core.compose_renderer import render_app_compose, render_db_compose

# ---------------------------------------------------------------------------
# render_app_compose — happy path
# ---------------------------------------------------------------------------


class TestRenderAppComposeBasic:
    def test_image_app_contains_image_directive(self):
        content = render_app_compose("my-api", port=8080, image="nginx:alpine")
        assert "image: nginx:alpine" in content

    def test_image_app_contains_container_name(self):
        content = render_app_compose("my-api", port=8080, image="nginx:alpine")
        assert "container_name: infrakt-my-api" in content

    def test_image_app_contains_port(self):
        content = render_app_compose("my-api", port=8080, image="nginx:alpine")
        assert "8080" in content

    def test_git_app_uses_build_context(self):
        content = render_app_compose("my-api", port=3000, build_context="./repo")
        assert "build: ./repo" in content
        assert "image:" not in content

    def test_git_app_contains_container_name(self):
        content = render_app_compose("my-api", port=3000, build_context="./repo")
        assert "container_name: infrakt-my-api" in content

    def test_app_name_with_hyphens_is_preserved(self):
        content = render_app_compose("my-cool-app", port=5000, image="python:3.12")
        assert "my-cool-app" in content
        assert "container_name: infrakt-my-cool-app" in content

    def test_network_infrakt_is_present(self):
        content = render_app_compose("svc", port=3000, image="redis:7")
        assert "infrakt" in content

    def test_output_is_valid_yaml(self):
        content = render_app_compose("my-api", port=8080, image="nginx:alpine")
        parsed = yaml.safe_load(content)
        assert isinstance(parsed, dict)

    def test_services_key_exists_in_parsed_yaml(self):
        content = render_app_compose("api", port=3000, image="node:20")
        parsed = yaml.safe_load(content)
        assert "services" in parsed

    def test_port_variable_uses_upper_snake_case(self):
        # Port var for "my-api" should be MY_API_PORT
        content = render_app_compose("my-api", port=3000, image="node:20")
        assert "MY_API_PORT" in content

    def test_port_variable_for_simple_name(self):
        content = render_app_compose("web", port=80, image="nginx")
        assert "WEB_PORT" in content

    def test_restart_policy_present(self):
        content = render_app_compose("svc", port=3000, image="nginx")
        assert "unless-stopped" in content

    def test_env_file_directive_present(self):
        content = render_app_compose("svc", port=3000, image="nginx")
        assert ".env" in content


# ---------------------------------------------------------------------------
# render_app_compose — resource limits
# ---------------------------------------------------------------------------


class TestRenderAppComposeLimits:
    def test_both_limits_produce_deploy_block(self):
        content = render_app_compose(
            "api",
            port=3000,
            image="node:20",
            cpu_limit="0.5",
            memory_limit="512M",
        )
        assert "deploy:" in content
        assert "resources:" in content
        assert "limits:" in content
        assert 'cpus: "0.5"' in content
        assert "memory: 512M" in content

    def test_both_limits_valid_yaml(self):
        content = render_app_compose(
            "api",
            port=3000,
            image="node:20",
            cpu_limit="0.5",
            memory_limit="512M",
        )
        parsed = yaml.safe_load(content)
        service = parsed["services"]["api"]
        limits = service["deploy"]["resources"]["limits"]
        assert limits["cpus"] == "0.5"
        assert limits["memory"] == "512M"

    def test_only_cpu_limit_produces_deploy_block(self):
        content = render_app_compose(
            "api",
            port=3000,
            image="node:20",
            cpu_limit="1.0",
        )
        assert "deploy:" in content
        assert 'cpus: "1.0"' in content
        assert "memory:" not in content

    def test_only_memory_limit_produces_deploy_block(self):
        content = render_app_compose(
            "api",
            port=3000,
            image="node:20",
            memory_limit="256M",
        )
        assert "deploy:" in content
        assert "memory: 256M" in content
        assert "cpus:" not in content

    def test_no_limits_omits_deploy_block(self):
        content = render_app_compose("api", port=3000, image="node:20")
        assert "deploy:" not in content
        assert "resources:" not in content

    def test_no_limits_valid_yaml(self):
        content = render_app_compose("api", port=3000, image="node:20")
        parsed = yaml.safe_load(content)
        service = parsed["services"]["api"]
        assert "deploy" not in service


# ---------------------------------------------------------------------------
# render_db_compose — database types
# ---------------------------------------------------------------------------


class TestRenderDbCompose:
    def _postgres_compose(self, name="mydb", version="16") -> str:
        return render_db_compose(
            db_type="postgres",
            name=name,
            image=f"postgres:{version}",
            port=5432,
            env_vars={"POSTGRES_USER": name, "POSTGRES_PASSWORD": "secret"},
            volume=f"{name}_data:/var/lib/postgresql/data",
        )

    def _mysql_compose(self, name="mydb", version="8") -> str:
        return render_db_compose(
            db_type="mysql",
            name=name,
            image=f"mysql:{version}",
            port=3306,
            env_vars={"MYSQL_ROOT_PASSWORD": "secret", "MYSQL_DATABASE": name},
            volume=f"{name}_data:/var/lib/mysql",
        )

    def _redis_compose(self, name="cache", version="7-alpine") -> str:
        return render_db_compose(
            db_type="redis",
            name=name,
            image=f"redis:{version}",
            port=6379,
            env_vars={},
            volume=f"{name}_data:/data",
        )

    def _mongo_compose(self, name="mydb", version="7") -> str:
        return render_db_compose(
            db_type="mongo",
            name=name,
            image=f"mongo:{version}",
            port=27017,
            env_vars={"MONGO_INITDB_ROOT_USERNAME": "root", "MONGO_INITDB_ROOT_PASSWORD": "secret"},
            volume=f"{name}_data:/data/db",
        )

    def test_postgres_contains_image(self):
        content = self._postgres_compose()
        assert "image: postgres:16" in content

    def test_postgres_contains_container_name(self):
        content = self._postgres_compose()
        assert "container_name: infrakt-db-mydb" in content

    def test_postgres_contains_port(self):
        content = self._postgres_compose()
        assert "5432" in content

    def test_postgres_binds_to_loopback(self):
        content = self._postgres_compose()
        assert "127.0.0.1" in content

    def test_postgres_contains_env_vars(self):
        content = self._postgres_compose()
        assert "POSTGRES_USER" in content
        assert "POSTGRES_PASSWORD" in content

    def test_postgres_valid_yaml(self):
        parsed = yaml.safe_load(self._postgres_compose())
        assert "services" in parsed

    def test_mysql_contains_image(self):
        content = self._mysql_compose()
        assert "image: mysql:8" in content

    def test_mysql_contains_container_name(self):
        content = self._mysql_compose()
        assert "container_name: infrakt-db-mydb" in content

    def test_mysql_valid_yaml(self):
        parsed = yaml.safe_load(self._mysql_compose())
        assert "services" in parsed

    def test_redis_contains_image(self):
        content = self._redis_compose()
        assert "image: redis:7-alpine" in content

    def test_redis_no_env_vars_when_empty(self):
        content = self._redis_compose()
        assert "environment:" not in content

    def test_redis_valid_yaml(self):
        parsed = yaml.safe_load(self._redis_compose())
        assert "services" in parsed

    def test_mongo_contains_image(self):
        content = self._mongo_compose()
        assert "image: mongo:7" in content

    def test_mongo_contains_env_vars(self):
        content = self._mongo_compose()
        assert "MONGO_INITDB_ROOT_USERNAME" in content

    def test_mongo_valid_yaml(self):
        parsed = yaml.safe_load(self._mongo_compose())
        assert "services" in parsed

    def test_custom_version_in_image(self):
        content = self._postgres_compose(version="15")
        assert "image: postgres:15" in content

    def test_volume_declaration_present(self):
        content = self._postgres_compose()
        assert "volumes:" in content

    def test_network_infrakt_is_present(self):
        content = self._postgres_compose()
        assert "infrakt" in content

    def test_db_type_comment_in_output(self):
        content = self._postgres_compose()
        assert "postgres" in content
