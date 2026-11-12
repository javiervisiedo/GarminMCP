"""MCP tool definitions for Garmin Coach MCP."""

from __future__ import annotations

from garmin_coach_mcp.tools.activities import get_activity_details, list_recent_activities
from garmin_coach_mcp.tools.briefing import (
    get_coach_daily_briefing,
    render_daily_briefing_markdown,
)
from garmin_coach_mcp.tools.health import (
    get_body_composition_and_biometrics,
    get_health_trends,
    get_sleep_and_recovery,
    get_training_status_and_load,
)
from garmin_coach_mcp.tools.workouts import create_structured_workout_json

__all__ = [
    "create_structured_workout_json",
    "get_activity_details",
    "get_body_composition_and_biometrics",
    "get_coach_daily_briefing",
    "get_health_trends",
    "get_sleep_and_recovery",
    "get_training_status_and_load",
    "list_recent_activities",
    "render_daily_briefing_markdown",
]
