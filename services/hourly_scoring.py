from datetime import date, datetime
from math import acos, asin, atan, ceil, cos, degrees, floor, isfinite, radians, sin, tan


SCORING_FIELDS = (
    "wave_height_max",
    "swell_wave_height_max",
    "swell_wave_period_max",
    "wind_wave_height_max",
)
DEFAULT_DAYLIGHT_HOURS = (5, 20)


def _number(value):
    try:
        number = float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    return number if number is not None and isfinite(number) and number >= 0 else None


def _factor(name, points, reason):
    return {"name": name, "points": points, "max_points": 25, "reason": reason}


def _score_swell_size(value):
    if value is None:
        return _factor("Swell size", 0, "Swell height is missing for this hour.")
    feet = value * 3.28084
    if value < 0.3:
        points, description = 3, "very small"
    elif value < 0.6:
        points, description = 10, "small"
    elif value < 1.0:
        points, description = 18, "moderate"
    elif value <= 2.0:
        points, description = 25, "a useful, surfable range"
    elif value <= 3.0:
        points, description = 20, "powerful and less broadly approachable"
    else:
        points, description = 12, "very large and demanding"
    return _factor("Swell size", points, f"{feet:.1f} ft swell is {description}.")


def _score_swell_period(value):
    if value is None:
        return _factor("Swell period", 0, "Swell period is missing for this hour.")
    if value < 6:
        points, description = 3, "short and weak"
    elif value < 9:
        points, description = 10, "short-period"
    elif value < 12:
        points, description = 18, "moderate-period"
    elif value < 16:
        points, description = 25, "long enough to carry solid energy"
    else:
        points, description = 23, "long-period and energetic"
    return _factor("Swell period", points, f"{value:g} sec is {description}.")


def _score_cleanliness(swell_height, wind_wave_height):
    if swell_height is None or wind_wave_height is None:
        return _factor(
            "Wave cleanliness",
            0,
            "Swell or wind-wave height is missing, so chop cannot be compared.",
        )
    if swell_height <= 0:
        return _factor(
            "Wave cleanliness", 0, "No measurable swell is available to compare with chop."
        )
    ratio = wind_wave_height / swell_height
    if ratio <= 0.15:
        points, description = 25, "little wind chop versus the swell"
    elif ratio <= 0.30:
        points, description = 20, "limited wind chop versus the swell"
    elif ratio <= 0.50:
        points, description = 12, "noticeable wind chop versus the swell"
    else:
        points, description = 5, "heavy wind chop versus the swell"
    return _factor(
        "Wave cleanliness",
        points,
        f"{wind_wave_height * 3.28084:.1f} ft wind wave means {description}.",
    )


def _score_completeness(conditions):
    available = sum(
        _number(conditions.get(field)) is not None for field in SCORING_FIELDS
    )
    points = round(25 * available / len(SCORING_FIELDS))
    if available == len(SCORING_FIELDS):
        reason = "All four measurements used by this comparison are available."
    else:
        reason = f"{available} of {len(SCORING_FIELDS)} comparison measurements are available."
    return _factor("Data completeness", points, reason)


def score_hour(conditions, requested_hour=None):
    """Return a transparent 0–100 comparison score for one provider hour."""
    timestamp = conditions.get("timestamp")
    try:
        hour = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00")).hour
    except (TypeError, ValueError):
        return None

    swell_height = _number(conditions.get("swell_wave_height_max"))
    factors = [
        _score_swell_size(swell_height),
        _score_swell_period(_number(conditions.get("swell_wave_period_max"))),
        _score_cleanliness(
            swell_height, _number(conditions.get("wind_wave_height_max"))
        ),
        _score_completeness(conditions),
    ]
    return {
        "hour": hour,
        "time_label": datetime(2000, 1, 1, hour).strftime("%-I %p"),
        "score": sum(factor["points"] for factor in factors),
        "factors": factors,
        "is_requested": hour == requested_hour,
    }


def _normalize_degrees(value):
    return value % 360


