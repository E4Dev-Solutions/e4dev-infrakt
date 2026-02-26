from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, func
from sqlalchemy.orm import Mapped, mapped_column

from cli.core.database import Base


class GitHubIntegration(Base):
    __tablename__ = "github_integrations"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_encrypted: Mapped[str] = mapped_column(String(500), nullable=False)
    github_username: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<GitHubIntegration user={self.github_username}>"
