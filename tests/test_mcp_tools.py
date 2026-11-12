"""Integration and protocol introspection tests for garmin-coach-mcp tools, resources, and prompts."""

from __future__ import annotations

import asyncio
import inspect
import json
from typing import Any

import pytest

from garmin_coach_mcp.client import GarminCoachClient
from garmin_coach_mcp.server import mcp

EXPECTED_TOOLS = {
    "get_coach_daily_briefing",
    "get_sleep_and_recovery",
    "get_training_status_and_load",
    "list_recent_activities",
    "get_activity_details",
    "get_health_trends",
    "get_body_composition_and_biometrics",
    "create_structured_workout_json",
}

EXPECTED_RESOURCES = {
    "garmin://athlete/profile",
    "garmin://coach/context/today",
}

EXPECTED_PROMPTS = {
    "morning-readiness-check",
    "post-workout-debrief",
    "weekly-training-plan",
}


def _run_async(coro: Any) -> Any:
    """Execute an awaitable or return a synchronous value directly."""
    if inspect.isawaitable(coro):
        return asyncio.run(coro)
    return coro


def _extract_text(result: Any) -> str:
    """Extract text string from a FastMCP call_tool / read_resource / get_prompt result."""
    if isinstance(result, str):
        return result
    if isinstance(result, tuple) and len(result) > 0:
        return _extract_text(result[0])
    if isinstance(result, list):
        parts: list[str] = []
        for item in result:
            if isinstance(item, str):
                parts.append(item)
            elif hasattr(item, "text") and item.text is not None:
                parts.append(str(item.text))
            elif hasattr(item, "content") and item.content is not None:
                parts.append(_extract_text(item.content))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    if hasattr(result, "messages"):
        return _extract_text(result.messages)
    if hasattr(result, "contents"):
        return _extract_text(result.contents)
    if hasattr(result, "content"):
        return _extract_text(result.content)
    if hasattr(result, "text"):
        return str(result.text)
    return str(result)


def invoke_mcp_tool(tool_name: str, **arguments: Any) -> str:
    """Invoke a registered tool on the FastMCP server and return its text output."""
    res = _run_async(mcp.call_tool(tool_name, arguments))
    return _extract_text(res)


class TestMCPProtocolIntrospection:
    """Verify FastMCP registration of all 8 tools, 2 resources, and 3 prompts."""

    def test_all_8_tools_registered_with_descriptions(self) -> None:
        tools = _run_async(mcp.list_tools())
        registered_names = {t.name for t in tools}
        assert EXPECTED_TOOLS.issubset(registered_names), (
            f"Missing tools: {EXPECTED_TOOLS - registered_names}"
        )
        for tool in tools:
            if tool.name in EXPECTED_TOOLS:
                assert tool.description and len(tool.description.strip()) > 20
                assert "TODO" not in tool.description

    def test_all_2_resources_registered_with_descriptions(self) -> None:
        resources = _run_async(mcp.list_resources())
        registered_uris = {str(r.uri) for r in resources}
        assert EXPECTED_RESOURCES.issubset(registered_uris), (
            f"Missing resources: {EXPECTED_RESOURCES - registered_uris}"
        )
        for resource in resources:
            if str(resource.uri) in EXPECTED_RESOURCES:
                desc = resource.description or ""
                assert len(desc.strip()) > 10
                assert "TODO" not in desc

    def test_all_3_prompts_registered_with_descriptions(self) -> None:
        prompts = _run_async(mcp.list_prompts())
        registered_names = {p.name for p in prompts}
        assert EXPECTED_PROMPTS.issubset(registered_names), (
            f"Missing prompts: {EXPECTED_PROMPTS - registered_names}"
        )
        for prompt in prompts:
            if prompt.name in EXPECTED_PROMPTS:
                desc = prompt.description or ""
                assert len(desc.strip()) > 10
                assert "TODO" not in desc


