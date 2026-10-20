import hashlib
import json

from services.intelligence_prompts import (
    PROMPT_VERSION,
    SYSTEM_INSTRUCTIONS,
    USER_REQUEST,
    build_user_prompt,
)
from services.intelligence_validator import validate_intelligence_output


FORECAST_FIELDS = (
    "wave_height_max",
    "wave_direction_dominant",
    "wave_period_max",
    "swell_wave_height_max",
    "swell_wave_direction_dominant",
    "swell_wave_period_max",
    "wind_wave_height_max",
)


def _json_value(value):
    return float(value) if value is not None else None


def build_retrieved_context(forecast, wikipedia_info):
    """Use only the saved forecast row and its cached Wikipedia record."""
    if forecast is None or wikipedia_info is None:
        return None
    summary = wikipedia_info.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        return None

    return {
        "saved_surf_forecast": {
            "forecast_date": forecast.forecast_date.isoformat(),
            "forecast_hour": forecast.forecast_hour,
            "units": {"wave_heights": "meters", "directions": "degrees", "periods": "seconds"},
            **{field: _json_value(getattr(forecast, field)) for field in FORECAST_FIELDS},
        },
        "cached_wikipedia_summary": {
            "title": wikipedia_info.get("title"),
            "summary": summary.strip(),
        },
    }


def context_hash(context):
    canonical = json.dumps(context, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def generate_intelligence(ai_service, context):
    raw_output = ai_service.generate(
        SYSTEM_INSTRUCTIONS,
        build_user_prompt(context),
    )
    return validate_intelligence_output(raw_output)
