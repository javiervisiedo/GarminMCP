"""Unit tests for TTLCache, GarminAuthManager, and GarminCoachClient."""

from __future__ import annotations

import stat
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from garmin_coach_mcp.auth import GarminAuthManager
from garmin_coach_mcp.cache import TTLCache
from garmin_coach_mcp.client import GarminCoachClient
from garmin_coach_mcp.exceptions import (
    GarminAuthError,
    GarminCoachError,
    GarminRateLimitError,
)


class TestTTLCache:
    """Tests for SQLite-backed TTLCache."""

    def test_set_and_get_roundtrip(self, tmp_path: Path) -> None:
        db_file = tmp_path / "cache_dir" / "cache.db"
        cache = TTLCache(db_path=db_file, default_ttl=300)

        payload = {"score": 84, "stages": ["deep", "rem"], "nested": {"hrv": 68.0}}
        cache.set("sleep:2026-11-11", payload)

        assert cache.get("sleep:2026-11-11") == payload
        assert cache.get("nonexistent:key") is None

        # Check directory permissions (0o700)
        dir_mode = stat.S_IMODE(db_file.parent.stat().st_mode)
        assert dir_mode == 0o700
        cache.close()

    def test_ttl_expiry_and_clear_expired(self, tmp_path: Path) -> None:
        cache = TTLCache(db_path=tmp_path / "expiry.db", default_ttl=60)
        cache.set("expired_key", {"val": 1}, ttl=-5)
        cache.set("another_expired", {"val": 2}, ttl=-10)
        cache.set("valid_key", {"val": 3}, ttl=600)

        # Getting an expired key deletes it and returns None
        assert cache.get("expired_key") is None
        # Clearing remaining expired entries removes another_expired
        removed = cache.clear_expired()
        assert removed >= 1
        assert cache.get("valid_key") == {"val": 3}
        cache.close()

    def test_prefix_invalidation_and_full_clear(self) -> None:
        cache = TTLCache(db_path=":memory:", default_ttl=600)
        cache.set("sleep:2026-11-10", {"day": 1})
        cache.set("sleep:2026-11-11", {"day": 2})
        cache.set("activity:17501001", {"id": 17501001})

        cache.invalidate(key_prefix="sleep:")
        assert cache.get("sleep:2026-11-10") is None
        assert cache.get("sleep:2026-11-11") is None
        assert cache.get("activity:17501001") == {"id": 17501001}

        cache.invalidate(key_prefix=None)
        assert cache.get("activity:17501001") is None
        cache.close()

    def test_sql_injection_safety(self) -> None:
        cache = TTLCache(db_path=":memory:", default_ttl=600)
        safe_key = "normal:key"
        malicious_key = "sleep'; DROP TABLE cache_entries; --"
        wildcard_prefix = "%' OR '1'='1"

        cache.set(safe_key, {"safe": True})
        cache.set(malicious_key, {"injected": False})

        assert cache.get(malicious_key) == {"injected": False}
        assert cache.get(safe_key) == {"safe": True}

        # Invalidating with SQL wildcard/injection characters must not wipe safe_key
        cache.invalidate(key_prefix=wildcard_prefix)
        assert cache.get(safe_key) == {"safe": True}
        assert cache.get(malicious_key) == {"injected": False}
        cache.close()

    def test_make_key_deterministic(self) -> None:
        k1 = TTLCache.make_key("briefing", "2026-11-11", b=2, a=1)
        k2 = TTLCache.make_key("briefing", "2026-11-11", a=1, b=2)
        assert k1 == k2
        assert "briefing" in k1
        assert "2026-11-11" in k1


