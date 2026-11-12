"""MCP Resources for Garmin Coach MCP (`garmin://athlete/profile` and `garmin://coach/context/today`)."""

from __future__ import annotations

from datetime import date
from typing import Any

from garmin_coach_mcp.exceptions import GarminCoachError
from garmin_coach_mcp.models.readiness import AthleteProfileReport, ZoneConfigItem
from garmin_coach_mcp.normalizers import normalize_athlete_profile, normalize_daily_briefing
from garmin_coach_mcp.tools.briefing import render_daily_briefing_markdown


def _fmt(val: Any, suffix: str = "", fallback: str = "N/A") -> str:
    """Format an optional value with suffix or fallback."""
    if val is None:
        return fallback
    return f"{val}{suffix}"


def _format_zone_table(title: str, zones: list[ZoneConfigItem]) -> list[str]:
    """Render a section of configured training zones."""
    lines = ["", f"## {title}"]
    if not zones:
        lines.append("- Not configured.")
        return lines
    for z in zones:
        lines.append(
            f"- **Zone {z.zone_number} ({z.name})**: {z.lower_bound} – {z.upper_bound} {z.unit}"
        )
    return lines


def render_athlete_profile_markdown(profile: AthleteProfileReport) -> str:
    """Render Markdown summary for AthleteProfileReport."""
    bio = profile.biometrics
    lines: list[str] = [
        f"# Garmin Athlete Profile — {profile.full_name or profile.display_name or 'Athlete'}",
        "",
        "## 1. Athlete Demographics & Anthropometrics",
        f"- **Full Name**: {_fmt(profile.full_name)} (Display: {_fmt(profile.display_name)})",
        f"- **Gender**: {_fmt(profile.gender)} | **Birth Date**: {_fmt(profile.birth_date)}",
        f"- **Weight**: {_fmt(profile.weight, f' {profile.weight_unit}')} | **Height**: {_fmt(profile.height_cm, ' cm')}",
        f"- **Unit System**: `{profile.unit_system}`",
        "",
        "## 2. Physiological Anchors & Thresholds",
        f"- **Max Heart Rate**: {_fmt(bio.max_hr_bpm, ' bpm')}",
        f"- **Resting Heart Rate**: {_fmt(bio.resting_hr_bpm, ' bpm')}",
        f"- **Lactate Threshold HR (LTHR)**: {_fmt(bio.lactate_threshold_hr_bpm, ' bpm')}",
        f"- **Lactate Threshold Pace**: {_fmt(bio.lactate_threshold_pace)}",
        f"- **Functional Threshold Power (FTP)**: {_fmt(bio.ftp_watts, ' W')}",
        f"- **VO2 Max (Running / Cycling)**: {_fmt(bio.vo2_max_running)} / {_fmt(bio.vo2_max_cycling)} mL/kg/min",
    ]

    lines.extend(_format_zone_table("3. Heart Rate Zones", profile.hr_zones))
    lines.extend(_format_zone_table("4. Running Pace Zones", profile.pace_zones))
    lines.extend(_format_zone_table("5. Cycling Power Zones", profile.power_zones))

    lines.extend(["", "## 6. Personal Records (PRs)"])
    if not profile.personal_records:
        lines.append("- No personal records available.")
    else:
        for pr in profile.personal_records:
            sport_tag = f" ({pr.activity_type})" if pr.activity_type else ""
            date_tag = f" — achieved on `{pr.achieved_date}`" if pr.achieved_date else ""
            lines.append(f"- **{pr.type_key}**{sport_tag}: **{pr.formatted_value}**{date_tag}")

    return "\n".join(lines)


def get_athlete_profile() -> str:
    """Return the athlete's profile, HR/Pace/Power zones, Max HR, Lactate Threshold, and Personal Records in Markdown + JSON."""
    from garmin_coach_mcp.server import format_error_output, format_tool_output, get_client

    try:
        client = get_client()
        raw = client.fetch_athlete_profile_raw()
        unit_system = getattr(client, "unit_system", "metric")
        profile = normalize_athlete_profile(raw, unit_system=unit_system)
        md = render_athlete_profile_markdown(profile)
        return format_tool_output(md, profile, response_format="hybrid")
    except GarminCoachError as exc:
        return format_error_output(
            exc, tool_name="garmin://athlete/profile", response_format="hybrid"
        )
    except Exception as exc:
        return format_error_output(
            exc, tool_name="garmin://athlete/profile", response_format="hybrid"
        )


def get_coach_context_today() -> str:
    """Return today's complete readiness, sleep, HRV, Body Battery, and coaching snapshot in clean Markdown."""
    from garmin_coach_mcp.server import format_error_output, format_tool_output, get_client

    try:
        client = get_client()
        today_str = date.today().isoformat()
        raw = client.fetch_daily_briefing_raw(target_date=today_str)
        unit_system = getattr(client, "unit_system", "metric")
        briefing = normalize_daily_briefing(raw, unit_system=unit_system)
        md = render_daily_briefing_markdown(briefing)
        return format_tool_output(md, briefing, response_format="markdown")
    except GarminCoachError as exc:
        return format_error_output(
            exc, tool_name="garmin://coach/context/today", response_format="markdown"
        )
    except Exception as exc:
        return format_error_output(
            exc, tool_name="garmin://coach/context/today", response_format="markdown"
        )


# Standard aliases for convenience in direct imports and tests
athlete_profile = get_athlete_profile
get_athlete_profile_resource = get_athlete_profile
read_athlete_profile = get_athlete_profile

coach_context_today = get_coach_context_today
get_coach_context_today_resource = get_coach_context_today
read_coach_context_today = get_coach_context_today

import garmin_coach_mcp.server  # noqa: E402, F401
