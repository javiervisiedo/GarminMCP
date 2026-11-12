"""Defensive, null-safe data normalizers and unit converters for Garmin Connect JSON payloads."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from garmin_coach_mcp.models.activity import (
    ActivityDetailsReport,
    ActivitySummary,
    LapSplitSummary,
    StructuredWorkoutInput,
    StructuredWorkoutResult,
    TrainingEffectSummary,
    WeatherSummary,
    WorkoutStepInput,
    ZoneDistributionItem,
)
from garmin_coach_mcp.models.health import (
    BiometricsConfig,
    BodyCompositionAndBiometricsReport,
    BodyCompositionEntry,
    HealthTrendsReport,
    MetricTrendSummary,
    SleepAndRecoveryReport,
    SleepRecoveryDay,
    SleepStagesSummary,
)
from garmin_coach_mcp.models.readiness import (
    AthleteProfileReport,
    BodyBatterySummary,
    CoachDailyBriefing,
    HRVSummary,
    PersonalRecordItem,
    TrainingLoadMetrics,
    TrainingReadinessSummary,
    TrainingStatusAndLoadReport,
    ZoneConfigItem,
)

UnitSystem = Literal["metric", "imperial"]

_METERS_PER_KM = 1000.0
_METERS_PER_MILE = 1609.344
_FEET_PER_METER = 3.28084
_LBS_PER_KG = 2.20462262


# ---------------------------------------------------------------------------
# Internal Safe Type Coercion Helpers
# ---------------------------------------------------------------------------


def _as_dict(val: Any) -> dict[str, Any]:
    """Return val if it is a dict, or its first element if a list of dicts, else {}."""
    if isinstance(val, dict):
        return val
    if isinstance(val, list) and val and isinstance(val[0], dict):
        return val[0]
    return {}


def _to_float(val: Any, ndigits: int | None = None) -> float | None:
    """Safely convert a value to float, returning None on failure or None."""
    if val is None or isinstance(val, bool):
        return None
    try:
        f = float(val)
        return round(f, ndigits) if ndigits is not None else f
    except (TypeError, ValueError):
        return None


def _to_int(val: Any) -> int | None:
    """Safely convert a numeric value to int, returning None on failure or None."""
    if val is None or isinstance(val, bool):
        return None
    try:
        return int(round(float(val)))
    except (TypeError, ValueError):
        return None


def _first_not_none(*values: Any) -> Any:
    """Return the first value that is not None."""
    for v in values:
        if v is not None:
            return v
    return None


# ---------------------------------------------------------------------------
# 1. Unit & Formatting Helpers
# ---------------------------------------------------------------------------


def format_duration(seconds: float | int | None) -> str:
    """Format seconds into human-readable duration (e.g. 2730 -> '45:30', 4520 -> '1:15:20')."""
    if seconds is None:
        return "0:00"
    try:
        val = float(seconds)
    except (TypeError, ValueError):
        return "0:00"
    if val <= 0:
        return "0:00"

    total_secs = int(round(val))
    hours, rem = divmod(total_secs, 3600)
    minutes, secs = divmod(rem, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_pace(speed_m_per_s: float | None, unit_system: UnitSystem = "metric") -> str | None:
    """Convert speed in m/s to pace string ('4:35 /km' for metric or '7:22 /mi' for imperial)."""
    if speed_m_per_s is None:
        return None
    try:
        speed = float(speed_m_per_s)
    except (TypeError, ValueError):
        return None
    if speed <= 0:
        return None

    meters_per_unit = _METERS_PER_MILE if unit_system == "imperial" else _METERS_PER_KM
    unit_label = "/mi" if unit_system == "imperial" else "/km"
    total_seconds = int(round(meters_per_unit / speed))
    minutes, secs = divmod(total_seconds, 60)
    return f"{minutes}:{secs:02d} {unit_label}"


def meters_to_distance(meters: float | None, unit_system: UnitSystem = "metric") -> float | None:
    """Convert meters to km (metric) or miles (imperial) rounded to 2 decimal places."""
    if meters is None:
        return None
    try:
        m = float(meters)
    except (TypeError, ValueError):
        return None

    if unit_system == "imperial":
        return round(m / _METERS_PER_MILE, 2)
    return round(m / _METERS_PER_KM, 2)


def meters_to_elevation(meters: float | None, unit_system: UnitSystem = "metric") -> float | None:
    """Convert elevation meters to m (metric) or ft (imperial) rounded to 1 decimal place."""
    if meters is None:
        return None
    try:
        m = float(meters)
    except (TypeError, ValueError):
        return None

    if unit_system == "imperial":
        return round(m * _FEET_PER_METER, 1)
    return round(m, 1)


def grams_to_weight(
    grams_or_kg: float | None,
    unit_system: UnitSystem = "metric",
    is_grams: bool = True,
) -> float | None:
    """Convert Garmin gram values (e.g. 72500.0) or kg values (72.5) to kg or lbs rounded to 2 decimals."""
    if grams_or_kg is None:
        return None
    try:
        val = float(grams_or_kg)
    except (TypeError, ValueError):
        return None

    kg = (val / 1000.0) if is_grams else val
    if unit_system == "imperial":
        return round(kg * _LBS_PER_KG, 2)
    return round(kg, 2)


# ---------------------------------------------------------------------------
# 2. Internal Component Parsers
# ---------------------------------------------------------------------------


def _parse_sleep_day(raw_day: dict[str, Any]) -> SleepRecoveryDay:
    """Parse a single day's sleep, HRV, Body Battery, SpO2, and respiration dict into SleepRecoveryDay."""
    if not isinstance(raw_day, dict):
        raw_day = {}

    sleep_root = _as_dict(raw_day.get("sleep_data")) if "sleep_data" in raw_day else raw_day
    dto = _as_dict(sleep_root.get("dailySleepDTO")) if "dailySleepDTO" in sleep_root else sleep_root
    user_summary = _as_dict(raw_day.get("user_summary"))
    hrv_root = _as_dict(raw_day.get("hrv_data"))
    hrv_summary = _as_dict(hrv_root.get("hrvSummary")) if "hrvSummary" in hrv_root else hrv_root
    bb_item = _as_dict(raw_day.get("body_battery"))
    spo2_data = _as_dict(raw_day.get("spo2_data"))
    resp_data = _as_dict(raw_day.get("respiration_data"))
    rhr_data = _as_dict(raw_day.get("rhr_data"))

    cdate = str(
        _first_not_none(
            raw_day.get("date"),
            dto.get("calendarDate"),
            sleep_root.get("calendarDate"),
            user_summary.get("calendarDate"),
            date.today().isoformat(),
        )
    )

    # Sleep score & qualifier
    sleep_scores = _as_dict(dto.get("sleepScores"))
    overall_score_obj = sleep_scores.get("overall")
    if isinstance(overall_score_obj, dict):
        sleep_score = _to_int(overall_score_obj.get("value"))
        qualifier = overall_score_obj.get("qualifierKey") or overall_score_obj.get("qualifier")
    else:
        sleep_score = _to_int(_first_not_none(overall_score_obj, dto.get("sleepScore")))
        qualifier = _first_not_none(
            sleep_scores.get("qualifierKey"),
            dto.get("sleepQualityQualifier"),
            dto.get("sleepQualityTypePK"),
        )

    # Stages
    deep_s = _to_int(_first_not_none(dto.get("deepSleepSeconds"), dto.get("deep_seconds"))) or 0
    light_s = _to_int(_first_not_none(dto.get("lightSleepSeconds"), dto.get("light_seconds"))) or 0
    rem_s = _to_int(_first_not_none(dto.get("remSleepSeconds"), dto.get("rem_seconds"))) or 0
    awake_s = _to_int(_first_not_none(dto.get("awakeSleepSeconds"), dto.get("awake_seconds"))) or 0
    total_s = (
        _to_int(
            _first_not_none(
                dto.get("sleepTimeSeconds"),
                dto.get("totalSleepSeconds"),
                dto.get("total_sleep_seconds"),
            )
        )
        or (deep_s + light_s + rem_s)
    )

    stages = SleepStagesSummary(
        deep_seconds=max(0, deep_s),
        light_seconds=max(0, light_s),
        rem_seconds=max(0, rem_s),
        awake_seconds=max(0, awake_s),
        total_sleep_seconds=max(0, total_s),
    )

    # Resting HR
    rhr = _to_int(
        _first_not_none(
            dto.get("restingHeartRate"),
            sleep_root.get("restingHeartRate"),
            user_summary.get("restingHeartRate"),
            rhr_data.get("restingHeartRate"),
        )
    )

    # Overnight HRV & baseline
    overnight_hrv = _to_float(
        _first_not_none(
            hrv_summary.get("lastNightAvg"),
            dto.get("avgOvernightHrv"),
            sleep_root.get("avgOvernightHrv"),
        ),
        1,
    )
    hrv_status = _first_not_none(
        hrv_summary.get("status"),
        dto.get("hrvStatus"),
        sleep_root.get("hrvStatus"),
    )
    hrv_baseline = _as_dict(
        _first_not_none(
            hrv_summary.get("baseline"),
            dto.get("hrvBaseline"),
            sleep_root.get("hrvBaseline"),
        )
    )
    baseline_low = _to_float(
        _first_not_none(hrv_baseline.get("balancedLow"), hrv_baseline.get("lowUpper")),
        1,
    )
    baseline_high = _to_float(hrv_baseline.get("balancedUpper"), 1)

    # Body battery
    bb_charged = _to_int(
        _first_not_none(
            bb_item.get("charged"),
            user_summary.get("bodyBatteryChargedValue"),
            sleep_root.get("bodyBatteryChange"),
            dto.get("bodyBatteryChange"),
        )
    )
    bb_drained = _to_int(
        _first_not_none(
            bb_item.get("drained"),
            user_summary.get("bodyBatteryDrainedValue"),
        )
    )
    bb_high = _to_int(
        _first_not_none(
            bb_item.get("highestLevel"),
            user_summary.get("bodyBatteryHighestValue"),
        )
    )
    bb_low = _to_int(
        _first_not_none(
            bb_item.get("lowestLevel"),
            user_summary.get("bodyBatteryLowestValue"),
        )
    )

    # SpO2
    spo2_dto = _as_dict(sleep_root.get("wellnessSpO2SleepSummaryDTO"))
    avg_spo2 = _to_float(
        _first_not_none(
            dto.get("averageSpO2Value"),
            dto.get("averageSpO2"),
            spo2_data.get("averageSpO2"),
            spo2_dto.get("averageSpO2"),
            user_summary.get("averageSpo2"),
        ),
        1,
    )
    low_spo2 = _to_float(
        _first_not_none(
            dto.get("lowestSpO2Value"),
            dto.get("lowestSpO2"),
            spo2_data.get("lowestSpO2"),
            spo2_dto.get("lowestSpO2"),
            user_summary.get("lowestSpo2"),
        ),
        1,
    )

    # Respiration
    waking_resp = _to_float(
        _first_not_none(
            resp_data.get("avgWakingRespirationValue"),
            user_summary.get("avgWakingRespirationValue"),
            dto.get("avgWakingRespirationValue"),
        ),
        1,
    )
    sleep_resp = _to_float(
        _first_not_none(
            dto.get("averageRespirationValue"),
            resp_data.get("avgSleepRespirationValue"),
            user_summary.get("avgSleepRespirationValue"),
        ),
        1,
    )

    # Sleep need
    sleep_need_raw = _first_not_none(dto.get("sleepNeed"), sleep_root.get("sleepNeed"))
    if isinstance(sleep_need_raw, dict):
        sleep_need_mins = _to_int(
            _first_not_none(sleep_need_raw.get("actual"), sleep_need_raw.get("baseline"))
        )
    else:
        sleep_need_mins = _to_int(_first_not_none(sleep_need_raw, dto.get("sleepNeedMinutes")))

    return SleepRecoveryDay(
        date=cdate,
        sleep_score=sleep_score,
        sleep_quality_qualifier=str(qualifier) if qualifier is not None else None,
        stages=stages,
        resting_hr_bpm=rhr,
        avg_overnight_hrv_ms=overnight_hrv,
        hrv_status=str(hrv_status) if hrv_status is not None else None,
        hrv_baseline_low_ms=baseline_low,
        hrv_baseline_high_ms=baseline_high,
        body_battery_charged=bb_charged,
        body_battery_drained=bb_drained,
        body_battery_high=bb_high,
        body_battery_low=bb_low,
        avg_spo2_pct=avg_spo2,
        lowest_spo2_pct=low_spo2,
        avg_waking_respiration_brpm=waking_resp,
        avg_sleep_respiration_brpm=sleep_resp,
        sleep_need_minutes=sleep_need_mins,
    )


