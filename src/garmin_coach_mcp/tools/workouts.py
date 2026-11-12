"""Structured workout builder and optional Garmin Connect uploader MCP tool."""

from __future__ import annotations

from typing import Any, Literal

from garmin_coach_mcp.exceptions import GarminCoachError
from garmin_coach_mcp.models.activity import (
    StructuredWorkoutInput,
    StructuredWorkoutResult,
    WorkoutStepInput,
)
from garmin_coach_mcp.normalizers import build_garmin_workout_json, meters_to_distance


def _default_steps_for_sport(
    sport_type: Literal["running", "cycling", "swimming", "strength", "cardio"],
) -> list[WorkoutStepInput]:
    """Provide a sensible default warmup + main set + cooldown structure when steps are omitted."""
    return [
        WorkoutStepInput(
            step_type="warmup",
            duration_type="time",
            duration_value=600,
            target_type="heart.rate.zone",
            target_zone_number=2,
            description=f"Easy {sport_type} aerobic warmup",
        ),
        WorkoutStepInput(
            step_type="interval",
            duration_type="time",
            duration_value=1200,
            target_type="heart.rate.zone",
            target_zone_number=3,
            description=f"Steady {sport_type} aerobic effort",
        ),
        WorkoutStepInput(
            step_type="cooldown",
            duration_type="time",
            duration_value=600,
            target_type="heart.rate.zone",
            target_zone_number=1,
            description="Easy recovery cooldown",
        ),
    ]


def _render_workout_result_markdown(
    result: StructuredWorkoutResult,
    unit_system: Literal["metric", "imperial"] = "metric",
) -> str:
    """Render Markdown summary for StructuredWorkoutResult."""
    dist_unit = "km" if unit_system == "metric" else "mi"
    converted_dist = meters_to_distance(result.total_estimated_distance_meters, unit_system) or 0.0
    upload_status = (
        f"Uploaded to Garmin Connect (Workout ID: `{result.uploaded_workout_id}`)"
        if result.uploaded
        else "Local JSON validated (set `upload_to_garmin=True` to push to Garmin Connect)"
    )

    lines: list[str] = [
        f"# Structured Workout: {result.workout_name} (`{result.sport_type}`)",
        "",
        "## 1. Prescription Summary",
        f"- **Estimated Duration**: {result.total_estimated_duration_formatted} ({int(result.total_estimated_duration_seconds)}s)",
        f"- **Estimated Distance**: {converted_dist} {dist_unit} ({result.total_estimated_distance_meters:.0f} m)",
        f"- **Upload Status**: {upload_status}",
        "",
        "## 2. Workout Structure & Steps",
    ]
    if result.human_readable_summary:
        for idx, step_line in enumerate(result.human_readable_summary, start=1):
            lines.append(f"{idx}. {step_line}")
    else:
        lines.append("- Custom structured workout steps generated.")

    return "\n".join(lines)


def create_structured_workout_json(
    workout_name: str,
    sport_type: Literal["running", "cycling", "swimming", "strength", "cardio"] = "running",
    steps: list[dict[str, Any]] | None = None,
    description: str | None = None,
    upload_to_garmin: bool = False,
    response_format: Literal["markdown", "json", "hybrid"] = "hybrid",
) -> str:
    """Validate, build, and optionally upload a structured Garmin Connect workout.

    Coaching Purpose:
        Translates a coach's workout prescription (warmups, intervals, recovery jogs,
        nested repeat blocks, cooldowns with time/distance/lap-button durations and
        HR/pace/power/cadence targets) into a schema-validated Garmin Connect
        `ExecutableStepDTO` / `RepeatGroupDTO` JSON payload. Optionally uploads the
        workout directly to the athlete's Garmin Connect calendar/device queue when
        `upload_to_garmin=True`.

    Args:
        workout_name: Descriptive title for the workout (e.g., `"Threshold 4x1km Cruise Intervals"`).
        sport_type: Target sport (`"running"`, `"cycling"`, `"swimming"`, `"strength"`, `"cardio"`).
        steps: List of step dictionaries matching `WorkoutStepInput` (`step_type`, `duration_type`,
            `duration_value`, `target_type`, `target_zone_number`, `target_low`, `target_high`,
            `description`, `repeat_steps`). If omitted, generates a standard 3-step template.
        description: Optional coaching notes or focus cues attached to the workout.
        upload_to_garmin: If `True`, uploads the generated JSON to Garmin Connect via
            `client.upload_structured_workout(...)`. Defaults to `False`.
        response_format: Output representation: `"markdown"`, `"json"`, or `"hybrid"` (default).

    Returns:
        Formatted workout summary and validated Garmin Connect workout JSON payload
        (including `uploaded` status and `uploaded_workout_id` when uploaded).
    """
    from garmin_coach_mcp.server import format_error_output, format_tool_output, get_client

    try:
        client = get_client()
        unit_system: Literal["metric", "imperial"] = getattr(client, "unit_system", "metric")

        if steps:
            parsed_steps = [
                s if isinstance(s, WorkoutStepInput) else WorkoutStepInput.model_validate(s)
                for s in steps
            ]
        else:
            parsed_steps = _default_steps_for_sport(sport_type)

        workout_input = StructuredWorkoutInput(
            workout_name=workout_name,
            sport_type=sport_type,
            description=description,
            steps=parsed_steps,
        )
        result = build_garmin_workout_json(workout_input, unit_system=unit_system)

        if upload_to_garmin:
            upload_resp = client.upload_structured_workout(result.garmin_workout_json)
            workout_id: int | str | None = None
            if isinstance(upload_resp, dict):
                workout_id = (
                    upload_resp.get("workoutId")
                    or upload_resp.get("id")
                    or upload_resp.get("workout_id")
                )
            result = result.model_copy(
                update={
                    "uploaded": True,
                    "uploaded_workout_id": workout_id,
                }
            )

        md = _render_workout_result_markdown(result, unit_system=unit_system)
        return format_tool_output(md, result, response_format=response_format)
    except GarminCoachError as exc:
        return format_error_output(
            exc, tool_name="create_structured_workout_json", response_format=response_format
        )
    except Exception as exc:
        return format_error_output(
            exc, tool_name="create_structured_workout_json", response_format=response_format
        )


import garmin_coach_mcp.server  # noqa: E402, F401
