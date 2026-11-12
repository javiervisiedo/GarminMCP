"""Daily readiness, training load, and athlete profile domain models."""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

from garmin_coach_mcp.models.activity import ActivitySummary
from garmin_coach_mcp.models.health import BiometricsConfig, SleepRecoveryDay


class BodyBatterySummary(BaseModel):
    """Garmin Body Battery energy reserve summary."""

    model_config = ConfigDict(extra="ignore")

    current_level: int | None = None
    charged: int | None = None
    drained: int | None = None
    highest_level: int | None = None
    lowest_level: int | None = None


class HRVSummary(BaseModel):
    """Heart Rate Variability status and overnight baseline comparison."""

    model_config = ConfigDict(extra="ignore")

    last_night_avg_ms: float | None = None
    last_night_5min_high_ms: float | None = None
    weekly_avg_ms: float | None = None
    status: str | None = None
    baseline_low_ms: float | None = None
    baseline_high_ms: float | None = None
    feedback_phrase: str | None = None


class TrainingReadinessSummary(BaseModel):
    """Garmin Training Readiness score and contributing factor percentages."""

    model_config = ConfigDict(extra="ignore")

    score: int | None = None
    level: str | None = None
    feedback_short: str | None = None
    recovery_time_hours: float | None = None
    sleep_score_factor_pct: int | None = None
    recovery_time_factor_pct: int | None = None
    acwr_factor_pct: int | None = None
    hrv_factor_pct: int | None = None
    stress_history_factor_pct: int | None = None


class CoachDailyBriefing(BaseModel):
    """Holistic morning readiness briefing combining sleep, HRV, Body Battery, and load."""

    model_config = ConfigDict(extra="ignore")

    date: str
    unit_system: str = "metric"
    readiness: TrainingReadinessSummary = Field(default_factory=TrainingReadinessSummary)
    body_battery: BodyBatterySummary = Field(default_factory=BodyBatterySummary)
    hrv: HRVSummary = Field(default_factory=HRVSummary)
    sleep: SleepRecoveryDay = Field(default_factory=lambda: SleepRecoveryDay(date="unknown"))
    resting_hr_bpm: int | None = None
    seven_day_avg_rhr_bpm: float | None = None
    stress_avg: int | None = None
    stress_qualifier: str | None = None
    steps_today: int | None = None
    daily_step_goal: int | None = None
    training_status_label: str | None = None
    yesterday_activities: list[ActivitySummary] = Field(default_factory=list)
    coach_recommendation: str = ""
    recommended_intensity: Literal["high_intensity", "moderate_steady", "easy_recovery", "rest"] = "easy_recovery"


class TrainingLoadMetrics(BaseModel):
    """Acute and chronic training load, ACWR ratio, and aerobic/anaerobic load balance."""

    model_config = ConfigDict(extra="ignore")

    acute_load: float | None = None
    chronic_load: float | None = None
    load_ratio: float | None = None
    acwr_status: str | None = None
    low_aerobic_load: float | None = None
    high_aerobic_load: float | None = None
    anaerobic_load: float | None = None
    load_focus: str | None = None


class TrainingStatusAndLoadReport(BaseModel):
    """Training status, VO2 Max, acute/chronic load ratio, and endurance/hill scores."""

    model_config = ConfigDict(extra="ignore")

    date: str
    training_status_key: str | None = None
    training_status_feedback: str | None = None
    vo2_max_running: float | None = None
    vo2_max_cycling: float | None = None
    fitness_age: int | None = None
    chronological_age: int | None = None
    recovery_time_hours: float | None = None
    load: TrainingLoadMetrics = Field(default_factory=TrainingLoadMetrics)
    endurance_score: int | None = None
    endurance_classification: str | None = None
    hill_score: int | None = None
    hill_strength_score: int | None = None
    hill_endurance_score: int | None = None
    coach_load_assessment: str = ""


class PersonalRecordItem(BaseModel):
    """Athlete personal record (PR) for a specific distance or metric."""

    model_config = ConfigDict(extra="ignore")

    type_key: str
    activity_type: str | None = None
    value: float | None = None
    formatted_value: str = ""
    achieved_date: str | None = None


class ZoneConfigItem(BaseModel):
    """Configured training zone boundary item (Heart Rate, Pace, or Power)."""

    model_config = ConfigDict(extra="ignore")

    zone_number: int
    name: str
    lower_bound: float | int
    upper_bound: float | int
    unit: str


class AthleteProfileReport(BaseModel):
    """Comprehensive athlete profile including biometrics, configured zones, and PRs."""

    model_config = ConfigDict(extra="ignore")

    full_name: str | None = None
    display_name: str | None = None
    unit_system: str = "metric"
    gender: str | None = None
    birth_date: str | None = None
    weight: float | None = None
    weight_unit: str = "kg"
    height_cm: float | None = None
    biometrics: BiometricsConfig = Field(default_factory=BiometricsConfig)
    hr_zones: list[ZoneConfigItem] = Field(default_factory=list)
    pace_zones: list[ZoneConfigItem] = Field(default_factory=list)
    power_zones: list[ZoneConfigItem] = Field(default_factory=list)
    personal_records: list[PersonalRecordItem] = Field(default_factory=list)