def _extract_training_status_key(ts_raw: Any) -> tuple[str | None, str | None]:
    """Extract (training_status_key, training_status_feedback) from raw training status data."""
    ts = _as_dict(ts_raw)
    if not ts:
        return None, None

    key = _first_not_none(ts.get("trainingStatusKey"), ts.get("status"))
    feedback = _first_not_none(
        ts.get("trainingStatusFeedbackPhrase"),
        ts.get("trainingStatusFeedback"),
        ts.get("feedbackPhrase"),
    )

    mrts = _as_dict(ts.get("mostRecentTrainingStatus"))
    latest_map = _as_dict(mrts.get("latestTrainingStatusData"))
    if latest_map:
        first_device = _as_dict(next(iter(latest_map.values())))
        key = _first_not_none(
            key,
            first_device.get("trainingStatusKey"),
            first_device.get("trainingStatusFeedbackPhrase"),
        )
        feedback = _first_not_none(
            feedback,
            first_device.get("trainingStatusFeedbackPhrase"),
            first_device.get("trainingStatusKey"),
        )

    return (
        str(key) if key is not None else None,
        str(feedback) if feedback is not None else (str(key) if key is not None else None),
    )


def _normalize_single_activity(
    act: dict[str, Any],
    unit_system: UnitSystem = "metric",
) -> ActivitySummary:
    """Normalize a single activity dict into ActivitySummary."""
    if not isinstance(act, dict):
        act = {}

    summary_dto = _as_dict(act.get("summaryDTO"))
    act_id = _first_not_none(act.get("activityId"), act.get("activity_id"), 0)
    act_name = str(
        _first_not_none(act.get("activityName"), act.get("activity_name"), "Unnamed Activity")
    )

    act_type_raw = _first_not_none(
        act.get("activityType"),
        act.get("activityTypeDTO"),
        summary_dto.get("activityType"),
        "unknown",
    )
    if isinstance(act_type_raw, dict):
        act_type = str(_first_not_none(act_type_raw.get("typeKey"), act_type_raw.get("type"), "unknown"))
    else:
        act_type = str(act_type_raw)

    start_local = _first_not_none(
        act.get("startTimeLocal"),
        summary_dto.get("startTimeLocal"),
        act.get("start_time_local"),
    )
    start_local_str = str(start_local) if start_local is not None else None
    act_date = (
        str(act["date"])
        if act.get("date")
        else (start_local_str[:10] if start_local_str and len(start_local_str) >= 10 else None)
    )

    duration_sec = (
        _to_float(
            _first_not_none(
                act.get("duration"),
                summary_dto.get("duration"),
                act.get("movingDuration"),
                summary_dto.get("movingDuration"),
                act.get("duration_seconds"),
            ),
            1,
        )
        or 0.0
    )

    raw_dist = _to_float(_first_not_none(act.get("distance"), summary_dto.get("distance")))
    distance_conv = meters_to_distance(raw_dist, unit_system)
    dist_unit = "mi" if unit_system == "imperial" else "km"

    avg_speed = _to_float(
        _first_not_none(
            act.get("averageSpeed"),
            summary_dto.get("averageSpeed"),
            act.get("avg_speed_mps"),
        ),
        4,
    )
    # Only format running/walking/swimming/hiking pace or when speed > 0
    avg_pace = format_pace(avg_speed, unit_system) if avg_speed and avg_speed > 0 else None

    avg_hr = _to_int(
        _first_not_none(act.get("averageHR"), summary_dto.get("averageHR"), act.get("avg_hr_bpm"))
    )
    max_hr = _to_int(
        _first_not_none(act.get("maxHR"), summary_dto.get("maxHR"), act.get("max_hr_bpm"))
    )

    avg_power = _to_float(
        _first_not_none(
            act.get("avgPower"),
            act.get("averagePower"),
            summary_dto.get("averagePower"),
            summary_dto.get("avgPower"),
            act.get("avg_power_watts"),
        ),
        1,
    )
    max_power = _to_float(
        _first_not_none(
            act.get("maxPower"),
            summary_dto.get("maxPower"),
            act.get("max_power_watts"),
        ),
        1,
    )
    norm_power = _to_float(
        _first_not_none(
            act.get("normPower"),
            act.get("normalizedPower"),
            summary_dto.get("normalizedPower"),
            summary_dto.get("normPower"),
            act.get("normalized_power_watts"),
        ),
        1,
    )

    avg_cadence = _to_float(
        _first_not_none(
            act.get("averageRunningCadenceInStepsPerMinute"),
            act.get("averageBikingCadenceInRevPerMinute"),
            summary_dto.get("averageRunCadence"),
            summary_dto.get("averageBikeCadence"),
            act.get("averageRunCadence"),
            act.get("avgCadence"),
            act.get("avg_cadence_spm"),
        ),
        1,
    )

    elev_gain_raw = _to_float(
        _first_not_none(act.get("elevationGain"), summary_dto.get("elevationGain"))
    )
    elev_loss_raw = _to_float(
        _first_not_none(act.get("elevationLoss"), summary_dto.get("elevationLoss"))
    )
    elev_unit = "ft" if unit_system == "imperial" else "m"

    calories = _to_int(_first_not_none(act.get("calories"), summary_dto.get("calories")))

    aerobic_te = _to_float(
        _first_not_none(
            act.get("aerobicTrainingEffect"),
            summary_dto.get("aerobicTrainingEffect"),
            summary_dto.get("trainingEffect"),
            act.get("trainingEffect"),
        ),
        1,
    )
    anaerobic_te = _to_float(
        _first_not_none(
            act.get("anaerobicTrainingEffect"),
            summary_dto.get("anaerobicTrainingEffect"),
        ),
        1,
    )
    primary_benefit = _first_not_none(
        act.get("trainingEffectLabel"),
        summary_dto.get("trainingEffectLabel"),
        act.get("aerobicTrainingEffectMessage"),
        summary_dto.get("aerobicTrainingEffectMessage"),
    )
    training_load = _to_float(
        _first_not_none(
            act.get("activityTrainingLoad"),
            summary_dto.get("activityTrainingLoad"),
        ),
        1,
    )

    return ActivitySummary(
        activity_id=act_id,
        activity_name=act_name,
        activity_type=act_type,
        start_time_local=start_local_str,
        date=act_date,
        duration_seconds=duration_sec,
        duration_formatted=format_duration(duration_sec),
        distance=distance_conv,
        distance_unit=dist_unit,
        avg_pace=avg_pace,
        avg_speed_mps=avg_speed,
        avg_hr_bpm=avg_hr,
        max_hr_bpm=max_hr,
        avg_power_watts=avg_power,
        max_power_watts=max_power,
        normalized_power_watts=norm_power,
        avg_cadence_spm=avg_cadence,
        elevation_gain=meters_to_elevation(elev_gain_raw, unit_system),
        elevation_loss=meters_to_elevation(elev_loss_raw, unit_system),
        elevation_unit=elev_unit,
        calories=calories,
        training_effect=TrainingEffectSummary(
            aerobic_effect=aerobic_te,
            anaerobic_effect=anaerobic_te,
            primary_benefit=str(primary_benefit) if primary_benefit is not None else None,
            training_load=training_load,
        ),
    )