class TestAllEightMCPTools:
    """Test all 8 MCP tools across markdown, json, and hybrid response formats."""

    @pytest.mark.parametrize("fmt", ["markdown", "json", "hybrid"])
    def test_get_coach_daily_briefing(self, coach_client: GarminCoachClient, fmt: str) -> None:
        out = invoke_mcp_tool(
            "get_coach_daily_briefing",
            target_date="2026-11-11",
            response_format=fmt,
        )
        assert out
        assert "TODO" not in out
        if fmt == "json":
            parsed = json.loads(out)
            assert parsed["date"] == "2026-11-11"
            assert parsed["readiness"]["score"] == 79
        elif fmt == "hybrid":
            assert "```json" in out
            assert "79" in out
        else:
            assert "79" in out

    @pytest.mark.parametrize("fmt", ["markdown", "json", "hybrid"])
    def test_get_sleep_and_recovery(self, coach_client: GarminCoachClient, fmt: str) -> None:
        out = invoke_mcp_tool(
            "get_sleep_and_recovery",
            start_date="2026-11-10",
            end_date="2026-11-11",
            response_format=fmt,
        )
        assert out
        if fmt == "json":
            parsed = json.loads(out)
            assert len(parsed["days"]) == 2
        elif fmt == "hybrid":
            assert "```json" in out

    @pytest.mark.parametrize("fmt", ["markdown", "json", "hybrid"])
    def test_get_training_status_and_load(self, coach_client: GarminCoachClient, fmt: str) -> None:
        out = invoke_mcp_tool(
            "get_training_status_and_load",
            target_date="2026-11-11",
            response_format=fmt,
        )
        assert out
        if fmt == "json":
            parsed = json.loads(out)
            assert parsed["vo2_max_running"] == pytest.approx(56.2)
            assert parsed["load"]["acute_load"] == pytest.approx(640.0)
        elif fmt == "hybrid":
            assert "```json" in out
            assert "56.2" in out

    @pytest.mark.parametrize("fmt", ["markdown", "json", "hybrid"])
    def test_list_recent_activities(self, coach_client: GarminCoachClient, fmt: str) -> None:
        out = invoke_mcp_tool(
            "list_recent_activities",
            limit=4,
            response_format=fmt,
        )
        assert out
        if fmt == "json":
            parsed = json.loads(out)
            items = parsed if isinstance(parsed, list) else parsed.get("activities", [])
            assert len(items) == 4
        elif fmt == "hybrid":
            assert "```json" in out
            assert "Threshold Interval Run" in out

    @pytest.mark.parametrize("fmt", ["markdown", "json", "hybrid"])
    def test_get_activity_details(self, coach_client: GarminCoachClient, fmt: str) -> None:
        out = invoke_mcp_tool(
            "get_activity_details",
            activity_id=17501001,
            response_format=fmt,
        )
        assert out
        if fmt == "json":
            parsed = json.loads(out)
            assert len(parsed["laps"]) == 9
            assert len(parsed["hr_zones"]) == 5
        elif fmt == "hybrid":
            assert "```json" in out

    @pytest.mark.parametrize("fmt", ["markdown", "json", "hybrid"])
    def test_get_health_trends(self, coach_client: GarminCoachClient, fmt: str) -> None:
        out = invoke_mcp_tool(
            "get_health_trends",
            days=14,
            end_date="2026-11-11",
            response_format=fmt,
        )
        assert out
        if fmt == "json":
            parsed = json.loads(out)
            assert parsed["days"] == 14
        elif fmt == "hybrid":
            assert "```json" in out

    @pytest.mark.parametrize("fmt", ["markdown", "json", "hybrid"])
    def test_get_body_composition_and_biometrics(
        self, coach_client: GarminCoachClient, fmt: str
    ) -> None:
        out = invoke_mcp_tool(
            "get_body_composition_and_biometrics",
            start_date="2026-10-12",
            end_date="2026-11-11",
            response_format=fmt,
        )
        assert out
        if fmt == "json":
            parsed = json.loads(out)
            assert parsed["latest_weight"] == pytest.approx(68.4, rel=1e-2)
            assert parsed["biometrics"]["lactate_threshold_hr_bpm"] == 174
        elif fmt == "hybrid":
            assert "```json" in out
            assert "68.4" in out

    @pytest.mark.parametrize("fmt", ["markdown", "json", "hybrid"])
    def test_create_structured_workout_json_and_upload(
        self, coach_client: GarminCoachClient, mock_garmin_api: Any, fmt: str
    ) -> None:
        steps = [
            {"step_type": "warmup", "duration_type": "time", "duration_value": 600},
            {
                "step_type": "repeat",
                "duration_type": "iterations",
                "duration_value": 4,
                "repeat_steps": [
                    {
                        "step_type": "interval",
                        "duration_type": "distance",
                        "duration_value": 1000,
                        "target_type": "heart.rate.zone",
                        "target_zone_number": 4,
                    },
                    {
                        "step_type": "recovery",
                        "duration_type": "time",
                        "duration_value": 120,
                    },
                ],
            },
            {"step_type": "cooldown", "duration_type": "time", "duration_value": 600},
        ]

        out = invoke_mcp_tool(
            "create_structured_workout_json",
            workout_name="4x1km Threshold Session",
            sport_type="running",
            steps=steps,
            description="Coach prescribed LT session",
            upload_to_garmin=(fmt == "json"),
            response_format=fmt,
        )
        assert out
        if fmt == "json":
            parsed = json.loads(out)
            assert parsed["workout_name"] == "4x1km Threshold Session"
            assert parsed["uploaded"] is True
            assert str(parsed["uploaded_workout_id"]) == "99887766"
            assert len(mock_garmin_api.uploaded_workouts) == 1
        elif fmt == "hybrid":
            assert "```json" in out
            assert "4x1km Threshold Session" in out


