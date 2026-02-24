from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cli.core.database import Base

if TYPE_CHECKING:
    from cli.models.app import App


class Deployment(Base):
    __tablename__ = "deployments"

    id: Mapped[int] = mapped_column(primary_key=True)
    app_id: Mapped[int] = mapped_column(ForeignKey("apps.id"), nullable=False)
    commit_hash: Mapped[str | None] = mapped_column(String(40))
    image_used: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="in_progress")
    log: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column()

    app: Mapped[App] = relationship(back_populates="deployments")

    def __repr__(self) -> str:
        return f"<Deployment {self.id} app_id={self.app_id} status={self.status}>"