def _extract_biometrics(raw: dict[str, Any], unit_system: UnitSystem = "metric") -> BiometricsConfig:
    """Extract BiometricsConfig from raw profile, body composition, lactate threshold, and max_metrics."""
    if not isinstance(raw, dict):
        raw = {}

    bc = _as_dict(raw.get("body_composition"))
    lt = _as_dict(raw.get("lactate_threshold"))
    lt_nested = _as_dict(lt.get("speed_and_heart_rate"))
    bio_sub = _as_dict(
        _first_not_none(
            raw.get("biometrics"),
            bc.get("biometrics"),
            lt.get("biometrics"),
        )
    )
    user_prof = _as_dict(raw.get("user_profile"))
    user_settings = _as_dict(raw.get("user_settings"))
    user_data = _as_dict(
        _first_not_none(
            raw.get("userData"),
            user_prof.get("userData"),
            user_settings.get("userData"),
        )
    )
    max_metrics = _as_dict(raw.get("max_metrics"))
    vo2_root = _as_dict(_first_not_none(max_metrics.get("mostRecentVO2Max"), max_metrics))
    vo2_generic = _as_dict(vo2_root.get("generic"))
    vo2_cycling = _as_dict(vo2_root.get("cycling"))

    max_hr = _to_int(
        _first_not_none(
            bio_sub.get("maxHeartRate"),
            bio_sub.get("max_hr_bpm"),
            lt.get("maxHeartRate"),
            user_data.get("maxHeartRate"),
            user_prof.get("maxHeartRate"),
            raw.get("maxHeartRate"),
        )
    )
    resting_hr = _to_int(
        _first_not_none(
            bio_sub.get("restingHeartRate"),
            bio_sub.get("resting_hr_bpm"),
            lt.get("restingHeartRate"),
            user_data.get("restingHeartRate"),
            user_prof.get("restingHeartRate"),
            raw.get("restingHeartRate"),
        )
    )
    lthr = _to_int(
        _first_not_none(
            bio_sub.get("lactateThresholdHeartRate"),
            bio_sub.get("lactate_threshold_hr_bpm"),
            lt.get("lactateThresholdHeartRate"),
            lt.get("heartRate"),
            lt_nested.get("heartRate"),
            user_data.get("lactateThresholdHeartRate"),
            raw.get("lactateThresholdHeartRate"),
        )
    )
    lt_speed = _to_float(
        _first_not_none(
            bio_sub.get("lactateThresholdSpeed"),
            bio_sub.get("lactate_threshold_speed_mps"),
            lt.get("lactateThresholdSpeed"),
            lt.get("speed"),
            lt_nested.get("speed"),
            user_data.get("lactateThresholdSpeed"),
            raw.get("lactateThresholdSpeed"),
        ),
        4,
    )
    lt_pace = format_pace(lt_speed, unit_system) if lt_speed and lt_speed > 0 else None

    ftp = _to_int(
        _first_not_none(
            bio_sub.get("functionalThresholdPower"),
            bio_sub.get("ftp_watts"),
            bio_sub.get("ftp"),
            lt.get("functionalThresholdPower"),
            lt.get("ftp"),
            user_data.get("functionalThresholdPower"),
            raw.get("functionalThresholdPower"),
        )
    )
    vo2_run = _to_float(
        _first_not_none(
            bio_sub.get("vo2MaxRunning"),
            lt.get("vo2MaxRunning"),
            vo2_generic.get("vo2MaxPreciseValue"),
            vo2_generic.get("vo2MaxValue"),
            user_data.get("vo2MaxRunning"),
            raw.get("vo2MaxRunning"),
        ),
        1,
    )
    vo2_bike = _to_float(
        _first_not_none(
            bio_sub.get("vo2MaxCycling"),
            lt.get("vo2MaxCycling"),
            vo2_cycling.get("vo2MaxPreciseValue"),
            vo2_cycling.get("vo2MaxValue"),
            user_data.get("vo2MaxCycling"),
            raw.get("vo2MaxCycling"),
        ),
        1,
    )

    return BiometricsConfig(
        max_hr_bpm=max_hr,
        resting_hr_bpm=resting_hr,
        lactate_threshold_hr_bpm=lthr,
        lactate_threshold_pace=lt_pace,
        lactate_threshold_speed_mps=lt_speed,
        ftp_watts=ftp,
        vo2_max_running=vo2_run,
        vo2_max_cycling=vo2_bike,
    )


# ---------------------------------------------------------------------------
# 3. Public Normalizer Functions
# ---------------------------------------------------------------------------


def normalize_daily_briefing(
    raw: dict[str, Any],
    unit_system: UnitSystem = "metric",
) -> CoachDailyBriefing:
    """Normalize raw daily briefing telemetry into a CoachDailyBriefing model."""
    if not isinstance(raw, dict):
        raw = {}

    user_summary = _as_dict(raw.get("user_summary"))
    tr = _as_dict(raw.get("training_readiness"))
    bb = _as_dict(raw.get("body_battery"))
    hrv_root = _as_dict(raw.get("hrv_data"))
    hrv_s = _as_dict(hrv_root.get("hrvSummary")) if "hrvSummary" in hrv_root else hrv_root
    stress_data = _as_dict(raw.get("stress_data"))
    rhr_data = _as_dict(raw.get("rhr_data"))

    cdate = str(
        _first_not_none(
            raw.get("date"),
            user_summary.get("calendarDate"),
            tr.get("calendarDate"),
            date.today().isoformat(),
        )
    )

    # Sleep day
    sleep_day = _parse_sleep_day(raw)

    # Training readiness
    rec_mins = _to_float(_first_not_none(tr.get("recoveryTime"), tr.get("recovery_time")))
    rec_hours_explicit = _to_float(
        _first_not_none(tr.get("recoveryTimeInHours"), tr.get("recovery_time_hours"))
    )
    recovery_hours = (
        round(rec_hours_explicit, 1)
        if rec_hours_explicit is not None
        else (round(rec_mins / 60.0, 1) if rec_mins is not None else None)
    )

    readiness = TrainingReadinessSummary(
        score=_to_int(tr.get("score")),
        level=str(tr["level"]) if tr.get("level") is not None else None,
        feedback_short=(
            str(_first_not_none(tr.get("feedbackShort"), tr.get("feedbackLong")))
            if _first_not_none(tr.get("feedbackShort"), tr.get("feedbackLong")) is not None
            else None
        ),
        recovery_time_hours=recovery_hours,
        sleep_score_factor_pct=_to_int(
            _first_not_none(tr.get("sleepScoreFactorPercent"), tr.get("sleep_score_factor_pct"))
        ),
        recovery_time_factor_pct=_to_int(
            _first_not_none(tr.get("recoveryTimeFactorPercent"), tr.get("recovery_time_factor_pct"))
        ),
        acwr_factor_pct=_to_int(
            _first_not_none(
                tr.get("acwrFactorPercent"),
                tr.get("acuteLoadFactorPercent"),
                tr.get("acwr_factor_pct"),
            )
        ),
        hrv_factor_pct=_to_int(
            _first_not_none(tr.get("hrvFactorPercent"), tr.get("hrv_factor_pct"))
        ),
        stress_history_factor_pct=_to_int(
            _first_not_none(
                tr.get("stressHistoryFactorPercent"), tr.get("stress_history_factor_pct")
            )
        ),
    )

    # Body battery
    bb_current = _to_int(
        _first_not_none(
            bb.get("currentLevel"),
            bb.get("mostRecentValue"),
            user_summary.get("bodyBatteryMostRecentValue"),
            user_summary.get("bodyBatteryCurrentValue"),
        )
    )
    if bb_current is None and isinstance(bb.get("bodyBatteryValuesArray"), list):
        arr = bb["bodyBatteryValuesArray"]
        if arr and isinstance(arr[-1], (list, tuple)) and len(arr[-1]) >= 2:
            bb_current = _to_int(arr[-1][1])

    body_battery = BodyBatterySummary(
        current_level=bb_current,
        charged=_to_int(
            _first_not_none(
                bb.get("charged"),
                user_summary.get("bodyBatteryChargedValue"),
                sleep_day.body_battery_charged,
            )
        ),
        drained=_to_int(
            _first_not_none(
                bb.get("drained"),
                user_summary.get("bodyBatteryDrainedValue"),
                sleep_day.body_battery_drained,
            )
        ),
        highest_level=_to_int(
            _first_not_none(
                bb.get("highestLevel"),
                user_summary.get("bodyBatteryHighestValue"),
                sleep_day.body_battery_high,
            )
        ),
        lowest_level=_to_int(
            _first_not_none(
                bb.get("lowestLevel"),
                user_summary.get("bodyBatteryLowestValue"),
                sleep_day.body_battery_low,
            )
        ),
    )

    # HRV
    hrv_baseline = _as_dict(hrv_s.get("baseline"))
    hrv = HRVSummary(
        last_night_avg_ms=_to_float(
            _first_not_none(hrv_s.get("lastNightAvg"), sleep_day.avg_overnight_hrv_ms), 1
        ),
        last_night_5min_high_ms=_to_float(hrv_s.get("lastNight5MinHigh"), 1),
        weekly_avg_ms=_to_float(_first_not_none(hrv_s.get("weeklyAvg"), tr.get("hrvWeeklyAverage")), 1),
        status=(
            str(_first_not_none(hrv_s.get("status"), sleep_day.hrv_status))
            if _first_not_none(hrv_s.get("status"), sleep_day.hrv_status) is not None
            else None
        ),
        baseline_low_ms=_to_float(
            _first_not_none(
                hrv_baseline.get("balancedLow"),
                hrv_baseline.get("lowUpper"),
                sleep_day.hrv_baseline_low_ms,
            ),
            1,
        ),
        baseline_high_ms=_to_float(
            _first_not_none(hrv_baseline.get("balancedUpper"), sleep_day.hrv_baseline_high_ms), 1
        ),
        feedback_phrase=(
            str(hrv_s["feedbackPhrase"]) if hrv_s.get("feedbackPhrase") is not None else None
        ),
    )

    # RHR, Stress, Steps
    resting_hr = _to_int(
        _first_not_none(
            user_summary.get("restingHeartRate"),
            rhr_data.get("restingHeartRate"),
            sleep_day.resting_hr_bpm,
        )
    )
    seven_day_rhr = _to_float(
        _first_not_none(
            user_summary.get("lastSevenDaysAvgRestingHeartRate"),
            rhr_data.get("lastSevenDaysAvgRestingHeartRate"),
        ),
        1,
    )

    raw_stress = _to_int(
        _first_not_none(
            user_summary.get("averageStressLevel"),
            stress_data.get("avgStressLevel"),
            stress_data.get("overallStressLevel"),
        )
    )
    stress_avg = raw_stress if (raw_stress is not None and raw_stress >= 0) else None
    stress_qual = _first_not_none(
        user_summary.get("stressQualifier"),
        stress_data.get("stressQualifier"),
    )
    if stress_qual is None and stress_avg is not None:
        if stress_avg <= 25:
            stress_qual = "LOW"
        elif stress_avg <= 50:
            stress_qual = "BALANCED"
        elif stress_avg <= 75:
            stress_qual = "HIGH"
        else:
            stress_qual = "VERY_HIGH"

    steps_today = _to_int(_first_not_none(user_summary.get("totalSteps"), user_summary.get("steps")))
    step_goal = _to_int(
        _first_not_none(user_summary.get("dailyStepGoal"), user_summary.get("stepGoal"))
    )

    ts_label, _ = _extract_training_status_key(raw.get("training_status"))

    yesterday_acts = normalize_activities_list(
        raw.get("yesterday_activities") if isinstance(raw.get("yesterday_activities"), list) else [],
        unit_system=unit_system,
    )

    # Determine recommended_intensity & coach_recommendation
    score = readiness.score
    hrv_unbalanced = (hrv.status or "").upper() in ("UNBALANCED", "LOW", "POOR")
    if score is not None:
        if score >= 75 and not hrv_unbalanced:
            intensity: Literal["high_intensity", "moderate_steady", "easy_recovery", "rest"] = (
                "high_intensity"
            )
        elif score >= 50:
            intensity = "moderate_steady"
        elif score >= 25:
            intensity = "easy_recovery"
        else:
            intensity = "rest"
    elif sleep_day.sleep_score is not None or body_battery.current_level is not None:
        s_val = sleep_day.sleep_score or 70
        b_val = body_battery.current_level or 70
        if s_val >= 80 and b_val >= 75 and not hrv_unbalanced:
            intensity = "high_intensity"
        elif s_val >= 65 and b_val >= 50:
            intensity = "moderate_steady"
        elif s_val >= 45 or b_val >= 30:
            intensity = "easy_recovery"
        else:
            intensity = "rest"
    else:
        intensity = "easy_recovery"

    if intensity == "high_intensity":
        rec_text = (
            f"Readiness is high (score {score if score is not None else 'strong'}, "
            f"HRV {hrv.status or 'stable'}, Body Battery {body_battery.current_level or 'charged'}). "
            "Green light for threshold intervals, VO2 max work, or key race-pace sessions."
        )
    elif intensity == "moderate_steady":
        rec_text = (
            f"Moderate readiness (score {score if score is not None else 'moderate'}). "
            "Prioritize Zone 2 aerobic base or controlled tempo efforts; avoid maximal anaerobic spikes."
        )
    elif intensity == "easy_recovery":
        rec_text = (
            "Recovery signals are mixed or partial. Keep today's session strictly in Zone 1/2 easy aerobic "
            "recovery or mobility work to support autonomic rebound."
        )
    else:
        rec_text = (
            "Significant recovery deficit detected. Take a complete rest day, prioritize hydration "
            "and 8+ hours of sleep tonight."
        )

    return CoachDailyBriefing(
        date=cdate,
        unit_system=unit_system,
        readiness=readiness,
        body_battery=body_battery,
        hrv=hrv,
        sleep=sleep_day,
        resting_hr_bpm=resting_hr,
        seven_day_avg_rhr_bpm=seven_day_rhr,
        stress_avg=stress_avg,
        stress_qualifier=str(stress_qual) if stress_qual is not None else None,
        steps_today=steps_today,
        daily_step_goal=step_goal,
        training_status_label=ts_label,
        yesterday_activities=yesterday_acts,
        coach_recommendation=rec_text,
        recommended_intensity=intensity,
    )


