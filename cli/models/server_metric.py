from __future__ import annotations

from datetime import datetime

from sqlalchemy import Float, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from cli.core.database import Base


class ServerMetric(Base):
    __tablename__ = "server_metrics"
    __table_args__ = (Index("ix_server_metrics_server_time", "server_id", "recorded_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id"), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(default=func.now())
    cpu_percent: Mapped[float | None] = mapped_column(Float)
    mem_percent: Mapped[float | None] = mapped_column(Float)
    disk_percent: Mapped[float | None] = mapped_column(Float)

    def __repr__(self) -> str:
        return f"<ServerMetric server_id={self.server_id} at={self.recorded_at}>"
