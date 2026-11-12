"""Pydantic v2 domain models for garmin-coach-mcp."""

from __future__ import annotations

from typing import Literal

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

__all__ = [
    "UnitSystem",
    # health
    "SleepStagesSummary",
    "SleepRecoveryDay",
    "SleepAndRecoveryReport",
    "MetricTrendSummary",
    "HealthTrendsReport",
    "BodyCompositionEntry",
    "BiometricsConfig",
    "BodyCompositionAndBiometricsReport",
    # activity
    "ZoneDistributionItem",
    "LapSplitSummary",
    "WeatherSummary",
    "TrainingEffectSummary",
    "ActivitySummary",
    "ActivityDetailsReport",
    "WorkoutStepInput",
    "StructuredWorkoutInput",
    "StructuredWorkoutResult",
    # readiness
    "BodyBatterySummary",
    "HRVSummary",
    "TrainingReadinessSummary",
    "CoachDailyBriefing",
    "TrainingLoadMetrics",
    "TrainingStatusAndLoadReport",
    "PersonalRecordItem",
    "ZoneConfigItem",
    "AthleteProfileReport",
]
