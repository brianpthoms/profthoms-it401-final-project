import json
from datetime import date, timedelta
from pathlib import Path

import pytest
from flask import g

from app import create_app
from models import db
from models.beach import Beach
from models.surf_forecast import SurfForecast
from models.forecast_request import ForecastRequest
from models.forecast_feedback import ForecastFeedback
from models.history_search import HistorySearch, HistorySearchInteraction
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
    assert b'id="use-forecast-location"' in response.data
    assert b'action="/#forecast-report"' in response.data
    assert b'id="forecast-report"' in response.data
    assert b"map.js" in response.data

    map_script = client.get("/static/map.js")
    assert map_script.status_code == 200
    assert b"tile.openstreetmap.org" in map_script.data
    assert b"overpass-api.de" in map_script.data
    assert b"nominatim.openstreetmap.org/reverse" in map_script.data
    assert b'sport"="surfing' in map_script.data
    assert b'natural"="beach' in map_script.data
    assert b"navigator.geolocation.getCurrentPosition" in map_script.data
    assert b"L.circleMarker" in map_script.data
    assert b"Your location:" in map_script.data
    assert b"Approximately" in map_script.data


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
    assert b"Rate this forecast" in response.data
    assert b'<details class="forecast-feedback"' in response.data
    assert b'<details class="forecast-feedback" id="forecast-feedback" open' not in response.data

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
    assert b"Rating" in profile.data
    assert b"Not rated" in profile.data

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
    assert b"Submit feedback" in saved_forecast.data

    invalid_feedback = client.post(
        f"/profile/history/{history_id}/feedback",
        data={"rating": "6", "comment": "Too optimistic."},
        follow_redirects=True,
    )
    assert invalid_feedback.status_code == 200
    assert b"Choose a rating from 1 to 5" in invalid_feedback.data
    assert b'<details class="forecast-feedback" id="forecast-feedback" open' in invalid_feedback.data
    with client.application.app_context():
        assert db.session.scalar(db.select(ForecastFeedback)) is None

    saved_feedback = client.post(
        f"/profile/history/{history_id}/feedback",
        data={"rating": "4", "comment": "Wave height was close."},
        follow_redirects=True,
    )
    assert saved_feedback.status_code == 200
    assert b"your forecast feedback was saved" in saved_feedback.data
    assert b"Wave height was close." in saved_feedback.data
    assert b"Update feedback" in saved_feedback.data
    assert b'value="4" checked' in saved_feedback.data

    updated_feedback = client.post(
        f"/profile/history/{history_id}/feedback",
        data={"rating": "2", "comment": "Conditions changed quickly."},
        follow_redirects=True,
    )
    assert updated_feedback.status_code == 200
    with client.application.app_context():
        feedback = db.session.execute(db.select(ForecastFeedback)).scalar_one()
        assert feedback.forecast_request_id == history_id
        assert feedback.rating == 2
        assert feedback.comment == "Conditions changed quickly."

    rated_profile = client.get("/profile")
    assert rated_profile.status_code == 200
    assert b"2/5" in rated_profile.data
    assert b"Not rated" not in rated_profile.data

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
        assert (
            other_client.post(
                f"/profile/history/{history_id}/feedback",
                data={"rating": "5", "comment": "Not mine."},
            ).status_code
            == 404
        )