def normalize_sleep_and_recovery(
    raw_days: list[dict[str, Any]],
    unit_system: UnitSystem = "metric",
) -> SleepAndRecoveryReport:
    """Normalize a list of daily sleep/recovery dicts into SleepAndRecoveryReport."""
    if not isinstance(raw_days, list) or not raw_days:
        return SleepAndRecoveryReport(
            start_date="unknown",
            end_date="unknown",
            unit_system=unit_system,
            days=[],
            avg_sleep_score=None,
            avg_sleep_hours=None,
            avg_overnight_hrv_ms=None,
            avg_resting_hr_bpm=None,
            recovery_takeaway="No sleep or overnight recovery records available for the requested period.",
        )

    parsed_days = [_parse_sleep_day(d) for d in raw_days if isinstance(d, dict)]
    parsed_days.sort(key=lambda d: d.date)

    start_date = parsed_days[0].date if parsed_days else "unknown"
    end_date = parsed_days[-1].date if parsed_days else "unknown"

    scores = [d.sleep_score for d in parsed_days if d.sleep_score is not None]
    sleep_hours = [
        d.stages.total_sleep_seconds / 3600.0
        for d in parsed_days
        if d.stages.total_sleep_seconds > 0
    ]
    hrvs = [d.avg_overnight_hrv_ms for d in parsed_days if d.avg_overnight_hrv_ms is not None]
    rhrs = [d.resting_hr_bpm for d in parsed_days if d.resting_hr_bpm is not None]

    avg_score = round(sum(scores) / len(scores), 1) if scores else None
    avg_hours = round(sum(sleep_hours) / len(sleep_hours), 2) if sleep_hours else None
    avg_hrv = round(sum(hrvs) / len(hrvs), 1) if hrvs else None
    avg_rhr = round(sum(rhrs) / len(rhrs), 1) if rhrs else None

    if avg_score is not None and avg_score >= 80:
        takeaway = (
            f"Strong sleep architecture averaging {avg_hours or 0:.1f} hrs (score {avg_score}/100) "
            f"with overnight HRV averaging {avg_hrv or 'N/A'} ms — autonomic recovery is well-supported."
        )
    elif avg_score is not None and avg_score >= 65:
        takeaway = (
            f"Adequate sleep recovery averaging {avg_hours or 0:.1f} hrs (score {avg_score}/100). "
            "Aim for an extra 30-45 minutes of sleep before high-load workouts."
        )
    elif avg_score is not None:
        takeaway = (
            f"Suboptimal sleep quality (score {avg_score}/100, {avg_hours or 0:.1f} hrs/night). "
            "Reduce training intensity until sleep duration and nocturnal HRV stabilize."
        )
    else:
        takeaway = "Partial sleep telemetry recorded; wear your Garmin watch overnight for full HRV and stage tracking."

    return SleepAndRecoveryReport(
        start_date=start_date,
        end_date=end_date,
        unit_system=unit_system,
        days=parsed_days,
        avg_sleep_score=avg_score,
        avg_sleep_hours=avg_hours,
        avg_overnight_hrv_ms=avg_hrv,
        avg_resting_hr_bpm=avg_rhr,
        recovery_takeaway=takeaway,
    )


def normalize_training_status_and_load(
    raw: dict[str, Any],
    unit_system: UnitSystem = "metric",
) -> TrainingStatusAndLoadReport:
    """Normalize raw training status, VO2 max, ACWR load, endurance, and hill scores."""
    if not isinstance(raw, dict):
        raw = {}

    ts = _as_dict(raw.get("training_status")) if "training_status" in raw else raw
    tr = _as_dict(raw.get("training_readiness"))
    max_metrics = _as_dict(raw.get("max_metrics"))
    user_summary = _as_dict(raw.get("user_summary"))

    cdate = str(
        _first_not_none(
            raw.get("date"),
            ts.get("calendarDate"),
            user_summary.get("calendarDate"),
            date.today().isoformat(),
        )
    )

    status_key, status_feedback = _extract_training_status_key(ts)

    # VO2 Max
    vo2_root = _as_dict(
        _first_not_none(ts.get("mostRecentVO2Max"), max_metrics.get("mostRecentVO2Max"), max_metrics)
    )
    vo2_generic = _as_dict(vo2_root.get("generic"))
    vo2_cycling_dto = _as_dict(vo2_root.get("cycling"))

    vo2_run = _to_float(
        _first_not_none(
            ts.get("vo2MaxRunning"),
            vo2_generic.get("vo2MaxPreciseValue"),
            vo2_generic.get("vo2MaxValue"),
            user_summary.get("vo2Max"),
        ),
        1,
    )
    vo2_bike = _to_float(
        _first_not_none(
            ts.get("vo2MaxCycling"),
            vo2_cycling_dto.get("vo2MaxPreciseValue"),
            vo2_cycling_dto.get("vo2MaxValue"),
        ),
        1,
    )

    # Fitness Age
    fa_raw = _first_not_none(raw.get("fitness_age"), ts.get("fitnessAge"))
    fa_dict = _as_dict(fa_raw)
    fitness_age = _to_int(
        _first_not_none(
            fa_dict.get("fitnessAge"),
            fa_raw if isinstance(fa_raw, (int, float)) else None,
            vo2_generic.get("fitnessAge"),
        )
    )
    chrono_age = _to_int(_first_not_none(fa_dict.get("chronologicalAge"), ts.get("chronologicalAge")))

    # Recovery time
    rec_mins = _to_float(_first_not_none(tr.get("recoveryTime"), ts.get("recoveryTime")))
    rec_hours_explicit = _to_float(
        _first_not_none(tr.get("recoveryTimeInHours"), ts.get("recoveryTimeHours"))
    )
    recovery_hours = (
        round(rec_hours_explicit, 1)
        if rec_hours_explicit is not None
        else (round(rec_mins / 60.0, 1) if rec_mins is not None else None)
    )

    # Acute/Chronic Load & Balance
    mrts = _as_dict(ts.get("mostRecentTrainingStatus"))
    latest_map = _as_dict(mrts.get("latestTrainingStatusData"))
    first_status_device = _as_dict(next(iter(latest_map.values()))) if latest_map else {}
    acute_dto = _as_dict(first_status_device.get("acuteTrainingLoadDTO"))

    mrlb = _as_dict(ts.get("mostRecentTrainingLoadBalance"))
    balance_map = _as_dict(mrlb.get("metricsTrainingLoadBalanceDTOMap"))
    first_balance_device = _as_dict(next(iter(balance_map.values()))) if balance_map else {}

    acute_load = _to_float(
        _first_not_none(
            ts.get("acuteLoad"),
            acute_dto.get("dailyTrainingLoadAcute"),
            tr.get("acuteLoad"),
        ),
        1,
    )
    chronic_load = _to_float(
        _first_not_none(
            ts.get("chronicLoad"),
            acute_dto.get("dailyTrainingLoadChronic"),
        ),
        1,
    )
    load_ratio = _to_float(
        _first_not_none(
            ts.get("loadRatio"),
            acute_dto.get("dailyAcuteChronicWorkloadRatio"),
            (acute_load / chronic_load) if (acute_load and chronic_load and chronic_load > 0) else None,
        ),
        2,
    )
    acwr_status = _first_not_none(ts.get("acwrStatus"), acute_dto.get("acwrStatus"))
    if acwr_status is None and load_ratio is not None:
        if 0.8 <= load_ratio <= 1.3:
            acwr_status = "OPTIMAL"
        elif load_ratio > 1.3:
            acwr_status = "HIGH"
        else:
            acwr_status = "LOW"

    low_aerobic = _to_float(
        _first_not_none(
            ts.get("lowAerobicLoad"),
            first_balance_device.get("monthlyLoadAerobicLow"),
        ),
        1,
    )
    high_aerobic = _to_float(
        _first_not_none(
            ts.get("highAerobicLoad"),
            first_balance_device.get("monthlyLoadAerobicHigh"),
        ),
        1,
    )
    anaerobic = _to_float(
        _first_not_none(
            ts.get("anaerobicLoad"),
            first_balance_device.get("monthlyLoadAnaerobic"),
        ),
        1,
    )
    load_focus = _first_not_none(
        ts.get("loadFocus"),
        first_balance_device.get("trainingBalanceFeedbackPhrase"),
    )

    load_metrics = TrainingLoadMetrics(
        acute_load=acute_load,
        chronic_load=chronic_load,
        load_ratio=load_ratio,
        acwr_status=str(acwr_status) if acwr_status is not None else None,
        low_aerobic_load=low_aerobic,
        high_aerobic_load=high_aerobic,
        anaerobic_load=anaerobic,
        load_focus=str(load_focus) if load_focus is not None else None,
    )

    # Endurance Score
    end_raw = _first_not_none(raw.get("endurance_score"), ts.get("enduranceScore"))
    end_dict = _as_dict(end_raw)
    endurance_score = _to_int(
        _first_not_none(
            end_dict.get("overallScore"),
            end_dict.get("score"),
            end_raw if isinstance(end_raw, (int, float)) else None,
        )
    )
    endurance_class = _first_not_none(
        end_dict.get("classification"),
        end_dict.get("classificationKey"),
        ts.get("enduranceClassification"),
    )

    # Hill Score
    hill_raw = _first_not_none(raw.get("hill_score"), ts.get("hillScore"))
    hill_dict = _as_dict(hill_raw)
    hill_score = _to_int(
        _first_not_none(
            hill_dict.get("overallScore"),
            hill_dict.get("score"),
            hill_raw if isinstance(hill_raw, (int, float)) else None,
        )
    )
    hill_strength = _to_int(
        _first_not_none(hill_dict.get("strengthScore"), ts.get("hillStrengthScore"))
    )
    hill_endurance = _to_int(
        _first_not_none(hill_dict.get("enduranceScore"), ts.get("hillEnduranceScore"))
    )

    # Coach load assessment
    if load_ratio is not None:
        if 0.8 <= load_ratio <= 1.3:
            assessment = (
                f"Training status is {status_key or 'ACTIVE'} with an optimal ACWR of {load_ratio:.2f} "
                f"(Acute {acute_load:.0f} / Chronic {chronic_load:.0f}). "
                "Workload progression is in the sweet spot for progressive fitness gains."
            )
        elif load_ratio > 1.3:
            assessment = (
                f"ACWR is elevated at {load_ratio:.2f} (Acute {acute_load:.0f} vs. Chronic {chronic_load:.0f}). "
                "Monitor recovery closely and avoid stacking consecutive high-intensity days."
            )
        else:
            assessment = (
                f"ACWR is low at {load_ratio:.2f}. Training load is below chronic baseline — "
                "suitable for a taper/deload week or ready to gradually build volume."
            )
    else:
        assessment = (
            f"Training status: {status_key or 'INSUFFICIENT_DATA'}. "
            "Continue recording workouts with heart rate/power to establish acute and chronic load baselines."
        )

    return TrainingStatusAndLoadReport(
        date=cdate,
        training_status_key=status_key,
        training_status_feedback=status_feedback,
        vo2_max_running=vo2_run,
        vo2_max_cycling=vo2_bike,
        fitness_age=fitness_age,
        chronological_age=chrono_age,
        recovery_time_hours=recovery_hours,
        load=load_metrics,
        endurance_score=endurance_score,
        endurance_classification=str(endurance_class) if endurance_class is not None else None,
        hill_score=hill_score,
        hill_strength_score=hill_strength,
        hill_endurance_score=hill_endurance,
        coach_load_assessment=assessment,
    )