class TestGarminAuthManager:
    """Tests for GarminAuthManager token resume, fallback, and interactive MFA login."""

    def test_missing_credentials_raises_auth_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GARMIN_EMAIL", raising=False)
        monkeypatch.delenv("GARMIN_PASSWORD", raising=False)
        token_dir = tmp_path / "empty_tokens"

        mgr = GarminAuthManager(email=None, password=None, token_dir=token_dir)
        assert not mgr.has_saved_tokens()
        assert stat.S_IMODE(token_dir.stat().st_mode) == 0o700

        with pytest.raises(GarminAuthError, match="garmin-coach-mcp auth"):
            mgr.get_authenticated_client()

    def test_token_resume_success(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        token_dir = tmp_path / "saved_tokens"
        token_dir.mkdir(parents=True)
        (token_dir / "oauth1_token.json").write_text('{"token": "1"}', encoding="utf-8")
        (token_dir / "oauth2_token.json").write_text('{"token": "2"}', encoding="utf-8")

        mock_instance = MagicMock()
        mock_instance.garth.dump = MagicMock()
        mock_garmin_cls = MagicMock(return_value=mock_instance)
        monkeypatch.setattr("garmin_coach_mcp.auth.Garmin", mock_garmin_cls)

        mgr = GarminAuthManager(token_dir=token_dir)
        assert mgr.has_saved_tokens()

        client = mgr.get_authenticated_client()
        assert client is mock_instance
        mock_instance.login.assert_called_once_with(str(token_dir))

    def test_email_password_fallback_when_token_resume_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        token_dir = tmp_path / "fallback_tokens"
        token_dir.mkdir(parents=True)
        (token_dir / "oauth1_token.json").write_text('{"expired": true}', encoding="utf-8")
        (token_dir / "oauth2_token.json").write_text('{"expired": true}', encoding="utf-8")

        resume_client = MagicMock()
        resume_client.login.side_effect = RuntimeError("Token expired")

        cred_client = MagicMock()
        cred_client.login.return_value = True
        cred_client.garth.dump = MagicMock()

        calls: list[ dict[str, Any] ] = []

        def fake_garmin(*args: Any, **kwargs: Any) -> Any:
            calls.append(kwargs)
            if not kwargs.get("email"):
                return resume_client
            return cred_client

        monkeypatch.setattr("garmin_coach_mcp.auth.Garmin", fake_garmin)

        mgr = GarminAuthManager(
            email="runner@example.com",
            password="secret-password",
            token_dir=token_dir,
        )
        client = mgr.get_authenticated_client()
        assert client is cred_client
        cred_client.garth.dump.assert_called_once_with(str(token_dir))

    def test_interactive_login_with_mfa_callback_and_permissions(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        token_dir = tmp_path / "mfa_tokens"
        captured_kwargs: dict[str, Any] = {}

        mock_client = MagicMock()

        def fake_dump(target_dir: str) -> None:
            p = Path(target_dir)
            (p / "oauth1_token.json").write_text('{"oauth1": "ok"}', encoding="utf-8")
            (p / "oauth2_token.json").write_text('{"oauth2": "ok"}', encoding="utf-8")

        mock_client.garth.dump.side_effect = fake_dump

        def fake_garmin(**kwargs: Any) -> Any:
            captured_kwargs.update(kwargs)
            # Simulate Garmin calling prompt_mfa during login
            if callable(kwargs.get("prompt_mfa")):
                code = kwargs["prompt_mfa"]()
                assert code == "123456"
            return mock_client

        monkeypatch.setattr("garmin_coach_mcp.auth.Garmin", fake_garmin)

        mgr = GarminAuthManager(token_dir=token_dir)
        saved_dir = mgr.interactive_login(
            email="runner@example.com",
            password="secret-password",
            mfa_prompt_fn=lambda: "123456",
        )

        assert saved_dir == token_dir
        assert mgr.has_saved_tokens()
        assert stat.S_IMODE(token_dir.stat().st_mode) == 0o700
        assert stat.S_IMODE((token_dir / "oauth1_token.json").stat().st_mode) == 0o600
        assert stat.S_IMODE((token_dir / "oauth2_token.json").stat().st_mode) == 0o600

    def test_export_tokens_base64_and_hydration_roundtrip(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GARMIN_TOKEN_BASE64", raising=False)
        source_dir = tmp_path / "source_tokens"
        source_dir.mkdir(parents=True)
        oauth1_data = {"oauth_token": "tok1", "oauth_token_secret": "sec1"}
        oauth2_data = {"access_token": "acc2", "refresh_token": "ref2", "expires_in": 3600}
        import json

        (source_dir / "oauth1_token.json").write_text(json.dumps(oauth1_data), encoding="utf-8")
        (source_dir / "oauth2_token.json").write_text(json.dumps(oauth2_data), encoding="utf-8")

        exporter = GarminAuthManager(token_dir=source_dir)
        b64_bundle = exporter.export_tokens_base64()
        assert isinstance(b64_bundle, str) and len(b64_bundle) > 20

        # Hydrate into a fresh empty token_dir via GARMIN_TOKEN_BASE64 env var
        target_dir = tmp_path / "hydrated_tokens"
        monkeypatch.setenv("GARMIN_TOKEN_BASE64", b64_bundle)
        hydrator = GarminAuthManager(token_dir=target_dir)

        assert hydrator.has_saved_tokens() is True
        oauth1_file = target_dir / "oauth1_token.json"
        oauth2_file = target_dir / "oauth2_token.json"
        assert oauth1_file.is_file()
        assert oauth2_file.is_file()
        assert stat.S_IMODE(target_dir.stat().st_mode) == 0o700
        assert stat.S_IMODE(oauth1_file.stat().st_mode) == 0o600
        assert stat.S_IMODE(oauth2_file.stat().st_mode) == 0o600
        assert json.loads(oauth1_file.read_text(encoding="utf-8")) == oauth1_data
        assert json.loads(oauth2_file.read_text(encoding="utf-8")) == oauth2_data

        # Verify get_authenticated_client resumes from hydrated tokens
        mock_instance = MagicMock()
        mock_instance.garth.dump = MagicMock()
        monkeypatch.setattr("garmin_coach_mcp.auth.Garmin", MagicMock(return_value=mock_instance))
        client = hydrator.get_authenticated_client()
        assert client is mock_instance
        mock_instance.login.assert_called_once_with(str(target_dir))

    @pytest.mark.parametrize(
        "bad_b64",
        [
            "!!!not-valid-base64@@@",
            "abcde",  # length % 4 == 1
            "bm90LWpzb24=",  # "not-json"
            "WzEsIDIsIDNd",  # "[1, 2, 3]" (JSON list, not dict)
            "eyJvYXV0aDFfdG9rZW4uanNvbiI6IHt9fQ==",  # missing oauth2_token.json
            "eyJvYXV0aDFfdG9rZW4uanNvbiI6ICJ7bm90X2pzb24iLCAib2F1dGgyX3Rva2VuLmpzb24iOiB7fX0=",  # invalid inner JSON string
        ],
    )
    def test_malformed_garmin_token_base64_raises_auth_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad_b64: str
    ) -> None:
        token_dir = tmp_path / "bad_b64_tokens"
        monkeypatch.setenv("GARMIN_TOKEN_BASE64", bad_b64)
        mgr = GarminAuthManager(token_dir=token_dir)
        with pytest.raises(GarminAuthError, match="Malformed GARMIN_TOKEN_BASE64"):
            mgr.has_saved_tokens()

    def test_export_tokens_base64_raises_when_no_saved_tokens(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GARMIN_TOKEN_BASE64", raising=False)
        empty_dir = tmp_path / "no_tokens_here"
        mgr = GarminAuthManager(token_dir=empty_dir)
        with pytest.raises(GarminAuthError, match="No saved tokens found"):
            mgr.export_tokens_base64()

    def test_garminconnect_03_native_client_tokens_lifecycle(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify garminconnect>=0.3.0 client.client.dump (garmin_tokens.json) across login, resume, and Base64 export/hydration."""
        import json

        monkeypatch.delenv("GARMIN_TOKEN_BASE64", raising=False)
        token_dir = tmp_path / "v03_tokens"
        token_payload = {"di_token": "eyJ_di_123", "di_refresh_token": "ref_456", "di_client_id": "GARMIN_CONNECT_MOBILE_ANDROID_DI"}

        mock_client = MagicMock()
        mock_client.garth = None

        def fake_native_dump(target_dir: str) -> None:
            p = Path(target_dir)
            (p / "garmin_tokens.json").write_text(json.dumps(token_payload), encoding="utf-8")

        mock_client.client.dump.side_effect = fake_native_dump
        monkeypatch.setattr("garmin_coach_mcp.auth.Garmin", MagicMock(return_value=mock_client))

        mgr = GarminAuthManager(token_dir=token_dir)
        saved_dir = mgr.interactive_login(
            email="runner@example.com",
            password="secret-password",
            mfa_prompt_fn=lambda: "654321",
        )
        assert saved_dir == token_dir
        assert mgr.has_saved_tokens() is True
        garmin_tokens_file = token_dir / "garmin_tokens.json"
        assert garmin_tokens_file.is_file()
        assert not (token_dir / "oauth1_token.json").exists()
        assert stat.S_IMODE(garmin_tokens_file.stat().st_mode) == 0o600

        # Resume session via get_authenticated_client()
        resume_instance = MagicMock()
        resume_instance.garth = None
        resume_instance.client.dump = MagicMock()
        monkeypatch.setattr("garmin_coach_mcp.auth.Garmin", MagicMock(return_value=resume_instance))

        resumed = mgr.get_authenticated_client()
        assert resumed is resume_instance
        resume_instance.login.assert_called_once_with(str(token_dir))
        resume_instance.client.dump.assert_called_once_with(str(token_dir))

        # Export Base64 bundle and hydrate into a clean directory
        b64_bundle = mgr.export_tokens_base64()
        hydrated_dir = tmp_path / "v03_hydrated"
        monkeypatch.setenv("GARMIN_TOKEN_BASE64", b64_bundle)

        hydrator = GarminAuthManager(token_dir=hydrated_dir)
        assert hydrator.has_saved_tokens() is True
        hydrated_file = hydrated_dir / "garmin_tokens.json"
        assert hydrated_file.is_file()
        assert stat.S_IMODE(hydrated_file.stat().st_mode) == 0o600
        assert json.loads(hydrated_file.read_text(encoding="utf-8")) == token_payload


class TestGarminCoachClient:
    """Tests for GarminCoachClient caching, optional sensor resilience, and error handling."""

    def test_caching_prevents_duplicate_api_calls(
        self, coach_client: GarminCoachClient, mock_garmin_api: Any
    ) -> None:
        raw1 = coach_client.fetch_daily_briefing_raw("2026-11-11")
        raw2 = coach_client.fetch_daily_briefing_raw("2026-11-11")

        assert raw1["date"] == "2026-11-11"
        assert raw1["user_summary"]["restingHeartRate"] == 46
        assert raw2["user_summary"]["restingHeartRate"] == 46
        assert mock_garmin_api.call_counts.get("get_user_summary") == 1

    def test_graceful_fallback_when_optional_sensors_fail(
        self, coach_client: GarminCoachClient, mock_garmin_api: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def broken_sensor(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("Sensor not supported on this watch model")

        monkeypatch.setattr(mock_garmin_api, "get_hrv_data", broken_sensor)
        monkeypatch.setattr(mock_garmin_api, "get_hill_score", broken_sensor)

        briefing = coach_client.fetch_daily_briefing_raw("2026-11-11")
        assert briefing["user_summary"]
        assert not briefing["hrv_data"]

        status = coach_client.fetch_training_status_and_load_raw("2026-11-11")
        assert status["training_status"]
        assert not status["hill_score"]

    def test_rate_limit_error_translation(
        self, coach_client: GarminCoachClient, mock_garmin_api: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def rate_limited(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("HTTP 429 Too Many Requests")

        monkeypatch.setattr(mock_garmin_api, "get_user_summary", rate_limited)

        with pytest.raises(GarminRateLimitError):
            coach_client._call_api("get_user_summary", "2026-11-11", required=True)

    def test_auth_error_translation(
        self, ttl_cache: TTLCache, mock_garmin_api: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bad_auth = MagicMock()
        bad_auth.get_authenticated_client.side_effect = GarminAuthError("Invalid session")

        client = GarminCoachClient(
            auth_manager=bad_auth,
            cache=ttl_cache,
            garmin_api=mock_garmin_api,
        )

        def unauthorized(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("401 Unauthorized")

        monkeypatch.setattr(mock_garmin_api, "get_user_summary", unauthorized)

        with pytest.raises(GarminAuthError):
            client._call_api("get_user_summary", "2026-11-11", required=True)

    def test_all_high_level_raw_fetchers(self, coach_client: GarminCoachClient) -> None:
        sleep_days = coach_client.fetch_sleep_and_recovery_raw("2026-11-10", "2026-11-11")
        assert len(sleep_days) == 2
        assert sleep_days[0]["date"] == "2026-11-10"

        activities = coach_client.fetch_recent_activities_raw(limit=2, activity_type="running")
        assert len(activities) == 2

        details = coach_client.fetch_activity_details_raw(17501001)
        assert str(details["activity_id"]) == "17501001"
        assert details["summary"] is not None

        trends = coach_client.fetch_health_trends_raw(days=7, end_date="2026-11-11")
        assert trends["days"] == 7
        assert len(trends["daily_summaries"]) == 7

        body = coach_client.fetch_body_composition_and_biometrics_raw("2026-10-12", "2026-11-11")
        assert body["body_composition"] is not None

        profile = coach_client.fetch_athlete_profile_raw()
        assert profile["full_name"] == "Alex Rivera"

        uploaded = coach_client.upload_structured_workout({"workoutName": "Test 5x1K"})
        assert uploaded.get("workoutId") == 99887766
