from datetime import date, datetime, timedelta
import math

from flask import render_template, request

from services.marine_weather_service import (
    MarineWeatherError,
    MarineWeatherService,
    format_daily_forecast,
)
from services.openstreetmap_service import OpenStreetMapError, OpenStreetMapService
from services.wikipedia_service import WikipediaError, WikipediaService


def register_routes(app):
    def empty_forecast():
        return {
            "wave_height": "—",
            "rating": "Awaiting forecast",
            "summary": "Choose a location to retrieve marine conditions.",
            "conditions": [
                {"label": "Swell", "value": "—"},
                {"label": "Wave direction", "value": "—"},
                {"label": "Wind waves", "value": "—"},
            ],
        }

    @app.route("/")
    def index():
        today_date = date.today()
        max_forecast_date = today_date + timedelta(days=15)
        location_type = request.args.get("location_type", "city")
        if location_type not in {"city", "coordinates", "surf_spot"}:
            location_type = "city"
        city = request.args.get("city", "").strip()[:100]
        state = request.args.get("state", "").strip()[:100]
        spot_name = request.args.get("spot_name", "").strip()[:100]
        latitude_text = request.args.get("latitude", "").strip()
        longitude_text = request.args.get("longitude", "").strip()
        forecast_requested = any(
            field in request.args
            for field in (
                "location_type",
                "city",
                "state",
                "spot_name",
                "latitude",
                "longitude",
            )
        )

        coordinates_are_valid = False
        latitude = longitude = None
        if latitude_text and longitude_text:
            try:
                latitude = float(latitude_text)
                longitude = float(longitude_text)
                coordinates_are_valid = (
                    math.isfinite(latitude)
                    and math.isfinite(longitude)
                    and -90 <= latitude <= 90
                    and -180 <= longitude <= 180
                )
            except ValueError:
                pass

        requested_date = request.args.get("date", today_date.isoformat())
        date_is_valid = True
        try:
            forecast_date = datetime.strptime(requested_date, "%Y-%m-%d").date()
        except ValueError:
            forecast_date = today_date
            date_is_valid = False

        if not today_date <= forecast_date <= max_forecast_date:
            date_is_valid = False

        forecast = empty_forecast()
        forecast_source = "pending"
        forecast_message = "Submit a location to generate a live APIFreaks forecast."
        location_attribution = False
        osm_url = None
        wikipedia_summary = None
        if location_type == "coordinates" and coordinates_are_valid:
            location_name = f"{latitude_text}, {longitude_text}"
            location_region = "Coordinates"
        elif city and state:
            location_name = city
            location_region = state
        elif location_type == "surf_spot" and spot_name:
            location_name = spot_name
            location_region = "Searching OpenStreetMap"
        else:
            location_name = "Choose a location"
            location_region = "Daily marine forecast"

        if forecast_requested and not date_is_valid:
            forecast_message = "Choose a date within the available 16-day forecast window."
        elif forecast_requested and location_type == "city" and (not city or not state):
            forecast_message = "Enter both a city and state."
        elif forecast_requested and location_type == "coordinates" and not coordinates_are_valid:
            forecast_message = (
                "Enter a latitude from -90 to 90 and longitude from -180 to 180."
            )
        elif forecast_requested and location_type == "surf_spot" and not spot_name:
            forecast_message = "Enter a surf spot name."
        elif forecast_requested and not app.config.get("APIFREAKS_API_KEY"):
            forecast_message = "APIFREAKS_API_KEY is not configured."
        elif forecast_requested:
            marine_weather = MarineWeatherService(
                api_key=app.config["APIFREAKS_API_KEY"],
                base_url=app.config["APIFREAKS_BASE_URL"],
            )
            try:
                if location_type == "surf_spot":
                    osm = OpenStreetMapService(
                        base_url=app.config["NOMINATIM_BASE_URL"],
                        user_agent=app.config["NOMINATIM_USER_AGENT"],
                    ).find_surf_spot(spot_name)
                    latitude = osm["latitude"]
                    longitude = osm["longitude"]
                    latitude_text = f"{latitude:.6f}"
                    longitude_text = f"{longitude:.6f}"
                    location_name = osm["name"]
                    location_region = osm["region"] or "OpenStreetMap surf spot"
                    location_attribution = True
                    osm_url = osm["osm_url"]
                    try:
                        wikipedia_summary = WikipediaService(
                            base_url=app.config["WIKIPEDIA_API_URL"]
                        ).find_spot_summary(location_name, location_region)
                    except WikipediaError:
                        # Wikipedia context is optional and must not block forecasts.
                        wikipedia_summary = None
                    result = marine_weather.daily_forecast(
                        forecast_date, latitude=latitude, longitude=longitude
                    )
                elif location_type == "coordinates":
                    result = marine_weather.daily_forecast(
                        forecast_date, latitude=latitude, longitude=longitude
                    )
                else:
                    result = marine_weather.daily_forecast(
                        forecast_date, location=f"{city}, {state}"
                    )

                forecast = format_daily_forecast(result["daily"])
                resolved_location = result.get("location", {})
                resolved_city = resolved_location.get("city") or resolved_location.get(
                    "locality"
                )
                resolved_region = resolved_location.get("state_prov")
                resolved_country = resolved_location.get("country_name")

                if resolved_city and location_type != "surf_spot":
                    location_name = resolved_city
                region_parts = []
                for part in (resolved_region, resolved_country):
                    if part and part not in region_parts and part != location_name:
                        region_parts.append(part)
                if region_parts and location_type != "surf_spot":
                    location_region = ", ".join(region_parts)

                forecast_source = "live"
                forecast_message = "Live daily marine forecast provided by APIFreaks."
            except OpenStreetMapError:
                location_region = "Surf spot not found"
                forecast_message = (
                    "No matching surf spot was found in OpenStreetMap. "
                    "Try its full beach or break name."
                )
            except MarineWeatherError:
                forecast_message = "No marine forecast is available for that location and date."

        return render_template(
            "index.html",
            location_type=location_type,
            city=city,
            state=state,
            spot_name=spot_name,
            latitude=latitude_text,
            longitude=longitude_text,
            location_name=location_name,
            location_region=location_region,
            location_attribution=location_attribution,
            osm_url=osm_url,
            wikipedia_summary=wikipedia_summary,
            forecast=forecast,
            forecast_source=forecast_source,
            forecast_message=forecast_message,
            forecast_date=forecast_date,
            today=today_date.isoformat(),
            max_forecast_date=max_forecast_date.isoformat(),
        )

    @app.route("/about")
    def about():
        return render_template("about.html")
