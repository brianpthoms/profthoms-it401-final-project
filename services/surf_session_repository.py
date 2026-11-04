from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from models import db
from models.surf_session import SurfSession


def get_user_sessions(user_id):
    return db.session.scalars(
        select(SurfSession)
        .options(selectinload(SurfSession.beach))
        .where(SurfSession.user_id == user_id)
        .order_by(
            SurfSession.planned_date.desc(),
            SurfSession.planned_time.desc(),
            SurfSession.id.desc(),
        )
    ).all()


def get_owned_session(session_id, user_id):
    return db.session.scalar(
        select(SurfSession).where(
            SurfSession.id == session_id,
            SurfSession.user_id == user_id,
        )
    )


def get_session_counts(user_id):
    rows = db.session.execute(
        select(SurfSession.status, func.count(SurfSession.id))
        .where(SurfSession.user_id == user_id)
        .group_by(SurfSession.status)
    ).all()
    counts = {"planned": 0, "completed": 0, "cancelled": 0}
    counts.update(dict(rows))
    counts["total"] = sum(counts.values())
    return counts
