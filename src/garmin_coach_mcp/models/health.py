"""Health, sleep, recovery, longitudinal trend, and body composition domain models."""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator


def _format_sleep_seconds(seconds: int | float | None) -> str:
    if seconds is None or seconds <= 0:
        return "0:00"
    total_secs = int(round(float(seconds)))
    hours, rem = divmod(total_secs, 3600)
    minutes, secs = divmod(rem, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


class SleepStagesSummary(BaseModel):
    """Breakdown of sleep stages with computed durations and percentages."""

    model_config = ConfigDict(extra="ignore")

    deep_seconds: int = 0
    light_seconds: int = 0
    rem_seconds: int = 0
    awake_seconds: int = 0
    total_sleep_seconds: int = 0

    @model_validator(mode="after")
    def _ensure_total_sleep(self) -> SleepStagesSummary:
        if self.total_sleep_seconds <= 0:
            stage_sum = max(0, self.deep_seconds) + max(0, self.light_seconds) + max(0, self.rem_seconds)
            if stage_sum > 0:
                self.total_sleep_seconds = stage_sum
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_sleep_formatted(self) -> str:
        return _format_sleep_seconds(self.total_sleep_seconds)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def deep_pct(self) -> float:
        if self.total_sleep_seconds <= 0:
            return 0.0
        return round((self.deep_seconds / self.total_sleep_seconds) * 100.0, 1)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def light_pct(self) -> float:
        if self.total_sleep_seconds <= 0:
            return 0.0
        return round((self.light_seconds / self.total_sleep_seconds) * 100.0, 1)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def rem_pct(self) -> float:
        if self.total_sleep_seconds <= 0:
            return 0.0
        return round((self.rem_seconds / self.total_sleep_seconds) * 100.0, 1)


class SleepRecoveryDay(BaseModel):
    """Single day of overnight sleep, HRV, SpO2, respiration, and Body Battery recovery."""

    model_config = ConfigDict(extra="ignore")

    date: str
    sleep_score: int | None = None
    sleep_quality_qualifier: str | None = None
    stages: SleepStagesSummary = Field(default_factory=SleepStagesSummary)
    resting_hr_bpm: int | None = None
    avg_overnight_hrv_ms: float | None = None
    hrv_status: str | None = None
    hrv_baseline_low_ms: float | None = None
    hrv_baseline_high_ms: float | None = None
    body_battery_charged: int | None = None
    body_battery_drained: int | None = None
    body_battery_high: int | None = None
    body_battery_low: int | None = None
    avg_spo2_pct: float | None = None
    lowest_spo2_pct: float | None = None
    avg_waking_respiration_brpm: float | None = None
    avg_sleep_respiration_brpm: float | None = None
    sleep_need_minutes: int | None = None


class SleepAndRecoveryReport(BaseModel):
    """Multi-day or single-day sleep and autonomic recovery report."""

    model_config = ConfigDict(extra="ignore")

    start_date: str
    end_date: str
    unit_system: str = "metric"
    days: list[SleepRecoveryDay] = Field(default_factory=list)
    avg_sleep_score: float | None = None
    avg_sleep_hours: float | None = None
    avg_overnight_hrv_ms: float | None = None
    avg_resting_hr_bpm: float | None = None
    recovery_takeaway: str = ""


class MetricTrendSummary(BaseModel):
    """First-half vs second-half longitudinal trend summary for a single physiological metric."""

    model_config = ConfigDict(extra="ignore")

    metric_name: str
    unit: str
    average: float | None = None
    min_val: float | None = None
    max_val: float | None = None
    first_half_avg: float | None = None
    second_half_avg: float | None = None
    delta: float | None = None
    delta_pct: float | None = None
    trend_direction: Literal["improving", "declining", "stable", "insufficient_data"] = "insufficient_data"


class HealthTrendsReport(BaseModel):
    """Longitudinal health trends and training volume report over a multi-day window."""

    model_config = ConfigDict(extra="ignore")

    days: int
    start_date: str
    end_date: str
    unit_system: str = "metric"
    rhr_trend: MetricTrendSummary
    hrv_trend: MetricTrendSummary
    sleep_hours_trend: MetricTrendSummary
    daily_steps_trend: MetricTrendSummary
    stress_trend: MetricTrendSummary
    total_activities_count: int = 0
    total_training_duration_hours: float = 0.0
    total_training_distance: float = 0.0
    distance_unit: str = "km"
    weekly_volume_avg_hours: float = 0.0
    activity_type_breakdown: dict[str, int] = Field(default_factory=dict)
    coach_flags: list[str] = Field(default_factory=list)


class BodyCompositionEntry(BaseModel):
    """Single body composition measurement entry."""

    model_config = ConfigDict(extra="ignore")

    date: str
    weight: float | None = None
    weight_unit: str = "kg"
    bmi: float | None = None
    body_fat_pct: float | None = None
    muscle_mass: float | None = None
    bone_mass: float | None = None
    body_water_pct: float | None = None


class BiometricsConfig(BaseModel):
    """Athlete physiological thresholds and aerobic capacities."""

    model_config = ConfigDict(extra="ignore")

    max_hr_bpm: int | None = None
    resting_hr_bpm: int | None = None
    lactate_threshold_hr_bpm: int | None = None
    lactate_threshold_pace: str | None = None
    lactate_threshold_speed_mps: float | None = None
    ftp_watts: int | None = None
    vo2_max_running: float | None = None
    vo2_max_cycling: float | None = None


class BodyCompositionAndBiometricsReport(BaseModel):
    """Body composition trends, hydration, and physiological threshold biometrics."""

    model_config = ConfigDict(extra="ignore")

    start_date: str
    end_date: str
    unit_system: str = "metric"
    latest_weight: float | None = None
    weight_unit: str = "kg"
    weight_delta: float | None = None
    entries: list[BodyCompositionEntry] = Field(default_factory=list)
    avg_daily_hydration_ml: float | None = None
    biometrics: BiometricsConfig = Field(default_factory=BiometricsConfig)
