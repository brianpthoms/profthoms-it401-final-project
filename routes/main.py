from datetime import date, datetime, timedelta

from flask import render_template, request
from flask_login import current_user
from sqlalchemy.exc import SQLAlchemyError

from models import db
from services.forecast_repository import save_forecast
from services.marine_weather_service import MarineWeatherError, MarineWeatherService
from services.request_history_repository import track_forecast_request
from services.wikipedia_service import WikipediaService
from services.wikipedia_repository import (
    get_cached_wikipedia_info,
    save_wikipedia_info,
)


def parse_coordinate(raw_value, label, minimum, maximum):
    try:
        value = float(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Enter a valid {label.lower()}.") from exc

    if not minimum <= value <= maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}.")
    return value


def compass_direction(degrees):
    if degrees is None:
        return "Not available"
    directions = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
    return f"{directions[round(float(degrees) / 45) % 8]} · {float(degrees):.0f}°"


def display_value(value, suffix=""):
    return "Not available" if value is None else f"{value:g}{suffix}"


def display_height_feet(meters):
    return "Not available" if meters is None else f"{float(meters) * 3.28084:.1f} ft"


def present_forecast(raw_forecast):
    location = raw_forecast["location"]
    conditions = raw_forecast["conditions"]
    wave_height = conditions.get("wave_height_max")
    place_parts = [
        location.get("city"),
        location.get("state_prov"),
        location.get("country_name"),
    ]
    place_name = ", ".join(part for part in place_parts if part) or "Open water"

    return {
        "place_name": place_name,
        "latitude": location.get("latitude"),
        "longitude": location.get("longitude"),
        "wave_height": display_height_feet(wave_height),
        "wave_direction": compass_direction(conditions.get("wave_direction_dominant")),
        "wave_period": display_value(conditions.get("wave_period_max"), " sec"),
        "swell": (
            f"{display_height_feet(conditions.get('swell_wave_height_max'))} · "
            f"{compass_direction(conditions.get('swell_wave_direction_dominant'))}"
        ),
        "swell_period": display_value(conditions.get("swell_wave_period_max"), " sec"),
        "wind_wave": display_height_feet(conditions.get("wind_wave_height_max")),
    }


