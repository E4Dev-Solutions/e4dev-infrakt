"""Platform settings API routes (S3 backup storage, etc.)."""

from fastapi import APIRouter

from api.schemas import S3ConfigSave
from cli.core.crypto import encrypt
from cli.core.database import get_session, init_db
from cli.models.s3_config import S3Config

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/s3")
def get_s3_config() -> dict:
    init_db()
    with get_session() as session:
        cfg = session.query(S3Config).first()
        if not cfg:
            return {"configured": False}
        return {
            "configured": True,
            "endpoint_url": cfg.endpoint_url,
            "bucket": cfg.bucket,
            "region": cfg.region,
            "access_key": cfg.access_key,
            "prefix": cfg.prefix,
        }


@router.put("/s3")
def save_s3_config(body: S3ConfigSave) -> dict[str, str]:
    init_db()
    with get_session() as session:
        cfg = session.query(S3Config).first()
        if cfg:
            cfg.endpoint_url = body.endpoint_url
            cfg.bucket = body.bucket
            cfg.region = body.region
            cfg.access_key = body.access_key
            cfg.secret_key_encrypted = encrypt(body.secret_key)
            cfg.prefix = body.prefix
        else:
            cfg = S3Config(
                endpoint_url=body.endpoint_url,
                bucket=body.bucket,
                region=body.region,
                access_key=body.access_key,
                secret_key_encrypted=encrypt(body.secret_key),
                prefix=body.prefix,
            )
            session.add(cfg)
    return {"message": "S3 configuration saved"}


@router.delete("/s3")
def delete_s3_config() -> dict[str, str]:
    init_db()
    with get_session() as session:
        cfg = session.query(S3Config).first()
        if cfg:
            session.delete(cfg)
    return {"message": "S3 configuration removed"}
