from datetime import date
from unittest.mock import Mock, patch

from services.marine_weather_service import MarineWeatherService


def test_daily_forecast_sends_key_and_location_to_apifreaks():
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "location": {"city": "Huntington Beach", "state_prov": "California"},
        "forecast": {"2026-08-13": {"daily": {"wave_height_max": 1.5}}}
    }

    with patch("services.marine_weather_service.requests.get", return_value=response) as get:
        result = MarineWeatherService("secret-key").daily_forecast(
            date(2026, 8, 13), location="Huntington Beach, California"
        )

    assert result == {
        "daily": {"wave_height_max": 1.5},
        "location": {"city": "Huntington Beach", "state_prov": "California"},
    }
    get.assert_called_once_with(
        "https://api.apifreaks.com/v1.0/weather/marine",
        headers={"X-apiKey": "secret-key"},
        params={
            "location": "Huntington Beach, California",
            "startDate": "2026-08-13",
            "endDate": "2026-08-13",
            "precision": "daily",
        },
        timeout=10,
    )


def test_daily_forecast_supports_coordinates():
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "forecast": {"2026-08-13": {"daily": {"wave_height_max": 1.5}}}
    }

    with patch("services.marine_weather_service.requests.get", return_value=response) as get:
        MarineWeatherService("secret-key").daily_forecast(
            date(2026, 8, 13), latitude=33.6553, longitude=-118.0034
        )

    assert get.call_args.kwargs["params"]["lat"] == 33.6553
    assert get.call_args.kwargs["params"]["long"] == -118.0034
    assert "location" not in get.call_args.kwargs["params"]
