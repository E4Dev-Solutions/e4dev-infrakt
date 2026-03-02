from __future__ import annotations

from datetime import datetime

from sqlalchemy import Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from cli.core.database import Base


class BackupPolicy(Base):
    __tablename__ = "backup_policies"

    id: Mapped[int] = mapped_column(primary_key=True)
    default_cron: Mapped[str | None] = mapped_column(String(100), default=None)
    default_retention_days: Mapped[int] = mapped_column(Integer, default=7)
    s3_max_backups_per_db: Mapped[int] = mapped_column(Integer, default=10)
    s3_max_age_days: Mapped[int] = mapped_column(Integer, default=30)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())
