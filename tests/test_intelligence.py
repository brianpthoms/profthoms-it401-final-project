import json
from datetime import date, timedelta

import pytest
import requests

from app import create_app
from models import db
from models.forecast_intelligence import ForecastIntelligence
from services.ai_service import AiService, AiServiceError
from services.intelligence_validator import (
    IntelligenceValidationError,
    validate_intelligence_output,
)
from services.marine_weather_service import MarineWeatherService
from services.wikipedia_service import WikipediaService


@pytest.fixture
def intelligence_client(monkeypatch):
    monkeypatch.setattr(
        "routes.main.forecast_date_window",
        lambda: (date.today(), date.today() + timedelta(days=15)),
    )
    app = create_app(
        "development",
        {
            "TESTING": True,
            "DATABASE_ENABLED": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "SQLALCHEMY_ENGINE_OPTIONS": {},
            "AI_SERVICE_API_KEY": "test-ai-key",
            "AI_SERVICE_MODEL": "test-model",
        },
    )
    with app.app_context():
        db.create_all()
        with app.test_client() as client:
            yield client
        db.session.remove()
        db.drop_all()


def _forecast(*args, **kwargs):
    return {
        "location": {
            "city": "Newport Beach",
            "state_prov": "California",
            "country_name": "United States",
            "latitude": "33.5931",
            "longitude": "-117.8817",
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


def _wikipedia(*args, **kwargs):
    return {
        "title": "The Wedge (surfing)",
        "summary": "The Wedge is a surf break in Newport Beach, California.",
        "url": "https://en.wikipedia.org/wiki/The_Wedge_(surfing)",
        "page_id": 123,
        "revision_id": 456,
        "revision_timestamp": "2026-08-01T12:00:00Z",
    }


def test_validated_intelligence_is_displayed_stored_and_reused(
    intelligence_client, monkeypatch
):
    calls = []

    def fake_generate(self, system_instructions, user_prompt):
        calls.append((system_instructions, user_prompt))
        return json.dumps(
            {
                "rating": "Good",
                "summary": (
                    "The saved forecast shows a solid swell with a useful period. "
                    "Conditions look promising, although wind speed and tide are unavailable."
                ),
                "confidence": 0.82,
                "missing_info": ["wind speed and direction", "tide stage"],
            }
        )

    monkeypatch.setattr(MarineWeatherService, "get_hourly_forecast", _forecast)
    monkeypatch.setattr(WikipediaService, "get_spot_info", _wikipedia)
    monkeypatch.setattr(AiService, "generate", fake_generate)
    url = (
        f"/?lookup=coordinates&latitude=33.5931&longitude=-117.8817"
        f"&surf_break_name=The+Wedge&date={date.today().isoformat()}&time=06:00"
    )

    first = intelligence_client.get(url)
    second = intelligence_client.get(url)

    assert first.status_code == 200
    assert b"Good" in first.data
    assert b"82% confidence" in first.data
    assert b"wind speed and direction" in first.data
    assert b"View structured JSON" in first.data
    assert second.status_code == 200
    assert len(calls) == 1
    assert "saved_surf_forecast" in calls[0][1]
    assert "cached_wikipedia_summary" in calls[0][1]

    with intelligence_client.application.app_context():
        record = db.session.execute(db.select(ForecastIntelligence)).scalar_one()
        assert record.rating == "Good"
        assert float(record.confidence) == 0.82
        assert record.prompt_version == "surf-outlook-v1"
        assert record.model_name == "test-model"
        assert json.loads(record.source_records_json)["surf_forecast_id"]


def test_missing_ai_key_is_a_safe_forecast_fallback(intelligence_client, monkeypatch):
    monkeypatch.setattr(MarineWeatherService, "get_hourly_forecast", _forecast)
    monkeypatch.setattr(WikipediaService, "get_spot_info", _wikipedia)
    intelligence_client.application.config["AI_SERVICE_API_KEY"] = None

    response = intelligence_client.get(
        f"/?latitude=33.5931&longitude=-117.8817&date={date.today().isoformat()}"
    )

    assert response.status_code == 200
    assert b"Hourly marine outlook unavailable" in response.data
    assert b"AI_SERVICE_API_KEY is not configured" in response.data
    with intelligence_client.application.app_context():
        assert db.session.scalar(db.select(ForecastIntelligence)) is None


def test_invalid_model_output_is_not_displayed_or_stored(
    intelligence_client, monkeypatch
):
    monkeypatch.setattr(MarineWeatherService, "get_hourly_forecast", _forecast)
    monkeypatch.setattr(WikipediaService, "get_spot_info", _wikipedia)
    monkeypatch.setattr(
        AiService,
        "generate",
        lambda *args: '{"rating":"Amazing","summary":"Trust me.","confidence":2}',
    )

    response = intelligence_client.get(
        f"/?latitude=33.5931&longitude=-117.8817&date={date.today().isoformat()}"
    )

    assert response.status_code == 200
    assert b"AI outlook unavailable" in response.data
    assert b"unexpected fields" in response.data
    assert b"Amazing" not in response.data
    with intelligence_client.application.app_context():
        assert db.session.scalar(db.select(ForecastIntelligence)) is None


def test_validator_accepts_only_the_documented_schema():
    valid = validate_intelligence_output(
        {
            "rating": "Fair",
            "summary": "The swell is moderate for this hour. Wind speed and tide are not included.",
            "confidence": 0.61,
            "missing_info": ["tide stage"],
        }
    )
    assert valid["rating"] == "Fair"

    with pytest.raises(IntelligenceValidationError, match="invalid rating"):
        validate_intelligence_output({**valid, "rating": "Amazing"})
    with pytest.raises(IntelligenceValidationError, match="unexpected fields"):
        validate_intelligence_output({**valid, "extra": "not allowed"})
    with pytest.raises(IntelligenceValidationError, match="2–3 sentences"):
        validate_intelligence_output({**valid, "summary": "Only one sentence here."})


def test_ai_service_maps_timeout_and_rate_limit(monkeypatch):
    def timeout(*args, **kwargs):
        raise requests.Timeout

    monkeypatch.setattr("services.ai_service.requests.post", timeout)
    with pytest.raises(AiServiceError, match="timed out"):
        AiService("key").generate("system", "user")

    class RateLimitedResponse:
        status_code = 429

    monkeypatch.setattr(
        "services.ai_service.requests.post", lambda *args, **kwargs: RateLimitedResponse()
    )
    with pytest.raises(AiServiceError, match="rate limited"):
        AiService("key").generate("system", "user")


def test_ai_service_distinguishes_exhausted_quota(monkeypatch):
    class ExhaustedResponse:
        status_code = 429

        def json(self):
            return {"error": {"code": "credit_balance_exhausted"}}

    monkeypatch.setattr(
        "services.ai_service.requests.post", lambda *args, **kwargs: ExhaustedResponse()
    )

    with pytest.raises(AiServiceError, match="no credits remaining"):
        AiService("key").generate("system", "user")


def test_ai_service_retries_transient_server_errors(monkeypatch):
    calls = []

    class Response:
        def __init__(self, status_code):
            self.status_code = status_code

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": '{"rating":"Fair"}'}}]}

    responses = iter((Response(503), Response(502), Response(200)))

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))
        return next(responses)

    monkeypatch.setattr("services.ai_service.requests.post", fake_post)

    result = AiService("key", max_retries=2, retry_backoff=0).generate(
        "system", "user"
    )

    assert result == '{"rating":"Fair"}'
    assert len(calls) == 3


def test_ai_service_reports_exhausted_transient_retries(monkeypatch):
    class UnavailableResponse:
        status_code = 503

    monkeypatch.setattr(
        "services.ai_service.requests.post",
        lambda *args, **kwargs: UnavailableResponse(),
    )

    with pytest.raises(AiServiceError, match=r"after retries \(HTTP 503\)"):
        AiService("key", max_retries=2, retry_backoff=0).generate("system", "user")


def test_ai_service_supports_gemini_openai_compatible_endpoint(monkeypatch):
    captured = {}

    class SuccessfulResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {"message": {"content": '{"rating":"Fair"}'}}
                ]
            }

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return SuccessfulResponse()

    monkeypatch.setattr("services.ai_service.requests.post", fake_post)
    service = AiService(
        api_key="gemini-test-key",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        model="gemini-3.8-flash",
    )

    result = service.generate("system instructions", "forecast input")

    assert captured["url"] == (
        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    )
    assert captured["headers"]["Authorization"] == "Bearer gemini-test-key"
    assert captured["json"]["model"] == "gemini-3.8-flash"
    assert captured["json"]["response_format"] == {"type": "json_object"}
    assert result == '{"rating":"Fair"}'