def normalize_activities_list(
    raw_activities: list[dict[str, Any]],
    unit_system: UnitSystem = "metric",
) -> list[ActivitySummary]:
    """Normalize a list of raw Garmin activity dicts into a list of ActivitySummary models."""
    if not isinstance(raw_activities, list):
        return []
    return [
        _normalize_single_activity(act, unit_system=unit_system)
        for act in raw_activities
        if isinstance(act, dict)
    ]


def _parse_zone_distribution(
    raw_zones: Any,
    fallback_total_seconds: float = 0.0,
) -> list[ZoneDistributionItem]:
    """Parse Garmin hrTimeInZones or powerTimeInZones into ZoneDistributionItem list."""
    if not isinstance(raw_zones, list) or not raw_zones:
        return []

    items_raw = [z for z in raw_zones if isinstance(z, dict)]
    if not items_raw:
        return []

    total_secs = sum(
        _to_float(_first_not_none(z.get("secsInZone"), z.get("duration_seconds"), z.get("duration"))) or 0.0
        for z in items_raw
    )
    denom = total_secs if total_secs > 0 else fallback_total_seconds

    default_names = {
        1: "Zone 1 (Easy / Recovery)",
        2: "Zone 2 (Aerobic Base)",
        3: "Zone 3 (Tempo / Aerobic)",
        4: "Zone 4 (Threshold)",
        5: "Zone 5 (VO2 Max / Anaerobic)",
    }

    parsed: list[ZoneDistributionItem] = []
    for idx, z in enumerate(items_raw, start=1):
        z_num = _to_int(_first_not_none(z.get("zoneNumber"), z.get("zone_number"), idx)) or idx
        secs = (
            _to_float(
                _first_not_none(z.get("secsInZone"), z.get("duration_seconds"), z.get("duration")),
                1,
            )
            or 0.0
        )
        pct = round((secs / denom) * 100.0, 1) if denom > 0 else (_to_float(z.get("percentage"), 1) or 0.0)
        low_b = _to_float(_first_not_none(z.get("zoneLowBoundary"), z.get("low_boundary")))
        high_b = _to_float(_first_not_none(z.get("zoneHighBoundary"), z.get("high_boundary")))
        z_name = _first_not_none(z.get("zoneName"), z.get("zone_name"), default_names.get(z_num))

        parsed.append(
            ZoneDistributionItem(
                zone_number=z_num,
                zone_name=str(z_name) if z_name is not None else None,
                low_boundary=int(low_b) if (low_b is not None and low_b.is_integer()) else low_b,
                high_boundary=int(high_b) if (high_b is not None and high_b.is_integer()) else high_b,
                duration_seconds=secs,
                duration_formatted=format_duration(secs),
                percentage=pct,
            )
        )

    parsed.sort(key=lambda item: item.zone_number)
    return parsed


