from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import db


class SurfForecast(db.Model):
    __tablename__ = "surf_forecasts"
    __table_args__ = (
        UniqueConstraint(
            "beach_id",
            "forecast_date",
            "forecast_hour",
            name="uq_surf_forecasts_beach_date_hour",
        ),
        CheckConstraint(
            "forecast_hour BETWEEN 0 AND 23", name="ck_surf_forecasts_hour"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    beach_id: Mapped[int] = mapped_column(
        ForeignKey("beaches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    forecast_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    forecast_hour: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    wave_height_max: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    wave_direction_dominant: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    wave_period_max: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    swell_wave_height_max: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    swell_wave_direction_dominant: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 2)
    )
    swell_wave_period_max: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    wind_wave_height_max: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    source: Mapped[str] = mapped_column(
        String(50), default="APIFreaks", nullable=False
    )
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    beach: Mapped["Beach"] = relationship(back_populates="forecasts")
    intelligence: Mapped[list["ForecastIntelligence"]] = relationship(
        back_populates="forecast", cascade="all, delete-orphan"
    )


from models.beach import Beach  # noqa: E402
from models.forecast_intelligence import ForecastIntelligence  # noqa: E402