def register_routes(app):
    wikipedia_service = WikipediaService(
        base_url=app.config["WIKIPEDIA_BASE_URL"],
        user_agent=app.config["WIKIPEDIA_USER_AGENT"],
    )

    @app.route("/")
    def index():
        requested_date = request.args.get("date", date.today().isoformat())
        requested_time = request.args.get("time", f"{datetime.now().hour:02d}:00")
        max_date = date.today() + timedelta(days=16)
        error = None
        forecast = None
        wikipedia_info = None

        try:
            forecast_date = datetime.strptime(requested_date, "%Y-%m-%d").date()
        except ValueError:
            forecast_date = date.today()
            error = "Enter a valid forecast date."

        try:
            forecast_time = datetime.strptime(requested_time, "%H:%M").time()
            if forecast_time.minute != 0:
                raise ValueError
        except ValueError:
            forecast_time = datetime.now().replace(minute=0).time()
            error = error or "Choose a forecast time on the hour."

        latitude_input = request.args.get("latitude", "33.6595")
        longitude_input = request.args.get("longitude", "-117.9988")
        location_input = request.args.get("location", "")
        selected_city = request.args.get("selected_city", "").strip()
        surf_break_name = request.args.get("surf_break_name", "").strip()
        lookup_mode = request.args.get("lookup", "coordinates")
        if lookup_mode not in ("coordinates", "location"):
            lookup_mode = "coordinates"

        if error is None and (
            "lookup" in request.args
            or "latitude" in request.args
            or "longitude" in request.args
        ):
            try:
                if not date.today() <= forecast_date <= max_date:
                    raise ValueError(
                        "Choose a forecast date from today through the next 16 days."
                    )

                service = MarineWeatherService(
                    api_key=app.config.get("APIFREAKS_API_KEY"),
                    base_url=app.config["APIFREAKS_BASE_URL"],
                )

                if lookup_mode == "location":
                    location = location_input.strip()
                    if not location:
                        raise ValueError("Enter a city or place name.")
                    if len(location) > 150:
                        raise ValueError("City or place name must be 150 characters or fewer.")
                    raw_forecast = service.get_hourly_forecast_by_location(
                        location, forecast_date, forecast_time.hour
                    )
                else:
                    latitude = parse_coordinate(latitude_input, "Latitude", -90, 90)
                    longitude = parse_coordinate(longitude_input, "Longitude", -180, 180)
                    if len(surf_break_name) > 150:
                        raise ValueError("Surf break name must be 150 characters or fewer.")
                    raw_forecast = service.get_hourly_forecast(
                        latitude, longitude, forecast_date, forecast_time.hour
                    )

                forecast = present_forecast(raw_forecast)
                if lookup_mode == "coordinates" and selected_city:
                    if len(selected_city) > 150:
                        raise ValueError("Location name must be 150 characters or fewer.")
                    forecast["place_name"] = selected_city
                if lookup_mode == "coordinates" and surf_break_name:
                    forecast["area_name"] = forecast["place_name"]
                    forecast["place_name"] = surf_break_name
                    forecast["surf_break"] = True

                location_data = raw_forecast.get("location", {})
                beach_name = (
                    surf_break_name
                    or location_data.get("city")
                    or selected_city
                    or location_input.strip()
                    or "Unnamed beach"
                )
                saved_forecast = None
                if app.config["DATABASE_ENABLED"]:
                    try:
                        saved_forecast = save_forecast(
                            raw_forecast,
                            forecast_date,
                            forecast_time.hour,
                            beach_name=beach_name,
                            fallback_latitude=(
                                latitude_input if lookup_mode == "coordinates" else None
                            ),
                            fallback_longitude=(
                                longitude_input if lookup_mode == "coordinates" else None
                            ),
                            update_beach_name=bool(surf_break_name),
                        )
                    except (SQLAlchemyError, ValueError):
                        db.session.rollback()
                        app.logger.warning(
                            "Forecast rendered but could not be persisted.", exc_info=True
                        )

                if saved_forecast is not None and current_user.is_authenticated:
                    try:
                        track_forecast_request(
                            current_user.id,
                            saved_forecast,
                            lookup_mode=lookup_mode,
                            requested_location=(
                                location_input.strip()
                                if lookup_mode == "location"
                                else selected_city
                            ),
                            surf_break_name=surf_break_name,
                        )
                    except SQLAlchemyError:
                        db.session.rollback()
                        app.logger.warning(
                            "The user's forecast request could not be tracked.",
                            exc_info=True,
                        )

                if saved_forecast is not None:
                    try:
                        wikipedia_info = get_cached_wikipedia_info(
                            saved_forecast.beach_id,
                            max_age_days=app.config["WIKIPEDIA_CACHE_DAYS"],
                        )
                    except SQLAlchemyError:
                        db.session.rollback()
                        app.logger.warning(
                            "Stored Wikipedia information could not be read.",
                            exc_info=True,
                        )

                if wikipedia_info is None:
                    wikipedia_info = wikipedia_service.get_spot_info(
                        surf_break=surf_break_name or None,
                        city=location_data.get("city") or location_input,
                    )
                    if wikipedia_info and saved_forecast is not None:
                        try:
                            save_wikipedia_info(
                                saved_forecast.beach_id, wikipedia_info
                            )
                        except SQLAlchemyError:
                            db.session.rollback()
                            app.logger.warning(
                                "Wikipedia information could not be persisted.",
                                exc_info=True,
                            )
            except (ValueError, MarineWeatherError) as exc:
                error = str(exc)

        return render_template(
            "index.html",
            latitude=latitude_input,
            longitude=longitude_input,
            location=location_input,
            selected_city=selected_city,
            surf_break_name=surf_break_name,
            lookup_mode=lookup_mode,
            forecast=forecast,
            wikipedia_info=wikipedia_info,
            error=error,
            forecast_date=forecast_date,
            forecast_time=forecast_time,
            today=date.today().isoformat(),
            max_date=max_date.isoformat(),
        )

    @app.route("/about")
    def about():
        return render_template("about.html")
