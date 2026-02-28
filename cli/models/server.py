from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cli.core.database import Base

if TYPE_CHECKING:
    from cli.models.app import App
    from cli.models.server_tag import ServerTag


class Server(Base):
    __tablename__ = "servers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, default=22)
    user: Mapped[str] = mapped_column(String(100), default="root")
    ssh_key_path: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="inactive")
    is_infrakt_host: Mapped[bool] = mapped_column(Boolean, default=False)
    provider: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())

    apps: Mapped[list[App]] = relationship(back_populates="server", cascade="all, delete-orphan")
    tags: Mapped[list[ServerTag]] = relationship(cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Server {self.name} ({self.host})>"
