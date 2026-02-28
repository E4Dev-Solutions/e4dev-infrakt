from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, func
from sqlalchemy.orm import Mapped, mapped_column

from cli.core.database import Base


class S3Config(Base):
    __tablename__ = "s3_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    endpoint_url: Mapped[str] = mapped_column(String(500), nullable=False)
    bucket: Mapped[str] = mapped_column(String(200), nullable=False)
    region: Mapped[str] = mapped_column(String(50), nullable=False)
    access_key: Mapped[str] = mapped_column(String(200), nullable=False)
    secret_key_encrypted: Mapped[str] = mapped_column(String(500), nullable=False)
    prefix: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())
