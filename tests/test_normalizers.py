"""Unit tests for data normalizers, unit conversions, and defensive null-safety."""

from __future__ import annotations

from typing import Any

import pytest

from garmin_coach_mcp.client import GarminCoachClient
from garmin_coach_mcp.models import (
    ActivityDetailsReport,
    AthleteProfileReport,
    BodyCompositionAndBiometricsReport,
    CoachDailyBriefing,
    HealthTrendsReport,
    SleepAndRecoveryReport,
    StructuredWorkoutInput,
    TrainingStatusAndLoadReport,
    WorkoutStepInput,
)
from garmin_coach_mcp.normalizers import (
    build_garmin_workout_json,
    format_duration,
    format_pace,
    grams_to_weight,
    meters_to_distance,
    meters_to_elevation,
    normalize_activities_list,
    normalize_activity_details,
    normalize_athlete_profile,
    normalize_body_composition_and_biometrics,
    normalize_daily_briefing,
    normalize_health_trends,
    normalize_sleep_and_recovery,
    normalize_training_status_and_load,
)


class TestFormattingAndUnitHelpers:
    """Tests for duration, pace, distance, elevation, and weight converters."""

    def test_format_duration(self) -> None:
        assert format_duration(None) == "0:00"
        assert format_duration(0) == "0:00"
        assert format_duration(2730) == "45:30"
        assert format_duration(4520) == "1:15:20"

    def test_format_pace_metric_and_imperial(self) -> None:
        assert format_pace(None) is None
        assert format_pace(0) is None
        assert format_pace(-2.5) is None

        # 4.1666667 m/s == 240 sec/km == 4:00 /km
        metric_pace = format_pace(4.1666667, "metric")
        assert metric_pace == "4:00 /km"

        imperial_pace = format_pace(4.1666667, "imperial")
        assert imperial_pace is not None
        assert imperial_pace.endswith("/mi")
        assert imperial_pace.startswith("6:26")

    def test_meters_to_distance_and_elevation(self) -> None:
        assert meters_to_distance(None) is None
        assert meters_to_distance(10500.0, "metric") == pytest.approx(10.5, rel=1e-2)
        assert meters_to_distance(10500.0, "imperial") == pytest.approx(6.52, rel=1e-2)

        assert meters_to_elevation(None) is None
        assert meters_to_elevation(100.0, "metric") == pytest.approx(100.0, rel=1e-2)
        assert meters_to_elevation(100.0, "imperial") == pytest.approx(328.1, rel=1e-2)

    def test_grams_to_weight(self) -> None:
        assert grams_to_weight(None) is None
        assert grams_to_weight(68400.0, "metric", is_grams=True) == pytest.approx(68.4, rel=1e-2)
        assert grams_to_weight(68400.0, "imperial", is_grams=True) == pytest.approx(150.79, rel=1e-2)
        assert grams_to_weight(68.4, "metric", is_grams=False) == pytest.approx(68.4, rel=1e-2)


