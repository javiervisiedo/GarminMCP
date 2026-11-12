"""Activity summaries, deep-dive workout telemetry, and structured workout models."""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ZoneDistributionItem(BaseModel):
    """Time and percentage spent in a single heart rate, power, or pace zone."""

    model_config = ConfigDict(extra="ignore")

    zone_number: int
    zone_name: str | None = None
    low_boundary: float | int | None = None
    high_boundary: float | int | None = None
    duration_seconds: float = 0.0
    duration_formatted: str = "0:00"
    percentage: float = 0.0


class LapSplitSummary(BaseModel):
    """Normalized summary for a single activity lap or split."""

    model_config = ConfigDict(extra="ignore")

    lap_index: int
    distance: float | None = None
    distance_unit: str = "km"
    duration_seconds: float = 0.0
    duration_formatted: str = "0:00"
    avg_pace: str | None = None
    avg_speed_mps: float | None = None
    avg_hr_bpm: int | None = None
    max_hr_bpm: int | None = None
    avg_power_watts: float | None = None
    avg_cadence_spm: float | None = None
    elevation_gain: float | None = None
    elevation_loss: float | None = None
    elevation_unit: str = "m"
    intensity_type: str | None = None


class WeatherSummary(BaseModel):
    """Environmental conditions recorded during an outdoor activity."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    temp_c: float | None = None
    temp_f: float | None = None
    apparent_temp_c: float | None = None
    relative_humidity_pct: int | None = None
    wind_speed_kph: float | None = None
    weather_Condition: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_weather_condition(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "weather_Condition" not in data and "weather_condition" in data:
                data = dict(data)
                data["weather_Condition"] = data["weather_condition"]
        return data

    @property
    def weather_condition(self) -> str | None:
        return self.weather_Condition


class TrainingEffectSummary(BaseModel):
    """Garmin Firstbeat aerobic and anaerobic training effect and load."""

    model_config = ConfigDict(extra="ignore")

    aerobic_effect: float | None = None
    anaerobic_effect: float | None = None
    primary_benefit: str | None = None
    training_load: float | None = None


class ActivitySummary(BaseModel):
    """Token-efficient summary of a single recorded workout or activity."""

    model_config = ConfigDict(extra="ignore")

    activity_id: int | str
    activity_name: str
    activity_type: str
    start_time_local: str | None = None
    date: str | None = None
    duration_seconds: float = 0.0
    duration_formatted: str = "0:00"
    distance: float | None = None
    distance_unit: str = "km"
    avg_pace: str | None = None
    avg_speed_mps: float | None = None
    avg_hr_bpm: int | None = None
    max_hr_bpm: int | None = None
    avg_power_watts: float | None = None
    max_power_watts: float | None = None
    normalized_power_watts: float | None = None
    avg_cadence_spm: float | None = None
    elevation_gain: float | None = None
    elevation_loss: float | None = None
    elevation_unit: str = "m"
    calories: int | None = None
    training_effect: TrainingEffectSummary = Field(default_factory=TrainingEffectSummary)


class ActivityDetailsReport(BaseModel):
    """Deep-dive analysis of a single workout including splits, zones, weather, and drift."""

    model_config = ConfigDict(extra="ignore")

    summary: ActivitySummary
    laps: list[LapSplitSummary] = Field(default_factory=list)
    hr_zones: list[ZoneDistributionItem] = Field(default_factory=list)
    power_or_pace_zones: list[ZoneDistributionItem] = Field(default_factory=list)
    weather: WeatherSummary | None = None
    cardiac_drift_pct: float | None = None
    pacing_evenness_assessment: str | None = None
    execution_notes: list[str] = Field(default_factory=list)


class WorkoutStepInput(BaseModel):
    """Input definition for a single step or repeat block in a structured workout."""

    model_config = ConfigDict(extra="ignore")

    step_type: Literal["warmup", "interval", "recovery", "rest", "cooldown", "repeat"] = "interval"
    duration_type: Literal["time", "distance", "lap.button", "iterations"] = "time"
    duration_value: float | int | None = None
    target_type: Literal["no.target", "heart.rate.zone", "pace.zone", "power.zone", "cadence"] = "no.target"
    target_zone_number: int | None = None
    target_low: float | None = None
    target_high: float | None = None
    description: str | None = None
    repeat_steps: list[WorkoutStepInput] | None = None


WorkoutStepInput.model_rebuild()


class StructuredWorkoutInput(BaseModel):
    """Structured workout prescription input schema."""

    model_config = ConfigDict(extra="ignore")

    workout_name: str
    sport_type: Literal["running", "cycling", "swimming", "strength", "cardio"] = "running"
    description: str | None = None
    steps: list[WorkoutStepInput] = Field(default_factory=list)


class StructuredWorkoutResult(BaseModel):
    """Formatted Garmin Connect workout payload and coaching summary."""

    model_config = ConfigDict(extra="ignore")

    workout_name: str
    sport_type: str
    total_estimated_duration_seconds: float = 0.0
    total_estimated_duration_formatted: str = "0:00"
    total_estimated_distance_meters: float = 0.0
    garmin_workout_json: dict[str, Any] = Field(default_factory=dict)
    uploaded: bool = False
    uploaded_workout_id: int | str | None = None
    human_readable_summary: list[str] = Field(default_factory=list)
