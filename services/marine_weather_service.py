import requests


class MarineWeatherError(RuntimeError):
    """Raised when marine weather data cannot be retrieved or understood."""


class MarineWeatherService:
    """Client for the APIFreaks Marine Weather API."""

    def __init__(self, api_key, base_url="https://api.apifreaks.com/v1.0", timeout=10):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def daily_forecast(
        self, forecast_date, *, location=None, latitude=None, longitude=None
    ):
        if not self.api_key:
            raise MarineWeatherError("APIFREAKS_API_KEY is not configured")

        date_string = forecast_date.isoformat()
        params = {
            "startDate": date_string,
            "endDate": date_string,
            "precision": "daily",
        }
        if location:
            params["location"] = location
        elif latitude is not None and longitude is not None:
            params["lat"] = latitude
            params["long"] = longitude
        else:
            raise MarineWeatherError("A location or coordinates are required")

        try:
            response = requests.get(
                f"{self.base_url}/weather/marine",
                headers={"X-apiKey": self.api_key},
                params=params,
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise MarineWeatherError("The marine weather request failed") from exc

        daily = payload.get("forecast", {}).get(date_string, {}).get("daily")
        if not daily:
            raise MarineWeatherError("No daily forecast was returned for this date")

        return {
            "daily": daily,
            "location": payload.get("location", {}),
        }


def _feet(meters):
    return None if meters is None else meters * 3.28084


def _cardinal(degrees):
    if degrees is None:
        return "—"
    directions = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
    return directions[round(float(degrees) / 45) % 8]


def _height(meters):
    feet = _feet(meters)
    return "—" if feet is None else f"{feet:.1f} ft"


def _period(seconds):
    return "—" if seconds is None else f"{seconds:g} sec"


def format_daily_forecast(daily):
    """Translate APIFreaks' metric response into display-ready surf data."""
    wave_height_m = daily.get("wave_height_max")
    wave_height_ft = _feet(wave_height_m)
    wave_direction = _cardinal(daily.get("wave_direction_dominant"))
    wave_period = _period(daily.get("wave_period_max"))

    if wave_height_ft is None:
        rating = "Unavailable"
        summary = "The API returned no wave-height reading for this location and date."
    elif wave_height_ft < 2:
        rating = "Small"
        summary = f"A smaller day, with dominant waves from {wave_direction} at {wave_period}."
    elif wave_height_ft < 5:
        rating = "Moderate"
        summary = f"Moderate wave energy from {wave_direction} at {wave_period}."
    elif wave_height_ft < 8:
        rating = "Solid"
        summary = f"Solid waves from {wave_direction} at {wave_period}; check local conditions."
    else:
        rating = "Heavy"
        summary = f"Heavy surf from {wave_direction} at {wave_period}; verify local advisories."

    swell_height = _height(daily.get("swell_wave_height_max"))
    swell_direction = _cardinal(daily.get("swell_wave_direction_dominant"))
    swell_period = _period(daily.get("swell_wave_period_max"))
    wind_wave_period = _period(daily.get("wind_wave_period_max"))

    return {
        "wave_height": _height(wave_height_m),
        "rating": rating,
        "summary": summary,
        "conditions": [
            {
                "label": "Swell",
                "value": f"{swell_height} · {swell_direction} · {swell_period}",
            },
            {"label": "Wave direction", "value": wave_direction},
            {
                "label": "Wind waves",
                "value": (
                    f"{_height(daily.get('wind_wave_height_max'))} · "
                    f"{_cardinal(daily.get('wind_wave_direction_dominant'))} · "
                    f"{wind_wave_period}"
                ),
            },
        ],
    }
