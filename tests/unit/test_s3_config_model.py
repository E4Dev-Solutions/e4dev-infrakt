"""Tests for S3Config model."""

from cli.core.database import get_session, init_db
from cli.models.s3_config import S3Config


class TestS3ConfigModel:
    def test_create_s3_config(self, isolated_config):
        init_db()
        with get_session() as session:
            config = S3Config(
                endpoint_url="https://s3.amazonaws.com",
                bucket="my-backups",
                region="us-east-1",
                access_key="AKIAIOSFODNN7EXAMPLE",
                secret_key_encrypted="encrypted-secret",
                prefix="infrakt/",
            )
            session.add(config)
            session.flush()
            assert config.id is not None

    def test_read_s3_config(self, isolated_config):
        init_db()
        with get_session() as session:
            config = S3Config(
                endpoint_url="https://nyc3.digitaloceanspaces.com",
                bucket="backups",
                region="nyc3",
                access_key="DO_KEY",
                secret_key_encrypted="encrypted",
                prefix="",
            )
            session.add(config)

        with get_session() as session:
            found = session.query(S3Config).first()
            assert found is not None
            assert found.endpoint_url == "https://nyc3.digitaloceanspaces.com"
            assert found.bucket == "backups"

    def test_prefix_defaults_to_empty(self, isolated_config):
        init_db()
        with get_session() as session:
            config = S3Config(
                endpoint_url="https://s3.amazonaws.com",
                bucket="b",
                region="us-east-1",
                access_key="k",
                secret_key_encrypted="s",
            )
            session.add(config)
            session.flush()
            assert config.prefix == ""