def normalize_activity_details(
    raw: dict[str, Any],
    unit_system: UnitSystem = "metric",
) -> ActivityDetailsReport:
    """Normalize raw deep-dive activity telemetry into ActivityDetailsReport."""
    if not isinstance(raw, dict):
        raw = {}

    summary_raw = _as_dict(raw.get("summary")) if "summary" in raw else raw
    details_raw = _as_dict(raw.get("details"))

    # Merge top-level identifiers with summary_raw so _normalize_single_activity sees everything
    merged_summary: dict[str, Any] = {}
    merged_summary.update(details_raw)
    merged_summary.update(summary_raw)
    if "activity_id" in raw and "activityId" not in merged_summary:
        merged_summary["activityId"] = raw["activity_id"]

    summary = _normalize_single_activity(merged_summary, unit_system=unit_system)

    # Extract laps
    splits_obj = raw.get("splits")
    typed_splits_obj = raw.get("typed_splits")
    raw_laps: list[dict[str, Any]] = []
    for candidate in (
        raw.get("lapDTOs"),
        splits_obj.get("lapDTOs") if isinstance(splits_obj, dict) else splits_obj,
        summary_raw.get("lapDTOs"),
        details_raw.get("lapDTOs"),
        typed_splits_obj.get("splits") if isinstance(typed_splits_obj, dict) else typed_splits_obj,
    ):
        if isinstance(candidate, list) and candidate:
            raw_laps = [lap for lap in candidate if isinstance(lap, dict)]
            break

    dist_unit = "mi" if unit_system == "imperial" else "km"
    elev_unit = "ft" if unit_system == "imperial" else "m"

    laps: list[LapSplitSummary] = []
    for idx, lap in enumerate(raw_laps, start=1):
        lap_idx = _to_int(_first_not_none(lap.get("lapIndex"), lap.get("lap_index"), idx)) or idx
        lap_dur = (
            _to_float(
                _first_not_none(lap.get("duration"), lap.get("movingDuration"), lap.get("duration_seconds")),
                1,
            )
            or 0.0
        )
        lap_dist = meters_to_distance(_to_float(lap.get("distance")), unit_system)
        lap_speed = _to_float(_first_not_none(lap.get("averageSpeed"), lap.get("avg_speed_mps")), 4)
        lap_pace = format_pace(lap_speed, unit_system) if lap_speed and lap_speed > 0 else None
        lap_hr = _to_int(_first_not_none(lap.get("averageHR"), lap.get("avg_hr_bpm")))
        lap_max_hr = _to_int(_first_not_none(lap.get("maxHR"), lap.get("max_hr_bpm")))
        lap_power = _to_float(
            _first_not_none(lap.get("averagePower"), lap.get("avgPower"), lap.get("avg_power_watts")),
            1,
        )
        lap_cadence = _to_float(
            _first_not_none(
                lap.get("averageRunCadence"),
                lap.get("averageRunningCadenceInStepsPerMinute"),
                lap.get("averageBikeCadence"),
                lap.get("avgCadence"),
                lap.get("avg_cadence_spm"),
            ),
            1,
        )
        lap_gain = meters_to_elevation(_to_float(lap.get("elevationGain")), unit_system)
        lap_loss = meters_to_elevation(_to_float(lap.get("elevationLoss")), unit_system)
        intensity = _first_not_none(
            lap.get("intensityType"),
            lap.get("splitType"),
            lap.get("intensity_type"),
        )

        laps.append(
            LapSplitSummary(
                lap_index=lap_idx,
                distance=lap_dist,
                distance_unit=dist_unit,
                duration_seconds=lap_dur,
                duration_formatted=format_duration(lap_dur),
                avg_pace=lap_pace,
                avg_speed_mps=lap_speed,
                avg_hr_bpm=lap_hr,
                max_hr_bpm=lap_max_hr,
                avg_power_watts=lap_power,
                avg_cadence_spm=lap_cadence,
                elevation_gain=lap_gain,
                elevation_loss=lap_loss,
                elevation_unit=elev_unit,
                intensity_type=str(intensity) if intensity is not None else None,
            )
        )

    # Extract HR zones and Power/Pace zones
    raw_hr_zones = _first_not_none(
        raw.get("hr_zones") if isinstance(raw.get("hr_zones"), list) and raw.get("hr_zones") else None,
        raw.get("hrTimeInZones"),
        summary_raw.get("hrTimeInZones"),
        details_raw.get("hrTimeInZones"),
    )
    hr_zones = _parse_zone_distribution(raw_hr_zones, fallback_total_seconds=summary.duration_seconds)

    raw_power_zones = _first_not_none(
        raw.get("power_or_pace_zones"),
        raw.get("powerTimeInZones"),
        summary_raw.get("powerTimeInZones"),
        details_raw.get("powerTimeInZones"),
        raw.get("paceTimeInZones"),
        summary_raw.get("paceTimeInZones"),
    )
    power_or_pace_zones = _parse_zone_distribution(
        raw_power_zones, fallback_total_seconds=summary.duration_seconds
    )

    # Weather
    weather_raw = _as_dict(
        _first_not_none(
            raw.get("weather") if isinstance(raw.get("weather"), dict) and raw.get("weather") else None,
            raw.get("weatherDTO"),
            summary_raw.get("weatherDTO"),
            details_raw.get("weatherDTO"),
        )
    )
    weather: WeatherSummary | None = None
    if weather_raw:
        temp_c = _to_float(
            _first_not_none(weather_raw.get("temperatureC"), weather_raw.get("temp_c")), 1
        )
        temp_f = _to_float(
            _first_not_none(weather_raw.get("temp"), weather_raw.get("temp_f")), 1
        )
        if temp_c is None and temp_f is not None:
            temp_c = round((temp_f - 32.0) * 5.0 / 9.0, 1)
        elif temp_f is None and temp_c is not None:
            temp_f = round(temp_c * 9.0 / 5.0 + 32.0, 1)

        app_temp_c = _to_float(
            _first_not_none(
                weather_raw.get("apparentTemperatureC"),
                weather_raw.get("apparent_temp_c"),
            ),
            1,
        )
        if app_temp_c is None and weather_raw.get("apparentTemp") is not None:
            app_f = _to_float(weather_raw.get("apparentTemp"))
            if app_f is not None:
                app_temp_c = round((app_f - 32.0) * 5.0 / 9.0, 1)

        weather_type_dto = _as_dict(weather_raw.get("weatherTypeDTO"))
        cond = _first_not_none(
            weather_type_dto.get("desc"),
            weather_raw.get("weather_Condition"),
            weather_raw.get("weather_condition"),
            weather_raw.get("weatherCondition"),
        )

        weather = WeatherSummary(
            temp_c=temp_c,
            temp_f=temp_f,
            apparent_temp_c=app_temp_c,
            relative_humidity_pct=_to_int(
                _first_not_none(
                    weather_raw.get("relativeHumidity"), weather_raw.get("relative_humidity_pct")
                )
            ),
            wind_speed_kph=_to_float(
                _first_not_none(weather_raw.get("windSpeed"), weather_raw.get("wind_speed_kph")), 1
            ),
            weather_Condition=str(cond) if cond is not None else None,
        )

    # Cardiac drift & Pacing assessment
    interval_laps = [
        lap
        for lap in laps
        if (lap.intensity_type or "").upper() in ("INTERVAL", "ACTIVE") and lap.avg_hr_bpm
    ]
    target_laps = interval_laps if len(interval_laps) >= 2 else [lap for lap in laps if lap.avg_hr_bpm]

    cardiac_drift_pct: float | None = None
    pacing_assessment: str | None = None
    execution_notes: list[str] = []

    if len(target_laps) >= 2:
        mid = len(target_laps) // 2
        first_hr = sum(lap.avg_hr_bpm or 0 for lap in target_laps[:mid]) / mid
        second_hr = sum(lap.avg_hr_bpm or 0 for lap in target_laps[mid:]) / (len(target_laps) - mid)
        if first_hr > 0:
            cardiac_drift_pct = round(((second_hr - first_hr) / first_hr) * 100.0, 2)

        first_spd = [lap.avg_speed_mps for lap in target_laps[:mid] if lap.avg_speed_mps]
        second_spd = [lap.avg_speed_mps for lap in target_laps[mid:] if lap.avg_speed_mps]
        if first_spd and second_spd:
            avg_spd_1 = sum(first_spd) / len(first_spd)
            avg_spd_2 = sum(second_spd) / len(second_spd)
            spd_diff_pct = ((avg_spd_2 - avg_spd_1) / avg_spd_1) * 100.0 if avg_spd_1 > 0 else 0.0
            if spd_diff_pct > 1.0:
                pacing_assessment = "Negative split (progressive speed increase across work intervals)"
            elif spd_diff_pct < -2.0:
                pacing_assessment = "Positive split (pace faded in second half)"
            else:
                pacing_assessment = "Even, well-controlled pacing across work splits"

    if cardiac_drift_pct is not None:
        if cardiac_drift_pct <= 5.0:
            execution_notes.append(
                f"Low cardiac drift ({cardiac_drift_pct:+.1f}%) indicates strong aerobic durability."
            )
        else:
            execution_notes.append(
                f"Elevated cardiac drift ({cardiac_drift_pct:+.1f}%); check hydration, cooling, or pacing."
            )

    if summary.training_effect.primary_benefit:
        execution_notes.append(
            f"Primary physiological stimulus: {summary.training_effect.primary_benefit} "
            f"(Load: {summary.training_effect.training_load or 'N/A'})."
        )

    return ActivityDetailsReport(
        summary=summary,
        laps=laps,
        hr_zones=hr_zones,
        power_or_pace_zones=power_or_pace_zones,
        weather=weather,
        cardiac_drift_pct=cardiac_drift_pct,
        pacing_evenness_assessment=pacing_assessment,
        execution_notes=execution_notes,
    )


def _compute_metric_trend(
    metric_name: str,
    unit: str,
    values: list[float],
    higher_is_better: bool = True,
) -> MetricTrendSummary:
    """Compute first-half vs second-half trend summary for a numeric time series."""
    clean = [float(v) for v in values if v is not None]
    if not clean:
        return MetricTrendSummary(
            metric_name=metric_name,
            unit=unit,
            trend_direction="insufficient_data",
        )

    avg_val = round(sum(clean) / len(clean), 2)
    min_val = round(min(clean), 2)
    max_val = round(max(clean), 2)

    if len(clean) < 2:
        return MetricTrendSummary(
            metric_name=metric_name,
            unit=unit,
            average=avg_val,
            min_val=min_val,
            max_val=max_val,
            first_half_avg=avg_val,
            second_half_avg=avg_val,
            delta=0.0,
            delta_pct=0.0,
            trend_direction="insufficient_data",
        )

    mid = len(clean) // 2
    first_half = clean[:mid]
    second_half = clean[mid:]
    first_avg = round(sum(first_half) / len(first_half), 2)
    second_avg = round(sum(second_half) / len(second_half), 2)
    delta = round(second_avg - first_avg, 2)
    delta_pct = round(((second_avg - first_avg) / first_avg) * 100.0, 2) if first_avg != 0 else 0.0

    if abs(delta_pct) < 2.0:
        direction: Literal["improving", "declining", "stable", "insufficient_data"] = "stable"
    elif higher_is_better:
        direction = "improving" if delta > 0 else "declining"
    else:
        direction = "improving" if delta < 0 else "declining"

    return MetricTrendSummary(
        metric_name=metric_name,
        unit=unit,
        average=avg_val,
        min_val=min_val,
        max_val=max_val,
        first_half_avg=first_avg,
        second_half_avg=second_avg,
        delta=delta,
        delta_pct=delta_pct,
        trend_direction=direction,
    )


def normalize_health_trends(
    raw: dict[str, Any],
    unit_system: UnitSystem = "metric",
) -> HealthTrendsReport:
    """Normalize longitudinal health summaries, sleep, HRV, and activities into HealthTrendsReport."""
    if not isinstance(raw, dict):
        raw = {}

    days_count = _to_int(raw.get("days")) or 28
    start_date = str(raw.get("start_date") or "unknown")
    end_date = str(raw.get("end_date") or "unknown")

    daily_summaries = raw.get("daily_summaries") if isinstance(raw.get("daily_summaries"), list) else []
    sleep_entries = raw.get("sleep_entries") if isinstance(raw.get("sleep_entries"), list) else []
    hrv_entries = raw.get("hrv_entries") if isinstance(raw.get("hrv_entries"), list) else []
    raw_activities = raw.get("activities") if isinstance(raw.get("activities"), list) else []

    rhr_vals: list[float] = []
    steps_vals: list[float] = []
    stress_vals: list[float] = []
    for ds in daily_summaries:
        if not isinstance(ds, dict):
            continue
        rhr = _to_float(ds.get("restingHeartRate"))
        if rhr is not None and rhr > 0:
            rhr_vals.append(rhr)
        steps = _to_float(_first_not_none(ds.get("totalSteps"), ds.get("steps")))
        if steps is not None and steps >= 0:
            steps_vals.append(steps)
        stress = _to_float(_first_not_none(ds.get("averageStressLevel"), ds.get("stressAvg")))
        if stress is not None and stress >= 0:
            stress_vals.append(stress)

    sleep_hours_vals: list[float] = []
    for se in sleep_entries:
        if not isinstance(se, dict):
            continue
        dto = _as_dict(se.get("dailySleepDTO")) if "dailySleepDTO" in se else se
        sec = _to_float(_first_not_none(dto.get("sleepTimeSeconds"), dto.get("totalSleepSeconds")))
        if sec is not None and sec > 0:
            sleep_hours_vals.append(round(sec / 3600.0, 2))
        if not rhr_vals:
            s_rhr = _to_float(_first_not_none(dto.get("restingHeartRate"), se.get("restingHeartRate")))
            if s_rhr is not None and s_rhr > 0:
                rhr_vals.append(s_rhr)

    hrv_vals: list[float] = []
    for he in hrv_entries:
        if not isinstance(he, dict):
            continue
        hs = _as_dict(he.get("hrvSummary")) if "hrvSummary" in he else he
        h_val = _to_float(_first_not_none(hs.get("lastNightAvg"), hs.get("weeklyAvg")))
        if h_val is not None and h_val > 0:
            hrv_vals.append(h_val)

    rhr_trend = _compute_metric_trend("Resting Heart Rate", "bpm", rhr_vals, higher_is_better=False)
    hrv_trend = _compute_metric_trend("Overnight HRV", "ms", hrv_vals, higher_is_better=True)
    sleep_trend = _compute_metric_trend("Sleep Duration", "hours", sleep_hours_vals, higher_is_better=True)
    steps_trend = _compute_metric_trend("Daily Steps", "steps", steps_vals, higher_is_better=True)
    stress_trend = _compute_metric_trend("Daily Stress", "score", stress_vals, higher_is_better=False)

    activities = normalize_activities_list(raw_activities, unit_system=unit_system)
    total_acts = len(activities)
    total_hours = round(sum(a.duration_seconds for a in activities) / 3600.0, 2)
    total_dist = round(sum(a.distance or 0.0 for a in activities), 2)
    dist_unit = "mi" if unit_system == "imperial" else "km"
    weeks = max(days_count / 7.0, 1.0)
    weekly_avg_hours = round(total_hours / weeks, 2)

    breakdown: dict[str, int] = {}
    for a in activities:
        breakdown[a.activity_type] = breakdown.get(a.activity_type, 0) + 1

    flags: list[str] = []
    if rhr_trend.trend_direction == "declining":
        flags.append(f"Resting HR is trending upward (+{rhr_trend.delta} bpm) — monitor for fatigue.")
    if hrv_trend.trend_direction == "declining":
        flags.append(f"Overnight HRV is declining ({hrv_trend.delta} ms) — prioritize recovery.")
    if sleep_trend.average is not None and sleep_trend.average < 7.0:
        flags.append(f"Average sleep ({sleep_trend.average} hrs) is below the 7.5+ hr endurance target.")
    if not flags:
        flags.append("Autonomic biomarkers (RHR, HRV, sleep, stress) are stable and well-regulated.")

    return HealthTrendsReport(
        days=days_count,
        start_date=start_date,
        end_date=end_date,
        unit_system=unit_system,
        rhr_trend=rhr_trend,
        hrv_trend=hrv_trend,
        sleep_hours_trend=sleep_trend,
        daily_steps_trend=steps_trend,
        stress_trend=stress_trend,
        total_activities_count=total_acts,
        total_training_duration_hours=total_hours,
        total_training_distance=total_dist,
        distance_unit=dist_unit,
        weekly_volume_avg_hours=weekly_avg_hours,
        activity_type_breakdown=breakdown,
        coach_flags=flags,
    )


