from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cli.core.database import Base


class App(Base):
    __tablename__ = "apps"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id"), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(255))
    port: Mapped[int] = mapped_column(Integer, default=3000)
    git_repo: Mapped[str | None] = mapped_column(String(500))
    branch: Mapped[str] = mapped_column(String(100), default="main")
    image: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="stopped")
    app_type: Mapped[str] = mapped_column(String(50), default="compose")
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())

    server: Mapped["Server"] = relationship(back_populates="apps")  # noqa: F821
    deployments: Mapped[list["Deployment"]] = relationship(  # noqa: F821
        back_populates="app", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("name", "server_id"),)

    def __repr__(self) -> str:
        return f"<App {self.name} on server_id={self.server_id}>"
