import json
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import db


class ForecastIntelligence(db.Model):
    """One validated AI outlook for an exact set of retrieved source records."""

    __tablename__ = "forecast_intelligence"
    __table_args__ = (
        UniqueConstraint(
            "surf_forecast_id",
            "prompt_version",
            "model_name",
            "context_hash",
            name="uq_forecast_intelligence_source_version",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    surf_forecast_id: Mapped[int] = mapped_column(
        ForeignKey("surf_forecasts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    wikipedia_spot_info_id: Mapped[int | None] = mapped_column(
        ForeignKey("wikipedia_spot_info.id", ondelete="SET NULL"), index=True
    )
    rating: Mapped[str] = mapped_column(String(10), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    missing_info_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    output_json: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    context_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_records_json: Mapped[str] = mapped_column(Text, nullable=False)
    user_request: Mapped[str] = mapped_column(String(255), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    forecast: Mapped["SurfForecast"] = relationship(back_populates="intelligence")
    wikipedia_info: Mapped["WikipediaSpotInfo | None"] = relationship()

    @property
    def missing_info(self):
        try:
            value = json.loads(self.missing_info_json)
            return value if isinstance(value, list) else []
        except (TypeError, json.JSONDecodeError):
            return []


from models.surf_forecast import SurfForecast  # noqa: E402
from models.wikipedia_spot_info import WikipediaSpotInfo  # noqa: E402
