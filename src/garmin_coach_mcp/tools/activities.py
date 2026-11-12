"""Activity listing and deep-dive workout analysis MCP tools for Garmin Coach MCP."""

from __future__ import annotations

from typing import Any, Literal

from garmin_coach_mcp.exceptions import GarminCoachError
from garmin_coach_mcp.models.activity import ActivityDetailsReport, ActivitySummary
from garmin_coach_mcp.normalizers import normalize_activities_list, normalize_activity_details


def _fmt(val: Any, suffix: str = "", fallback: str = "N/A") -> str:
    """Format an optional value with suffix or fallback."""
    if val is None:
        return fallback
    return f"{val}{suffix}"


def _render_activities_list_markdown(
    activities: list[ActivitySummary],
    limit: int,
    activity_type: str | None,
    start_date: str | None,
    end_date: str | None,
) -> str:
    """Render Markdown summary for a list of ActivitySummary items."""
    filters: list[str] = [f"limit={limit}"]
    if activity_type:
        filters.append(f"type={activity_type}")
    if start_date:
        filters.append(f"start={start_date}")
    if end_date:
        filters.append(f"end={end_date}")

    lines: list[str] = [
        f"# Recent Garmin Activities ({len(activities)} workouts; {', '.join(filters)})",
        "",
    ]

    if not activities:
        lines.append("No matching activities found for the specified filters.")
        return "\n".join(lines)

    for idx, act in enumerate(activities, start=1):
        dist_str = (
            f"{act.distance} {act.distance_unit}"
            if act.distance is not None and act.distance > 0
            else "N/A"
        )
        te = act.training_effect
        lines.extend(
            [
                f"## {idx}. {act.activity_name} (`{act.activity_type}`) — ID `{act.activity_id}`",
                f"- **Date / Start Time**: {_fmt(act.date)} ({_fmt(act.start_time_local)})",
                f"- **Distance & Duration**: {dist_str} in {act.duration_formatted}",
                (
                    f"- **Pace & Power**: Pace {_fmt(act.avg_pace)} | "
                    f"Avg Power {_fmt(act.avg_power_watts, ' W')} "
                    f"(NP {_fmt(act.normalized_power_watts, ' W')}, Max {_fmt(act.max_power_watts, ' W')})"
                ),
                (
                    f"- **Heart Rate & Cadence**: Avg HR {_fmt(act.avg_hr_bpm, ' bpm')} "
                    f"(Max {_fmt(act.max_hr_bpm, ' bpm')}) | "
                    f"Cadence {_fmt(act.avg_cadence_spm, ' spm')}"
                ),
                (
                    f"- **Elevation & Calories**: +{_fmt(act.elevation_gain, f' {act.elevation_unit}')} / "
                    f"-{_fmt(act.elevation_loss, f' {act.elevation_unit}')} | "
                    f"{_fmt(act.calories, ' kcal')}"
                ),
                (
                    f"- **Training Effect**: Load {_fmt(te.training_load)} | "
                    f"Aerobic {_fmt(te.aerobic_effect)} | "
                    f"Anaerobic {_fmt(te.anaerobic_effect)} | "
                    f"Primary Benefit: {_fmt(te.primary_benefit)}"
                ),
                "",
            ]
        )

    return "\n".join(lines).rstrip()