class TestMCPResourcesAndPrompts:
    """Test both MCP resources and all 3 MCP coaching prompts."""

    def test_athlete_profile_resource(self, coach_client: GarminCoachClient) -> None:
        res = _run_async(mcp.read_resource("garmin://athlete/profile"))
        text = _extract_text(res)
        assert "Alex Rivera" in text
        assert "174" in text

    def test_coach_context_today_resource(self, coach_client: GarminCoachClient) -> None:
        res = _run_async(mcp.read_resource("garmin://coach/context/today"))
        text = _extract_text(res)
        assert "79" in text
        assert "78" in text

    def test_morning_readiness_check_prompt(self) -> None:
        res = _run_async(
            mcp.get_prompt("morning-readiness-check", {"target_date": "2026-11-11"})
        )
        text = _extract_text(res)
        assert "get_coach_daily_briefing" in text
        assert "2026-11-11" in text

    def test_post_workout_debrief_prompt(self) -> None:
        res = _run_async(
            mcp.get_prompt("post-workout-debrief", {"activity_id": "17501001"})
        )
        text = _extract_text(res)
        assert "get_activity_details" in text
        assert "17501001" in text

    def test_weekly_training_plan_prompt(self) -> None:
        res = _run_async(
            mcp.get_prompt(
                "weekly-training-plan",
                {
                    "goal": "Sub-90 Half Marathon",
                    "target_race_date": "2027-03-15",
                },
            )
        )
        text = _extract_text(res)
        assert "get_health_trends" in text
        assert "Sub-90 Half Marathon" in text

    def test_graceful_error_handling_in_tools_and_resources(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from unittest.mock import MagicMock
        from garmin_coach_mcp import server
        from garmin_coach_mcp.exceptions import GarminAuthError

        failing_client = MagicMock()
        failing_client.unit_system = "metric"
        failing_client.fetch_daily_briefing_raw.side_effect = GarminAuthError(
            "Session expired; run `garmin-coach-mcp auth`."
        )
        failing_client.fetch_athlete_profile_raw.side_effect = GarminAuthError(
            "Session expired; run `garmin-coach-mcp auth`."
        )
        server.set_client(failing_client)
        try:
            err_md = invoke_mcp_tool("get_coach_daily_briefing", response_format="markdown")
            assert "garmin-coach-mcp auth" in err_md

            err_json = invoke_mcp_tool("get_coach_daily_briefing", response_format="json")
            parsed = json.loads(err_json)
            assert "error" in parsed

            res = _run_async(mcp.read_resource("garmin://athlete/profile"))
            assert "garmin-coach-mcp auth" in _extract_text(res)
        finally:
            server.set_client(None)

    def test_cli_main_auth_subcommand(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from garmin_coach_mcp.server import main

        monkeypatch.setattr(
            "garmin_coach_mcp.auth.GarminAuthManager.interactive_login",
            lambda self, **kwargs: tmp_path,
        )
        exit_code = main(["auth", "--email", "runner@example.com", "--token-dir", str(tmp_path)])
        assert exit_code == 0

    def test_cli_export_tokens_subcommand(
        self, tmp_path: Any, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from garmin_coach_mcp.auth import GarminAuthManager
        from garmin_coach_mcp.server import main

        monkeypatch.delenv("GARMIN_TOKEN_BASE64", raising=False)
        token_dir = tmp_path / "cli_export_tokens"
        token_dir.mkdir(parents=True)

        # Missing tokens -> exit code 1 and stderr message
        fail_code = main(["export-tokens", "--token-dir", str(token_dir)])
        assert fail_code == 1
        err_captured = capsys.readouterr()
        assert "Token export error:" in err_captured.err

        # Populate tokens -> exit code 0 and base64 bundle printed to stdout
        (token_dir / "oauth1_token.json").write_text('{"oauth_token": "abc"}', encoding="utf-8")
        (token_dir / "oauth2_token.json").write_text('{"access_token": "xyz"}', encoding="utf-8")

        ok_code = main(["export-tokens", "--token-dir", str(token_dir)])
        assert ok_code == 0
        ok_captured = capsys.readouterr()
        b64_out = ok_captured.out.strip()
        assert len(b64_out) > 10

        # Verify exported string hydrates cleanly into a new directory
        verify_dir = tmp_path / "cli_verify_hydrate"
        mgr = GarminAuthManager(token_dir=verify_dir, token_b64=b64_out)
        assert mgr.has_saved_tokens() is True

    def test_cli_verify_subcommand(
        self,
        tmp_path: Any,
        coach_client: GarminCoachClient,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from garmin_coach_mcp.server import main

        monkeypatch.delenv("GARMIN_TOKEN_BASE64", raising=False)
        token_dir = tmp_path / "cli_verify_tokens"
        token_dir.mkdir(parents=True)

        # Missing tokens -> exit code 1 and stderr message
        fail_code = main(["verify", "--token-dir", str(token_dir)])
        assert fail_code == 1
        err_captured = capsys.readouterr()
        assert "Verification error:" in err_captured.err

        # Populate tokens -> exit code 0 and athlete profile summary printed to stdout
        (token_dir / "garmin_tokens.json").write_text('{"oauth_token": "abc"}', encoding="utf-8")

        ok_code = main(["verify", "--token-dir", str(token_dir)])
        assert ok_code == 0
        ok_captured = capsys.readouterr()
        assert "Garmin Connect Verification: OK" in ok_captured.out
        assert "Alex Rivera" in ok_captured.out
        assert "metric" in ok_captured.out

    def test_install_sh_script_execution(self) -> None:
        from pathlib import Path
        import subprocess

        repo_root = Path(__file__).resolve().parent.parent
        install_script = repo_root / "install.sh"
        assert install_script.is_file()

        help_res = subprocess.run(
            [str(install_script), "--help"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        assert help_res.returncode == 0
        assert "Usage: ./install.sh" in help_res.stdout
        assert "--skip-auth" in help_res.stdout

        run_res = subprocess.run(
            [str(install_script), "--skip-auth", "--skip-verify"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        assert run_res.returncode == 0
        assert "[1/5]" in run_res.stdout
        assert "[2/5]" in run_res.stdout
        assert "[3/5]" in run_res.stdout
        assert "[4/5]" in run_res.stdout
        assert "[5/5]" in run_res.stdout
        assert "Setup Complete!" in run_res.stdout

    def test_install_ps1_script_structure(self) -> None:
        from pathlib import Path

        repo_root = Path(__file__).resolve().parent.parent
        ps1_script = repo_root / "install.ps1"
        assert ps1_script.is_file()

        content = ps1_script.read_text(encoding="utf-8")
        assert len(content.strip()) > 0

        # Verify all 5 stages are defined
        for stage in ("[1/5]", "[2/5]", "[3/5]", "[4/5]", "[5/5]"):
            assert stage in content

        # Verify all required CLI parameters are defined
        for param_name in ("$TokenDir", "$SkipAuth", "$SkipVerify", "$Yes", "$Help"):
            assert param_name in content

        # Verify Windows virtualenv paths and Final Summary Banner
        assert r".venv\Scripts\garmin-coach-mcp.exe" in content
        assert r".venv\Scripts\pip.exe" in content
        assert "Setup Complete! garmin-coach-mcp is ready." in content
        assert "gemini mcp add garmin-coach" in content

        # Verify install.sh includes the Windows hint pointing to .\install.ps1
        sh_content = (repo_root / "install.sh").read_text(encoding="utf-8")
        assert r"On Windows, please run .\install.ps1 in PowerShell" in sh_content

    def test_cli_parser_streamable_http_and_auth_token(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from unittest.mock import MagicMock
        from garmin_coach_mcp.server import _build_arg_parser, main

        monkeypatch.delenv("GARMIN_MCP_TRANSPORT", raising=False)
        monkeypatch.delenv("GARMIN_MCP_AUTH_TOKEN", raising=False)
        monkeypatch.delenv("GARMIN_MCP_PORT", raising=False)

        parser = _build_arg_parser()
        args = parser.parse_args(
            [
                "--transport",
                "streamable-http",
                "--port",
                "8080",
                "--auth-token",
                "secret-token-123",
            ]
        )
        assert args.transport == "streamable-http"
        assert args.host == "127.0.0.1"
        assert args.port == 8080
        assert args.auth_token == "secret-token-123"

        mock_uvicorn_run = MagicMock()
        monkeypatch.setattr("uvicorn.run", mock_uvicorn_run)
        exit_code = main(
            [
                "--transport",
                "streamable-http",
                "--host",
                "127.0.0.1",
                "--port",
                "8080",
                "--auth-token",
                "secret-token-123",
            ]
        )
        assert exit_code == 0
        mock_uvicorn_run.assert_called_once()
        _, call_kwargs = mock_uvicorn_run.call_args
        assert call_kwargs["host"] == "127.0.0.1"
        assert call_kwargs["port"] == 8080


class TestStreamableHTTPAndBearerAuth:
    """Tests for BearerAuthMiddleware and create_http_app (streamable-http and sse)."""

    def test_healthz_and_bearer_auth_on_create_http_app(self) -> None:
        from starlette.testclient import TestClient
        from garmin_coach_mcp.server import create_http_app

        app = create_http_app(transport="streamable-http", auth_token="secret-token-123")
        with TestClient(app, raise_server_exceptions=False) as client:
            # 1. GET /healthz returns 200 OK without Authorization header
            health_resp = client.get("/healthz")
            assert health_resp.status_code == 200
            health_json = health_resp.json()
            assert health_json["status"] == "ok"
            assert health_json["service"] == "garmin-coach-mcp"

            # 2. Request without Authorization header returns 401 Unauthorized + WWW-Authenticate: Bearer
            no_auth_resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
            assert no_auth_resp.status_code == 401
            assert no_auth_resp.headers.get("www-authenticate") == "Bearer"
            assert no_auth_resp.json()["error"] == "unauthorized"

            # 3. Request with wrong Bearer token returns 401 Unauthorized + WWW-Authenticate: Bearer
            bad_auth_resp = client.post(
                "/mcp",
                headers={"Authorization": "Bearer wrong-token-999"},
                json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
            )
            assert bad_auth_resp.status_code == 401
            assert bad_auth_resp.headers.get("www-authenticate") == "Bearer"

            # 4. Request with non-Bearer scheme returns 401 Unauthorized
            basic_auth_resp = client.post(
                "/mcp",
                headers={"Authorization": "Basic dXNlcjpwYXNz"},
                json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
            )
            assert basic_auth_resp.status_code == 401
            assert basic_auth_resp.headers.get("www-authenticate") == "Bearer"

            # 5. Request with valid Authorization: Bearer secret-token-123 passes through middleware cleanly
            valid_resp = client.post(
                "/mcp",
                headers={
                    "Authorization": "Bearer secret-token-123",
                    "Accept": "application/json, text/event-stream",
                },
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "pytest-http-client", "version": "0.1.0"},
                    },
                },
            )
            assert valid_resp.status_code != 401
            assert valid_resp.status_code == 200

    def test_bearer_auth_middleware_passthrough_with_inner_asgi_app(self) -> None:
        from starlette.testclient import TestClient
        from garmin_coach_mcp.server import BearerAuthMiddleware

        async def dummy_asgi_app(scope: dict[str, Any], receive: Any, send: Any) -> None:
            if scope.get("type") == "lifespan":
                while True:
                    msg = await receive()
                    if msg["type"] == "lifespan.startup":
                        await send({"type": "lifespan.startup.complete"})
                    elif msg["type"] == "lifespan.shutdown":
                        await send({"type": "lifespan.shutdown.complete"})
                        return
            await BearerAuthMiddleware._send_json_response(
                send,
                status_code=200,
                payload={"reached_inner_app": True, "path": scope.get("path")},
            )

        protected = BearerAuthMiddleware(dummy_asgi_app, auth_token="secret-token-123")
        with TestClient(protected) as client:
            assert client.get("/healthz").status_code == 200
            assert client.get("/mcp").status_code == 401
            ok_resp = client.get(
                "/mcp",
                headers={"Authorization": "Bearer secret-token-123"},
            )
            assert ok_resp.status_code == 200
            assert ok_resp.json() == {"reached_inner_app": True, "path": "/mcp"}



