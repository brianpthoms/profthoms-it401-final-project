import json
from datetime import date
from pathlib import Path

import pytest
from flask import g

from app import create_app
from models import db
from models.beach import Beach
from models.surf_forecast import SurfForecast
from models.forecast_request import ForecastRequest
from models.user import User
from models.wikipedia_spot_info import WikipediaSpotInfo
from services.marine_weather_service import MarineWeatherService
from services.wikipedia_service import WikipediaService


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(WikipediaService, "get_spot_info", lambda *args, **kwargs: None)
    app = create_app(
        "development",
        {
            "TESTING": True,
            "DATABASE_ENABLED": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "SQLALCHEMY_ENGINE_OPTIONS": {},
        },
    )
    with app.app_context():
        db.create_all()
        with app.test_client() as client:
            yield client
        db.session.remove()
        db.drop_all()


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
    assert b'name="time"' in response.data
    assert b'name="lookup"' in response.data
    assert b'name="surf_break_name"' in response.data
    assert b'name="selected_city"' in response.data
    assert b'id="location-map"' in response.data
    assert b'action="/#forecast-report"' in response.data
    assert b'id="forecast-report"' in response.data
    assert b"map.js" in response.data

    map_script = client.get("/static/map.js")
    assert map_script.status_code == 200
    assert b"tile.openstreetmap.org" in map_script.data
    assert b"overpass-api.de" in map_script.data
    assert b"nominatim.openstreetmap.org/reverse" in map_script.data
    assert b'sport"="surfing' in map_script.data


def test_forecast_results(client, monkeypatch):
    def fake_forecast(self, latitude, longitude, forecast_date, forecast_hour):
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

    monkeypatch.setattr(MarineWeatherService, "get_hourly_forecast", fake_forecast)
    response = client.get(
        f"/?latitude=33.6595&longitude=-117.9988&date={date.today().isoformat()}&time=06:00"
    )

    assert response.status_code == 200
    assert b"Huntington Beach" in response.data
    assert b"4.9 ft" in response.data
    assert b"3.9 ft" in response.data
    assert b"1.0 ft" in response.data
    assert b"1.5 m" not in response.data

    with client.application.app_context():
        beach = db.session.execute(db.select(Beach)).scalar_one()
        saved = db.session.execute(db.select(SurfForecast)).scalar_one()
        assert beach.name == "Huntington Beach"
        assert str(beach.latitude) == "33.659500"
        assert saved.beach_id == beach.id
        assert saved.forecast_date == date.today()
        assert saved.forecast_hour == 6
        assert float(saved.wave_height_max) == 1.5


def test_repeated_forecast_updates_existing_beach_date(client, monkeypatch):
    wave_heights = iter((1.5, 2.1))

    def fake_forecast(self, latitude, longitude, forecast_date, forecast_hour):
        return {
            "location": {
                "city": "Newport Beach",
                "state_prov": "California",
                "country_name": "United States",
                "latitude": str(latitude),
                "longitude": str(longitude),
            },
            "conditions": {"wave_height_max": next(wave_heights)},
        }

    monkeypatch.setattr(MarineWeatherService, "get_hourly_forecast", fake_forecast)
    url = (
        f"/?lookup=coordinates&latitude=33.5931&longitude=-117.8817"
        f"&surf_break_name=The+Wedge&date={date.today().isoformat()}&time=06:00"
    )
    assert client.get(url).status_code == 200
    assert client.get(url).status_code == 200

    with client.application.app_context():
        beaches = db.session.execute(db.select(Beach)).scalars().all()
        forecasts = db.session.execute(db.select(SurfForecast)).scalars().all()
        assert len(beaches) == 1
        assert beaches[0].name == "The Wedge"
        assert len(forecasts) == 1
        assert float(forecasts[0].wave_height_max) == 2.1