def _render_activity_details_markdown(report: ActivityDetailsReport) -> str:
    """Render Markdown summary for ActivityDetailsReport."""
    s = report.summary
    te = s.training_effect
    dist_str = (
        f"{s.distance} {s.distance_unit}"
        if s.distance is not None and s.distance > 0
        else "N/A"
    )

    lines: list[str] = [
        f"# Workout Deep-Dive: {s.activity_name} (ID `{s.activity_id}`)",
        "",
        "## 1. Session Overview",
        f"- **Sport / Type**: `{s.activity_type}` | **Date**: {_fmt(s.date)} ({_fmt(s.start_time_local)})",
        f"- **Distance & Duration**: {dist_str} in {s.duration_formatted} (Avg Pace: {_fmt(s.avg_pace)})",
        (
            f"- **Heart Rate**: Avg {_fmt(s.avg_hr_bpm, ' bpm')} / "
            f"Max {_fmt(s.max_hr_bpm, ' bpm')}"
        ),
        (
            f"- **Power & Cadence**: Avg {_fmt(s.avg_power_watts, ' W')} "
            f"(NP {_fmt(s.normalized_power_watts, ' W')}, Max {_fmt(s.max_power_watts, ' W')}) | "
            f"Avg Cadence {_fmt(s.avg_cadence_spm, ' spm')}"
        ),
        (
            f"- **Elevation & Energy**: Gain +{_fmt(s.elevation_gain, f' {s.elevation_unit}')} / "
            f"Loss -{_fmt(s.elevation_loss, f' {s.elevation_unit}')} | "
            f"Calories {_fmt(s.calories, ' kcal')}"
        ),
        (
            f"- **Training Effect & Load**: Load {_fmt(te.training_load)} | "
            f"Aerobic {_fmt(te.aerobic_effect)} | Anaerobic {_fmt(te.anaerobic_effect)} | "
            f"Benefit: {_fmt(te.primary_benefit)}"
        ),
        "",
        "## 2. Execution Quality, Pacing & Cardiac Drift",
        f"- **Cardiac Drift**: {_fmt(report.cardiac_drift_pct, '%')}",
        f"- **Pacing Evenness**: {_fmt(report.pacing_evenness_assessment)}",
    ]

    if report.execution_notes:
        for note in report.execution_notes:
            lines.append(f"- **Coach Execution Note**: {note}")

    if report.weather is not None:
        w = report.weather
        cond = getattr(w, "weather_Condition", None) or getattr(w, "weather_condition", None)
        lines.extend(
            [
                "",
                "## 3. Environmental & Weather Conditions",
                (
                    f"- **Condition**: {_fmt(cond)} | "
                    f"Temp: {_fmt(w.temp_c, '°C')} ({_fmt(w.temp_f, '°F')}, "
                    f"Feels Like {_fmt(w.apparent_temp_c, '°C')}) | "
                    f"Humidity: {_fmt(w.relative_humidity_pct, '%')} | "
                    f"Wind: {_fmt(w.wind_speed_kph, ' km/h')}"
                ),
            ]
        )

    lines.extend(["", f"## 4. Lap / Split Breakdown ({len(report.laps)} laps)"])
    if not report.laps:
        lines.append("- No lap/split breakdown recorded.")
    else:
        for lap in report.laps:
            lap_dist = (
                f"{lap.distance} {lap.distance_unit}"
                if lap.distance is not None and lap.distance > 0
                else "N/A"
            )
            intensity_tag = f" [{lap.intensity_type}]" if lap.intensity_type else ""
            lines.append(
                f"- **Lap {lap.lap_index}**{intensity_tag}: {lap_dist} in {lap.duration_formatted} | "
                f"Pace {_fmt(lap.avg_pace)} | HR {_fmt(lap.avg_hr_bpm)}/{_fmt(lap.max_hr_bpm)} bpm | "
                f"Power {_fmt(lap.avg_power_watts, ' W')} | Cadence {_fmt(lap.avg_cadence_spm, ' spm')} | "
                f"Elev +{_fmt(lap.elevation_gain, f' {lap.elevation_unit}')}"
            )

    lines.extend(["", "## 5. Heart Rate Zone Distribution"])
    if not report.hr_zones:
        lines.append("- No HR zone time distribution available.")
    else:
        for z in report.hr_zones:
            bounds = (
                f" ({z.low_boundary}–{z.high_boundary} bpm)"
                if z.low_boundary is not None and z.high_boundary is not None
                else ""
            )
            lines.append(
                f"- **Zone {z.zone_number}** ({_fmt(z.zone_name, '', 'Zone')}){bounds}: "
                f"{z.duration_formatted} ({z.percentage:.1f}%)"
            )

    lines.extend(["", "## 6. Power / Pace Zone Distribution"])
    if not report.power_or_pace_zones:
        lines.append("- No power or pace zone distribution available.")
    else:
        for z in report.power_or_pace_zones:
            bounds = (
                f" ({z.low_boundary}–{z.high_boundary})"
                if z.low_boundary is not None and z.high_boundary is not None
                else ""
            )
            lines.append(
                f"- **Zone {z.zone_number}** ({_fmt(z.zone_name, '', 'Zone')}){bounds}: "
                f"{z.duration_formatted} ({z.percentage:.1f}%)"
            )

    return "\n".join(lines)


