import json
from decimal import Decimal

from sqlalchemy import desc, select

from models import db
from models.forecast_intelligence import ForecastIntelligence


def present_intelligence(record):
    if record is None:
        return None
    return {
        "rating": record.rating,
        "summary": record.summary,
        "confidence": float(record.confidence),
        "missing_info": record.missing_info,
        "model": record.model_name,
        "prompt_version": record.prompt_version,
        "generated_at": record.generated_at,
        "stored": True,
    }


def get_cached_intelligence(forecast_id, prompt_version, model_name, context_hash):
    record = db.session.scalar(
        select(ForecastIntelligence).where(
            ForecastIntelligence.surf_forecast_id == forecast_id,
            ForecastIntelligence.prompt_version == prompt_version,
            ForecastIntelligence.model_name == model_name,
            ForecastIntelligence.context_hash == context_hash,
        )
    )
    return present_intelligence(record)


def get_latest_intelligence(forecast_id):
    record = db.session.scalar(
        select(ForecastIntelligence)
        .where(ForecastIntelligence.surf_forecast_id == forecast_id)
        .order_by(desc(ForecastIntelligence.generated_at), desc(ForecastIntelligence.id))
        .limit(1)
    )
    return present_intelligence(record)


def save_intelligence(
    forecast,
    wikipedia_record_id,
    result,
    *,
    prompt_version,
    model_name,
    context_hash,
    source_records,
    user_request,
):
    record = ForecastIntelligence(
        surf_forecast_id=forecast.id,
        wikipedia_spot_info_id=wikipedia_record_id,
        rating=result["rating"],
        summary=result["summary"],
        confidence=Decimal(str(result["confidence"])).quantize(Decimal("0.001")),
        missing_info_json=json.dumps(result["missing_info"]),
        output_json=json.dumps(result, sort_keys=True),
        prompt_version=prompt_version,
        model_name=model_name,
        context_hash=context_hash,
        source_records_json=json.dumps(source_records, sort_keys=True),
        user_request=user_request,
    )
    db.session.add(record)
    db.session.commit()
    return present_intelligence(record)