def test_different_hours_create_distinct_forecasts(client, monkeypatch):
    def fake_forecast(self, latitude, longitude, forecast_date, forecast_hour):
        return {
            "location": {
                "city": "Newport Beach",
                "latitude": str(latitude),
                "longitude": str(longitude),
            },
            "conditions": {"wave_height_max": forecast_hour / 10},
        }

    monkeypatch.setattr(MarineWeatherService, "get_hourly_forecast", fake_forecast)
    base_url = (
        f"/?lookup=coordinates&latitude=33.5931&longitude=-117.8817"
        f"&surf_break_name=The+Wedge&date={date.today().isoformat()}"
    )
    assert client.get(f"{base_url}&time=06:00").status_code == 200
    assert client.get(f"{base_url}&time=07:00").status_code == 200

    with client.application.app_context():
        forecasts = db.session.execute(
            db.select(SurfForecast).order_by(SurfForecast.forecast_hour)
        ).scalars().all()
        assert [item.forecast_hour for item in forecasts] == [6, 7]
        assert [float(item.wave_height_max) for item in forecasts] == [0.6, 0.7]


def test_signed_in_forecast_is_added_to_profile_history(client, monkeypatch):
    def fake_forecast(self, latitude, longitude, forecast_date, forecast_hour):
        return {
            "location": {
                "city": "Newport Beach",
                "latitude": str(latitude),
                "longitude": str(longitude),
            },
            "conditions": {"wave_height_max": 1.4},
        }

    monkeypatch.setattr(MarineWeatherService, "get_hourly_forecast", fake_forecast)
    with client.application.app_context():
        user = User(
            google_sub="google-user-123",
            email="surfer@example.com",
            display_name="Sample Surfer",
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id
    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True

    response = client.get(
        f"/?lookup=coordinates&latitude=33.5931&longitude=-117.8817"
        f"&surf_break_name=The+Wedge&selected_city=Newport+Beach"
        f"&date={date.today().isoformat()}&time=06:00"
    )
    assert response.status_code == 200

    with client.application.app_context():
        history = db.session.execute(db.select(ForecastRequest)).scalar_one()
        assert history.user_id == user_id
        assert history.surf_break_name == "The Wedge"
        assert history.forecast.forecast_hour == 6
        history_id = history.id

    profile = client.get("/profile")
    assert profile.status_code == 200
    assert b"The Wedge" in profile.data
    assert b"06:00" in profile.data
    assert f'/profile/history/{history_id}'.encode() in profile.data
    assert b"View forecast" in profile.data

    def unexpected_api_call(*args, **kwargs):
        raise AssertionError("Saved forecast views must not call the forecast API.")

    monkeypatch.setattr(
        MarineWeatherService, "get_hourly_forecast", unexpected_api_call
    )
    saved_forecast = client.get(f"/profile/history/{history_id}")
    assert saved_forecast.status_code == 200
    assert b"Saved conditions" in saved_forecast.data
    assert b"The Wedge" in saved_forecast.data
    assert b"4.6 ft" in saved_forecast.data
    assert b"6:00 AM" in saved_forecast.data

    with client.application.app_context():
        other_user = User(
            google_sub="google-user-456",
            email="other@example.com",
            display_name="Other Surfer",
        )
        db.session.add(other_user)
        db.session.commit()
        other_user_id = other_user.id
    with client.application.test_client() as other_client:
        with other_client.session_transaction() as session:
            session["_user_id"] = str(other_user_id)
            session["_fresh"] = True

        g.pop("_login_user", None)
        assert other_client.get(f"/profile/history/{history_id}").status_code == 404


def test_map_forecast_uses_openstreetmap_surf_break_name(client, monkeypatch):
    captured = {}

    def fake_forecast(self, latitude, longitude, forecast_date, forecast_hour):
        captured.update(
            {"latitude": latitude, "longitude": longitude, "hour": forecast_hour}
        )
        return {
            "location": {
                "city": "Newport Beach",
                "state_prov": "California",
                "latitude": str(latitude),
                "longitude": str(longitude),
            },
            "conditions": {"wave_height_max": 1.5},
        }

    monkeypatch.setattr(MarineWeatherService, "get_hourly_forecast", fake_forecast)
    response = client.get(
        f"/?lookup=coordinates&latitude=33.5931&longitude=-117.8817"
        f"&surf_break_name=The+Wedge&date={date.today().isoformat()}&time=08:00"
    )

    assert response.status_code == 200
    assert captured == {"latitude": 33.5931, "longitude": -117.8817, "hour": 8}
    assert b"The Wedge" in response.data
    assert b"Newport Beach" in response.data


def test_map_forecast_uses_human_readable_city_and_hides_coordinates(client, monkeypatch):
    def fake_forecast(self, latitude, longitude, forecast_date, forecast_hour):
        return {
            "location": {
                "city": "",
                "latitude": str(latitude),
                "longitude": str(longitude),
            },
            "conditions": {"wave_height_max": 1.5},
        }

    monkeypatch.setattr(MarineWeatherService, "get_hourly_forecast", fake_forecast)
    response = client.get(
        f"/?lookup=coordinates&latitude=33.65&longitude=-117.99"
        f"&selected_city=Huntington+Beach%2C+California&date={date.today().isoformat()}"
    )

    assert response.status_code == 200
    assert b"Huntington Beach, California" in response.data
    assert b"33.65, -117.99" not in response.data


def test_forecast_displays_wikipedia_api_info(client, monkeypatch):
    wikipedia_calls = []

    def fake_forecast(self, latitude, longitude, forecast_date, forecast_hour):
        return {
            "location": {
                "city": "Newport Beach",
                "latitude": str(latitude),
                "longitude": str(longitude),
            },
            "conditions": {"wave_height_max": 1.5},
        }

    monkeypatch.setattr(MarineWeatherService, "get_hourly_forecast", fake_forecast)
    def fake_wikipedia(*args, **kwargs):
        wikipedia_calls.append(kwargs)
        return {
            "title": "The Wedge (surfing)",
            "summary": "The Wedge is a renowned surf break in Newport Beach.",
            "url": "https://en.wikipedia.org/wiki/The_Wedge_(surfing)",
            "page_id": 123,
            "revision_id": 456,
            "revision_timestamp": "2026-08-01T12:00:00Z",
        }

    monkeypatch.setattr(WikipediaService, "get_spot_info", fake_wikipedia)
    response = client.get(
        f"/?lookup=coordinates&latitude=33.5931&longitude=-117.8817"
        f"&surf_break_name=The+Wedge&date={date.today().isoformat()}"
    )

    assert response.status_code == 200
    assert b"Know the break" in response.data
    assert b"The Wedge (surfing)" in response.data
    assert b"CC BY-SA 4.0" in response.data

    with client.application.app_context():
        stored = db.session.execute(db.select(WikipediaSpotInfo)).scalar_one()
        assert stored.title == "The Wedge (surfing)"
        assert stored.page_id == 123
        assert stored.revision_id == 456
        assert stored.license_name == "CC BY-SA 4.0"

    cached_response = client.get(
        f"/?lookup=coordinates&latitude=33.5931&longitude=-117.8817"
        f"&surf_break_name=The+Wedge&date={date.today().isoformat()}"
    )
    assert cached_response.status_code == 200
    assert b"The Wedge (surfing)" in cached_response.data
    assert len(wikipedia_calls) == 1


def test_forecast_by_city(client, monkeypatch):
    captured = {}

    def fake_forecast(self, location, forecast_date, forecast_hour):
        captured["location"] = location
        captured["hour"] = forecast_hour
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
        MarineWeatherService, "get_hourly_forecast_by_location", fake_forecast
    )
    response = client.get(
        f"/?lookup=location&location=Santa+CruZ%2C+California"
        f"&date={date.today().isoformat()}&time=09:00"
    )

    assert response.status_code == 200
    assert captured["location"] == "Santa CruZ, California"
    assert captured["hour"] == 9
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


def test_forecast_hour_must_be_on_the_hour(client):
    response = client.get(
        f"/?latitude=33.6595&longitude=-117.9988"
        f"&date={date.today().isoformat()}&time=06:30"
    )
    assert response.status_code == 200
    assert b"Choose a forecast time on the hour" in response.data


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


def test_init_db_command(client):
    result = client.application.test_cli_runner().invoke(args=["init-db"])
    assert result.exit_code == 0
    assert "Initialized the Breakline database." in result.output


def test_upgrade_db_command_is_idempotent(client):
    result = client.application.test_cli_runner().invoke(args=["upgrade-db"])
    assert result.exit_code == 0
    assert "Upgraded the Breakline database schema." in result.output


def test_surf_spots_data_file():
    spots_path = Path(__file__).parent.parent / "data" / "surf_spots.json"
    with spots_path.open(encoding="utf-8") as spots_file:
        spots = json.load(spots_file)

    assert spots["huntington"]["name"] == "Huntington Beach"
