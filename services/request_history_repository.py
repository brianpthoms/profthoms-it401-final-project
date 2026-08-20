from math import asin, cos, radians, sin, sqrt

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import selectinload

from models import db
from models.beach import Beach
from models.forecast_request import ForecastRequest
from models.surf_forecast import SurfForecast


TIME_PERIODS = {
    "overnight": (0, 4),
    "morning": (5, 11),
    "afternoon": (12, 16),
    "evening": (17, 23),
}
EARTH_RADIUS_MILES = 3958.7613


def count_forecast_requests(user_id):
    """Return the complete forecast-history size for one user."""
    return db.session.scalar(
        select(func.count(ForecastRequest.id)).where(
            ForecastRequest.user_id == user_id
        )
    ) or 0


def _escape_like(value):
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _distance_miles(latitude, longitude):
    latitude_delta = func.radians(Beach.latitude - latitude)
    longitude_delta = func.radians(Beach.longitude - longitude)
    origin_latitude = func.radians(latitude)
    beach_latitude = func.radians(Beach.latitude)
    haversine = (
        func.pow(func.sin(latitude_delta / 2), 2)
        + func.cos(origin_latitude)
        * func.cos(beach_latitude)
        * func.pow(func.sin(longitude_delta / 2), 2)
    )
    clamped_haversine = case((haversine > 1, 1.0), else_=haversine)
    return EARTH_RADIUS_MILES * 2 * func.asin(func.sqrt(clamped_haversine))


def calculate_distance_miles(
    origin_latitude,
    origin_longitude,
    target_latitude,
    target_longitude,
):
    latitude_delta = radians(float(target_latitude) - float(origin_latitude))
    longitude_delta = radians(float(target_longitude) - float(origin_longitude))
    origin_radians = radians(float(origin_latitude))
    target_radians = radians(float(target_latitude))
    haversine = (
        sin(latitude_delta / 2) ** 2
        + cos(origin_radians)
        * cos(target_radians)
        * sin(longitude_delta / 2) ** 2
    )
    return EARTH_RADIUS_MILES * 2 * asin(sqrt(min(1, haversine)))


def search_forecast_requests(
    user_id,
    *,
    spot=None,
    date_from=None,
    date_to=None,
    time_period=None,
    latitude=None,
    longitude=None,
    radius_miles=None,
    sort_order="recent",
    page=1,
    per_page=10,
):
    statement = (
        select(ForecastRequest)
        .outerjoin(
            SurfForecast,
            ForecastRequest.surf_forecast_id == SurfForecast.id,
        )
        .outerjoin(Beach, ForecastRequest.beach_id == Beach.id)
        .options(
            selectinload(ForecastRequest.beach),
            selectinload(ForecastRequest.forecast),
            selectinload(ForecastRequest.feedback),
        )
        .where(ForecastRequest.user_id == user_id)
    )

    if spot:
        pattern = f"%{_escape_like(spot)}%"
        statement = statement.where(
            or_(
                ForecastRequest.surf_break_name.ilike(pattern, escape="\\"),
                ForecastRequest.requested_location.ilike(pattern, escape="\\"),
                Beach.name.ilike(pattern, escape="\\"),
                Beach.city.ilike(pattern, escape="\\"),
            )
        )
    if date_from:
        statement = statement.where(SurfForecast.forecast_date >= date_from)
    if date_to:
        statement = statement.where(SurfForecast.forecast_date <= date_to)
    if time_period:
        first_hour, last_hour = TIME_PERIODS[time_period]
        statement = statement.where(
            SurfForecast.forecast_hour.between(first_hour, last_hour)
        )
    if latitude is not None and longitude is not None and radius_miles is not None:
        statement = statement.where(
            _distance_miles(latitude, longitude) <= radius_miles
        )

    if sort_order == "spot_asc":
        display_name = func.coalesce(
            ForecastRequest.surf_break_name,
            Beach.name,
            ForecastRequest.requested_location,
            "",
        )
        ordering = (
            func.lower(display_name).asc(),
            ForecastRequest.requested_at.desc(),
            ForecastRequest.id.desc(),
        )
    else:
        ordering = (
            ForecastRequest.requested_at.desc(),
            ForecastRequest.id.desc(),
        )

    return db.paginate(
        statement.order_by(*ordering),
        page=page,
        per_page=per_page,
        max_per_page=per_page,
        error_out=False,
    )


def track_forecast_request(
    user_id,
    forecast,
    lookup_mode,
    requested_location=None,
    surf_break_name=None,
):
    history = ForecastRequest(
        user_id=user_id,
        beach_id=forecast.beach_id,
        surf_forecast_id=forecast.id,
        lookup_mode=lookup_mode,
        requested_location=requested_location or None,
        surf_break_name=surf_break_name or None,
    )
    db.session.add(history)
    db.session.commit()
    return history
