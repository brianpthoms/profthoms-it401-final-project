import json
from datetime import date
from pathlib import Path

import pytest

from app import create_app
from services.marine_weather_service import MarineWeatherService
from services.wikipedia_scraper import WikipediaScraper


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(WikipediaScraper, "get_spot_info", lambda *args, **kwargs: None)
    app = create_app("development")
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_index(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Breakline" in response.data


def test_forecast_form(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b'name="latitude"' in response.data
    assert b'name="longitude"' in response.data
    assert b'name="location"' in response.data
    assert b'name="lookup"' in response.data
    assert b'name="surf_break_name"' in response.data
    assert b'name="selected_city"' in response.data
    assert b'id="location-map"' in response.data
    assert b"map.js" in response.data

    map_script = client.get("/static/map.js")
    assert map_script.status_code == 200
    assert b"tile.openstreetmap.org" in map_script.data
    assert b"overpass-api.de" in map_script.data
    assert b"nominatim.openstreetmap.org/reverse" in map_script.data
    assert b'sport"="surfing' in map_script.data


def test_forecast_results(client, monkeypatch):
    def fake_forecast(self, latitude, longitude, forecast_date):
        return {
            "location": {
                "city": "Huntington Beach",
                "state_prov": "California",
                "country_name": "United States",
                "latitude": "33.65950",
                "longitude": "-117.99880",
            },
            "conditions": {
                "wave_height_max": 1.5,
                "wave_direction_dominant": 225,
                "wave_period_max": 12,
                "swell_wave_height_max": 1.2,
                "swell_wave_direction_dominant": 220,
                "swell_wave_period_max": 14,
                "wind_wave_height_max": 0.3,
            },
        }

    monkeypatch.setattr(MarineWeatherService, "get_daily_forecast", fake_forecast)
    response = client.get(
        f"/?latitude=33.6595&longitude=-117.9988&date={date.today().isoformat()}"
    )

    assert response.status_code == 200
    assert b"Huntington Beach" in response.data
    assert b"4.9 ft" in response.data
    assert b"3.9 ft" in response.data
    assert b"1.0 ft" in response.data
    assert b"1.5 m" not in response.data


def test_map_forecast_uses_openstreetmap_surf_break_name(client, monkeypatch):
    captured = {}

    def fake_forecast(self, latitude, longitude, forecast_date):
        captured.update({"latitude": latitude, "longitude": longitude})
        return {
            "location": {
                "city": "Newport Beach",
                "state_prov": "California",
                "latitude": str(latitude),
                "longitude": str(longitude),
            },
            "conditions": {"wave_height_max": 1.5},
        }

    monkeypatch.setattr(MarineWeatherService, "get_daily_forecast", fake_forecast)
    response = client.get(
        f"/?lookup=coordinates&latitude=33.5931&longitude=-117.8817"
        f"&surf_break_name=The+Wedge&date={date.today().isoformat()}"
    )

    assert response.status_code == 200
    assert captured == {"latitude": 33.5931, "longitude": -117.8817}
    assert b"The Wedge" in response.data
    assert b"Newport Beach" in response.data


def test_map_forecast_uses_human_readable_city_and_hides_coordinates(client, monkeypatch):
    def fake_forecast(self, latitude, longitude, forecast_date):
        return {
            "location": {
                "city": "",
                "latitude": str(latitude),
                "longitude": str(longitude),
            },
            "conditions": {"wave_height_max": 1.5},
        }

    monkeypatch.setattr(MarineWeatherService, "get_daily_forecast", fake_forecast)
    response = client.get(
        f"/?lookup=coordinates&latitude=33.65&longitude=-117.99"
        f"&selected_city=Huntington+Beach%2C+California&date={date.today().isoformat()}"
    )

    assert response.status_code == 200
    assert b"Huntington Beach, California" in response.data
    assert b"33.65, -117.99" not in response.data


def test_forecast_displays_scraped_wikipedia_info(client, monkeypatch):
    def fake_forecast(self, latitude, longitude, forecast_date):
        return {
            "location": {
                "city": "Newport Beach",
                "latitude": str(latitude),
                "longitude": str(longitude),
            },
            "conditions": {"wave_height_max": 1.5},
        }

    monkeypatch.setattr(MarineWeatherService, "get_daily_forecast", fake_forecast)
    monkeypatch.setattr(
        WikipediaScraper,
        "get_spot_info",
        lambda *args, **kwargs: {
            "title": "The Wedge (surfing)",
            "summary": "The Wedge is a renowned surf break in Newport Beach.",
            "url": "https://en.wikipedia.org/wiki/The_Wedge_(surfing)",
        },
    )
    response = client.get(
        f"/?lookup=coordinates&latitude=33.5931&longitude=-117.8817"
        f"&surf_break_name=The+Wedge&date={date.today().isoformat()}"
    )

    assert response.status_code == 200
    assert b"Know the break" in response.data
    assert b"The Wedge (surfing)" in response.data
    assert b"CC BY-SA 4.0" in response.data


def test_forecast_by_city(client, monkeypatch):
    captured = {}

    def fake_forecast(self, location, forecast_date):
        captured["location"] = location
        return {
            "location": {
                "city": "Santa Cruz",
                "state_prov": "California",
                "country_name": "United States",
                "latitude": "36.97410",
                "longitude": "-122.03080",
            },
            "conditions": {"wave_height_max": 1.8},
        }

    monkeypatch.setattr(
        MarineWeatherService, "get_daily_forecast_by_location", fake_forecast
    )
    response = client.get(
        f"/?lookup=location&location=Santa+CruZ%2C+California&date={date.today().isoformat()}"
    )

    assert response.status_code == 200
    assert captured["location"] == "Santa CruZ, California"
    assert b"Santa Cruz" in response.data
    assert b"5.9 ft" in response.data


@pytest.mark.parametrize(
    ("latitude", "longitude", "message"),
    [
        ("91", "0", b"Latitude must be between -90 and 90"),
        ("0", "-181", b"Longitude must be between -180 and 180"),
        ("north", "0", b"Enter a valid latitude"),
    ],
)
def test_forecast_coordinate_validation(client, latitude, longitude, message):
    response = client.get(
        f"/?latitude={latitude}&longitude={longitude}&date={date.today().isoformat()}"
    )
    assert response.status_code == 200
    assert message in response.data


def test_missing_api_key_is_explained(client):
    client.application.config["APIFREAKS_API_KEY"] = None
    response = client.get(
        f"/?latitude=33.6595&longitude=-117.9988&date={date.today().isoformat()}"
    )
    assert response.status_code == 200
    assert b"APIFREAKS_API_KEY" in response.data


def test_about(client):
    response = client.get("/about")
    assert response.status_code == 200
    assert b"The ocean is complex" in response.data


def test_surf_spots_data_file():
    spots_path = Path(__file__).parent.parent / "data" / "surf_spots.json"
    with spots_path.open(encoding="utf-8") as spots_file:
        spots = json.load(spots_file)

    assert spots["huntington"]["name"] == "Huntington Beach"
