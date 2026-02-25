from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from cli.core.database import Base


class SSHKey(Base):
    __tablename__ = "ssh_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(200), nullable=False)
    key_type: Mapped[str] = mapped_column(String(20), default="ed25519")
    public_key: Mapped[str] = mapped_column(Text, nullable=False)
    key_path: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=func.now())

    def __repr__(self) -> str:
        return f"<SSHKey {self.name}>"
