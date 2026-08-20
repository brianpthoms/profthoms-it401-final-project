from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import db
from models.user import utc_now


class HistorySearch(db.Model):
    __tablename__ = "history_searches"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    spot_query: Mapped[str | None] = mapped_column(String(150))
    forecast_date_from: Mapped[date | None] = mapped_column(Date)
    forecast_date_to: Mapped[date | None] = mapped_column(Date)
    time_period: Mapped[str | None] = mapped_column(String(20))
    used_location_radius: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    radius_miles: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    sort_order: Mapped[str] = mapped_column(
        String(20), default="recent", nullable=False
    )
    result_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False, index=True
    )

    user: Mapped["User"] = relationship(back_populates="history_searches")
    interactions: Mapped[list["HistorySearchInteraction"]] = relationship(
        back_populates="search", cascade="all, delete-orphan"
    )


class HistorySearchInteraction(db.Model):
    __tablename__ = "history_search_interactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    search_id: Mapped[int | None] = mapped_column(
        ForeignKey("history_searches.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    forecast_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("forecast_requests.id", ondelete="SET NULL"), index=True
    )
    interaction_type: Mapped[str] = mapped_column(String(30), nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    result_position: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False, index=True
    )

    search: Mapped[HistorySearch | None] = relationship(back_populates="interactions")
    user: Mapped["User"] = relationship(back_populates="history_search_interactions")
    forecast_request: Mapped["ForecastRequest | None"] = relationship()


from models.forecast_request import ForecastRequest  # noqa: E402
from models.user import User  # noqa: E402
