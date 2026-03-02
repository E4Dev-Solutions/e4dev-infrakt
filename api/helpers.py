"""Shared API helper functions."""

from cli.core.database import get_session


def get_s3_config() -> dict | None:
    """Return decrypted S3 config dict, or None if not configured."""
    from cli.core.crypto import decrypt
    from cli.models.s3_config import S3Config

    with get_session() as session:
        cfg = session.query(S3Config).first()
        if not cfg:
            return None
        return {
            "endpoint_url": cfg.endpoint_url,
            "bucket": cfg.bucket,
            "region": cfg.region,
            "access_key": cfg.access_key,
            "secret_key": decrypt(cfg.secret_key_encrypted),
            "prefix": cfg.prefix,
        }