def test_profile_history_supports_combined_search_filters(client, monkeypatch):
    locations = {
        33.59: "Newport Beach",
        34.03: "Malibu",
        32.72: "San Diego",
    }

    def fake_forecast(self, latitude, longitude, forecast_date, forecast_hour):
        return {
            "location": {
                "city": locations[round(latitude, 2)],
                "latitude": str(latitude),
                "longitude": str(longitude),
            },
            "conditions": {"wave_height_max": 1.2},
        }

    monkeypatch.setattr(MarineWeatherService, "get_hourly_forecast", fake_forecast)
    with client.application.app_context():
        user = User(
            google_sub="history-search-user",
            email="search@example.com",
            display_name="History Searcher",
        )
        other_user = User(
            google_sub="other-history-user",
            email="private@example.com",
            display_name="Private Surfer",
        )
        db.session.add_all((user, other_user))
        db.session.commit()
        user_id = user.id
        other_user_id = other_user.id

    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True

    today = date.today()
    requests = (
        (33.59, -117.88, "The Wedge", today, "05:00"),
        (34.03, -118.68, "Malibu Point", today + timedelta(days=1), "12:00"),
        (32.72, -117.26, "Sunset Cliffs", today + timedelta(days=2), "17:00"),
    )
    for latitude, longitude, spot, forecast_date, forecast_time in requests:
        response = client.get(
            "/",
            query_string={
                "lookup": "coordinates",
                "latitude": latitude,
                "longitude": longitude,
                "surf_break_name": spot,
                "date": forecast_date.isoformat(),
                "time": forecast_time,
            },
        )
        assert response.status_code == 200

    with client.application.app_context():
        wedge = db.session.scalar(db.select(Beach).where(Beach.name == "The Wedge"))
        morning_forecast = db.session.scalar(
            db.select(SurfForecast).where(SurfForecast.forecast_hour == 5)
        )
        private_history = ForecastRequest(
            user_id=other_user_id,
            beach_id=wedge.id,
            surf_forecast_id=morning_forecast.id,
            lookup_mode="coordinates",
            requested_location="Newport Beach",
            surf_break_name="Private Reef",
        )
        db.session.add(private_history)
        db.session.commit()

    initial_profile = client.get("/profile")
    assert b"Enter at least one search filter" not in initial_profile.data
    assert b"<strong>The Wedge</strong>" in initial_profile.data
    assert b"Distance from you" not in initial_profile.data
    assert b"Use my location" in initial_profile.data
    assert b'id="history-location-label"' in initial_profile.data
    assert b"profile.js" in initial_profile.data
    assert b"Total history" in initial_profile.data
    assert b"3</strong>\n            <small>forecasts saved" in initial_profile.data
    assert b"Search recall" not in initial_profile.data

    profile_script = client.get("/static/profile.js")
    assert profile_script.status_code == 200
    assert b"navigator.geolocation.getCurrentPosition" in profile_script.data
    assert b"nominatim.openstreetmap.org/reverse" in profile_script.data
    assert b"address.state" in profile_script.data
    assert b"address.country" in profile_script.data

    empty_search = client.get(
        "/profile",
        query_string={
            "spot": "",
            "date_from": "",
            "date_to": "",
            "time_period": "",
        },
    )
    assert b"Enter at least one search filter" in empty_search.data
    assert b"<strong>The Wedge</strong>" not in empty_search.data

    spot_results = client.get("/profile", query_string={"spot": "wEdGe"})
    assert b"<strong>The Wedge</strong>" in spot_results.data
    assert b"Malibu Point" not in spot_results.data
    assert b"Search recall" in spot_results.data
    assert b"33.3%" in spot_results.data
    assert b"1 of 3 forecasts matched" in spot_results.data

    city_results = client.get("/profile", query_string={"spot": "Newport"})
    assert b"<strong>The Wedge</strong>" in city_results.data

    morning_results = client.get(
        "/profile", query_string={"time_period": "morning"}
    )
    assert b"<strong>The Wedge</strong>" in morning_results.data
    assert b"Malibu Point" not in morning_results.data

    afternoon_results = client.get(
        "/profile", query_string={"time_period": "afternoon"}
    )
    assert b"Malibu Point" in afternoon_results.data
    assert b"<strong>The Wedge</strong>" not in afternoon_results.data
    assert b"Sunset Cliffs" not in afternoon_results.data

    evening_results = client.get(
        "/profile", query_string={"time_period": "evening"}
    )
    assert b"Sunset Cliffs" in evening_results.data
    assert b"Malibu Point" not in evening_results.data

    alphabetical_results = client.get(
        "/profile", query_string={"sort": "spot_asc"}
    )
    malibu_position = alphabetical_results.data.find(
        b"<strong>Malibu Point</strong>"
    )
    sunset_position = alphabetical_results.data.find(
        b"<strong>Sunset Cliffs</strong>"
    )
    wedge_position = alphabetical_results.data.find(b"<strong>The Wedge</strong>")
    assert 0 < malibu_position < sunset_position < wedge_position
    assert b"Enter at least one search filter" not in alphabetical_results.data

    radius_results = client.get(
        "/profile",
        query_string={
            "latitude": "33.59",
            "longitude": "-117.88",
            "radius": "10",
            "location_label": "Newport Beach, California, United States",
        },
    )
    assert radius_results.status_code == 200
    assert b"<strong>The Wedge</strong>" in radius_results.data
    assert b"Malibu Point" not in radius_results.data
    assert b"Sunset Cliffs" not in radius_results.data
    assert b"Current location: Newport Beach, California, United States" in radius_results.data
    assert b"Distance from you" in radius_results.data
    assert b"&lt; 0.1 mi" in radius_results.data

    date_results = client.get(
        "/profile",
        query_string={
            "date_from": (today + timedelta(days=1)).isoformat(),
            "date_to": (today + timedelta(days=2)).isoformat(),
        },
    )
    assert b"Malibu Point" in date_results.data
    assert b"Sunset Cliffs" in date_results.data
    assert b"<strong>The Wedge</strong>" not in date_results.data

    combined_results = client.get(
        "/profile",
        query_string={
            "spot": "Malibu",
            "date_from": (today + timedelta(days=1)).isoformat(),
            "date_to": (today + timedelta(days=1)).isoformat(),
            "time_period": "afternoon",
        },
    )
    assert b"Showing 1\xe2\x80\x931 of 1 forecast" in combined_results.data
    assert b"33.3%" in combined_results.data
    assert b"1 of 3 forecasts matched" in combined_results.data
    assert b"Malibu Point" in combined_results.data
    assert b"<strong>The Wedge</strong>" not in combined_results.data
    assert b"Sunset Cliffs" not in combined_results.data

    private_results = client.get("/profile", query_string={"spot": "Private"})
    assert b"No forecasts match those filters" in private_results.data
    assert b"Private Reef" not in private_results.data
    assert b"0.0%" in private_results.data
    assert b"0 of 3 forecasts matched" in private_results.data

    with client.application.app_context():
        combined_search = db.session.scalar(
            db.select(HistorySearch).where(HistorySearch.spot_query == "Malibu")
        )
        assert combined_search.user_id == user_id
        assert combined_search.forecast_date_from == today + timedelta(days=1)
        assert combined_search.forecast_date_to == today + timedelta(days=1)
        assert combined_search.time_period == "afternoon"
        assert combined_search.result_count == 1
        assert combined_search.used_location_radius is False

        radius_search = db.session.scalar(
            db.select(HistorySearch).where(HistorySearch.used_location_radius.is_(True))
        )
        assert float(radius_search.radius_miles) == 10
        assert not hasattr(radius_search, "latitude")
        assert not hasattr(radius_search, "longitude")
        analytics_count_before_invalid_searches = db.session.scalar(
            db.select(db.func.count()).select_from(HistorySearch)
        )

    invalid_range = client.get(
        "/profile",
        query_string={
            "date_from": (today + timedelta(days=2)).isoformat(),
            "date_to": today.isoformat(),
        },
    )
    assert b"Review the highlighted search fields" in invalid_range.data
    assert b"End date must be on or after start date" in invalid_range.data
    assert b'aria-describedby="date-to-error"' in invalid_range.data

    invalid_date = client.get("/profile", query_string={"date_from": "not-a-date"})
    assert b"Enter a valid start date" in invalid_date.data
    assert b'aria-describedby="date-from-error"' in invalid_date.data

    invalid_time = client.get(
        "/profile", query_string={"time_period": "late-night"}
    )
    assert b"Choose a listed time of day" in invalid_time.data
    assert b'aria-describedby="time-period-error"' in invalid_time.data

    oversized_spot = client.get("/profile", query_string={"spot": "a" * 151})
    assert b"Use 150 characters or fewer" in oversized_spot.data
    assert b'aria-describedby="spot-error"' in oversized_spot.data

    invalid_sort = client.get("/profile", query_string={"sort": "unsupported"})
    assert b"Choose a listed sort order" in invalid_sort.data
    assert b'aria-describedby="sort-error"' in invalid_sort.data

    missing_location = client.get("/profile", query_string={"radius": "10"})
    assert b"Choose Use my location first" in missing_location.data

    invalid_location = client.get(
        "/profile",
        query_string={"latitude": "91", "longitude": "-117.88", "radius": "10"},
    )
    assert b"Current location coordinates are invalid" in invalid_location.data

    invalid_radius = client.get(
        "/profile",
        query_string={
            "latitude": "33.59",
            "longitude": "-117.88",
            "radius": "101",
        },
    )
    assert b"Enter a radius from 1 to 100 miles" in invalid_radius.data
    assert b'aria-describedby="radius-error"' in invalid_radius.data

    with client.application.app_context():
        assert db.session.scalar(
            db.select(db.func.count()).select_from(HistorySearch)
        ) == analytics_count_before_invalid_searches

    with client.application.app_context():
        wedge_id = db.session.scalar(
            db.select(Beach.id).where(Beach.name == "The Wedge")
        )
        morning_forecast_id = db.session.scalar(
            db.select(SurfForecast.id).where(SurfForecast.forecast_hour == 5)
        )
        db.session.add_all(
            ForecastRequest(
                user_id=user_id,
                beach_id=wedge_id,
                surf_forecast_id=morning_forecast_id,
                lookup_mode="coordinates",
                requested_location="Newport Beach",
                surf_break_name="The Wedge",
            )
            for _ in range(11)
        )
        db.session.commit()

    first_page = client.get("/profile", query_string={"spot": "Wedge"})
    assert first_page.status_code == 200
    assert b"Showing 1\xe2\x80\x9310 of 12 forecasts" in first_page.data
    assert b"85.7%" in first_page.data
    assert b"12 of 14 forecasts matched" in first_page.data
    assert first_page.data.count(b"View forecast") == 10
    assert b"page=2" in first_page.data
    assert b"spot=Wedge" in first_page.data
    assert b"search_id=" in first_page.data
    assert b"#history-results" in first_page.data
    assert b'aria-current="page">1</span>' in first_page.data

    with client.application.app_context():
        wedge_search = db.session.scalar(
            db.select(HistorySearch)
            .where(HistorySearch.spot_query == "Wedge")
            .order_by(HistorySearch.id.desc())
        )
        assert wedge_search.result_count == 12
        wedge_search_id = wedge_search.id

    second_page = client.get(
        "/profile",
        query_string={
            "spot": "Wedge",
            "page": "2",
            "search_id": wedge_search_id,
        },
    )
    assert second_page.status_code == 200
    assert b"Showing 11\xe2\x80\x9312 of 12 forecasts" in second_page.data
    assert second_page.data.count(b"View forecast") == 2
    assert b"page=1" in second_page.data
    assert b"spot=Wedge" in second_page.data
    assert f"search_id={wedge_search_id}".encode() in second_page.data
    assert b"#history-results" in second_page.data
    assert b'aria-current="page">2</span>' in second_page.data

    with client.application.app_context():
        page_view = db.session.scalar(
            db.select(HistorySearchInteraction).where(
                HistorySearchInteraction.search_id == wedge_search_id,
                HistorySearchInteraction.interaction_type == "page_view",
            )
        )
        assert page_view.user_id == user_id
        assert page_view.page_number == 2
        wedge_result_id = db.session.scalar(
            db.select(ForecastRequest.id)
            .where(
                ForecastRequest.user_id == user_id,
                ForecastRequest.surf_break_name == "The Wedge",
            )
            .order_by(ForecastRequest.id.desc())
        )

    viewed_result = client.get(
        f"/profile/history/{wedge_result_id}",
        query_string={
            "search_id": wedge_search_id,
            "page": "2",
            "position": "11",
        },
    )
    assert viewed_result.status_code == 200

    with client.application.app_context():
        result_view = db.session.scalar(
            db.select(HistorySearchInteraction).where(
                HistorySearchInteraction.search_id == wedge_search_id,
                HistorySearchInteraction.interaction_type == "result_view",
            )
        )
        assert result_view.user_id == user_id
        assert result_view.forecast_request_id == wedge_result_id
        assert result_view.page_number == 2
        assert result_view.result_position == 11

    sorted_first_page = client.get(
        "/profile", query_string={"sort": "spot_asc"}
    )
    assert b"Showing 1\xe2\x80\x9310 of 14 forecasts" in sorted_first_page.data
    assert b"page=2" in sorted_first_page.data
    assert b"sort=spot_asc" in sorted_first_page.data
    assert b"#history-results" in sorted_first_page.data
    malibu_position = sorted_first_page.data.find(b"<strong>Malibu Point</strong>")
    sunset_position = sorted_first_page.data.find(b"<strong>Sunset Cliffs</strong>")
    wedge_position = sorted_first_page.data.find(b"<strong>The Wedge</strong>")
    assert 0 < malibu_position < sunset_position < wedge_position

    radius_first_page = client.get(
        "/profile",
        query_string={
            "latitude": "33.59",
            "longitude": "-117.88",
            "radius": "10",
            "location_label": "Newport Beach, California, United States",
        },
    )
    assert b"Showing 1\xe2\x80\x9310 of 12 forecasts" in radius_first_page.data
    assert radius_first_page.data.count(b"&lt; 0.1 mi") == 10
    assert b"latitude=33.59" in radius_first_page.data
    assert b"longitude=-117.88" in radius_first_page.data
    assert b"radius=10&amp;location_label=" in radius_first_page.data
    assert b"location_label=Newport+Beach" in radius_first_page.data
    assert b"#history-results" in radius_first_page.data

    invalid_page = client.get(
        "/profile", query_string={"spot": "Wedge", "page": "not-a-number"}
    )
    assert invalid_page.status_code == 200
    assert b"Showing 1\xe2\x80\x9310 of 12 forecasts" in invalid_page.data

    out_of_range = client.get(
        "/profile", query_string={"spot": "Wedge", "page": "999"}
    )
    assert out_of_range.status_code == 302
    assert "page=2" in out_of_range.location
    assert "spot=Wedge" in out_of_range.location
    assert out_of_range.location.endswith("#history-results")


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


