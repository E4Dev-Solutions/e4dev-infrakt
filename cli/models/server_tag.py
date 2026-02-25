from __future__ import annotations

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from cli.core.database import Base


class ServerTag(Base):
    __tablename__ = "server_tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id"), nullable=False)
    tag: Mapped[str] = mapped_column(String(100), nullable=False)

    __table_args__ = (UniqueConstraint("server_id", "tag"),)

    def __repr__(self) -> str:
        return f"<ServerTag server_id={self.server_id} tag={self.tag!r}>"
