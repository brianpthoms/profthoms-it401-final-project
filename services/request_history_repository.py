from models import db
from models.forecast_request import ForecastRequest


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
