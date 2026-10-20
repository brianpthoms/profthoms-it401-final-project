import re

import requests


class MarineWeatherError(Exception):
    """A user-safe error raised when marine conditions cannot be retrieved."""


class MarineWeatherService:
    def __init__(self, api_key, base_url="https://api.apifreaks.com/v1.0", timeout=10):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def get_daily_forecast(self, latitude, longitude, forecast_date):
        return self._get_daily_forecast(
            {"lat": latitude, "long": longitude}, forecast_date
        )

    def get_daily_forecast_by_location(self, location, forecast_date):
        return self._get_daily_forecast({"location": location}, forecast_date)

    def get_hourly_forecast(self, latitude, longitude, forecast_date, forecast_hour):
        return self._get_hourly_forecast(
            {"lat": latitude, "long": longitude}, forecast_date, forecast_hour
        )

    def get_hourly_forecast_by_location(
        self, location, forecast_date, forecast_hour
    ):
        return self._get_hourly_forecast(
            {"location": location}, forecast_date, forecast_hour
        )

    def _get_daily_forecast(self, location_params, forecast_date):
        payload = self._request_forecast(location_params, forecast_date, "daily")
        daily = (
            payload.get("forecast", {})
            .get(forecast_date.isoformat(), {})
            .get("daily")
        )
        if not daily:
            raise MarineWeatherError(
                "No wave conditions were returned for that location and date."
            )

        return {"location": payload.get("location", {}), "conditions": daily}

    def _get_hourly_forecast(self, location_params, forecast_date, forecast_hour):
        payload = self._request_forecast(location_params, forecast_date, "hourly")
        hourly = (
            payload.get("forecast", {})
            .get(forecast_date.isoformat(), {})
            .get("hourly", [])
        )
        timestamp_prefix = f"{forecast_date.isoformat()}T{forecast_hour:02d}:"
        selected = next(
            (
                conditions
                for conditions in hourly
                if str(conditions.get("timestamp", "")).startswith(timestamp_prefix)
            ),
            None,
        )
        if not selected:
            raise MarineWeatherError(
                "No wave conditions were returned for that location and hour."
            )

        marine_fields = (
            "wave_height",
            "wave_direction",
            "wave_period",
            "swell_wave_height",
            "swell_wave_direction",
            "swell_wave_period",
            "wind_wave_height",
        )
        if all(selected.get(field) is None for field in marine_fields):
            raise MarineWeatherError(
                "No marine conditions were returned for that place. "
                "Choose a coastal city or select a surf spot from the catalog."
            )

        return {
            "location": payload.get("location", {}),
            "conditions": {
                "timestamp": selected.get("timestamp"),
                "wave_height_max": selected.get("wave_height"),
                "wave_direction_dominant": selected.get("wave_direction"),
                "wave_period_max": selected.get("wave_period"),
                "swell_wave_height_max": selected.get("swell_wave_height"),
                "swell_wave_direction_dominant": selected.get(
                    "swell_wave_direction"
                ),
                "swell_wave_period_max": selected.get("swell_wave_period"),
                "wind_wave_height_max": selected.get("wind_wave_height"),
            },
        }

    def _request_forecast(self, location_params, forecast_date, precision):
        if not self.api_key:
            raise MarineWeatherError(
                "Marine forecasts are not configured yet. Add an APIFREAKS_API_KEY to the server environment."
            )

        params = {
            **location_params,
            "startDate": forecast_date.isoformat(),
            "endDate": forecast_date.isoformat(),
            "precision": precision,
        }

        try:
            response = requests.get(
                f"{self.base_url}/weather/marine",
                headers={"Accept": "application/json", "X-apiKey": self.api_key},
                params=params,
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.Timeout as exc:
            raise MarineWeatherError(
                "The marine forecast service took too long to respond. Please try again."
            ) from exc
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code in (401, 403):
                message = "The marine forecast API key was rejected. Check the server configuration."
            elif status_code == 404:
                message = "No marine forecast was found for those coordinates."
            elif status_code == 400:
                provider_message = ""
                try:
                    provider_message = exc.response.json().get("message", "")
                except (AttributeError, TypeError, ValueError):
                    pass
                date_window = re.fullmatch(
                    r"Forecast date range must be within "
                    r"(\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})",
                    provider_message,
                )
                if date_window:
                    message = (
                        "Marine forecasts are currently available from "
                        f"{date_window.group(1)} through {date_window.group(2)}."
                    )
                else:
                    message = "The marine forecast service rejected those coordinates or date."
            else:
                message = "The marine forecast service is currently unavailable. Please try again."
            raise MarineWeatherError(message) from exc
        except (requests.RequestException, ValueError) as exc:
            raise MarineWeatherError(
                "The marine forecast service is currently unavailable. Please try again."
            ) from exc

        return payload