def _solar_event_utc_hour(forecast_date, latitude, longitude, sunrise):
    """Approximate civil dawn/dusk using NOAA's dependency-free algorithm."""
    day = forecast_date.timetuple().tm_yday
    longitude_hour = longitude / 15
    approximate_time = day + ((6 if sunrise else 18) - longitude_hour) / 24
    mean_anomaly = (0.9856 * approximate_time) - 3.289
    true_longitude = _normalize_degrees(
        mean_anomaly
        + (1.916 * sin(radians(mean_anomaly)))
        + (0.020 * sin(radians(2 * mean_anomaly)))
        + 282.634
    )
    right_ascension = _normalize_degrees(
        degrees(atan(0.91764 * tan(radians(true_longitude))))
    )
    longitude_quadrant = floor(true_longitude / 90) * 90
    ascension_quadrant = floor(right_ascension / 90) * 90
    right_ascension = (right_ascension + longitude_quadrant - ascension_quadrant) / 15
    sin_declination = 0.39782 * sin(radians(true_longitude))
    cos_declination = cos(asin(sin_declination))
    cos_hour_angle = (
        cos(radians(96)) - sin_declination * sin(radians(latitude))
    ) / (cos_declination * cos(radians(latitude)))
    if not -1 <= cos_hour_angle <= 1:
        return None
    hour_angle = (
        360 - degrees(acos(cos_hour_angle))
        if sunrise
        else degrees(acos(cos_hour_angle))
    ) / 15
    local_mean_time = (
        hour_angle + right_ascension - (0.06571 * approximate_time) - 6.622
    )
    return (local_mean_time - longitude_hour) % 24


def daylight_hour_range(forecast_date=None, latitude=None, longitude=None):
    """Return whole clock hours inside civil twilight, with a safe fallback."""
    try:
        if not isinstance(forecast_date, date):
            raise ValueError
        latitude = float(latitude)
        longitude = float(longitude)
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError
        dawn_utc = _solar_event_utc_hour(
            forecast_date, latitude, longitude, sunrise=True
        )
        dusk_utc = _solar_event_utc_hour(
            forecast_date, latitude, longitude, sunrise=False
        )
        if dawn_utc is None or dusk_utc is None:
            raise ValueError

        # APIFreaks timestamps are local clock hours but do not consistently
        # include an offset. Longitude supplies a conservative standard-time
        # approximation; this may omit a marginal twilight hour during DST.
        estimated_utc_offset = round(longitude / 15)
        dawn = (dawn_utc + estimated_utc_offset) % 24
        dusk = (dusk_utc + estimated_utc_offset) % 24
        first_hour = ceil(dawn)
        last_hour = floor(dusk)
        if not 0 <= first_hour <= last_hour <= 23:
            raise ValueError
        return first_hour, last_hour
    except (TypeError, ValueError, ZeroDivisionError):
        return DEFAULT_DAYLIGHT_HOURS


def compare_hourly_windows(
    hourly_conditions,
    requested_hour,
    limit=3,
    forecast_date=None,
    latitude=None,
    longitude=None,
):
    """Rank valid hours and retain the requested hour plus useful alternatives."""
    scored = [
        score
        for conditions in (hourly_conditions or [])
        if (score := score_hour(conditions, requested_hour)) is not None
    ]
    if not scored:
        return None

    daylight_start, daylight_end = daylight_hour_range(
        forecast_date, latitude, longitude
    )
    requested = next((item for item in scored if item["is_requested"]), None)
    requested_is_daylight = (
        requested is not None
        and daylight_start <= requested["hour"] <= daylight_end
    )
    alternatives = sorted(
        (
            item
            for item in scored
            if not item["is_requested"]
            and daylight_start <= item["hour"] <= daylight_end
        ),
        key=lambda item: (-item["score"], item["hour"]),
    )[:limit]
    recommendable = alternatives + ([requested] if requested_is_daylight else [])
    best = (
        min(recommendable, key=lambda item: (-item["score"], item["hour"]))
        if recommendable
        else requested
    )
    for item in alternatives:
        item["is_better"] = requested is not None and (
            not requested_is_daylight or item["score"] > requested["score"]
        )

    return {
        "requested": requested,
        "alternatives": alternatives,
        "best_hour": best["hour"] if best else None,
        "best_time_label": best["time_label"] if best else None,
        "daylight_start_label": datetime(2000, 1, 1, daylight_start).strftime("%-I %p"),
        "daylight_end_label": datetime(2000, 1, 1, daylight_end).strftime("%-I %p"),
        "requested_is_daylight": requested_is_daylight,
        "has_better_window": (
            requested is not None
            and best is not None
            and (not requested_is_daylight or best["score"] > requested["score"])
        ),
    }
