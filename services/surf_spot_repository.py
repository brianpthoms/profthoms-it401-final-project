import json
import re
import unicodedata
from decimal import Decimal
from pathlib import Path

from sqlalchemy import case, func, select
from sqlalchemy.orm import selectinload

from models import db
from models.surf_spot import SurfSpot, SurfSpotAlias


def normalize_spot_name(value):
    decomposed = unicodedata.normalize("NFKD", value or "")
    ascii_text = "".join(character for character in decomposed if not unicodedata.combining(character))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_text.casefold()).split())


def present_surf_spot(spot):
    return {
        "id": spot.id,
        "name": spot.canonical_name,
        "location": spot.location_label,
        "latitude": float(spot.latitude),
        "longitude": float(spot.longitude),
    }


def get_surf_spot(spot_id):
    if not spot_id:
        return None
    return db.session.scalar(
        select(SurfSpot).where(SurfSpot.id == spot_id, SurfSpot.active.is_(True))
    )


def find_exact_surf_spot(query):
    """Return a spot only when one normalized alias identifies it unambiguously."""
    normalized = normalize_spot_name(query)
    if not normalized:
        return None
    spots = db.session.scalars(
        select(SurfSpot)
        .join(SurfSpotAlias)
        .where(
            SurfSpot.active.is_(True),
            SurfSpotAlias.normalized_alias == normalized,
        )
        .order_by(SurfSpot.id)
        .limit(2)
    ).unique().all()
    return spots[0] if len(spots) == 1 else None


def search_surf_spots(query, limit=8):
    normalized = normalize_spot_name(query)
    if len(normalized) < 2:
        return []
    escaped = normalized.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    exact_first = case((SurfSpotAlias.normalized_alias == normalized, 0), else_=1)
    prefix_first = case((SurfSpotAlias.normalized_alias.like(f"{escaped}%", escape="\\"), 0), else_=1)
    spots = db.session.scalars(
        select(SurfSpot)
        .join(SurfSpotAlias)
        .where(
            SurfSpot.active.is_(True),
            SurfSpotAlias.normalized_alias.like(pattern, escape="\\"),
        )
        .options(selectinload(SurfSpot.aliases))
        .order_by(exact_first, prefix_first, func.lower(SurfSpot.canonical_name))
        .limit(limit)
    ).unique().all()
    return [present_surf_spot(spot) for spot in spots]


def seed_surf_spots(path):
    records = json.loads(Path(path).read_text(encoding="utf-8"))
    created = 0
    updated = 0
    for item in records:
        spot = db.session.scalar(select(SurfSpot).where(SurfSpot.slug == item["slug"]))
        if spot is None:
            spot = SurfSpot(slug=item["slug"])
            db.session.add(spot)
            created += 1
        else:
            updated += 1

        for field in (
            "canonical_name", "city", "state_prov", "country_name",
            "source_name", "source_url", "source_license",
        ):
            setattr(spot, field, item.get(field))
        spot.latitude = Decimal(str(item["latitude"])).quantize(Decimal("0.000001"))
        spot.longitude = Decimal(str(item["longitude"])).quantize(Decimal("0.000001"))
        spot.active = True
        db.session.flush()

        aliases = [item["canonical_name"], *item.get("aliases", [])]
        desired = {normalize_spot_name(alias): alias for alias in aliases if normalize_spot_name(alias)}
        existing = {alias.normalized_alias: alias for alias in spot.aliases}
        for normalized, alias_text in desired.items():
            alias = existing.pop(normalized, None)
            if alias is None:
                alias = SurfSpotAlias(surf_spot=spot, normalized_alias=normalized)
                db.session.add(alias)
            alias.alias = alias_text
            alias.source_name = item["source_name"]
        for obsolete in existing.values():
            db.session.delete(obsolete)

    db.session.commit()
    return created, updated
