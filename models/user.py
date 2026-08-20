from datetime import datetime, timezone

from flask_login import UserMixin
from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import db


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    google_sub: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    last_login_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )

    forecast_requests: Mapped[list["ForecastRequest"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    history_searches: Mapped[list["HistorySearch"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    history_search_interactions: Mapped[list["HistorySearchInteraction"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


from models.forecast_request import ForecastRequest  # noqa: E402
from models.history_search import HistorySearch, HistorySearchInteraction  # noqa: E402
