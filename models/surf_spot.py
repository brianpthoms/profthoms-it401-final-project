from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import db


class SurfSpot(db.Model):
    __tablename__ = "surf_spots"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(150), nullable=False)
    slug: Mapped[str] = mapped_column(String(180), nullable=False, unique=True, index=True)
    city: Mapped[str] = mapped_column(String(150), nullable=False)
    state_prov: Mapped[str] = mapped_column(String(150), nullable=False)
    country_name: Mapped[str] = mapped_column(String(150), nullable=False)
    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    source_name: Mapped[str] = mapped_column(String(100), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(500))
    source_license: Mapped[str | None] = mapped_column(String(100))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    aliases: Mapped[list["SurfSpotAlias"]] = relationship(
        back_populates="surf_spot", cascade="all, delete-orphan"
    )

    @property
    def location_label(self):
        return ", ".join((self.city, self.state_prov, self.country_name))


class SurfSpotAlias(db.Model):
    __tablename__ = "surf_spot_aliases"
    __table_args__ = (
        UniqueConstraint(
            "surf_spot_id", "normalized_alias", name="uq_surf_spot_alias"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    surf_spot_id: Mapped[int] = mapped_column(
        ForeignKey("surf_spots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alias: Mapped[str] = mapped_column(String(150), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    source_name: Mapped[str] = mapped_column(String(100), nullable=False)

    surf_spot: Mapped[SurfSpot] = relationship(back_populates="aliases")
