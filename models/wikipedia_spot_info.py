from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import db


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class WikipediaSpotInfo(db.Model):
    __tablename__ = "wikipedia_spot_info"

    id: Mapped[int] = mapped_column(primary_key=True)
    beach_id: Mapped[int] = mapped_column(
        ForeignKey("beaches.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    page_id: Mapped[int | None] = mapped_column(BigInteger)
    revision_id: Mapped[int | None] = mapped_column(BigInteger)
    revision_timestamp: Mapped[datetime | None] = mapped_column(DateTime)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    license_name: Mapped[str] = mapped_column(
        String(50), default="CC BY-SA 4.0", nullable=False
    )
    license_url: Mapped[str] = mapped_column(
        String(500),
        default="https://creativecommons.org/licenses/by-sa/4.0/",
        nullable=False,
    )
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )

    beach: Mapped["Beach"] = relationship(back_populates="wikipedia_info")


from models.beach import Beach  # noqa: E402
