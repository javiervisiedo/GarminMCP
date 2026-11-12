"""Health, sleep/recovery, training status/load, longitudinal trends, and biometrics MCP tools."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Literal

from garmin_coach_mcp.exceptions import GarminCoachError
from garmin_coach_mcp.models.health import (
    BodyCompositionAndBiometricsReport,
    HealthTrendsReport,
    MetricTrendSummary,
    SleepAndRecoveryReport,
)
from garmin_coach_mcp.models.readiness import TrainingStatusAndLoadReport
from garmin_coach_mcp.normalizers import (
    normalize_body_composition_and_biometrics,
    normalize_health_trends,
    normalize_sleep_and_recovery,
    normalize_training_status_and_load,
)


def _fmt(val: Any, suffix: str = "", fallback: str = "N/A") -> str:
    """Format an optional value with suffix or fallback."""
    if val is None:
        return fallback
    return f"{val}{suffix}"


def _render_sleep_and_recovery_markdown(report: SleepAndRecoveryReport) -> str:
    """Render Markdown summary for SleepAndRecoveryReport."""
    lines: list[str] = [
        f"# Sleep & Recovery Report ({report.start_date} to {report.end_date})",
        "",
        "## Period Summary",
        f"- **Average Sleep Score**: {_fmt(report.avg_sleep_score, '/100')}",
        f"- **Average Sleep Duration**: {_fmt(report.avg_sleep_hours, ' hrs')}",
        f"- **Average Overnight HRV**: {_fmt(report.avg_overnight_hrv_ms, ' ms')}",
        f"- **Average Resting HR**: {_fmt(report.avg_resting_hr_bpm, ' bpm')}",
        f"- **Recovery Takeaway**: {report.recovery_takeaway}",
        "",
        "## Daily Sleep & Autonomic Breakdown",
    ]

    if not report.days:
        lines.append("- No sleep or recovery entries recorded for this period.")
    else:
        for d in report.days:
            stg = d.stages
            lines.append(
                f"### {d.date} — Score: {_fmt(d.sleep_score, '/100')} "
                f"({_fmt(d.sleep_quality_qualifier)}) | Total: {stg.total_sleep_formatted}"
            )
            lines.append(
                f"- **Sleep Stages**: Deep {_fmt(stg.deep_pct, '%')} ({stg.deep_seconds}s) | "
                f"Light {_fmt(stg.light_pct, '%')} ({stg.light_seconds}s) | "
                f"REM {_fmt(stg.rem_pct, '%')} ({stg.rem_seconds}s) | "
                f"Awake {stg.awake_seconds}s"
            )
            lines.append(
                f"- **Autonomic & Vitals**: Overnight HRV {_fmt(d.avg_overnight_hrv_ms, ' ms')} "
                f"({_fmt(d.hrv_status)}, Baseline {_fmt(d.hrv_baseline_low_ms)}–{_fmt(d.hrv_baseline_high_ms)} ms) | "
                f"RHR {_fmt(d.resting_hr_bpm, ' bpm')}"
            )
            lines.append(
                f"- **Body Battery & Respiration**: Charged +{_fmt(d.body_battery_charged, '', '0')} / "
                f"Drained -{_fmt(d.body_battery_drained, '', '0')} "
                f"(Range {_fmt(d.body_battery_low)}–{_fmt(d.body_battery_high)}) | "
                f"SpO2 {_fmt(d.avg_spo2_pct, '%')} (Low {_fmt(d.lowest_spo2_pct, '%')}) | "
                f"Respiration {_fmt(d.avg_sleep_respiration_brpm, ' brpm')}"
            )

    return "\n".join(lines)


def _render_training_status_markdown(report: TrainingStatusAndLoadReport) -> str:
    """Render Markdown summary for TrainingStatusAndLoadReport."""
    ld = report.load
    lines: list[str] = [
        f"# Training Status & Load Analysis — {report.date}",
        "",
        "## 1. Training Status & Aerobic Fitness",
        f"- **Training Status**: {_fmt(report.training_status_key)} ({_fmt(report.training_status_feedback)})",
        f"- **VO2 Max (Running)**: {_fmt(report.vo2_max_running, ' mL/kg/min')}",
        f"- **VO2 Max (Cycling)**: {_fmt(report.vo2_max_cycling, ' mL/kg/min')}",
        (
            f"- **Fitness Age**: {_fmt(report.fitness_age)} "
            f"(Chronological Age: {_fmt(report.chronological_age)})"
        ),
        f"- **Recovery Time Remaining**: {_fmt(report.recovery_time_hours, ' hrs')}",
        "",
        "## 2. Acute vs. Chronic Training Load (ACWR)",
        f"- **Acute Load (7-Day)**: {_fmt(ld.acute_load)}",
        f"- **Chronic Load (28-Day)**: {_fmt(ld.chronic_load)}",
        f"- **Load Ratio (ACWR)**: {_fmt(ld.load_ratio)} ({_fmt(ld.acwr_status)})",
        (
            f"- **Load Balance**: Low Aerobic {_fmt(ld.low_aerobic_load)} | "
            f"High Aerobic {_fmt(ld.high_aerobic_load)} | "
            f"Anaerobic {_fmt(ld.anaerobic_load)} (Focus: {_fmt(ld.load_focus)})"
        ),
        "",
        "## 3. Endurance & Hill Scores",
        f"- **Endurance Score**: {_fmt(report.endurance_score)} ({_fmt(report.endurance_classification)})",
        (
            f"- **Hill Score**: {_fmt(report.hill_score)} "
            f"(Hill Strength: {_fmt(report.hill_strength_score)}, "
            f"Hill Endurance: {_fmt(report.hill_endurance_score)})"
        ),
        "",
        "## 4. Coach Load Assessment",
        f"- {report.coach_load_assessment}",
    ]
    return "\n".join(lines)


def _format_trend_line(t: MetricTrendSummary) -> str:
    """Format a single MetricTrendSummary bullet."""
    delta_str = f"{t.delta:+g}" if t.delta is not None else "N/A"
    pct_str = f"{t.delta_pct:+.1f}%" if t.delta_pct is not None else "N/A"
    return (
        f"- **{t.metric_name}** ({t.unit}): Avg {_fmt(t.average)} "
        f"(Min {_fmt(t.min_val)}, Max {_fmt(t.max_val)}) | "
        f"1st Half {_fmt(t.first_half_avg)} -> 2nd Half {_fmt(t.second_half_avg)} | "
        f"Delta {delta_str} ({pct_str}) -> `{t.trend_direction}`"
    )


def _render_health_trends_markdown(report: HealthTrendsReport) -> str:
    """Render Markdown summary for HealthTrendsReport."""
    lines: list[str] = [
        f"# Longitudinal Health & Training Trends ({report.days} Days: {report.start_date} to {report.end_date})",
        "",
        "## 1. Rolling Biomarker Trends",
        _format_trend_line(report.rhr_trend),
        _format_trend_line(report.hrv_trend),
        _format_trend_line(report.sleep_hours_trend),
        _format_trend_line(report.daily_steps_trend),
        _format_trend_line(report.stress_trend),
        "",
        "## 2. Training Volume Aggregation",
        f"- **Total Activities**: {report.total_activities_count}",
        f"- **Total Training Duration**: {report.total_training_duration_hours} hrs",
        f"- **Total Training Distance**: {report.total_training_distance} {report.distance_unit}",
        f"- **Average Weekly Volume**: {report.weekly_volume_avg_hours} hrs/week",
    ]
    if report.activity_type_breakdown:
        breakdown_str = ", ".join(
            f"{k}: {v}" for k, v in sorted(report.activity_type_breakdown.items())
        )
        lines.append(f"- **Activity Type Breakdown**: {breakdown_str}")

    lines.extend(["", "## 3. Coach Diagnostic Flags"])
    if report.coach_flags:
        for flag in report.coach_flags:
            lines.append(f"- {flag}")
    else:
        lines.append("- All longitudinal physiological markers are within normal tolerances.")

    return "\n".join(lines)


def _render_body_composition_markdown(report: BodyCompositionAndBiometricsReport) -> str:
    """Render Markdown summary for BodyCompositionAndBiometricsReport."""
    bio = report.biometrics
    delta_str = (
        f"{report.weight_delta:+.2f} {report.weight_unit}"
        if report.weight_delta is not None
        else "N/A"
    )
    lines: list[str] = [
        f"# Body Composition & Physiological Biometrics ({report.start_date} to {report.end_date})",
        "",
        "## 1. Weight, Body Composition & Hydration",
        f"- **Latest Weight**: {_fmt(report.latest_weight, f' {report.weight_unit}')}",
        f"- **Weight Delta (Period)**: {delta_str}",
        f"- **Average Daily Hydration**: {_fmt(report.avg_daily_hydration_ml, ' mL')}",
    ]
    if report.entries:
        lines.append(f"- **Recorded Weigh-Ins ({len(report.entries)})**:")
        for entry in report.entries[:10]:
            lines.append(
                f"  - `{entry.date}`: {_fmt(entry.weight, f' {entry.weight_unit}')} | "
                f"Body Fat: {_fmt(entry.body_fat_pct, '%')} | "
                f"Muscle Mass: {_fmt(entry.muscle_mass, f' {entry.weight_unit}')} | "
                f"BMI: {_fmt(entry.bmi)} | Water: {_fmt(entry.body_water_pct, '%')}"
            )
    else:
        lines.append("- No body composition weigh-in entries recorded in this window.")

    lines.extend(
        [
            "",
            "## 2. Physiological Thresholds & Biometrics",
            f"- **Max Heart Rate**: {_fmt(bio.max_hr_bpm, ' bpm')}",
            f"- **Resting Heart Rate**: {_fmt(bio.resting_hr_bpm, ' bpm')}",
            f"- **Lactate Threshold Heart Rate (LTHR)**: {_fmt(bio.lactate_threshold_hr_bpm, ' bpm')}",
            f"- **Lactate Threshold Pace**: {_fmt(bio.lactate_threshold_pace)}",
            f"- **Cycling Functional Threshold Power (FTP)**: {_fmt(bio.ftp_watts, ' W')}",
            f"- **VO2 Max (Running / Cycling)**: {_fmt(bio.vo2_max_running)} / {_fmt(bio.vo2_max_cycling)} mL/kg/min",
        ]
    )
    return "\n".join(lines)


def get_sleep_and_recovery(
    start_date: str | None = None,
    end_date: str | None = None,
    response_format: Literal["markdown", "json", "hybrid"] = "hybrid",
) -> str:
    """Analyze overnight sleep architecture, HRV vs. baseline, SpO2, respiration, and Body Battery recharge.

    Coaching Purpose:
        Evaluates multi-day or single-night sleep quality and autonomic nervous system
        recovery. Useful for diagnosing cumulative sleep debt, suppressed nocturnal HRV,
        elevated sleeping heart rate/respiration (early illness or overreaching markers),
        and poor Body Battery recharge.

    Args:
        start_date: Start ISO date (`YYYY-MM-DD`). If omitted, defaults to a 7-day window
            ending on `end_date` (or today). If provided and `end_date` is omitted, fetches
            that single day.
        end_date: End ISO date (`YYYY-MM-DD`). Defaults to `start_date` when `start_date` is
            explicitly provided, or today when `start_date` is omitted.
        response_format: Output representation: `"markdown"`, `"json"`, or `"hybrid"` (default).

    Returns:
        Formatted sleep & recovery analysis including deep/light/REM/awake sleep stages,
        sleep score, SpO2, respiration rate, overnight HRV + baseline, and Body Battery recharge.
    """
    from garmin_coach_mcp.server import format_error_output, format_tool_output, get_client

    try:
        client = get_client()
        clean_start = (start_date or "").strip() or None
        clean_end = (end_date or "").strip() or None

        if clean_start is None and clean_end is None:
            end_dt = date.today()
            start_dt = end_dt - timedelta(days=6)
            resolved_start = start_dt.isoformat()
            resolved_end = end_dt.isoformat()
        elif clean_start is not None and clean_end is None:
            resolved_start = clean_start
            resolved_end = clean_start
        elif clean_start is None and clean_end is not None:
            end_dt = date.fromisoformat(clean_end)
            start_dt = end_dt - timedelta(days=6)
            resolved_start = start_dt.isoformat()
            resolved_end = clean_end
        else:
            resolved_start = clean_start
            resolved_end = clean_end

        raw_days = client.fetch_sleep_and_recovery_raw(
            start_date=resolved_start, end_date=resolved_end
        )
        unit_system = getattr(client, "unit_system", "metric")
        report = normalize_sleep_and_recovery(raw_days, unit_system=unit_system)
        md = _render_sleep_and_recovery_markdown(report)
        return format_tool_output(md, report, response_format=response_format)
    except GarminCoachError as exc:
        return format_error_output(
            exc, tool_name="get_sleep_and_recovery", response_format=response_format
        )
    except Exception as exc:
        return format_error_output(
            exc, tool_name="get_sleep_and_recovery", response_format=response_format
        )


def get_training_status_and_load(
    target_date: str | None = None,
    response_format: Literal["markdown", "json", "hybrid"] = "hybrid",
) -> str:
    """Retrieve VO2 Max, Acute/Chronic Load (ACWR), Training Status, Recovery Time, Fitness Age, and Endurance/Hill scores.

    Coaching Purpose:
        Quantifies macro- and meso-cycle training load progression and aerobic fitness
        adaptations. Assesses whether the athlete is Productive, Peaking, Maintaining,
        Strained, or Overreaching, inspects Acute-to-Chronic Workload Ratio (ACWR) for
        injury-risk management, and checks low/high aerobic vs. anaerobic load balance.

    Args:
        target_date: Target ISO date (`YYYY-MM-DD`). Defaults to today if omitted.
        response_format: Output representation: `"markdown"`, `"json"`, or `"hybrid"` (default).

    Returns:
        Formatted report of VO2 Max (running/cycling), Acute Load, Chronic Load, ACWR load ratio,
        Training Status, Recovery Time remaining, Fitness Age, Endurance Score, and Hill Score.
    """
    from garmin_coach_mcp.server import format_error_output, format_tool_output, get_client

    try:
        client = get_client()
        resolved_date = (target_date or "").strip() or date.today().isoformat()
        raw = client.fetch_training_status_and_load_raw(target_date=resolved_date)
        unit_system = getattr(client, "unit_system", "metric")
        report = normalize_training_status_and_load(raw, unit_system=unit_system)
        md = _render_training_status_markdown(report)
        return format_tool_output(md, report, response_format=response_format)
    except GarminCoachError as exc:
        return format_error_output(
            exc, tool_name="get_training_status_and_load", response_format=response_format
        )
    except Exception as exc:
        return format_error_output(
            exc, tool_name="get_training_status_and_load", response_format=response_format
        )


def get_health_trends(
    days: int = 28,
    end_date: str | None = None,
    response_format: Literal["markdown", "json", "hybrid"] = "hybrid",
) -> str:
    """Compute longitudinal rolling averages, first-half vs. second-half deltas, and training volume over N days.

    Coaching Purpose:
        Detects multi-week physiological trends and early overtraining signals across
        Resting Heart Rate (RHR), overnight HRV, sleep duration, daily steps, daily stress,
        and total training volume (hours, distance, activity breakdown) over a configurable
        window (e.g., 7, 14, 28, 30, or 90 days).

    Args:
        days: Number of days to aggregate (default `28`). Clamped to a positive integer.
        end_date: End ISO date (`YYYY-MM-DD`) of the analysis window. Defaults to today.
        response_format: Output representation: `"markdown"`, `"json"`, or `"hybrid"` (default).

    Returns:
        Formatted longitudinal trend report with biomarker averages, min/max, 1st-half vs.
        2nd-half deltas, trend directions, training volume totals, and diagnostic coach flags.
    """
    from garmin_coach_mcp.server import format_error_output, format_tool_output, get_client

    try:
        client = get_client()
        resolved_end = (end_date or "").strip() or date.today().isoformat()
        safe_days = max(1, int(days))
        raw = client.fetch_health_trends_raw(days=safe_days, end_date=resolved_end)
        unit_system = getattr(client, "unit_system", "metric")
        report = normalize_health_trends(raw, unit_system=unit_system)
        md = _render_health_trends_markdown(report)
        return format_tool_output(md, report, response_format=response_format)
    except GarminCoachError as exc:
        return format_error_output(
            exc, tool_name="get_health_trends", response_format=response_format
        )
    except Exception as exc:
        return format_error_output(
            exc, tool_name="get_health_trends", response_format=response_format
        )


def get_body_composition_and_biometrics(
    start_date: str | None = None,
    end_date: str | None = None,
    response_format: Literal["markdown", "json", "hybrid"] = "hybrid",
) -> str:
    """Fetch weight trends, body fat %, muscle mass, hydration, and physiological thresholds (LTHR, Max HR, FTP).

    Coaching Purpose:
        Tracks body composition shifts (weight, body fat percentage, skeletal muscle mass,
        body water, BMI), daily hydration intake, and physiological threshold anchors
        (Lactate Threshold Heart Rate & Pace, Max HR, Resting HR, Cycling FTP, VO2 Max)
        used to calibrate training zones and race power/pacing targets.

    Args:
        start_date: Start ISO date (`YYYY-MM-DD`). Defaults to a 30-day window ending on `end_date`.
        end_date: End ISO date (`YYYY-MM-DD`). Defaults to today.
        response_format: Output representation: `"markdown"`, `"json"`, or `"hybrid"` (default).

    Returns:
        Formatted body composition and biometrics report with weight delta, weigh-in history,
        hydration averages, and Lactate Threshold / Max HR / FTP configurations.
    """
    from garmin_coach_mcp.server import format_error_output, format_tool_output, get_client

    try:
        client = get_client()
        resolved_end = (end_date or "").strip() or date.today().isoformat()
        clean_start = (start_date or "").strip() or None
        if clean_start is None:
            end_dt = date.fromisoformat(resolved_end)
            resolved_start = (end_dt - timedelta(days=29)).isoformat()
        else:
            resolved_start = clean_start

        raw = client.fetch_body_composition_and_biometrics_raw(
            start_date=resolved_start, end_date=resolved_end
        )
        unit_system = getattr(client, "unit_system", "metric")
        report = normalize_body_composition_and_biometrics(raw, unit_system=unit_system)
        md = _render_body_composition_markdown(report)
        return format_tool_output(md, report, response_format=response_format)
    except GarminCoachError as exc:
        return format_error_output(
            exc, tool_name="get_body_composition_and_biometrics", response_format=response_format
        )
    except Exception as exc:
        return format_error_output(
            exc, tool_name="get_body_composition_and_biometrics", response_format=response_format
        )


import garmin_coach_mcp.server  # noqa: E402, F401
