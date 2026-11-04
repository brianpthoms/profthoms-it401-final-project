from datetime import date

from services.hourly_scoring import (
    compare_hourly_windows,
    daylight_hour_range,
    score_hour,
)


def conditions(hour, swell, period, wind_wave, wave=1.5):
    return {
        "timestamp": f"2026-08-13T{hour:02d}:00",
        "wave_height_max": wave,
        "swell_wave_height_max": swell,
        "swell_wave_period_max": period,
        "wind_wave_height_max": wind_wave,
    }


def test_score_hour_explains_each_rule_factor():
    result = score_hour(conditions(7, 1.2, 13, 0.1), requested_hour=7)

    assert result["hour"] == 7
    assert result["time_label"] == "7 AM"
    assert result["score"] == 100
    assert result["is_requested"] is True
    assert [factor["name"] for factor in result["factors"]] == [
        "Swell size",
        "Swell period",
        "Wave cleanliness",
        "Data completeness",
    ]
    assert all(factor["reason"] for factor in result["factors"])


def test_comparison_finds_better_window_without_more_weather_data():
    hourly = [
        conditions(6, 0.4, 7, 0.3),
        conditions(7, 1.2, 13, 0.1),
        conditions(8, 0.8, 10, 0.2),
    ]

    comparison = compare_hourly_windows(hourly, requested_hour=6)

    assert comparison["requested"]["time_label"] == "6 AM"
    assert comparison["best_time_label"] == "7 AM"
    assert comparison["has_better_window"] is True
    assert comparison["alternatives"][0]["time_label"] == "7 AM"
    assert comparison["alternatives"][0]["is_better"] is True


def test_missing_data_reduces_score_and_is_explained():
    result = score_hour(
        {
            "timestamp": "2026-08-13T09:00",
            "wave_height_max": 1.0,
            "swell_wave_height_max": None,
            "swell_wave_period_max": None,
            "wind_wave_height_max": None,
        }
    )

    assert result["score"] == 6
    assert result["factors"][-1]["points"] == 6
    assert result["factors"][-1]["reason"] == (
        "1 of 4 comparison measurements are available."
    )


def test_daylight_range_uses_civil_twilight_for_date_and_location():
    assert daylight_hour_range(date(2026, 11, 4), 33.6595, -117.9988) == (6, 17)


def test_midnight_is_not_recommended_even_when_it_scores_highest():
    hourly = [
        conditions(0, 1.2, 13, 0.1),
        conditions(13, 0.8, 7, 0.2),
        conditions(16, 1.1, 12, 0.1),
    ]

    comparison = compare_hourly_windows(
        hourly,
        requested_hour=13,
        forecast_date=date(2026, 11, 4),
        latitude=33.6595,
        longitude=-117.9988,
    )

    assert comparison["daylight_start_label"] == "6 AM"
    assert comparison["daylight_end_label"] == "5 PM"
    assert [item["hour"] for item in comparison["alternatives"]] == [16]
    assert comparison["best_time_label"] == "4 PM"


def test_nighttime_request_is_shown_but_only_daylight_is_recommended():
    hourly = [
        conditions(0, 1.2, 13, 0.1),
        conditions(16, 0.8, 10, 0.2),
    ]

    comparison = compare_hourly_windows(
        hourly,
        requested_hour=0,
        forecast_date=date(2026, 11, 4),
        latitude=33.6595,
        longitude=-117.9988,
    )

    assert comparison["requested"]["time_label"] == "12 AM"
    assert comparison["requested_is_daylight"] is False
    assert comparison["best_time_label"] == "4 PM"
    assert comparison["has_better_window"] is True
    assert comparison["alternatives"][0]["is_better"] is True
