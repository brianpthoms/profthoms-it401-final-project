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

    def _get_daily_forecast(self, location_params, forecast_date):
        if not self.api_key:
            raise MarineWeatherError(
                "Marine forecasts are not configured yet. Add an APIFREAKS_API_KEY to the server environment."
            )

        params = {
            **location_params,
            "startDate": forecast_date.isoformat(),
            "endDate": forecast_date.isoformat(),
            "precision": "daily",
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
                message = "The marine forecast service rejected those coordinates or date."
            else:
                message = "The marine forecast service is currently unavailable. Please try again."
            raise MarineWeatherError(message) from exc
        except (requests.RequestException, ValueError) as exc:
            raise MarineWeatherError(
                "The marine forecast service is currently unavailable. Please try again."
            ) from exc

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
