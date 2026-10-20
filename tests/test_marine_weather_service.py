from datetime import date

import pytest

from services.marine_weather_service import MarineWeatherError, MarineWeatherService


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(response=self)

    def json(self):
        return self.payload


def test_daily_forecast_request_contract(monkeypatch):
    requested_date = date(2026, 8, 13)
    payload = {
        "location": {"latitude": "33.65", "longitude": "-117.99"},
        "forecast": {
            requested_date.isoformat(): {
                "daily": {"wave_height_max": 1.4, "wave_period_max": 11}
            }
        },
    }
    captured = {}

    def fake_get(url, headers, params, timeout):
        captured.update(
            {"url": url, "headers": headers, "params": params, "timeout": timeout}
        )
        return FakeResponse(payload)

    monkeypatch.setattr("services.marine_weather_service.requests.get", fake_get)
    service = MarineWeatherService("secret-key", base_url="https://example.test/v1.0")

    result = service.get_daily_forecast(33.65, -117.99, requested_date)

    assert captured["url"] == "https://example.test/v1.0/weather/marine"
    assert captured["headers"]["X-apiKey"] == "secret-key"
    assert "apiKey" not in captured["params"]
    assert captured["params"] == {
        "lat": 33.65,
        "long": -117.99,
        "startDate": "2026-08-13",
        "endDate": "2026-08-13",
        "precision": "daily",
    }
    assert result["conditions"]["wave_height_max"] == 1.4


def test_missing_api_key_does_not_make_request(monkeypatch):
    def unexpected_request(*args, **kwargs):
        pytest.fail("A request should not be made without an API key")

    monkeypatch.setattr(
        "services.marine_weather_service.requests.get", unexpected_request
    )

    with pytest.raises(MarineWeatherError, match="APIFREAKS_API_KEY"):
        MarineWeatherService(None).get_daily_forecast(33.65, -117.99, date.today())


def test_location_forecast_sends_location_instead_of_coordinates(monkeypatch):
    requested_date = date(2026, 8, 13)
    payload = {
        "location": {"city": "Santa Cruz"},
        "forecast": {
            requested_date.isoformat(): {"daily": {"wave_height_max": 1.8}}
        },
    }
    captured = {}

    def fake_get(url, headers, params, timeout):
        captured.update(params)
        return FakeResponse(payload)

    monkeypatch.setattr("services.marine_weather_service.requests.get", fake_get)
    service = MarineWeatherService("secret-key")

    service.get_daily_forecast_by_location("Santa Cruz, California", requested_date)

    assert captured["location"] == "Santa Cruz, California"
    assert "lat" not in captured
    assert "long" not in captured


def test_hourly_forecast_selects_requested_hour(monkeypatch):
    requested_date = date(2026, 8, 13)
    payload = {
        "location": {"city": "Huntington Beach"},
        "forecast": {
            requested_date.isoformat(): {
                "hourly": [
                    {
                        "timestamp": "2026-08-13T06:00",
                        "wave_height": 1.4,
                        "wave_direction": 225,
                        "wave_period": 11,
                        "swell_wave_height": 1.2,
                        "swell_wave_direction": 220,
                        "swell_wave_period": 13,
                        "wind_wave_height": 0.2,
                    },
                    {"timestamp": "2026-08-13T07:00", "wave_height": 1.6},
                ]
            }
        },
    }
    captured = {}

    def fake_get(url, headers, params, timeout):
        captured.update(params)
        return FakeResponse(payload)

    monkeypatch.setattr("services.marine_weather_service.requests.get", fake_get)
    result = MarineWeatherService("secret-key").get_hourly_forecast(
        33.65, -117.99, requested_date, 6
    )

    assert captured["precision"] == "hourly"
    assert result["conditions"] == {
        "timestamp": "2026-08-13T06:00",
        "wave_height_max": 1.4,
        "wave_direction_dominant": 225,
        "wave_period_max": 11,
        "swell_wave_height_max": 1.2,
        "swell_wave_direction_dominant": 220,
        "swell_wave_period_max": 13,
        "wind_wave_height_max": 0.2,
    }


def test_hourly_forecast_reports_missing_hour(monkeypatch):
    requested_date = date(2026, 8, 13)
    monkeypatch.setattr(
        "services.marine_weather_service.requests.get",
        lambda *args, **kwargs: FakeResponse(
            {"forecast": {requested_date.isoformat(): {"hourly": []}}}
        ),
    )

    with pytest.raises(MarineWeatherError, match="location and hour"):
        MarineWeatherService("secret-key").get_hourly_forecast(
            33.65, -117.99, requested_date, 6
        )


def test_bad_request_preserves_safe_provider_date_window(monkeypatch):
    monkeypatch.setattr(
        "services.marine_weather_service.requests.get",
        lambda *args, **kwargs: FakeResponse(
            {
                "message": (
                    "Forecast date range must be within "
                    "2026-10-13 to 2026-10-28"
                )
            },
            status_code=400,
        ),
    )

    with pytest.raises(
        MarineWeatherError,
        match=(
            "Marine forecasts are currently available from "
            "2026-10-13 through 2026-10-28"
        ),
    ):
        MarineWeatherService("secret-key").get_hourly_forecast(
            33.65, -117.99, date(2026, 10, 12), 17
        )


def test_hourly_forecast_rejects_all_empty_marine_values(monkeypatch):
    requested_date = date(2026, 10, 13)
    monkeypatch.setattr(
        "services.marine_weather_service.requests.get",
        lambda *args, **kwargs: FakeResponse(
            {
                "location": {"city": "Calgary"},
                "forecast": {
                    requested_date.isoformat(): {
                        "hourly": [{"timestamp": "2026-10-13T10:00"}]
                    }
                },
            }
        ),
    )

    with pytest.raises(MarineWeatherError, match="select a surf spot"):
        MarineWeatherService("secret-key").get_hourly_forecast_by_location(
            "The Wedge, CA", requested_date, 10
        )