def test_current_location_drives_wikipedia_lookup_and_beach_identity(client, monkeypatch):
    wikipedia_calls = []

    def fake_forecast(self, latitude, longitude, forecast_date, forecast_hour):
        return {
            "location": {
                "city": "Huntington Beach",
                "state_prov": "California",
                "latitude": "33.6595",
                "longitude": "-117.9988",
            },
            "conditions": {"wave_height_max": 1.5},
        }

    def fake_wikipedia(*args, **kwargs):
        wikipedia_calls.append(kwargs)
        return {
            "title": "San Diego",
            "summary": "San Diego is a coastal city in Southern California.",
            "url": "https://en.wikipedia.org/wiki/San_Diego",
            "page_id": 1,
            "revision_id": 2,
            "revision_timestamp": "2026-08-01T12:00:00Z",
        }

    monkeypatch.setattr(MarineWeatherService, "get_hourly_forecast", fake_forecast)
    monkeypatch.setattr(WikipediaService, "get_spot_info", fake_wikipedia)

    response = client.get(
        f"/?lookup=coordinates&latitude=32.7157&longitude=-117.1611"
        f"&selected_city=San+Diego%2C+California%2C+United+States"
        f"&date={date.today().isoformat()}"
    )

    assert response.status_code == 200
    assert wikipedia_calls == [
        {
            "surf_break": None,
            "city": "San Diego, California, United States",
        }
    ]
    assert b"San Diego" in response.data

    with client.application.app_context():
        beach = db.session.execute(db.select(Beach)).scalar_one()
        assert beach.name == "San Diego, California, United States"
        assert float(beach.latitude) == pytest.approx(32.7157)
        assert float(beach.longitude) == pytest.approx(-117.1611)


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
