from datetime import date, datetime, timedelta

from flask import render_template, request

from services.marine_weather_service import MarineWeatherError, MarineWeatherService
from services.wikipedia_scraper import WikipediaScraper


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
    wikipedia_scraper = WikipediaScraper(base_url=app.config["WIKIPEDIA_BASE_URL"])

    @app.route("/")
    def index():
        requested_date = request.args.get("date", date.today().isoformat())
        max_date = date.today() + timedelta(days=16)
        error = None
        forecast = None
        wikipedia_info = None

        try:
            forecast_date = datetime.strptime(requested_date, "%Y-%m-%d").date()
        except ValueError:
            forecast_date = date.today()
            error = "Enter a valid forecast date."

        latitude_input = request.args.get("latitude", "33.6595")
        longitude_input = request.args.get("longitude", "-117.9988")
        location_input = request.args.get("location", "")
        selected_city = request.args.get("selected_city", "").strip()
        surf_break_name = request.args.get("surf_break_name", "").strip()
        lookup_mode = request.args.get("lookup", "coordinates")
        if lookup_mode not in ("coordinates", "location"):
            lookup_mode = "coordinates"

        if "lookup" in request.args or "latitude" in request.args or "longitude" in request.args:
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
                    raw_forecast = service.get_daily_forecast_by_location(
                        location, forecast_date
                    )
                else:
                    latitude = parse_coordinate(latitude_input, "Latitude", -90, 90)
                    longitude = parse_coordinate(longitude_input, "Longitude", -180, 180)
                    if len(surf_break_name) > 150:
                        raise ValueError("Surf break name must be 150 characters or fewer.")
                    raw_forecast = service.get_daily_forecast(
                        latitude, longitude, forecast_date
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

                wikipedia_info = wikipedia_scraper.get_spot_info(
                    surf_break=surf_break_name or None,
                    city=raw_forecast.get("location", {}).get("city") or location_input,
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
            today=date.today().isoformat(),
            max_date=max_date.isoformat(),
        )

    @app.route("/about")
    def about():
        return render_template("about.html")
