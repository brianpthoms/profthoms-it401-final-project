import json
import re


RATINGS = ("Flat", "Poor", "Fair", "Good", "Epic")
REQUIRED_FIELDS = {"rating", "summary", "confidence", "missing_info"}


class IntelligenceValidationError(ValueError):
    pass


def _sentence_count(text):
    return len(re.findall(r"(?:[.!?](?:\s|$))", text))


def validate_intelligence_output(raw_output):
    """Parse and strictly validate an untrusted model response."""
    if isinstance(raw_output, str):
        try:
            data = json.loads(raw_output)
        except json.JSONDecodeError as exc:
            raise IntelligenceValidationError("The AI response was not valid JSON.") from exc
    elif isinstance(raw_output, dict):
        data = raw_output
    else:
        raise IntelligenceValidationError("The AI response was not a JSON object.")

    if not isinstance(data, dict) or set(data) != REQUIRED_FIELDS:
        raise IntelligenceValidationError("The AI response had unexpected fields.")

    rating = data["rating"]
    if rating not in RATINGS:
        raise IntelligenceValidationError("The AI response used an invalid rating.")

    summary = data["summary"]
    if not isinstance(summary, str):
        raise IntelligenceValidationError("The AI summary was missing.")
    summary = " ".join(summary.split())
    if not 40 <= len(summary) <= 900 or _sentence_count(summary) not in (2, 3):
        raise IntelligenceValidationError("The AI summary must contain 2–3 sentences.")

    confidence = data["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise IntelligenceValidationError("The AI confidence was invalid.")
    confidence = float(confidence)
    if not 0 <= confidence <= 1:
        raise IntelligenceValidationError("The AI confidence was outside 0–1.")

    missing_info = data["missing_info"]
    if not isinstance(missing_info, list) or len(missing_info) > 10:
        raise IntelligenceValidationError("The AI missing-info value was invalid.")
    normalized_missing = []
    for item in missing_info:
        if not isinstance(item, str):
            raise IntelligenceValidationError("The AI missing-info entries were invalid.")
        item = " ".join(item.split())
        if not item or len(item) > 160:
            raise IntelligenceValidationError("The AI missing-info entries were invalid.")
        normalized_missing.append(item)

    return {
        "rating": rating,
        "summary": summary,
        "confidence": confidence,
        "missing_info": normalized_missing,
    }
