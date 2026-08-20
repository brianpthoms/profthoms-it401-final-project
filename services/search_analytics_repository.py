from decimal import Decimal

from sqlalchemy import select

from models import db
from models.history_search import HistorySearch, HistorySearchInteraction


def record_history_search(
    user_id,
    *,
    spot_query=None,
    date_from=None,
    date_to=None,
    time_period=None,
    radius_miles=None,
    sort_order="recent",
    result_count=0,
):
    search = HistorySearch(
        user_id=user_id,
        spot_query=spot_query or None,
        forecast_date_from=date_from,
        forecast_date_to=date_to,
        time_period=time_period or None,
        used_location_radius=radius_miles is not None,
        radius_miles=radius_miles,
        sort_order=sort_order,
        result_count=result_count,
    )
    db.session.add(search)
    db.session.commit()
    return search


def get_owned_history_search(search_id, user_id):
    if search_id is None:
        return None
    return db.session.scalar(
        select(HistorySearch).where(
            HistorySearch.id == search_id,
            HistorySearch.user_id == user_id,
        )
    )


def history_search_matches(
    search,
    *,
    spot_query=None,
    date_from=None,
    date_to=None,
    time_period=None,
    radius_miles=None,
    sort_order="recent",
):
    stored_radius = (
        Decimal(search.radius_miles) if search.radius_miles is not None else None
    )
    requested_radius = (
        Decimal(str(radius_miles)) if radius_miles is not None else None
    )
    return (
        search.spot_query == (spot_query or None)
        and search.forecast_date_from == date_from
        and search.forecast_date_to == date_to
        and search.time_period == (time_period or None)
        and stored_radius == requested_radius
        and search.sort_order == sort_order
    )


def record_history_interaction(
    user_id,
    interaction_type,
    *,
    search_id=None,
    forecast_request_id=None,
    page_number=None,
    result_position=None,
):
    interaction = HistorySearchInteraction(
        search_id=search_id,
        user_id=user_id,
        forecast_request_id=forecast_request_id,
        interaction_type=interaction_type,
        page_number=page_number,
        result_position=result_position,
    )
    db.session.add(interaction)
    db.session.commit()
    return interaction
