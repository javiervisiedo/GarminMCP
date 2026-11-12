"""Pytest configuration and shared fixtures for garmin-coach-mcp tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture_json(filename: str) -> Any:
    """Load and parse a JSON fixture from tests/fixtures/."""
    path = FIXTURES_DIR / filename
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


class MockGarthClient:
    """Mock Garth client embedded inside MockGarminAPI."""

    def __init__(self) -> None:
        self.dumped_dirs: list[str] = []
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def dump(self, dir_path: str) -> None:
        self.dumped_dirs.append(dir_path)
        target = Path(dir_path)
        target.mkdir(parents=True, exist_ok=True)
        (target / "oauth1_token.json").write_text('{"oauth_token": "mock_oauth1"}', encoding="utf-8")
        (target / "oauth2_token.json").write_text('{"access_token": "mock_oauth2"}', encoding="utf-8")

    def connectapi(self, path: str, method: str = "GET", **kwargs: Any) -> Any:
        self.calls.append((path, method, kwargs))
        if "workout" in path and method.upper() == "POST":
            payload = kwargs.get("json") or {}
            return {
                "workoutId": 99887766,
                "workoutName": payload.get("workoutName", "Custom Workout"),
                "status": "CREATED",
            }
        return {}


class MockGarminAPI:
    """Comprehensive offline mock of garminconnect.Garmin returning realistic fixtures."""

    def __init__(self, fixtures: dict[str, Any]) -> None:
        self.fixtures = fixtures
        self.garth = MockGarthClient()
        self.call_counts: dict[str, int] = {}
        self.uploaded_workouts: list[dict[str, Any]] = []

    def _record_call(self, name: str) -> None:
        self.call_counts[name] = self.call_counts.get(name, 0) + 1

    def login(self, tokenstore: str | None = None) -> bool:
        self._record_call("login")
        return True

    def get_full_name(self) -> str:
        self._record_call("get_full_name")
        return str(self.fixtures["athlete_profile"].get("fullName", "Alex Rivera"))

    def get_user_summary(self, cdate: str) -> dict[str, Any]:
        self._record_call("get_user_summary")
        data = copy.deepcopy(self.fixtures["user_summary"])
        data["calendarDate"] = cdate
        return data

    def get_stats(self, cdate: str) -> dict[str, Any]:
        self._record_call("get_stats")
        return self.get_user_summary(cdate)

    def get_sleep_data(self, cdate: str) -> dict[str, Any]:
        self._record_call("get_sleep_data")
        data = copy.deepcopy(self.fixtures["sleep_data"])
        if "dailySleepDTO" in data and isinstance(data["dailySleepDTO"], dict):
            data["dailySleepDTO"]["calendarDate"] = cdate
        return data

    def get_hrv_data(self, cdate: str) -> dict[str, Any]:
        self._record_call("get_hrv_data")
        data = copy.deepcopy(self.fixtures["hrv_data"])
        if "hrvSummary" in data and isinstance(data["hrvSummary"], dict):
            data["hrvSummary"]["calendarDate"] = cdate
        return data

    def get_training_readiness(self, cdate: str) -> dict[str, Any]:
        self._record_call("get_training_readiness")
        data = copy.deepcopy(self.fixtures["training_readiness"])
        data["calendarDate"] = cdate
        return data

    def get_training_status(self, cdate: str) -> dict[str, Any]:
        self._record_call("get_training_status")
        data = copy.deepcopy(self.fixtures["training_status"])
        data["calendarDate"] = cdate
        return data

    def get_body_battery(self, startdate: str, enddate: str | None = None) -> list[dict[str, Any]]:
        self._record_call("get_body_battery")
        summary = self.fixtures["user_summary"]
        return [
            {
                "date": startdate,
                "charged": summary.get("bodyBatteryChargedValue", 62),
                "drained": summary.get("bodyBatteryDrainedValue", 34),
                "highestLevel": summary.get("bodyBatteryHighestValue", 88),
                "lowestLevel": summary.get("bodyBatteryLowestValue", 26),
                "currentLevel": summary.get("bodyBatteryMostRecentValue", 78),
                "bodyBatteryValuesArray": [
                    [1731274200000, 26],
                    [1731303000000, 88],
                    [1731317400000, 78],
                ],
            }
        ]

    def get_stress_data(self, cdate: str) -> dict[str, Any]:
        self._record_call("get_stress_data")
        summary = self.fixtures["user_summary"]
        return {
            "calendarDate": cdate,
            "avgStressLevel": summary.get("averageStressLevel", 27),
            "maxStressLevel": summary.get("maxStressLevel", 74),
            "stressQualifier": summary.get("stressQualifier", "LOW"),
        }

    def get_all_day_stress(self, cdate: str) -> dict[str, Any]:
        self._record_call("get_all_day_stress")
        return self.get_stress_data(cdate)

    def get_rhr_day(self, cdate: str) -> dict[str, Any]:
        self._record_call("get_rhr_day")
        summary = self.fixtures["user_summary"]
        return {
            "calendarDate": cdate,
            "restingHeartRate": summary.get("restingHeartRate", 46),
            "lastSevenDaysAvgRestingHeartRate": summary.get("lastSevenDaysAvgRestingHeartRate", 47),
            " userProfileId": summary.get("userProfileId", 84920145),
        }

    def get_heart_rates(self, cdate: str) -> dict[str, Any]:
        self._record_call("get_heart_rates")
        summary = self.fixtures["user_summary"]
        return {
            "calendarDate": cdate,
            "restingHeartRate": summary.get("restingHeartRate", 46),
            "maxHeartRate": summary.get("maxHeartRate", 176),
            "minHeartRate": summary.get("minHeartRate", 44),
            "lastSevenDaysAvgRestingHeartRate": summary.get("lastSevenDaysAvgRestingHeartRate", 47),
        }

    def get_spo2_data(self, cdate: str) -> dict[str, Any]:
        self._record_call("get_spo2_data")
        return {
            "calendarDate": cdate,
            "averageSpO2": 96.5,
            "lowestSpO2": 93,
        }

    def get_respiration_data(self, cdate: str) -> dict[str, Any]:
        self._record_call("get_respiration_data")
        return {
            "calendarDate": cdate,
            "avgWakingRespirationValue": 14.2,
            "avgSleepRespirationValue": 13.8,
        }

    def get_max_metrics(self, cdate: str) -> dict[str, Any]:
        self._record_call("get_max_metrics")
        ts = self.fixtures["training_status"]
        return copy.deepcopy(ts.get("mostRecentVO2Max", ts))

    def get_endurance_score(self, startdate: str, enddate: str | None = None) -> dict[str, Any]:
        self._record_call("get_endurance_score")
        return copy.deepcopy(self.fixtures["training_status"].get("enduranceScore", {}))

    def get_hill_score(self, startdate: str, enddate: str | None = None) -> dict[str, Any]:
        self._record_call("get_hill_score")
        return copy.deepcopy(self.fixtures["training_status"].get("hillScore", {}))

    def get_fitnessage_data(self, cdate: str) -> dict[str, Any]:
        self._record_call("get_fitnessage_data")
        return copy.deepcopy(self.fixtures["training_status"].get("fitnessAge", {}))

    def get_activities(
        self, start: int = 0, limit: int = 10, activitytype: str | None = None
    ) -> list[dict[str, Any]]:
        self._record_call("get_activities")
        items = copy.deepcopy(self.fixtures["activities_list"])
        if activitytype:
            items = [
                a
                for a in items
                if activitytype.lower()
                in str((a.get("activityType") or {}).get("typeKey", "")).lower()
            ]
        return items[start : start + limit]

    def get_activities_by_date(
        self,
        startdate: str,
        enddate: str | None = None,
        activitytype: str | None = None,
    ) -> list[dict[str, Any]]:
        self._record_call("get_activities_by_date")
        return self.get_activities(0, 50, activitytype=activitytype)

    def get_activities_fordate(self, fordate: str) -> dict[str, Any]:
        self._record_call("get_activities_fordate")
        return {
            "ActivitiesForDay": {
                "payload": copy.deepcopy(self.fixtures["activities_list"][:1])
            }
        }

    def get_activity(self, activity_id: int | str) -> dict[str, Any]:
        self._record_call("get_activity")
        data = copy.deepcopy(self.fixtures["activity_details"])
        data["activityId"] = int(activity_id) if str(activity_id).isdigit() else activity_id
        return data

    def get_activity_details(
        self, activity_id: int | str, maxchart: int = 2000, maxpoly: int = 4000
    ) -> dict[str, Any]:
        self._record_call("get_activity_details")
        return self.get_activity(activity_id)

    def get_activity_splits(self, activity_id: int | str) -> dict[str, Any]:
        self._record_call("get_activity_splits")
        return {"lapDTOs": copy.deepcopy(self.fixtures["activity_details"].get("lapDTOs", []))}

    def get_activity_typed_splits(self, activity_id: int | str) -> dict[str, Any]:
        self._record_call("get_activity_typed_splits")
        return {"splits": copy.deepcopy(self.fixtures["activity_details"].get("lapDTOs", []))}

    def get_activity_split_summaries(self, activity_id: int | str) -> dict[str, Any]:
        self._record_call("get_activity_split_summaries")
        return {"splitSummaries": copy.deepcopy(self.fixtures["activity_details"].get("lapDTOs", []))}

    def get_activity_hr_in_timezones(self, activity_id: int | str) -> list[dict[str, Any]]:
        self._record_call("get_activity_hr_in_timezones")
        return copy.deepcopy(self.fixtures["activity_details"].get("hrTimeInZones", []))

    def get_activity_power_in_timezones(self, activity_id: int | str) -> list[dict[str, Any]]:
        self._record_call("get_activity_power_in_timezones")
        return copy.deepcopy(self.fixtures["activity_details"].get("powerTimeInZones", []))

    def get_activity_weather(self, activity_id: int | str) -> dict[str, Any]:
        self._record_call("get_activity_weather")
        return copy.deepcopy(self.fixtures["activity_details"].get("weatherDTO", {}))

    def get_body_composition(self, startdate: str, enddate: str | None = None) -> dict[str, Any]:
        self._record_call("get_body_composition")
        return copy.deepcopy(self.fixtures["body_composition"])

    def get_hydration_data(self, cdate: str) -> dict[str, Any]:
        self._record_call("get_hydration_data")
        return copy.deepcopy(self.fixtures["body_composition"].get("hydration", {}))

    def get_lactate_threshold(
        self, latest: bool = True, start_date: str | None = None, end_date: str | None = None
    ) -> dict[str, Any]:
        self._record_call("get_lactate_threshold")
        return copy.deepcopy(self.fixtures["body_composition"].get("biometrics", {}))

    def get_user_profile(self) -> dict[str, Any]:
        self._record_call("get_user_profile")
        return copy.deepcopy(self.fixtures["athlete_profile"])

    def get_userprofile_settings(self) -> dict[str, Any]:
        self._record_call("get_userprofile_settings")
        return copy.deepcopy(self.fixtures["athlete_profile"])

    def get_personal_record(self) -> list[dict[str, Any]]:
        self._record_call("get_personal_record")
        return copy.deepcopy(self.fixtures["athlete_profile"].get("personalRecords", []))

    def upload_workout(self, workout_json: dict[str, Any]) -> dict[str, Any]:
        self._record_call("upload_workout")
        self.uploaded_workouts.append(workout_json)
        return {
            "workoutId": 99887766,
            "workoutName": workout_json.get("workoutName", "Uploaded Workout"),
            "status": "CREATED",
        }


@pytest.fixture(scope="session")
def raw_fixtures() -> dict[str, Any]:
    """Load all 9 Garmin Connect JSON fixtures into memory."""
    return {
        "user_summary": load_fixture_json("user_summary.json"),
        "sleep_data": load_fixture_json("sleep_data.json"),
        "hrv_data": load_fixture_json("hrv_data.json"),
        "training_readiness": load_fixture_json("training_readiness.json"),
        "training_status": load_fixture_json("training_status.json"),
        "activities_list": load_fixture_json("activities_list.json"),
        "activity_details": load_fixture_json("activity_details.json"),
        "body_composition": load_fixture_json("body_composition.json"),
        "athlete_profile": load_fixture_json("athlete_profile.json"),
    }


@pytest.fixture()
def mock_garmin_api(raw_fixtures: dict[str, Any]) -> MockGarminAPI:
    """Provide a fresh MockGarminAPI instance per test."""
    return MockGarminAPI(raw_fixtures)


@pytest.fixture()
def ttl_cache(tmp_path: Path) -> Any:
    """Provide a SQLite TTLCache backed by a temporary file."""
    from garmin_coach_mcp.cache import TTLCache

    cache = TTLCache(db_path=tmp_path / "test_cache.db", default_ttl=900)
    yield cache
    cache.close()


@pytest.fixture()
def coach_client(mock_garmin_api: MockGarminAPI, ttl_cache: Any) -> Any:
    """Provide a configured GarminCoachClient injected into garmin_coach_mcp.server."""
    from garmin_coach_mcp.client import GarminCoachClient

    client = GarminCoachClient(
        cache=ttl_cache,
        unit_system="metric",
        garmin_api=mock_garmin_api,
    )
    try:
        from garmin_coach_mcp import server

        server.set_client(client)
    except ImportError:
        pass
    yield client
    try:
        from garmin_coach_mcp import server

        server.set_client(None)
    except ImportError:
        pass
