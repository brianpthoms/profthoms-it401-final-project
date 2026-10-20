import json


PROMPT_VERSION = "surf-outlook-v1"
USER_REQUEST = "Classify and summarize this saved hourly surf forecast."

SYSTEM_INSTRUCTIONS = """You are Breakline's surf-forecast classification component.
Use only the retrieved context supplied by the application. Do not add current weather,
local hazards, tide, wind speed, or other facts that are absent. Classify the overall
surf outlook as exactly one of: Flat, Poor, Fair, Good, Epic. Return JSON only with
exactly these keys: rating, summary, confidence, missing_info. The summary must be 2–3
plain-language sentences. confidence must be a number from 0 to 1. missing_info must
be a JSON array of short strings naming information that would materially improve the
classification; use an empty array when nothing important is missing."""


def build_user_prompt(context):
    """Keep model context explicit, minimal, and reproducible."""
    return (
        f"User request:\n{USER_REQUEST}\n\n"
        "Retrieved context (JSON):\n"
        f"{json.dumps(context, sort_keys=True, separators=(',', ':'))}\n\n"
        "Return the required JSON object and nothing else."
    )
