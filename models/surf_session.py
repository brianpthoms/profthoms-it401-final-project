from datetime import date, datetime, time

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import db
from models.user import utc_now


class SurfSession(db.Model):
    __tablename__ = "surf_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('planned', 'completed', 'cancelled')",
            name="ck_surf_sessions_status",
        ),
        CheckConstraint(
            "rating IS NULL OR rating BETWEEN 1 AND 5",
            name="ck_surf_sessions_rating",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    beach_id: Mapped[int | None] = mapped_column(
        ForeignKey("beaches.id", ondelete="SET NULL"), index=True
    )
    source_forecast_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("forecast_requests.id", ondelete="SET NULL"),
        unique=True,
        index=True,
    )
    source_forecast_id: Mapped[int | None] = mapped_column(
        ForeignKey("surf_forecasts.id", ondelete="SET NULL"), index=True
    )
    spot_name: Mapped[str] = mapped_column(String(150), nullable=False)
    planned_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    planned_time: Mapped[time] = mapped_column(Time, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="planned", nullable=False, index=True
    )
    rating: Mapped[int | None] = mapped_column(Integer)
    journal_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="surf_sessions")
    beach: Mapped["Beach | None"] = relationship()
    source_forecast_request: Mapped["ForecastRequest | None"] = relationship(
        back_populates="surf_session"
    )
    source_forecast: Mapped["SurfForecast | None"] = relationship()


from models.beach import Beach  # noqa: E402
from models.forecast_request import ForecastRequest  # noqa: E402
from models.surf_forecast import SurfForecast  # noqa: E402
from models.user import User  # noqa: E402