def normalize_body_composition_and_biometrics(
    raw: dict[str, Any],
    unit_system: UnitSystem = "metric",
) -> BodyCompositionAndBiometricsReport:
    """Normalize body composition weigh-ins, hydration, and threshold biometrics."""
    if not isinstance(raw, dict):
        raw = {}

    bc = _as_dict(raw.get("body_composition")) if "body_composition" in raw else raw
    start_date = str(_first_not_none(raw.get("start_date"), bc.get("startDate"), "unknown"))
    end_date = str(_first_not_none(raw.get("end_date"), bc.get("endDate"), "unknown"))
    weight_unit = "lbs" if unit_system == "imperial" else "kg"

    raw_list = _first_not_none(
        bc.get("dateWeightList"),
        bc.get("dailyWeightSummaries"),
        raw.get("dateWeightList"),
        [],
    )
    entries: list[BodyCompositionEntry] = []
    if isinstance(raw_list, list):
        for item in raw_list:
            if not isinstance(item, dict):
                continue
            metric_src = _as_dict(item.get("latestWeight")) if "latestWeight" in item else item
            cdate = str(
                _first_not_none(
                    metric_src.get("calendarDate"),
                    item.get("calendarDate"),
                    item.get("date"),
                    "unknown",
                )
            )
            w_raw = _to_float(metric_src.get("weight"))
            w_conv = (
                grams_to_weight(w_raw, unit_system, is_grams=(w_raw > 500))
                if w_raw is not None
                else None
            )
            muscle_raw = _to_float(
                _first_not_none(metric_src.get("muscleMass"), metric_src.get("muscle_mass"))
            )
            muscle_conv = (
                grams_to_weight(muscle_raw, unit_system, is_grams=(muscle_raw > 500))
                if muscle_raw is not None
                else None
            )
            bone_raw = _to_float(
                _first_not_none(metric_src.get("boneMass"), metric_src.get("bone_mass"))
            )
            bone_conv = (
                grams_to_weight(bone_raw, unit_system, is_grams=(bone_raw > 500))
                if bone_raw is not None
                else None
            )

            entries.append(
                BodyCompositionEntry(
                    date=cdate,
                    weight=w_conv,
                    weight_unit=weight_unit,
                    bmi=_to_float(metric_src.get("bmi"), 1),
                    body_fat_pct=_to_float(
                        _first_not_none(metric_src.get("bodyFat"), metric_src.get("body_fat_pct")), 1
                    ),
                    muscle_mass=muscle_conv,
                    bone_mass=bone_conv,
                    body_water_pct=_to_float(
                        _first_not_none(metric_src.get("bodyWater"), metric_src.get("body_water_pct")),
                        1,
                    ),
                )
            )

    # Sort chronologically ascending so entries[-1] is latest and entries[0] is earliest
    entries.sort(key=lambda e: e.date)

    latest_weight: float | None = None
    weight_delta: float | None = None
    weighed_entries = [e for e in entries if e.weight is not None]
    if weighed_entries:
        latest_weight = weighed_entries[-1].weight
        if len(weighed_entries) >= 2 and latest_weight is not None and weighed_entries[0].weight is not None:
            weight_delta = round(latest_weight - weighed_entries[0].weight, 2)
        else:
            weight_delta = 0.0
    else:
        avg_obj = _as_dict(bc.get("totalAverage"))
        w_avg = _to_float(avg_obj.get("weight"))
        if w_avg is not None:
            latest_weight = grams_to_weight(w_avg, unit_system, is_grams=(w_avg > 500))

    # Hydration
    hyd_raw = _as_dict(_first_not_none(raw.get("hydration_data"), bc.get("hydration")))
    avg_hydration = _to_float(
        _first_not_none(
            hyd_raw.get("valueInML"),
            hyd_raw.get("sweatLossInML"),
            raw.get("avg_daily_hydration_ml"),
        ),
        1,
    )

    biometrics = _extract_biometrics(raw, unit_system=unit_system)

    return BodyCompositionAndBiometricsReport(
        start_date=start_date,
        end_date=end_date,
        unit_system=unit_system,
        latest_weight=latest_weight,
        weight_unit=weight_unit,
        weight_delta=weight_delta,
        entries=entries,
        avg_daily_hydration_ml=avg_hydration,
        biometrics=biometrics,
    )


def _parse_zone_configs(raw_zones: Any, default_unit: str) -> list[ZoneConfigItem]:
    """Parse configured training zones (HR, Pace, or Power) into ZoneConfigItem list."""
    if not isinstance(raw_zones, list):
        return []
    zones: list[ZoneConfigItem] = []
    for idx, z in enumerate(raw_zones, start=1):
        if not isinstance(z, dict):
            continue
        z_num = _to_int(_first_not_none(z.get("zoneNumber"), z.get("zone_number"), idx)) or idx
        name = str(_first_not_none(z.get("name"), z.get("zoneName"), f"Zone {z_num}"))
        low = _to_float(_first_not_none(z.get("lowerBound"), z.get("lower_bound"), 0)) or 0.0
        high = _to_float(_first_not_none(z.get("upperBound"), z.get("upper_bound"), 0)) or 0.0
        unit = str(_first_not_none(z.get("unit"), default_unit))
        zones.append(
            ZoneConfigItem(
                zone_number=z_num,
                name=name,
                lower_bound=int(low) if low.is_integer() else low,
                upper_bound=int(high) if high.is_integer() else high,
                unit=unit,
            )
        )
    zones.sort(key=lambda item: item.zone_number)
    return zones


def normalize_athlete_profile(
    raw: dict[str, Any],
    unit_system: UnitSystem = "metric",
) -> AthleteProfileReport:
    """Normalize athlete profile, biometrics, configured training zones, and personal records."""
    if not isinstance(raw, dict):
        raw = {}

    user_prof = _as_dict(raw.get("user_profile")) if "user_profile" in raw else raw
    user_settings = _as_dict(raw.get("user_settings"))
    inner_prof = _as_dict(user_prof.get("userProfile"))
    user_data = _as_dict(
        _first_not_none(
            user_prof.get("userData"),
            user_settings.get("userData"),
            raw.get("userData"),
        )
    )

    full_name = _first_not_none(
        raw.get("full_name"),
        user_prof.get("fullName"),
        inner_prof.get("fullName"),
        raw.get("fullName"),
    )
    display_name = _first_not_none(
        raw.get("display_name"),
        user_prof.get("displayName"),
        inner_prof.get("displayName"),
        inner_prof.get("userName"),
        raw.get("displayName"),
    )
    gender = _first_not_none(user_data.get("gender"), user_prof.get("gender"), raw.get("gender"))
    birth_date = _first_not_none(
        user_data.get("birthDate"), user_prof.get("birthDate"), raw.get("birthDate")
    )

    w_raw = _to_float(_first_not_none(user_data.get("weight"), user_prof.get("weight"), raw.get("weight")))
    weight = (
        grams_to_weight(w_raw, unit_system, is_grams=(w_raw > 500)) if w_raw is not None else None
    )
    weight_unit = "lbs" if unit_system == "imperial" else "kg"

    height_cm = _to_float(
        _first_not_none(user_data.get("height"), user_prof.get("height"), raw.get("height")), 1
    )

    biometrics = _extract_biometrics(raw, unit_system=unit_system)

    hr_zones = _parse_zone_configs(
        _first_not_none(user_prof.get("hrZones"), user_settings.get("hrZones"), raw.get("hrZones")),
        "bpm",
    )
    pace_zones = _parse_zone_configs(
        _first_not_none(
            user_prof.get("paceZones"), user_settings.get("paceZones"), raw.get("paceZones")
        ),
        "m/s",
    )
    power_zones = _parse_zone_configs(
        _first_not_none(
            user_prof.get("powerZones"), user_settings.get("powerZones"), raw.get("powerZones")
        ),
        "W",
    )

    raw_prs = _first_not_none(
        raw.get("personal_records") if isinstance(raw.get("personal_records"), list) and raw.get("personal_records") else None,
        user_prof.get("personalRecords"),
        raw.get("personalRecords"),
        [],
    )
    personal_records: list[PersonalRecordItem] = []
    if isinstance(raw_prs, list):
        for pr in raw_prs:
            if not isinstance(pr, dict):
                continue
            t_key = str(_first_not_none(pr.get("typeKey"), pr.get("type_key"), pr.get("typeId"), "record"))
            act_type = _first_not_none(pr.get("activityType"), pr.get("activity_type"))
            val = _to_float(pr.get("value"))
            fmt_val = pr.get("formatted_value") or pr.get("formattedValue")
            if not fmt_val:
                if val is not None and ("fastest" in t_key.lower() or "time" in t_key.lower() or val > 60):
                    fmt_val = format_duration(val)
                elif val is not None:
                    fmt_val = f"{val:g}"
                else:
                    fmt_val = "N/A"
            achieved = _first_not_none(
                pr.get("achieved_date"),
                pr.get("actStartDateTimeInGMTFormatted"),
                pr.get("prStartTimeGmtFormatted"),
            )
            achieved_str = str(achieved)[:10] if achieved is not None else None
            personal_records.append(
                PersonalRecordItem(
                    type_key=t_key,
                    activity_type=str(act_type) if act_type is not None else None,
                    value=val,
                    formatted_value=str(fmt_val),
                    achieved_date=achieved_str,
                )
            )

    return AthleteProfileReport(
        full_name=str(full_name) if full_name is not None else None,
        display_name=str(display_name) if display_name is not None else None,
        unit_system=unit_system,
        gender=str(gender) if gender is not None else None,
        birth_date=str(birth_date) if birth_date is not None else None,
        weight=weight,
        weight_unit=weight_unit,
        height_cm=height_cm,
        biometrics=biometrics,
        hr_zones=hr_zones,
        pace_zones=pace_zones,
        power_zones=power_zones,
        personal_records=personal_records,
    )