class TestNormalizersMetricAndImperial:
    """Tests for all normalizer functions across metric and imperial unit systems."""

    def test_normalize_daily_briefing(self, coach_client: GarminCoachClient) -> None:
        raw = coach_client.fetch_daily_briefing_raw("2026-11-11")

        brief_m = normalize_daily_briefing(raw, "metric")
        assert isinstance(brief_m, CoachDailyBriefing)
        assert brief_m.date == "2026-11-11"
        assert brief_m.readiness.score == 79
        assert brief_m.body_battery.current_level == 78
        assert brief_m.body_battery.charged == 62
        assert brief_m.hrv.last_night_avg_ms == 68.0
        assert brief_m.resting_hr_bpm == 46
        assert brief_m.sleep.sleep_score == 84
        assert brief_m.coach_recommendation
        assert brief_m.recommended_intensity in (
            "high_intensity",
            "moderate_steady",
            "easy_recovery",
            "rest",
        )

        brief_i = normalize_daily_briefing(raw, "imperial")
        assert brief_i.unit_system == "imperial"
        if brief_i.yesterday_activities:
            assert brief_i.yesterday_activities[0].distance_unit == "mi"

    def test_normalize_sleep_and_recovery(self, coach_client: GarminCoachClient) -> None:
        raw_days = coach_client.fetch_sleep_and_recovery_raw("2026-11-10", "2026-11-11")
        report = normalize_sleep_and_recovery(raw_days, "metric")

        assert isinstance(report, SleepAndRecoveryReport)
        assert len(report.days) == 2
        day0 = report.days[0]
        assert day0.sleep_score == 84
        assert day0.stages.deep_seconds == 5400
        assert day0.stages.total_sleep_seconds == 27900
        assert day0.avg_spo2_pct == 96.5
        assert day0.avg_overnight_hrv_ms == 68.0
        assert report.recovery_takeaway

    def test_normalize_training_status_and_load(self, coach_client: GarminCoachClient) -> None:
        raw = coach_client.fetch_training_status_and_load_raw("2026-11-11")
        report = normalize_training_status_and_load(raw, "metric")

        assert isinstance(report, TrainingStatusAndLoadReport)
        assert report.vo2_max_running == pytest.approx(56.2)
        assert report.vo2_max_cycling == pytest.approx(58.0)
        assert report.load.acute_load == pytest.approx(640.0)
        assert report.load.chronic_load == pytest.approx(580.0)
        assert report.load.load_ratio == pytest.approx(1.10)
        assert report.endurance_score == 7420
        assert report.hill_score == 68
        assert report.fitness_age == 26
        assert report.coach_load_assessment

    def test_normalize_activities_list_and_details(self, coach_client: GarminCoachClient) -> None:
        raw_list = coach_client.fetch_recent_activities_raw(limit=4)
        acts_m = normalize_activities_list(raw_list, "metric")
        acts_i = normalize_activities_list(raw_list, "imperial")

        assert len(acts_m) == 4
        assert acts_m[0].distance == pytest.approx(10.5, rel=1e-2)
        assert acts_m[0].distance_unit == "km"
        assert acts_i[0].distance == pytest.approx(6.52, rel=1e-2)
        assert acts_i[0].distance_unit == "mi"

        raw_details = coach_client.fetch_activity_details_raw(17501001)
        details_m = normalize_activity_details(raw_details, "metric")
        details_i = normalize_activity_details(raw_details, "imperial")

        assert isinstance(details_m, ActivityDetailsReport)
        assert len(details_m.laps) == 9
        assert len(details_m.hr_zones) == 5
        assert details_m.weather is not None
        assert details_i.summary.distance_unit == "mi"

    def test_normalize_health_trends(self, coach_client: GarminCoachClient) -> None:
        raw_trends = coach_client.fetch_health_trends_raw(days=14, end_date="2026-11-11")
        trends_m = normalize_health_trends(raw_trends, "metric")
        trends_i = normalize_health_trends(raw_trends, "imperial")

        assert isinstance(trends_m, HealthTrendsReport)
        assert trends_m.days == 14
        assert trends_m.rhr_trend.average == pytest.approx(46.0)
        assert trends_m.hrv_trend.average == pytest.approx(68.0)
        assert trends_m.distance_unit == "km"
        assert trends_i.distance_unit == "mi"

    def test_normalize_body_composition_and_athlete_profile(
        self, coach_client: GarminCoachClient
    ) -> None:
        raw_body = coach_client.fetch_body_composition_and_biometrics_raw(
            "2026-10-12", "2026-11-11"
        )
        body_m = normalize_body_composition_and_biometrics(raw_body, "metric")
        body_i = normalize_body_composition_and_biometrics(raw_body, "imperial")

        assert isinstance(body_m, BodyCompositionAndBiometricsReport)
        assert body_m.latest_weight == pytest.approx(68.4, rel=1e-2)
        assert body_m.weight_unit == "kg"
        assert body_i.latest_weight == pytest.approx(150.79, rel=1e-2)
        assert body_i.weight_unit in ("lbs", "lb")
        assert body_m.biometrics.lactate_threshold_hr_bpm == 174
        assert body_m.biometrics.ftp_watts == 285

        raw_profile = coach_client.fetch_athlete_profile_raw()
        prof_m = normalize_athlete_profile(raw_profile, "metric")
        prof_i = normalize_athlete_profile(raw_profile, "imperial")

        assert isinstance(prof_m, AthleteProfileReport)
        assert prof_m.full_name == "Alex Rivera"
        assert len(prof_m.hr_zones) == 5
        assert len(prof_m.personal_records) == 4
        assert prof_i.unit_system == "imperial"

    def test_build_garmin_workout_json(self) -> None:
        workout_input = StructuredWorkoutInput(
            workout_name="Threshold 4x1km Repeat Session",
            sport_type="running",
            description="Warmup + 4x1000m @ Z4 + Cooldown",
            steps=[
                WorkoutStepInput(
                    step_type="warmup",
                    duration_type="time",
                    duration_value=600,
                    target_type="heart.rate.zone",
                    target_zone_number=2,
                ),
                WorkoutStepInput(
                    step_type="repeat",
                    duration_type="iterations",
                    duration_value=4,
                    repeat_steps=[
                        WorkoutStepInput(
                            step_type="interval",
                            duration_type="distance",
                            duration_value=1000,
                            target_type="pace.zone",
                            target_low=4.05,
                            target_high=4.25,
                        ),
                        WorkoutStepInput(
                            step_type="recovery",
                            duration_type="time",
                            duration_value=120,
                            target_type="no.target",
                        ),
                    ],
                ),
                WorkoutStepInput(
                    step_type="cooldown",
                    duration_type="time",
                    duration_value=600,
                    target_type="heart.rate.zone",
                    target_zone_number=1,
                ),
            ],
        )

        result = build_garmin_workout_json(workout_input, "metric")
        assert result.workout_name == "Threshold 4x1km Repeat Session"
        assert result.total_estimated_duration_seconds > 1200
        assert result.total_estimated_distance_meters >= 4000
        assert "workoutSegments" in result.garmin_workout_json
        assert len(result.human_readable_summary) >= 3


class TestDefensiveNullSafety:
    """Verify normalizers never raise KeyError/TypeError when raw payloads are empty or partial."""

    def test_empty_dicts_do_not_crash_any_normalizer(self) -> None:
        brief = normalize_daily_briefing({})
        assert isinstance(brief, CoachDailyBriefing)
        assert brief.resting_hr_bpm is None

        sleep = normalize_sleep_and_recovery([])
        assert isinstance(sleep, SleepAndRecoveryReport)
        assert sleep.days == []

        sleep_unworn = normalize_sleep_and_recovery([{"date": "2026-11-11", "sleep_data": {}}])
        assert len(sleep_unworn.days) == 1
        assert sleep_unworn.days[0].sleep_score is None

        status = normalize_training_status_and_load({})
        assert isinstance(status, TrainingStatusAndLoadReport)

        acts = normalize_activities_list([{}])
        assert len(acts) == 1
        assert acts[0].avg_power_watts is None

        details = normalize_activity_details({})
        assert isinstance(details, ActivityDetailsReport)
        assert details.laps == []

        trends = normalize_health_trends({})
        assert isinstance(trends, HealthTrendsReport)

        body = normalize_body_composition_and_biometrics({})
        assert isinstance(body, BodyCompositionAndBiometricsReport)

        profile = normalize_athlete_profile({})
        assert isinstance(profile, AthleteProfileReport)
