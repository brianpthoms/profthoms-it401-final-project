from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import db


class Beach(db.Model):
    __tablename__ = "beaches"
    __table_args__ = (
        UniqueConstraint("latitude", "longitude", name="uq_beaches_coordinates"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    city: Mapped[str | None] = mapped_column(String(150))
    state_prov: Mapped[str | None] = mapped_column(String(150))
    country_name: Mapped[str | None] = mapped_column(String(150))
    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    forecasts: Mapped[list["SurfForecast"]] = relationship(
        back_populates="beach", cascade="all, delete-orphan"
    )
    wikipedia_info: Mapped["WikipediaSpotInfo | None"] = relationship(
        back_populates="beach", cascade="all, delete-orphan", uselist=False
    )


from models.surf_forecast import SurfForecast  # noqa: E402
from models.wikipedia_spot_info import WikipediaSpotInfo  # noqa: E402