def list_recent_activities(
    limit: int = 10,
    activity_type: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    response_format: Literal["markdown", "json", "hybrid"] = "hybrid",
) -> str:
    """List recent workouts with distance, duration, HR, pace/power, elevation, calories, and Training Effect.

    Coaching Purpose:
        Provides a scannable training log across running, cycling, swimming, strength,
        and cardio sessions. Supports filtering by workout type and date range to inspect
        training consistency, session load distribution, and recent activity IDs for deep-dives.

    Args:
        limit: Maximum number of activities to return (default `10`).
        activity_type: Optional sport filter (e.g., `"running"`, `"cycling"`, `"strength"`).
        start_date: Optional start ISO date (`YYYY-MM-DD`) filter.
        end_date: Optional end ISO date (`YYYY-MM-DD`) filter.
        response_format: Output representation: `"markdown"`, `"json"`, or `"hybrid"` (default).

    Returns:
        Formatted activity log containing activity IDs, distances, durations, average/max HR,
        pace/power, elevation gain/loss, calories, and aerobic/anaerobic Training Effect.
    """
    from garmin_coach_mcp.server import format_error_output, format_tool_output, get_client

    try:
        client = get_client()
        safe_limit = max(1, int(limit))
        clean_type = (activity_type or "").strip() or None
        clean_start = (start_date or "").strip() or None
        clean_end = (end_date or "").strip() or None

        raw_activities = client.fetch_recent_activities_raw(
            limit=safe_limit,
            activity_type=clean_type,
            start_date=clean_start,
            end_date=clean_end,
        )
        unit_system = getattr(client, "unit_system", "metric")
        activities = normalize_activities_list(raw_activities, unit_system=unit_system)
        md = _render_activities_list_markdown(
            activities,
            limit=safe_limit,
            activity_type=clean_type,
            start_date=clean_start,
            end_date=clean_end,
        )
        return format_tool_output(md, activities, response_format=response_format)
    except GarminCoachError as exc:
        return format_error_output(
            exc, tool_name="list_recent_activities", response_format=response_format
        )
    except Exception as exc:
        return format_error_output(
            exc, tool_name="list_recent_activities", response_format=response_format
        )


def get_activity_details(
    activity_id: int | str,
    response_format: Literal["markdown", "json", "hybrid"] = "hybrid",
) -> str:
    """Perform a granular post-workout debrief for a specific Garmin activity ID.

    Coaching Purpose:
        Deep-dives into a single completed workout to evaluate interval execution,
        lap-by-lap pacing stability, time spent in Heart Rate and Power/Pace zones,
        elevation gain/loss, running/cycling cadence, first-half vs. second-half
        cardiac drift percentage, and environmental weather stress.

    Args:
        activity_id: Numeric or string Garmin Connect activity ID (obtainable via `list_recent_activities`).
        response_format: Output representation: `"markdown"`, `"json"`, or `"hybrid"` (default).

    Returns:
        Formatted deep-dive workout analysis including lap/split breakdowns, HR zone distribution,
        power/pace zone distribution, cardiac drift %, pacing assessment, and weather conditions.
    """
    from garmin_coach_mcp.server import format_error_output, format_tool_output, get_client

    try:
        client = get_client()
        raw = client.fetch_activity_details_raw(activity_id=activity_id)
        unit_system = getattr(client, "unit_system", "metric")
        report = normalize_activity_details(raw, unit_system=unit_system)
        md = _render_activity_details_markdown(report)
        return format_tool_output(md, report, response_format=response_format)
    except GarminCoachError as exc:
        return format_error_output(
            exc, tool_name="get_activity_details", response_format=response_format
        )
    except Exception as exc:
        return format_error_output(
            exc, tool_name="get_activity_details", response_format=response_format
        )


import garmin_coach_mcp.server  # noqa: E402, F401
