from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from cli.core.database import Base


class AppDependency(Base):
    __tablename__ = "app_dependencies"

    id: Mapped[int] = mapped_column(primary_key=True)
    app_id: Mapped[int] = mapped_column(ForeignKey("apps.id"), nullable=False)
    depends_on_app_id: Mapped[int] = mapped_column(ForeignKey("apps.id"), nullable=False)

    __table_args__ = (UniqueConstraint("app_id", "depends_on_app_id"),)

    def __repr__(self) -> str:
        return f"<AppDependency app_id={self.app_id} depends_on={self.depends_on_app_id}>"
