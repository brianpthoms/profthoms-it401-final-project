from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import db
from models.user import utc_now


class ForecastFeedback(db.Model):
    __tablename__ = "forecast_feedback"
    __table_args__ = (
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_forecast_feedback_rating"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    forecast_request_id: Mapped[int] = mapped_column(
        ForeignKey("forecast_requests.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    forecast_request: Mapped["ForecastRequest"] = relationship(
        back_populates="feedback"
    )


from models.forecast_request import ForecastRequest  # noqa: E402