# ---------------------------------------------------------------------------
# 4. Structured Workout Builder
# ---------------------------------------------------------------------------

_SPORT_TYPE_MAP: dict[str, dict[str, Any]] = {
    "running": {"sportTypeId": 1, "sportTypeKey": "running", "displayOrder": 1},
    "cycling": {"sportTypeId": 2, "sportTypeKey": "cycling", "displayOrder": 2},
    "swimming": {"sportTypeId": 4, "sportTypeKey": "swimming", "displayOrder": 3},
    "strength": {"sportTypeId": 5, "sportTypeKey": "strength_training", "displayOrder": 4},
    "cardio": {"sportTypeId": 6, "sportTypeKey": "cardio_training", "displayOrder": 5},
}

_STEP_TYPE_MAP: dict[str, dict[str, Any]] = {
    "warmup": {"stepTypeId": 1, "stepTypeKey": "warmup", "displayOrder": 1},
    "cooldown": {"stepTypeId": 2, "stepTypeKey": "cooldown", "displayOrder": 2},
    "interval": {"stepTypeId": 3, "stepTypeKey": "interval", "displayOrder": 3},
    "recovery": {"stepTypeId": 4, "stepTypeKey": "recovery", "displayOrder": 4},
    "rest": {"stepTypeId": 5, "stepTypeKey": "rest", "displayOrder": 5},
    "repeat": {"stepTypeId": 6, "stepTypeKey": "repeat", "displayOrder": 6},
}

_CONDITION_TYPE_MAP: dict[str, dict[str, Any]] = {
    "lap.button": {
        "conditionTypeId": 1,
        "conditionTypeKey": "lap.button",
        "displayOrder": 1,
        "displayable": True,
    },
    "time": {
        "conditionTypeId": 2,
        "conditionTypeKey": "time",
        "displayOrder": 2,
        "displayable": True,
    },
    "distance": {
        "conditionTypeId": 3,
        "conditionTypeKey": "distance",
        "displayOrder": 3,
        "displayable": True,
    },
    "iterations": {
        "conditionTypeId": 7,
        "conditionTypeKey": "iterations",
        "displayOrder": 7,
        "displayable": False,
    },
}

_TARGET_TYPE_MAP: dict[str, dict[str, Any]] = {
    "no.target": {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target", "displayOrder": 1},
    "power.zone": {"workoutTargetTypeId": 2, "workoutTargetTypeKey": "power.zone", "displayOrder": 2},
    "cadence": {"workoutTargetTypeId": 3, "workoutTargetTypeKey": "cadence", "displayOrder": 3},
    "heart.rate.zone": {
        "workoutTargetTypeId": 4,
        "workoutTargetTypeKey": "heart.rate.zone",
        "displayOrder": 4,
    },
    "pace.zone": {"workoutTargetTypeId": 6, "workoutTargetTypeKey": "pace.zone", "displayOrder": 6},
}


def _describe_step_target(step: WorkoutStepInput, unit_system: UnitSystem) -> str:
    """Create a human-readable target description for a workout step."""
    if step.target_type == "no.target":
        return "open target"
    if step.target_zone_number is not None:
        return f"{step.target_type} Z{step.target_zone_number}"
    if step.target_low is not None and step.target_high is not None:
        if step.target_type == "pace.zone":
            p_low = format_pace(step.target_low, unit_system) or f"{step.target_low} m/s"
            p_high = format_pace(step.target_high, unit_system) or f"{step.target_high} m/s"
            return f"Pace {p_low} to {p_high}"
        return f"{step.target_type} {step.target_low:g}-{step.target_high:g}"
    return step.target_type


def _build_step_dto(
    step: WorkoutStepInput,
    step_order: int,
    sport_type: str,
    unit_system: UnitSystem,
) -> tuple[dict[str, Any], int, float, float, str]:
    """Build a Garmin step DTO and return (dto, next_order, est_seconds, est_meters, summary_line)."""
    default_speed = 8.0 if sport_type == "cycling" else 3.4

    if step.step_type == "repeat" or step.repeat_steps:
        iterations = max(1, int(step.duration_value or 1))
        group_order = step_order
        current_order = step_order + 1
        child_dtos: list[dict[str, Any]] = []
        child_secs = 0.0
        child_meters = 0.0
        child_summaries: list[str] = []

        for child in step.repeat_steps or []:
            c_dto, current_order, c_s, c_m, c_sum = _build_step_dto(
                child, current_order, sport_type, unit_system
            )
            child_dtos.append(c_dto)
            child_secs += c_s
            child_meters += c_m
            child_summaries.append(c_sum)

        dto: dict[str, Any] = {
            "type": "RepeatGroupDTO",
            "stepOrder": group_order,
            "stepType": _STEP_TYPE_MAP["repeat"],
            "numberOfIterations": iterations,
            "endCondition": _CONDITION_TYPE_MAP["iterations"],
            "endConditionValue": float(iterations),
            "workoutSteps": child_dtos,
            "smartRepeat": False,
        }
        total_s = child_secs * iterations
        total_m = child_meters * iterations
        summary_str = f"Repeat {iterations}x: [{' + '.join(child_summaries)}]"
        return dto, current_order, total_s, total_m, summary_str

    step_type_info = _STEP_TYPE_MAP.get(step.step_type, _STEP_TYPE_MAP["interval"])
    cond_info = _CONDITION_TYPE_MAP.get(step.duration_type, _CONDITION_TYPE_MAP["time"])
    target_info = _TARGET_TYPE_MAP.get(step.target_type, _TARGET_TYPE_MAP["no.target"])

    est_speed = default_speed
    if step.target_type == "pace.zone" and step.target_low and step.target_high:
        est_speed = max(0.5, (float(step.target_low) + float(step.target_high)) / 2.0)

    dur_val = float(step.duration_value or 0.0)
    if step.duration_type == "time":
        est_seconds = dur_val
        est_meters = round(dur_val * est_speed, 1) if sport_type in ("running", "cycling", "swimming") else 0.0
        dur_label = format_duration(dur_val)
    elif step.duration_type == "distance":
        est_meters = dur_val
        est_seconds = round(dur_val / est_speed, 1) if est_speed > 0 else 0.0
        conv_dist = meters_to_distance(dur_val, unit_system) or 0.0
        dist_unit = "mi" if unit_system == "imperial" else "km"
        dur_label = f"{conv_dist} {dist_unit} ({int(dur_val)}m)"
    else:
        est_seconds = 0.0
        est_meters = 0.0
        dur_label = "Lap Button"

    dto = {
        "type": "ExecutableStepDTO",
        "stepOrder": step_order,
        "stepType": step_type_info,
        "endCondition": cond_info,
        "endConditionValue": dur_val if step.duration_type in ("time", "distance") else None,
        "targetType": target_info,
        "zoneNumber": step.target_zone_number,
        "targetValueOne": step.target_low,
        "targetValueTwo": step.target_high,
        "description": step.description,
    }
    target_desc = _describe_step_target(step, unit_system)
    summary_line = f"{step.step_type.capitalize()}: {dur_label} @ {target_desc}"
    if step.description:
        summary_line += f" ({step.description})"

    return dto, step_order + 1, est_seconds, est_meters, summary_line


def build_garmin_workout_json(
    workout: StructuredWorkoutInput,
    unit_system: UnitSystem = "metric",
) -> StructuredWorkoutResult:
    """Build a Garmin Connect compatible workout JSON payload from StructuredWorkoutInput."""
    if not isinstance(workout, StructuredWorkoutInput):
        workout = StructuredWorkoutInput.model_validate(workout)

    sport_info = _SPORT_TYPE_MAP.get(workout.sport_type, _SPORT_TYPE_MAP["running"])
    step_dtos: list[dict[str, Any]] = []
    human_summary: list[str] = []
    total_seconds = 0.0
    total_meters = 0.0
    order = 1

    for step in workout.steps:
        dto, order, s_sec, s_met, s_line = _build_step_dto(
            step, order, workout.sport_type, unit_system
        )
        step_dtos.append(dto)
        total_seconds += s_sec
        total_meters += s_met
        human_summary.append(s_line)

    garmin_json: dict[str, Any] = {
        "workoutName": workout.workout_name,
        "description": workout.description or f"Generated by garmin-coach-mcp ({workout.sport_type})",
        "sportType": sport_info,
        "estimatedDurationInSecs": int(round(total_seconds)),
        "estimatedDistanceInMeters": round(total_meters, 1),
        "workoutSegments": [
            {
                "segmentOrder": 1,
                "sportType": sport_info,
                "workoutSteps": step_dtos,
            }
        ],
    }

    return StructuredWorkoutResult(
        workout_name=workout.workout_name,
        sport_type=workout.sport_type,
        total_estimated_duration_seconds=round(total_seconds, 1),
        total_estimated_duration_formatted=format_duration(total_seconds),
        total_estimated_distance_meters=round(total_meters, 1),
        garmin_workout_json=garmin_json,
        uploaded=False,
        uploaded_workout_id=None,
        human_readable_summary=human_summary,
    )
