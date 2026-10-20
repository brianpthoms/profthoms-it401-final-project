from datetime import datetime, timedelta, timezone

from flask import jsonify, render_template, request
from flask_login import current_user
from sqlalchemy.exc import SQLAlchemyError

from models import db
from services.forecast_repository import save_forecast
from services.ai_service import AiService, AiServiceError
from services.intelligence_prompts import PROMPT_VERSION, USER_REQUEST
from services.intelligence_repository import (
    get_cached_intelligence,
    save_intelligence,
)
from services.intelligence_service import (
    build_retrieved_context,
    context_hash,
    generate_intelligence,
)
from services.intelligence_validator import IntelligenceValidationError
from services.marine_weather_service import MarineWeatherError, MarineWeatherService
from services.request_history_repository import track_forecast_request
from services.wikipedia_service import WikipediaService
from services.wikipedia_repository import (
    get_cached_wikipedia_info,
    save_wikipedia_info,
)
from services.surf_spot_repository import (
    find_exact_surf_spot,
    get_surf_spot,
    search_surf_spots,
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


def forecast_date_window(now_utc=None):
    """Return APIFreaks' UTC-based inclusive 16-day forecast window."""
    first_date = (now_utc or datetime.now(timezone.utc)).date()
    return first_date, first_date + timedelta(days=15)


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


def build_forecast_intelligence(app, saved_forecast, wikipedia_info):
    """Retrieve, generate, validate, and persist one forecast outlook."""
    if not wikipedia_info or wikipedia_info.get("id") is None:
        return None, "AI outlook needs both a saved forecast and cached beach context."
    context = build_retrieved_context(saved_forecast, wikipedia_info)
    if context is None:
        return None, "AI outlook needs both a saved forecast and cached beach context."

    model_name = app.config["AI_SERVICE_MODEL"]
    fingerprint = context_hash(context)
    cached = get_cached_intelligence(
        saved_forecast.id, PROMPT_VERSION, model_name, fingerprint
    )
    if cached is not None:
        return cached, None

    ai_service = AiService(
        api_key=app.config.get("AI_SERVICE_API_KEY"),
        base_url=app.config["AI_SERVICE_BASE_URL"],
        model=model_name,
        timeout=app.config["AI_SERVICE_TIMEOUT"],
        max_retries=app.config["AI_SERVICE_MAX_RETRIES"],
        retry_backoff=app.config["AI_SERVICE_RETRY_BACKOFF"],
    )
    result = generate_intelligence(ai_service, context)
    source_records = {
        "surf_forecast_id": saved_forecast.id,
        "wikipedia_spot_info_id": wikipedia_info.get("id"),
    }
    try:
        stored = save_intelligence(
            saved_forecast,
            wikipedia_info.get("id"),
            result,
            prompt_version=PROMPT_VERSION,
            model_name=model_name,
            context_hash=fingerprint,
            source_records=source_records,
            user_request=USER_REQUEST,
        )
        return stored, None
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.warning("AI outlook was generated but could not be saved.", exc_info=True)
        return {
            **result,
            "model": model_name,
            "prompt_version": PROMPT_VERSION,
            "stored": False,
        }, "The AI outlook was generated but could not be stored."


def register_routes(app):
    wikipedia_service = WikipediaService(
        base_url=app.config["WIKIPEDIA_BASE_URL"],
        user_agent=app.config["WIKIPEDIA_USER_AGENT"],
    )

    @app.get("/api/surf-spots")
    def surf_spot_suggestions():
        query = request.args.get("q", "").strip()
        if len(query) > 150:
            return jsonify({"spots": []}), 400
        if not app.config["DATABASE_ENABLED"] or len(query) < 2:
            return jsonify({"spots": []})
        try:
            return jsonify({"spots": search_surf_spots(query)})
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.warning("Surf-spot catalog search failed.", exc_info=True)
            return jsonify({"spots": []}), 503

    @app.route("/")
    def index():
        min_date, max_date = forecast_date_window()
        requested_date = request.args.get("date", min_date.isoformat())
        requested_time = request.args.get("time", f"{datetime.now().hour:02d}:00")
        error = None
        forecast = None
        history_item = None
        wikipedia_info = None
        forecast_intelligence = None
        intelligence_error = None

        try:
            forecast_date = datetime.strptime(requested_date, "%Y-%m-%d").date()
        except ValueError:
            forecast_date = min_date
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
        surf_spot_id_input = request.args.get("surf_spot_id", "").strip()
        selected_surf_spot = None
        lookup_mode = request.args.get("lookup", "coordinates")
        if lookup_mode not in ("coordinates", "location"):
            lookup_mode = "coordinates"

        if error is None and (
            "lookup" in request.args
            or "latitude" in request.args
            or "longitude" in request.args
        ):
            try:
                if not min_date <= forecast_date <= max_date:
                    raise ValueError(
                        f"Choose a forecast date from {min_date.isoformat()} "
                        f"through {max_date.isoformat()}."
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
                    if not surf_spot_id_input and app.config["DATABASE_ENABLED"]:
                        try:
                            selected_surf_spot = find_exact_surf_spot(location)
                        except SQLAlchemyError:
                            db.session.rollback()
                            app.logger.warning(
                                "Exact surf-spot lookup failed.", exc_info=True
                            )
                    if surf_spot_id_input:
                        try:
                            surf_spot_id = int(surf_spot_id_input)
                        except ValueError as exc:
                            raise ValueError("Choose a surf spot from the suggestions.") from exc
                        selected_surf_spot = get_surf_spot(surf_spot_id)
                        if selected_surf_spot is None:
                            raise ValueError("That surf spot is no longer available.")
                    if selected_surf_spot is not None:
                        raw_forecast = service.get_hourly_forecast(
                            float(selected_surf_spot.latitude),
                            float(selected_surf_spot.longitude),
                            forecast_date,
                            forecast_time.hour,
                        )
                        surf_break_name = selected_surf_spot.canonical_name
                        selected_city = selected_surf_spot.location_label
                    else:
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
                if selected_surf_spot is not None:
                    forecast["area_name"] = forecast["place_name"]
                    forecast["place_name"] = selected_surf_spot.canonical_name
                    forecast["surf_break"] = True
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
                    or selected_city
                    or location_data.get("city")
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
                                selected_surf_spot.latitude
                                if selected_surf_spot is not None
                                else latitude_input if lookup_mode == "coordinates" else None
                            ),
                            fallback_longitude=(
                                selected_surf_spot.longitude
                                if selected_surf_spot is not None
                                else longitude_input if lookup_mode == "coordinates" else None
                            ),
                            update_beach_name=bool(
                                surf_break_name
                                or (lookup_mode == "coordinates" and selected_city)
                            ),
                            use_fallback_coordinates=(
                                lookup_mode == "coordinates" or selected_surf_spot is not None
                            ),
                        )
                    except (SQLAlchemyError, ValueError):
                        db.session.rollback()
                        app.logger.warning(
                            "Forecast rendered but could not be persisted.", exc_info=True
                        )

                if saved_forecast is not None and current_user.is_authenticated:
                    try:
                        history_item = track_forecast_request(
                            current_user.id,
                            saved_forecast,
                            lookup_mode=lookup_mode,
                            requested_location=(
                                selected_city if selected_surf_spot is not None
                                else location_input.strip()
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
                    wikipedia_city = (
                        selected_city
                        if lookup_mode == "coordinates" and selected_city
                        else location_data.get("city") or location_input
                    )
                    wikipedia_info = wikipedia_service.get_spot_info(
                        surf_break=surf_break_name or None,
                        city=wikipedia_city,
                    )
                    if wikipedia_info and saved_forecast is not None:
                        try:
                            stored_wikipedia = save_wikipedia_info(
                                saved_forecast.beach_id, wikipedia_info
                            )
                            wikipedia_info["id"] = stored_wikipedia.id
                        except SQLAlchemyError:
                            db.session.rollback()
                            app.logger.warning(
                                "Wikipedia information could not be persisted.",
                                exc_info=True,
                            )

                if saved_forecast is not None:
                    try:
                        forecast_intelligence, intelligence_error = (
                            build_forecast_intelligence(
                                app, saved_forecast, wikipedia_info
                            )
                        )
                    except (AiServiceError, IntelligenceValidationError) as exc:
                        intelligence_error = str(exc)
                        app.logger.warning("AI outlook was unavailable: %s", exc)
                    except SQLAlchemyError:
                        db.session.rollback()
                        intelligence_error = "Stored AI outlook data could not be read."
                        app.logger.warning(
                            "AI outlook cache could not be read.", exc_info=True
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
            surf_spot_id=(selected_surf_spot.id if selected_surf_spot else surf_spot_id_input),
            lookup_mode=lookup_mode,
            forecast=forecast,
            history_item=history_item,
            wikipedia_info=wikipedia_info,
            forecast_intelligence=forecast_intelligence,
            intelligence_error=intelligence_error,
            error=error,
            forecast_date=forecast_date,
            forecast_time=forecast_time,
            today=min_date.isoformat(),
            max_date=max_date.isoformat(),
        )

    @app.route("/about")
    def about():
        return render_template("about.html")
