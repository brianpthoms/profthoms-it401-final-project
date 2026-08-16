from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from models import db
from models.wikipedia_spot_info import WikipediaSpotInfo, utc_now


def _parse_timestamp(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
            timezone.utc
        ).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def _present_wikipedia_info(record):
    return {
        "title": record.title,
        "summary": record.summary,
        "url": record.url,
        "page_id": record.page_id,
        "revision_id": record.revision_id,
        "revision_timestamp": (
            record.revision_timestamp.isoformat() if record.revision_timestamp else None
        ),
        "license_name": record.license_name,
        "license_url": record.license_url,
    }


def get_wikipedia_info(beach_id):
    record = db.session.scalar(
        select(WikipediaSpotInfo).where(WikipediaSpotInfo.beach_id == beach_id)
    )
    return _present_wikipedia_info(record) if record is not None else None


def get_cached_wikipedia_info(beach_id, max_age_days=30):
    record = db.session.scalar(
        select(WikipediaSpotInfo).where(WikipediaSpotInfo.beach_id == beach_id)
    )
    cutoff = utc_now() - timedelta(days=max_age_days)
    if record is None or record.retrieved_at < cutoff:
        return None
    return _present_wikipedia_info(record)


def save_wikipedia_info(beach_id, info):
    record = db.session.scalar(
        select(WikipediaSpotInfo).where(WikipediaSpotInfo.beach_id == beach_id)
    )
    if record is None:
        record = WikipediaSpotInfo(beach_id=beach_id)
        db.session.add(record)

    record.page_id = info.get("page_id")
    record.revision_id = info.get("revision_id")
    record.revision_timestamp = _parse_timestamp(info.get("revision_timestamp"))
    record.title = info["title"]
    record.summary = info["summary"]
    record.url = info["url"]
    record.license_name = "CC BY-SA 4.0"
    record.license_url = "https://creativecommons.org/licenses/by-sa/4.0/"
    record.retrieved_at = utc_now()
    db.session.commit()
    return record
