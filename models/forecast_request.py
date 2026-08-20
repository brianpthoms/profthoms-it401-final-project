from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import db
from models.user import utc_now


class ForecastRequest(db.Model):
    __tablename__ = "forecast_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    beach_id: Mapped[int | None] = mapped_column(
        ForeignKey("beaches.id", ondelete="SET NULL"), index=True
    )
    surf_forecast_id: Mapped[int | None] = mapped_column(
        ForeignKey("surf_forecasts.id", ondelete="SET NULL"), index=True
    )
    lookup_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    requested_location: Mapped[str | None] = mapped_column(String(150))
    surf_break_name: Mapped[str | None] = mapped_column(String(150))
    requested_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False, index=True
    )

    user: Mapped["User"] = relationship(back_populates="forecast_requests")
    beach: Mapped["Beach"] = relationship()
    forecast: Mapped["SurfForecast"] = relationship()
    feedback: Mapped["ForecastFeedback | None"] = relationship(
        back_populates="forecast_request",
        cascade="all, delete-orphan",
        single_parent=True,
        uselist=False,
    )


from models.beach import Beach  # noqa: E402
from models.surf_forecast import SurfForecast  # noqa: E402
from models.user import User  # noqa: E402
from models.forecast_feedback import ForecastFeedback  # noqa: E402
