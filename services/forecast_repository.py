from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import select

from models import db
from models.beach import Beach
from models.surf_forecast import SurfForecast


FORECAST_FIELDS = (
    "wave_height_max",
    "wave_direction_dominant",
    "wave_period_max",
    "swell_wave_height_max",
    "swell_wave_direction_dominant",
    "swell_wave_period_max",
    "wind_wave_height_max",
)


def _decimal(value, places):
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value)).quantize(Decimal(places))
    except (InvalidOperation, TypeError, ValueError):
        return None


def save_forecast(
    raw_forecast,
    forecast_date,
    forecast_hour,
    beach_name,
    fallback_latitude=None,
    fallback_longitude=None,
    update_beach_name=False,
):
    """Create or update one beach/date/hour forecast and commit it atomically."""
    location = raw_forecast.get("location", {})
    conditions = raw_forecast.get("conditions", {})
    latitude = _decimal(location.get("latitude", fallback_latitude), "0.000001")
    longitude = _decimal(location.get("longitude", fallback_longitude), "0.000001")
    if latitude is None or longitude is None:
        raise ValueError("Forecast coordinates are required for persistence.")

    beach = db.session.scalar(
        select(Beach).where(
            Beach.latitude == latitude,
            Beach.longitude == longitude,
        )
    )
    if beach is None:
        beach = Beach(
            name=beach_name or location.get("city") or "Unnamed beach",
            latitude=latitude,
            longitude=longitude,
        )
        db.session.add(beach)
    elif update_beach_name and beach_name:
        beach.name = beach_name

    for field in ("city", "state_prov", "country_name"):
        value = location.get(field)
        if value:
            setattr(beach, field, value)

    forecast = db.session.scalar(
        select(SurfForecast).where(
            SurfForecast.beach == beach,
            SurfForecast.forecast_date == forecast_date,
            SurfForecast.forecast_hour == forecast_hour,
        )
    )
    if forecast is None:
        forecast = SurfForecast(
            beach=beach,
            forecast_date=forecast_date,
            forecast_hour=forecast_hour,
        )
        db.session.add(forecast)

    for field in FORECAST_FIELDS:
        setattr(forecast, field, _decimal(conditions.get(field), "0.001"))
    forecast.source = "APIFreaks"
    forecast.retrieved_at = datetime.now(timezone.utc)

    db.session.commit()
    return forecast
