import json
from datetime import date
from pathlib import Path

import pytest

from app import create_app
from services.marine_weather_service import MarineWeatherService, format_daily_forecast
from services.openstreetmap_service import OpenStreetMapService
from services.wikipedia_service import WikipediaService


@pytest.fixture
def client():
    app = create_app("development")
    app.config["TESTING"] = True
    app.config["APIFREAKS_API_KEY"] = None
    with app.test_client() as client:
        yield client


def test_index(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Breakline" in response.data
    assert b'id="forecast-map"' in response.data
    assert b"leaflet@1.9.4" in response.data


def test_forecast_accepts_city_and_state(client):
    response = client.get(
        f"/?city=Huntington+Beach&state=California&date={date.today().isoformat()}"
    )
    assert response.status_code == 200
    assert b"Huntington Beach" in response.data
    assert b"California" in response.data
    assert b"APIFREAKS_API_KEY is not configured" in response.data


def test_forecast_renders_apifreaks_daily_response(client, monkeypatch):
    client.application.config["APIFREAKS_API_KEY"] = "test-key"
    monkeypatch.setattr(
        MarineWeatherService,
        "daily_forecast",
        lambda self, forecast_date, **location: {
            "location": {
                "city": "Huntington Beach",
                "state_prov": "California",
                "country_name": "United States",
            },
            "daily": {
                "wave_height_max": 0.68,
                "wave_direction_dominant": 231,
                "wave_period_max": 11.2,
                "wind_wave_height_max": 0.22,
                "wind_wave_direction_dominant": 260,
                "wind_wave_period_max": 2.1,
                "swell_wave_height_max": 0.44,
                "swell_wave_direction_dominant": 209,
                "swell_wave_period_max": 12.7,
            },
        },
    )

    response = client.get(
        f"/?city=Huntington+Beach&state=California&date={date.today().isoformat()}"
    )

    assert response.status_code == 200
    assert b"Live outlook" in response.data
    assert b"2.2 ft" in response.data
    assert b"1.4 ft" in response.data
    assert b"12.7 sec" in response.data


def test_forecast_accepts_latitude_and_longitude(client, monkeypatch):
    client.application.config["APIFREAKS_API_KEY"] = "test-key"
    received = {}

    def daily_forecast(self, forecast_date, **location):
        received.update(location)
        return {
            "daily": {"wave_height_max": 0.68},
            "location": {
                "city": "Huntington Beach",
                "state_prov": "California",
                "country_name": "United States",
            },
        }

    monkeypatch.setattr(MarineWeatherService, "daily_forecast", daily_forecast)

    response = client.get(
        f"/?location_type=coordinates&latitude=33.6553&longitude=-118.0034"
        f"&date={date.today().isoformat()}"
    )

    assert response.status_code == 200
    assert b"Huntington Beach" in response.data
    assert b"California, United States" in response.data
    assert received == {"latitude": 33.6553, "longitude": -118.0034}


def test_forecast_rejects_coordinates_outside_valid_ranges(client):
    response = client.get(
        f"/?location_type=coordinates&latitude=91&longitude=-181"
        f"&date={date.today().isoformat()}"
    )

    assert response.status_code == 200
    assert b"latitude from -90 to 90" in response.data


def test_forecast_resolves_surf_spot_name_with_openstreetmap(client, monkeypatch):
    client.application.config["APIFREAKS_API_KEY"] = "test-key"
    received = {}

    monkeypatch.setattr(
        OpenStreetMapService,
        "find_surf_spot",
        lambda self, spot_name: {
            "name": "County Line Beach",
            "latitude": 34.0523255,
            "longitude": -118.9615825,
            "region": "Ventura County, California, United States",
            "osm_url": "https://www.openstreetmap.org/way/264378737",
        },
    )
    monkeypatch.setattr(
        WikipediaService,
        "find_spot_summary",
        lambda self, spot_name, region: {
            "title": "County Line Beach",
            "extract": "County Line Beach is a popular California surf spot.",
            "url": "https://en.wikipedia.org/wiki/County_Line_Beach",
        },
    )

    def daily_forecast(self, forecast_date, **location):
        received.update(location)
        return {"daily": {"wave_height_max": 0.68}, "location": {}}

    monkeypatch.setattr(MarineWeatherService, "daily_forecast", daily_forecast)

    response = client.get(
        f"/?location_type=surf_spot&spot_name=County+Line"
        f"&date={date.today().isoformat()}"
    )

    assert response.status_code == 200
    assert b"County Line Beach" in response.data
    assert b"Ventura County, California, United States" in response.data
    assert b"OpenStreetMap contributors" in response.data
    assert b"About this surf spot" in response.data
    assert b"popular California surf spot" in response.data
    assert b"Read more on Wikipedia" in response.data
    assert received == {"latitude": 34.0523255, "longitude": -118.9615825}


def test_about(client):
    response = client.get("/about")
    assert response.status_code == 200
    assert b"The ocean is complex" in response.data


def test_surf_spots_data_file():
    spots_path = Path(__file__).parent.parent / "data" / "surf_spots.json"
    with spots_path.open(encoding="utf-8") as spots_file:
        spots = json.load(spots_file)

    assert spots["huntington"]["name"] == "Huntington Beach"
    assert spots["huntington"]["latitude"] == 33.6553


def test_format_daily_forecast_converts_metric_values():
    forecast = format_daily_forecast(
        {
            "wave_height_max": 1.5,
            "wave_direction_dominant": 231,
            "wave_period_max": 11.2,
            "swell_wave_height_max": 1.2,
            "swell_wave_direction_dominant": 225,
            "swell_wave_period_max": 14.0,
            "wind_wave_height_max": 0.3,
            "wind_wave_direction_dominant": 45,
            "wind_wave_period_max": 2.1,
        }
    )

    assert forecast["wave_height"] == "4.9 ft"
    assert forecast["rating"] == "Moderate"
    assert forecast["conditions"][0]["value"] == "3.9 ft · SW · 14 sec"
    assert forecast["conditions"][1]["value"] == "SW"
    assert forecast["conditions"][2]["value"] == "1.0 ft · NE · 2.1 sec"
