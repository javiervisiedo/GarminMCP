"""Daily coaching briefing MCP tool for Garmin Coach MCP."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from garmin_coach_mcp.exceptions import GarminCoachError
from garmin_coach_mcp.models.readiness import CoachDailyBriefing
from garmin_coach_mcp.normalizers import normalize_daily_briefing


def _fmt_val(val: Any, suffix: str = "", fallback: str = "N/A") -> str:
    """Format an optional metric value with an optional unit suffix."""
    if val is None:
        return fallback
    return f"{val}{suffix}"


def render_daily_briefing_markdown(briefing: CoachDailyBriefing) -> str:
    """Render a comprehensive human- and LLM-readable Markdown summary for CoachDailyBriefing."""
    r = briefing.readiness
    bb = briefing.body_battery
    hrv = briefing.hrv
    slp = briefing.sleep
    stg = slp.stages

    lines: list[str] = [
        f"# Daily Coach Briefing — {briefing.date}",
        "",
        "## 1. Training Readiness & Coaching Verdict",
        f"- **Readiness Score**: {_fmt_val(r.score, '/100')} ({_fmt_val(r.level)})",
        f"- **Garmin Feedback**: {_fmt_val(r.feedback_short)}",
        f"- **Recovery Time Remaining**: {_fmt_val(r.recovery_time_hours, ' hrs')}",
        f"- **Training Status**: {_fmt_val(briefing.training_status_label)}",
        f"- **Recommended Intensity**: `{briefing.recommended_intensity}`",
        f"- **Coach Recommendation**: {briefing.coach_recommendation}",
    ]

    factors: list[str] = []
    if r.sleep_score_factor_pct is not None:
        factors.append(f"Sleep {r.sleep_score_factor_pct}%")
    if r.recovery_time_factor_pct is not None:
        factors.append(f"Recovery Time {r.recovery_time_factor_pct}%")
    if r.acwr_factor_pct is not None:
        factors.append(f"ACWR Load {r.acwr_factor_pct}%")
    if r.hrv_factor_pct is not None:
        factors.append(f"HRV {r.hrv_factor_pct}%")
    if r.stress_history_factor_pct is not None:
        factors.append(f"Stress History {r.stress_history_factor_pct}%")
    if factors:
        lines.append(f"- **Readiness Factors**: {', '.join(factors)}")

    lines.extend(
        [
            "",
            "## 2. Autonomic Recovery, HRV & Body Battery",
            (
                f"- **Body Battery**: Current {_fmt_val(bb.current_level, '/100')} "
                f"(Charged +{_fmt_val(bb.charged, '', '0')}, Drained -{_fmt_val(bb.drained, '', '0')}, "
                f"Range {_fmt_val(bb.lowest_level)}–{_fmt_val(bb.highest_level)})"
            ),
            (
                f"- **Overnight HRV**: {_fmt_val(hrv.last_night_avg_ms, ' ms')} "
                f"(Status: {_fmt_val(hrv.status)}, 7-Day Avg: {_fmt_val(hrv.weekly_avg_ms, ' ms')}, "
                f"5-Min High: {_fmt_val(hrv.last_night_5min_high_ms, ' ms')})"
            ),
        ]
    )
    if hrv.baseline_low_ms is not None or hrv.baseline_high_ms is not None:
        lines.append(
            f"- **HRV Baseline Range**: {_fmt_val(hrv.baseline_low_ms, ' ms')} – "
            f"{_fmt_val(hrv.baseline_high_ms, ' ms')}"
        )
    lines.extend(
        [
            (
                f"- **Resting Heart Rate (RHR)**: {_fmt_val(briefing.resting_hr_bpm, ' bpm')} "
                f"(7-Day Avg: {_fmt_val(briefing.seven_day_avg_rhr_bpm, ' bpm')})"
            ),
            (
                f"- **Daily Stress**: {_fmt_val(briefing.stress_avg, '/100')} "
                f"({_fmt_val(briefing.stress_qualifier)})"
            ),
            (
                f"- **Steps**: {_fmt_val(briefing.steps_today)} / "
                f"{_fmt_val(briefing.daily_step_goal)}"
            ),
            "",
            "## 3. Overnight Sleep Architecture",
            (
                f"- **Sleep Score**: {_fmt_val(slp.sleep_score, '/100')} "
                f"({_fmt_val(slp.sleep_quality_qualifier)})"
            ),
            (
                f"- **Total Sleep Duration**: {stg.total_sleep_formatted} "
                f"(Deep: {_fmt_val(stg.deep_pct, '%')}, Light: {_fmt_val(stg.light_pct, '%')}, "
                f"REM: {_fmt_val(stg.rem_pct, '%')})"
            ),
            (
                f"- **SpO2 & Respiration**: Avg SpO2 {_fmt_val(slp.avg_spo2_pct, '%')} "
                f"(Low {_fmt_val(slp.lowest_spo2_pct, '%')}) | "
                f"Sleep Respiration {_fmt_val(slp.avg_sleep_respiration_brpm, ' brpm')}"
            ),
            "",
            "## 4. Yesterday's Activities",
        ]
    )

    if not briefing.yesterday_activities:
        lines.append("- Rest day — no recorded activities yesterday.")
    else:
        for act in briefing.yesterday_activities:
            dist_str = (
                f"{act.distance} {act.distance_unit}"
                if act.distance is not None and act.distance > 0
                else "N/A"
            )
            pace_or_power = act.avg_pace or (
                f"{act.avg_power_watts} W" if act.avg_power_watts is not None else "N/A"
            )
            lines.append(
                f"- **{act.activity_name}** (`{act.activity_type}`, ID `{act.activity_id}`): "
                f"{dist_str} in {act.duration_formatted} | Avg HR: {_fmt_val(act.avg_hr_bpm, ' bpm')} | "
                f"Pace/Power: {pace_or_power} | Load: {_fmt_val(act.training_effect.training_load)} "
                f"(AE {_fmt_val(act.training_effect.aerobic_effect)} / "
                f"ANE {_fmt_val(act.training_effect.anaerobic_effect)})"
            )

    return "\n".join(lines)


def get_coach_daily_briefing(
    target_date: str | None = None,
    response_format: Literal["markdown", "json", "hybrid"] = "hybrid",
) -> str:
    """Fetch a complete morning coaching briefing for a single date (defaults to today).

    Coaching Purpose:
        High-level morning readiness aggregator designed to be the first tool called
        in a daily check-in. Synthesizes Training Readiness score & contributors,
        Body Battery (current, charged, drained), overnight Sleep quality & stages,
        Heart Rate Variability (HRV) status vs. personal baseline, Resting Heart Rate
        (RHR vs. 7-day baseline), daily Stress, and yesterday's completed workouts into
        an actionable training intensity prescription (`high_intensity`, `moderate_steady`,
        `easy_recovery`, or `rest`).

    Args:
        target_date: Target ISO calendar date (`YYYY-MM-DD`). Defaults to today if omitted.
        response_format: Output representation: `"markdown"` for human-readable summary,
            `"json"` for compact normalized JSON, or `"hybrid"` (default) for Markdown + JSON.

    Returns:
        Formatted coaching briefing containing readiness score, autonomic recovery metrics,
        sleep architecture, yesterday's training load, and today's recommended workout intensity.
    """
    from garmin_coach_mcp.server import format_error_output, format_tool_output, get_client

    try:
        client = get_client()
        resolved_date = (target_date or "").strip() or date.today().isoformat()
        raw = client.fetch_daily_briefing_raw(target_date=resolved_date)
        unit_system = getattr(client, "unit_system", "metric")
        briefing = normalize_daily_briefing(raw, unit_system=unit_system)
        markdown_summary = render_daily_briefing_markdown(briefing)
        return format_tool_output(markdown_summary, briefing, response_format=response_format)
    except GarminCoachError as exc:
        return format_error_output(
            exc, tool_name="get_coach_daily_briefing", response_format=response_format
        )
    except Exception as exc:
        return format_error_output(
            exc, tool_name="get_coach_daily_briefing", response_format=response_format
        )


import garmin_coach_mcp.server  # noqa: E402, F401
