"""High-level Garmin Connect client with SQLite TTL caching and resilient sensor fallbacks."""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from typing import Any, Literal

from garmin_coach_mcp.auth import (
    GarminAuthManager,
    GarminConnectAuthenticationError,
    GarminConnectTooManyRequestsError,
)
from garmin_coach_mcp.cache import TTLCache
from garmin_coach_mcp.exceptions import (
    GarminAPIError,
    GarminAuthError,
    GarminRateLimitError,
)

logger = logging.getLogger(__name__)

UnitSystem = Literal["metric", "imperial"]


class GarminCoachClient:
    """Resilient, caching Garmin Connect API client tailored for AI coaching workflows."""

    def __init__(
        self,
        auth_manager: GarminAuthManager | None = None,
        cache: TTLCache | None = None,
        unit_system: UnitSystem | None = None,
        garmin_api: Any | None = None,
    ) -> None:
        self._explicit_auth_manager = auth_manager is not None
        self.auth_manager: GarminAuthManager = auth_manager or GarminAuthManager()
        self.cache: TTLCache = cache or TTLCache()

        if unit_system is not None:
            normalized_unit = unit_system.strip().lower()
            if normalized_unit not in ("metric", "imperial"):
                raise ValueError(
                    f"Invalid unit_system '{unit_system}'. Expected 'metric' or 'imperial'."
                )
            self.unit_system: UnitSystem = normalized_unit  # type: ignore[assignment]
        else:
            env_unit = os.environ.get("GARMIN_UNITS", "metric").strip().lower()
            self.unit_system = (
                env_unit if env_unit in ("metric", "imperial") else "metric"  # type: ignore[assignment]
            )

        self._garmin_api: Any | None = garmin_api

    def _get_api(self, force_reauth: bool = False) -> Any:
        """Return the active Garmin API instance, authenticating lazily if needed."""
        if self._garmin_api is not None and not force_reauth:
            return self._garmin_api
        self._garmin_api = self.auth_manager.get_authenticated_client()
        return self._garmin_api

    @staticmethod
    def _is_rate_limit_error(exc: Exception) -> bool:
        if isinstance(exc, (GarminRateLimitError, GarminConnectTooManyRequestsError)):
            return True
        status_code = getattr(exc, "status_code", None) or getattr(
            getattr(exc, "response", None), "status_code", None
        )
        if status_code == 429:
            return True
        msg = str(exc).lower()
        return "429" in msg or "too many requests" in msg or "rate limit" in msg

    @staticmethod
    def _is_auth_error(exc: Exception) -> bool:
        if isinstance(exc, (GarminAuthError, GarminConnectAuthenticationError)):
            return True
        status_code = getattr(exc, "status_code", None) or getattr(
            getattr(exc, "response", None), "status_code", None
        )
        if status_code in (401, 403):
            return True
        msg = str(exc).lower()
        return (
            "401" in msg
            or "403" in msg
            or "unauthorized" in msg
            or "forbidden" in msg
            or "authentication" in msg
            or "token expired" in msg
        )

    def _call_api(
        self,
        method_name: str,
        *args: Any,
        cache_ttl: int | None = 900,
        default: Any = None,
        required: bool = False,
        **kwargs: Any,
    ) -> Any:
        """Invoke a method on the Garmin API client with caching, retry on 401/403, and fallbacks."""
        cache_key = TTLCache.make_key(method_name, *args, **kwargs)
        if cache_ttl is not None and cache_ttl > 0:
            cached_val = self.cache.get(cache_key)
            if cached_val is not None:
                return cached_val

        api = self._get_api()
        if not hasattr(api, method_name):
            if required:
                raise GarminAPIError(
                    f"Upstream Garmin client does not implement required method '{method_name}'."
                )
            return default

        for attempt in range(2):
            try:
                method = getattr(api, method_name)
                result = method(*args, **kwargs)
                if result is None:
                    return default
                if cache_ttl is not None and cache_ttl > 0:
                    self.cache.set(cache_key, result, ttl=cache_ttl)
                return result
            except Exception as exc:
                if self._is_rate_limit_error(exc):
                    raise GarminRateLimitError(
                        f"Garmin Connect API rate limit (HTTP 429) exceeded during '{method_name}'. "
                        "Please wait a few minutes before retrying."
                    ) from exc

                if self._is_auth_error(exc):
                    if attempt == 0:
                        logger.info(
                            "Authentication error on '%s'; attempting single re-authentication retry.",
                            method_name,
                        )
                        try:
                            api = self._get_api(force_reauth=True)
                        except GarminAuthError:
                            if self._explicit_auth_manager or self._garmin_api is None:
                                raise
                            api = self._garmin_api
                        continue
                    raise GarminAuthError(
                        f"Garmin Connect authentication failed calling '{method_name}': {exc}. "
                        "Run `garmin-coach-mcp auth` to refresh your tokens."
                    ) from exc

                if required:
                    raise GarminAPIError(
                        f"Garmin Connect API error in '{method_name}': {exc}"
                    ) from exc

                logger.debug(
                    "Optional Garmin endpoint '%s' returned error (%s); using default.",
                    method_name,
                    exc,
                )
                return default

        return default

    def _call_api_flexible_dates(
        self,
        method_name: str,
        start_date: str,
        end_date: str | None = None,
        *,
        cache_ttl: int | None = 900,
        default: Any = None,
    ) -> Any:
        """Call a Garmin method that may accept either (start, end) or (date) across versions."""
        cache_key = TTLCache.make_key(method_name, start_date, end_date or start_date)
        if cache_ttl is not None and cache_ttl > 0:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached

        api = self._get_api()
        if not hasattr(api, method_name):
            return default

        method = getattr(api, method_name)
        try:
            if end_date is not None:
                res = method(start_date, end_date)
            else:
                res = method(start_date)
        except TypeError:
            try:
                res = method(start_date)
            except TypeError:
                res = method(start_date, end_date or start_date)
            except Exception as exc:
                if self._is_rate_limit_error(exc):
                    raise GarminRateLimitError(str(exc)) from exc
                if self._is_auth_error(exc):
                    raise GarminAuthError(str(exc)) from exc
                return default
        except Exception as exc:
            if self._is_rate_limit_error(exc):
                raise GarminRateLimitError(str(exc)) from exc
            if self._is_auth_error(exc):
                # Delegate to _call_api so re-auth retry logic runs
                return self._call_api(
                    method_name,
                    start_date,
                    *([end_date] if end_date is not None else []),
                    cache_ttl=cache_ttl,
                    default=default,
                )
            return default

        if res is None:
            return default
        if cache_ttl is not None and cache_ttl > 0:
            self.cache.set(cache_key, res, ttl=cache_ttl)
        return res

    def fetch_daily_briefing_raw(self, target_date: str | None = None) -> dict[str, Any]:
        """Fetch raw data for the daily coaching readiness briefing."""
        cdate = target_date or date.today().isoformat()
        try:
            yesterday_str = (date.fromisoformat(cdate) - timedelta(days=1)).isoformat()
        except ValueError:
            yesterday_str = cdate

        user_summary = self._call_api("get_user_summary", cdate, default={})
        if not user_summary:
            user_summary = self._call_api("get_stats", cdate, default={})

        sleep_data = self._call_api("get_sleep_data", cdate, default={})
        hrv_data = self._call_api("get_hrv_data", cdate, default={})
        training_readiness = self._call_api("get_training_readiness", cdate, default={})
        body_battery = self._call_api_flexible_dates("get_body_battery", cdate, cdate, default=[])
        stress_data = self._call_api("get_stress_data", cdate, default={})
        rhr_data = self._call_api("get_rhr_day", cdate, default={})
        training_status = self._call_api("get_training_status", cdate, default={})

        yesterday_activities = self._call_api(
            "get_activities_by_date", yesterday_str, yesterday_str, default=None
        )
        if yesterday_activities is None:
            yesterday_activities = self._call_api("get_activities", 0, 5, default=[])

        return {
            "date": cdate,
            "user_summary": user_summary,
            "sleep_data": sleep_data,
            "hrv_data": hrv_data,
            "training_readiness": training_readiness,
            "body_battery": body_battery,
            "stress_data": stress_data,
            "rhr_data": rhr_data,
            "training_status": training_status,
            "yesterday_activities": (
                yesterday_activities if isinstance(yesterday_activities, list) else []
            ),
        }

    def fetch_sleep_and_recovery_raw(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch daily sleep stages, HRV, Body Battery, SpO2, and respiration over a date range."""
        if start_date is None and end_date is None:
            end_dt = date.today()
            start_dt = end_dt - timedelta(days=6)
        elif start_date is not None and end_date is None:
            start_dt = date.fromisoformat(start_date)
            end_dt = start_dt
        elif start_date is None and end_date is not None:
            end_dt = date.fromisoformat(end_date)
            start_dt = end_dt - timedelta(days=6)
        else:
            start_dt = date.fromisoformat(start_date)  # type: ignore[arg-type]
            end_dt = date.fromisoformat(end_date)  # type: ignore[arg-type]

        if start_dt > end_dt:
            start_dt, end_dt = end_dt, start_dt

        # Cap range at 31 days max to prevent excessive API fan-out
        if (end_dt - start_dt).days > 30:
            start_dt = end_dt - timedelta(days=30)

        results: list[dict[str, Any]] = []
        current_dt = start_dt
        while current_dt <= end_dt:
            d_str = current_dt.isoformat()
            results.append(
                {
                    "date": d_str,
                    "sleep_data": self._call_api("get_sleep_data", d_str, default={}),
                    "hrv_data": self._call_api("get_hrv_data", d_str, default={}),
                    "body_battery": self._call_api_flexible_dates(
                        "get_body_battery", d_str, d_str, default=[]
                    ),
                    "spo2_data": self._call_api("get_spo2_data", d_str, default={}),
                    "respiration_data": self._call_api("get_respiration_data", d_str, default={}),
                    "user_summary": self._call_api("get_user_summary", d_str, default={}),
                }
            )
            current_dt += timedelta(days=1)

        return results

    def fetch_training_status_and_load_raw(
        self,
        target_date: str | None = None,
    ) -> dict[str, Any]:
        """Fetch raw VO2 Max, Acute/Chronic training load, ACWR, endurance/hill scores, and fitness age."""
        cdate = target_date or date.today().isoformat()
        fitness_age = self._call_api("get_fitnessage_data", cdate, default={})
        if not fitness_age:
            fitness_age = self._call_api("get_fitness_age", cdate, default={})

        return {
            "date": cdate,
            "training_status": self._call_api("get_training_status", cdate, default={}),
            "training_readiness": self._call_api("get_training_readiness", cdate, default={}),
            "max_metrics": self._call_api("get_max_metrics", cdate, default={}),
            "endurance_score": self._call_api("get_endurance_score", cdate, default={}),
            "hill_score": self._call_api("get_hill_score", cdate, default={}),
            "fitness_age": fitness_age,
            "user_summary": self._call_api("get_user_summary", cdate, default={}),
        }

    def fetch_recent_activities_raw(
        self,
        limit: int = 10,
        activity_type: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch recent workouts by limit or date range, optionally filtered by activity_type."""
        effective_limit = max(1, int(limit))
        activities: list[dict[str, Any]] | None = None

        if start_date or end_date:
            s_date = start_date or "1970-01-01"
            e_date = end_date or date.today().isoformat()
            activities = self._call_api(
                "get_activities_by_date", s_date, e_date, default=None
            )

        if activities is None:
            fetch_count = effective_limit * 3 if activity_type else effective_limit
            activities = self._call_api("get_activities", 0, fetch_count, default=[])

        if not isinstance(activities, list):
            return []

        filtered = activities
        if activity_type:
            target = activity_type.strip().lower()
            matched: list[dict[str, Any]] = []
            for act in filtered:
                if not isinstance(act, dict):
                    continue
                act_type_obj = act.get("activityType") or act.get("activityTypeDTO") or {}
                if isinstance(act_type_obj, dict):
                    type_key = str(act_type_obj.get("typeKey") or "").lower()
                else:
                    type_key = str(act_type_obj).lower()
                act_name = str(act.get("activityName") or "").lower()
                if target in type_key or type_key in target or target in act_name:
                    matched.append(act)
            filtered = matched

        return filtered[:effective_limit]

    def fetch_activity_details_raw(self, activity_id: int | str) -> dict[str, Any]:
        """Fetch deep-dive telemetry for a single activity (summary, splits, HR zones, weather)."""
        summary = self._call_api("get_activity", activity_id, default={})
        if not summary:
            summary = self._call_api("get_activity_evaluation", activity_id, default={})

        details = self._call_api("get_activity_details", activity_id, default={})
        splits = self._call_api("get_activity_splits", activity_id, default={})
        typed_splits = self._call_api("get_activity_typed_splits", activity_id, default={})
        hr_zones = self._call_api("get_activity_hr_in_timezones", activity_id, default=[])
        if not hr_zones:
            hr_zones = self._call_api("get_activity_hr_zones", activity_id, default=[])
        weather = self._call_api("get_activity_weather", activity_id, default={})

        return {
            "activity_id": activity_id,
            "summary": summary,
            "details": details,
            "splits": splits,
            "typed_splits": typed_splits,
            "hr_zones": hr_zones,
            "weather": weather,
        }

    def fetch_health_trends_raw(
        self,
        days: int = 28,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """Fetch longitudinal health summaries, sleep, HRV, and activities over N days."""
        clamped_days = max(1, min(int(days), 365))
        end_dt = date.fromisoformat(end_date) if end_date else date.today()
        start_dt = end_dt - timedelta(days=clamped_days - 1)
        start_str = start_dt.isoformat()
        end_str = end_dt.isoformat()

        daily_summaries: list[dict[str, Any]] = []
        sleep_entries: list[dict[str, Any]] = []
        hrv_entries: list[dict[str, Any]] = []

        current_dt = start_dt
        while current_dt <= end_dt:
            d_str = current_dt.isoformat()
            summary = self._call_api("get_user_summary", d_str, default={})
            if isinstance(summary, dict) and summary:
                entry = dict(summary)
                entry.setdefault("calendarDate", d_str)
                entry.setdefault("date", d_str)
                daily_summaries.append(entry)

            sleep = self._call_api("get_sleep_data", d_str, default={})
            if isinstance(sleep, dict) and sleep:
                s_entry = dict(sleep)
                s_entry.setdefault("calendarDate", d_str)
                s_entry.setdefault("date", d_str)
                sleep_entries.append(s_entry)

            hrv = self._call_api("get_hrv_data", d_str, default={})
            if isinstance(hrv, dict) and hrv:
                h_entry = dict(hrv)
                h_entry.setdefault("calendarDate", d_str)
                h_entry.setdefault("date", d_str)
                hrv_entries.append(h_entry)

            current_dt += timedelta(days=1)

        activities = self._call_api("get_activities_by_date", start_str, end_str, default=None)
        if activities is None:
            activities = self._call_api("get_activities", 0, 50, default=[])

        return {
            "days": clamped_days,
            "start_date": start_str,
            "end_date": end_str,
            "daily_summaries": daily_summaries,
            "sleep_entries": sleep_entries,
            "hrv_entries": hrv_entries,
            "activities": activities if isinstance(activities, list) else [],
        }

    def fetch_body_composition_and_biometrics_raw(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """Fetch weight/body composition entries, hydration, lactate threshold, VO2 max, and profile."""
        end_dt = date.fromisoformat(end_date) if end_date else date.today()
        start_dt = date.fromisoformat(start_date) if start_date else (end_dt - timedelta(days=29))
        if start_dt > end_dt:
            start_dt, end_dt = end_dt, start_dt

        start_str = start_dt.isoformat()
        end_str = end_dt.isoformat()

        body_comp = self._call_api_flexible_dates(
            "get_body_composition", start_str, end_str, default={}
        )
        hydration = self._call_api("get_hydration_data", end_str, default={})
        lactate_threshold = self._call_api("get_lactate_threshold", default={})
        max_metrics = self._call_api("get_max_metrics", end_str, default={})
        user_profile = self._call_api("get_user_profile", default={})
        personal_records = self._call_api("get_personal_record", default=[])

        return {
            "start_date": start_str,
            "end_date": end_str,
            "body_composition": body_comp,
            "hydration_data": hydration,
            "lactate_threshold": lactate_threshold,
            "max_metrics": max_metrics,
            "user_profile": user_profile,
            "personal_records": personal_records,
        }

    def fetch_athlete_profile_raw(self) -> dict[str, Any]:
        """Fetch static/semi-static athlete profile, zones, personal records, and thresholds."""
        today_str = date.today().isoformat()
        user_settings = self._call_api("get_userprofile_settings", default={})
        if not user_settings:
            user_settings = self._call_api("get_user_settings", default={})

        personal_records = self._call_api("get_personal_record", default=[])
        if not personal_records:
            personal_records = self._call_api("get_personal_records", default=[])

        return {
            "full_name": self._call_api("get_full_name", default=None),
            "user_profile": self._call_api("get_user_profile", default={}),
            "user_settings": user_settings,
            "personal_records": personal_records,
            "lactate_threshold": self._call_api("get_lactate_threshold", default={}),
            "max_metrics": self._call_api("get_max_metrics", today_str, default={}),
        }

    def upload_structured_workout(self, workout_payload: dict[str, Any]) -> dict[str, Any]:
        """Upload a Garmin-compatible structured workout JSON payload to Garmin Connect."""
        api = self._get_api()
        result: Any = None

        try:
            if hasattr(api, "upload_workout"):
                result = api.upload_workout(workout_payload)
            elif hasattr(api, "garth") and hasattr(api.garth, "connectapi"):
                result = api.garth.connectapi(
                    "/workout-service/workout",
                    method="POST",
                    json=workout_payload,
                )
            else:
                raise GarminAPIError(
                    "Authenticated Garmin client does not support workout upload "
                    "(missing 'upload_workout' and 'garth.connectapi')."
                )
        except (GarminAuthError, GarminRateLimitError, GarminAPIError):
            raise
        except Exception as exc:
            if self._is_rate_limit_error(exc):
                raise GarminRateLimitError(
                    f"Rate limit exceeded while uploading workout: {exc}"
                ) from exc
            if self._is_auth_error(exc):
                raise GarminAuthError(
                    f"Authentication error while uploading workout: {exc}"
                ) from exc
            raise GarminAPIError(f"Failed to upload structured workout: {exc}") from exc

        self.cache.invalidate("get_workouts")
        self.cache.invalidate("workout")

        if isinstance(result, dict):
            return result
        return {"status": "uploaded", "workoutId": result}
