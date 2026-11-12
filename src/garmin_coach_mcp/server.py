"""FastMCP server, client dependency injection, output formatters, and CLI entrypoint."""

from __future__ import annotations

import argparse
import hmac
import json
import os
import sys
from typing import Any, Literal

try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:  # pragma: no cover
    from mcp.server.fastmcp import FastMCP  # type: ignore[no-redef]
from pydantic import BaseModel

from garmin_coach_mcp.auth import GarminAuthManager
from garmin_coach_mcp.client import GarminCoachClient
from garmin_coach_mcp.exceptions import (
    GarminAPIError,
    GarminAuthError,
    GarminCoachError,
    GarminRateLimitError,
)

ResponseFormat = Literal["markdown", "json", "hybrid"]

mcp = FastMCP(
    "garmin-coach-mcp",
    instructions="Elite Personal Health, Running, and Fitness Coach MCP Server powered by Garmin Connect telemetry.",
)

_client: GarminCoachClient | None = None


def get_client() -> GarminCoachClient:
    """Return the active GarminCoachClient instance, creating a default one if none is set."""
    global _client
    if _client is None:
        _client = GarminCoachClient()
    return _client


def set_client(client: GarminCoachClient | None) -> None:
    """Inject a custom or mocked GarminCoachClient for testing or reset to None."""
    global _client
    _client = client


def _serialize_payload(
    model_or_dict: BaseModel | list[BaseModel] | list[Any] | dict[str, Any],
) -> Any:
    """Convert Pydantic BaseModel instances (or lists of BaseModels) into JSON-serializable structures."""
    if isinstance(model_or_dict, BaseModel):
        return model_or_dict.model_dump(mode="json")
    if isinstance(model_or_dict, list):
        return [
            item.model_dump(mode="json") if isinstance(item, BaseModel) else item
            for item in model_or_dict
        ]
    return model_or_dict


def format_tool_output(
    markdown_summary: str,
    model_or_dict: BaseModel | list[BaseModel] | dict[str, Any],
    response_format: Literal["markdown", "json", "hybrid"] = "hybrid",
) -> str:
    """Format a tool response into Markdown, compact JSON, or hybrid Markdown + fenced JSON.

    Args:
        markdown_summary: Clean human/LLM-readable Markdown summary.
        model_or_dict: Normalized Pydantic model, list of models, or dictionary payload.
        response_format: One of `"markdown"`, `"json"`, or `"hybrid"` (default).

    Returns:
        Formatted string output matching the requested `response_format`.
    """
    fmt = (response_format or "hybrid").strip().lower()
    if fmt == "markdown":
        return markdown_summary.strip()

    payload = _serialize_payload(model_or_dict)
    if fmt == "json":
        return json.dumps(payload, separators=(",", ":"), default=str)

    json_block = json.dumps(payload, indent=2, default=str)
    return f"{markdown_summary.strip()}\n\n```json\n{json_block}\n```"


def format_error_output(
    error: Exception,
    tool_name: str,
    response_format: Literal["markdown", "json", "hybrid"] = "hybrid",
) -> str:
    """Format a graceful, actionable error message when a Garmin API or auth failure occurs."""
    if isinstance(error, GarminAuthError):
        remediation = (
            "Run `garmin-coach-mcp auth` in an interactive terminal to complete Garmin Connect "
            "login (including 2FA/MFA) and save OAuth tokens to `~/.garminconnect`, or set "
            "`GARMIN_EMAIL` and `GARMIN_PASSWORD` environment variables."
        )
        category = "authentication_error"
    elif isinstance(error, GarminRateLimitError):
        remediation = (
            "Garmin Connect API rate limit (HTTP 429) was reached. Wait a few minutes before "
            "retrying; cached responses in the local SQLite TTL cache will serve repeat queries."
        )
        category = "rate_limit_error"
    elif isinstance(error, GarminAPIError):
        remediation = (
            "Upstream Garmin Connect service returned an error. Verify network connectivity "
            "and check whether the requested activity ID or date range is valid."
        )
        category = "upstream_api_error"
    elif isinstance(error, GarminCoachError):
        remediation = (
            "Verify your Garmin Connect configuration (`garmin-coach-mcp auth`) and input parameters."
        )
        category = "coach_error"
    else:
        remediation = "Verify tool input parameters and Garmin Connect session status."
        category = "execution_error"

    error_payload: dict[str, Any] = {
        "error": type(error).__name__,
        "category": category,
        "tool": tool_name,
        "message": str(error),
        "remediation": remediation,
    }
    markdown_summary = (
        f"# Garmin Coach Error in `{tool_name}`\n\n"
        f"- **Error Type**: `{type(error).__name__}` ({category})\n"
        f"- **Details**: {error}\n"
        f"- **Actionable Remediation**: {remediation}"
    )
    return format_tool_output(markdown_summary, error_payload, response_format=response_format)


# Import and register all 8 MCP Tools, 2 MCP Resources, and 3 MCP Prompts
from garmin_coach_mcp.prompts import (  # noqa: E402
    morning_readiness_check,
    post_workout_debrief,
    weekly_training_plan,
)
from garmin_coach_mcp.resources import (  # noqa: E402
    athlete_profile,
    coach_context_today,
    get_athlete_profile,
    get_athlete_profile_resource,
    get_coach_context_today,
    get_coach_context_today_resource,
    read_athlete_profile,
    read_coach_context_today,
)
from garmin_coach_mcp.tools.activities import (  # noqa: E402
    get_activity_details,
    list_recent_activities,
)
from garmin_coach_mcp.tools.briefing import (  # noqa: E402
    get_coach_daily_briefing,
)
from garmin_coach_mcp.tools.health import (  # noqa: E402
    get_body_composition_and_biometrics,
    get_health_trends,
    get_sleep_and_recovery,
    get_training_status_and_load,
)
from garmin_coach_mcp.tools.workouts import (  # noqa: E402
    create_structured_workout_json,
)

# Register all 8 MCP tools
mcp.tool()(get_coach_daily_briefing)
mcp.tool()(get_sleep_and_recovery)
mcp.tool()(get_training_status_and_load)
mcp.tool()(list_recent_activities)
mcp.tool()(get_activity_details)
mcp.tool()(get_health_trends)
mcp.tool()(get_body_composition_and_biometrics)
mcp.tool()(create_structured_workout_json)

# Register all 2 MCP resources
mcp.resource(
    "garmin://athlete/profile",
    name="athlete_profile",
    description=(
        "Static and semi-static Garmin athlete profile including configured Heart Rate Zones, "
        "Pace Zones, Power Zones, Max HR, Lactate Threshold, and Personal Records (PRs) in Markdown + JSON."
    ),
)(get_athlete_profile)

mcp.resource(
    "garmin://coach/context/today",
    name="coach_context_today",
    description=(
        "Dynamic coaching context resource returning today's complete Training Readiness, "
        "Body Battery, Sleep, HRV, RHR, and workout intensity recommendation in clean Markdown."
    ),
)(get_coach_context_today)

# Register all 3 MCP prompts
mcp.prompt(
    name="morning-readiness-check",
    description=(
        "Calls get_coach_daily_briefing to evaluate Training Readiness, Body Battery, "
        "overnight HRV, and sleep quality, outputting a structured readiness score, "
        "recovery bottlenecks, and today's workout adjustment."
    ),
)(morning_readiness_check)

mcp.prompt(
    name="post-workout-debrief",
    description=(
        "Analyzes a specific activity_id (or latest activity via list_recent_activities) "
        "using get_activity_details and get_training_status_and_load to evaluate pacing "
        "evenness, cardiac drift, and HR/power/pace zone compliance."
    ),
)(post_workout_debrief)

mcp.prompt(
    name="weekly-training-plan",
    description=(
        "Audits the last 28 days of training load and biomarker trends (get_health_trends, "
        "list_recent_activities, get_training_status_and_load) to build a periodized 7-day "
        "training plan tailored to the athlete's goal, with optional structured workout JSON export."
    ),
)(weekly_training_plan)


class BearerAuthMiddleware:
    """ASGI middleware providing `/healthz` health checks and optional Bearer token authentication."""

    def __init__(self, app: Any, auth_token: str | None = None) -> None:
        self.app = app
        self.auth_token: str | None = (
            auth_token.strip() if auth_token and auth_token.strip() else None
        )

    @staticmethod
    def _extract_bearer_token(headers: Any) -> str | None:
        """Extract Bearer token from ASGI scope headers, returning None if absent or malformed."""
        if not headers:
            return None
        for raw_key, raw_val in headers:
            key = raw_key.decode("latin-1") if isinstance(raw_key, bytes) else str(raw_key)
            if key.lower() == "authorization":
                val = raw_val.decode("latin-1") if isinstance(raw_val, bytes) else str(raw_val)
                parts = val.strip().split(" ", 1)
                if len(parts) == 2 and parts[0].lower() == "bearer":
                    token = parts[1].strip()
                    if token:
                        return token
                return None
        return None

    @staticmethod
    async def _send_json_response(
        send: Any,
        status_code: int,
        payload: dict[str, Any],
        extra_headers: list[tuple[bytes, bytes]] | None = None,
    ) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers: list[tuple[bytes, bytes]] = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode("ascii")),
        ]
        if extra_headers:
            headers.extend(extra_headers)
        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": headers,
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": body,
                "more_body": False,
            }
        )

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        scope_type = scope.get("type")
        session_mgr = getattr(self.app, "_garmin_session_manager", None)

        if scope_type not in ("http", "websocket"):
            if scope_type == "lifespan" and session_mgr is not None:
                session_mgr._has_started = False
            await self.app(scope, receive, send)
            return

        # Unauthenticated health check endpoint for Cloud Run / Kubernetes probes
        if (
            scope_type == "http"
            and scope.get("path") == "/healthz"
            and str(scope.get("method", "GET")).upper() in ("GET", "HEAD")
        ):
            await self._send_json_response(
                send,
                status_code=200,
                payload={
                    "status": "ok",
                    "service": "garmin-coach-mcp",
                    "version": "0.1.0",
                },
            )
            return

        # Enforce Bearer token authentication when auth_token is configured
        if self.auth_token:
            provided_token = self._extract_bearer_token(scope.get("headers"))
            is_valid = (
                provided_token is not None
                and hmac.compare_digest(
                    provided_token.encode("utf-8"),
                    self.auth_token.encode("utf-8"),
                )
            )
            if not is_valid:
                await self._send_json_response(
                    send,
                    status_code=401,
                    payload={
                        "error": "unauthorized",
                        "message": "Valid Authorization: Bearer <token> header required.",
                    },
                    extra_headers=[(b"www-authenticate", b"Bearer")],
                )
                return

        if (
            scope_type == "http"
            and session_mgr is not None
            and getattr(session_mgr, "_task_group", None) is None
        ):
            session_mgr._has_started = False
            async with session_mgr.run():
                await self.app(scope, receive, send)
            session_mgr._has_started = False
            return

        await self.app(scope, receive, send)


def create_http_app(
    transport: Literal["sse", "streamable-http"] = "streamable-http",
    auth_token: str | None = None,
) -> Any:
    """Create a Starlette/ASGI HTTP application for `streamable-http` or `sse` wrapped with `BearerAuthMiddleware`."""
    if hasattr(mcp, "settings") and hasattr(mcp.settings, "transport_security"):
        mcp.settings.transport_security.enable_dns_rebinding_protection = False

    if transport == "sse":
        asgi_app = mcp.sse_app()
    else:
        if hasattr(mcp, "_session_manager"):
            mcp._session_manager = None
        asgi_app = mcp.streamable_http_app()
        if hasattr(mcp, "_session_manager"):
            asgi_app._garmin_session_manager = mcp._session_manager

    resolved_token = (
        auth_token if auth_token is not None else os.environ.get("GARMIN_MCP_AUTH_TOKEN")
    )
    return BearerAuthMiddleware(asgi_app, auth_token=resolved_token)


def _build_arg_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser for `garmin-coach-mcp`."""
    default_transport = os.environ.get("GARMIN_MCP_TRANSPORT", "stdio").strip() or "stdio"
    raw_port = (
        os.environ.get("GARMIN_MCP_PORT", "").strip()
        or os.environ.get("PORT", "").strip()
        or "8000"
    )
    try:
        default_port = int(raw_port)
    except ValueError:
        default_port = 8000
    default_auth_token = os.environ.get("GARMIN_MCP_AUTH_TOKEN")

    parser = argparse.ArgumentParser(
        prog="garmin-coach-mcp",
        description=(
            "Garmin Coach MCP Server — Elite Personal Health, Running, and Fitness Coach "
            "powered by Garmin Connect telemetry."
        ),
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default=default_transport,
        help="MCP transport protocol to run (default: stdio or GARMIN_MCP_TRANSPORT).",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind host address when using HTTP/SSE transport (default: 127.0.0.1 for local-only security).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=default_port,
        help="Bind port when using HTTP/SSE transport (default: 8000 or GARMIN_MCP_PORT / PORT).",
    )
    parser.add_argument(
        "--auth-token",
        dest="auth_token",
        default=default_auth_token,
        help="Optional Bearer token secret for authenticating HTTP requests (defaults to GARMIN_MCP_AUTH_TOKEN).",
    )

    subparsers = parser.add_subparsers(dest="command")
    auth_parser = subparsers.add_parser(
        "auth",
        help="Run interactive Garmin Connect login (supports 2FA/MFA) and save OAuth tokens.",
    )
    auth_parser.add_argument(
        "--email",
        default=None,
        help="Garmin Connect email address (overrides GARMIN_EMAIL).",
    )
    auth_parser.add_argument(
        "--password",
        default=None,
        help="Garmin Connect password (optional; prompts securely if omitted).",
    )
    auth_parser.add_argument(
        "--token-dir",
        dest="token_dir",
        default=None,
        help="Directory to store Garmin OAuth1/OAuth2 tokens (default: ~/.garminconnect or GARMIN_TOKEN_DIR).",
    )

    export_parser = subparsers.add_parser(
        "export-tokens",
        help="Export saved Garmin OAuth1/OAuth2 tokens as a Base64 string for stateless Cloud Run deployments.",
    )
    export_parser.add_argument(
        "--token-dir",
        dest="token_dir",
        default=None,
        help="Directory containing saved Garmin OAuth1/OAuth2 tokens (default: ~/.garminconnect or GARMIN_TOKEN_DIR).",
    )

    verify_parser = subparsers.add_parser(
        "verify",
        help="Verify saved Garmin OAuth tokens and fetch athlete profile to confirm account access.",
    )
    verify_parser.add_argument(
        "--token-dir",
        dest="token_dir",
        default=None,
        help="Directory containing saved Garmin OAuth1/OAuth2 tokens (default: ~/.garminconnect or GARMIN_TOKEN_DIR).",
    )
    return parser


_build_parser = _build_arg_parser


def _run_verify_command(args: argparse.Namespace) -> int:
    """Verify saved Garmin OAuth tokens and perform a live athlete profile read check."""
    from garmin_coach_mcp.normalizers import normalize_athlete_profile

    try:
        auth_manager = GarminAuthManager(token_dir=args.token_dir)
        if not auth_manager.has_saved_tokens():
            raise GarminAuthError(
                f"No saved Garmin OAuth tokens found in {auth_manager.token_dir}. "
                "Run `garmin-coach-mcp auth` to authenticate first."
            )
        client = (
            _client
            if _client is not None
            else GarminCoachClient(auth_manager=auth_manager)
        )
        raw_profile = client.fetch_athlete_profile_raw()
        unit_system = getattr(client, "unit_system", "metric")
        profile = normalize_athlete_profile(raw_profile, unit_system=unit_system)
        athlete_name = profile.full_name or profile.display_name or "Garmin Athlete"
        bio = profile.biometrics
        bio_parts: list[str] = []
        if bio.max_hr_bpm is not None:
            bio_parts.append(f"Max HR: {bio.max_hr_bpm} bpm")
        if bio.resting_hr_bpm is not None:
            bio_parts.append(f"Resting HR: {bio.resting_hr_bpm} bpm")
        if bio.vo2_max_running is not None:
            bio_parts.append(f"VO2 Max (Run): {bio.vo2_max_running}")
        if bio.vo2_max_cycling is not None:
            bio_parts.append(f"VO2 Max (Cycle): {bio.vo2_max_cycling}")
        biometrics_summary = ", ".join(bio_parts) if bio_parts else "N/A"

        print("Garmin Connect Verification: OK")
        print(f"  Token Directory : {auth_manager.token_dir} (OK)")
        print(f"  Athlete Name    : {athlete_name}")
        print(f"  Unit System     : {profile.unit_system}")
        print(f"  Key Biometrics  : {biometrics_summary}")
        return 0
    except GarminCoachError as exc:
        print(f"Verification error: {exc}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for `garmin-coach-mcp`."""
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    if args.command == "auth":
        try:
            auth_manager = GarminAuthManager(
                email=args.email,
                password=args.password,
                token_dir=args.token_dir,
            )
            saved_dir = auth_manager.interactive_login(
                email=args.email,
                password=args.password,
            )
            print(
                f"Successfully authenticated with Garmin Connect. OAuth tokens saved to: {saved_dir}"
            )
            return 0
        except GarminCoachError as exc:
            print(f"Authentication error: {exc}", file=sys.stderr)
            return 1

    if args.command == "export-tokens":
        try:
            auth_manager = GarminAuthManager(token_dir=args.token_dir)
            encoded = auth_manager.export_tokens_base64()
            print(encoded)
            return 0
        except GarminCoachError as exc:
            print(f"Token export error: {exc}", file=sys.stderr)
            return 1

    if args.command == "verify":
        return _run_verify_command(args)

    if args.transport in ("sse", "streamable-http"):
        if hasattr(mcp, "settings"):
            mcp.settings.host = args.host
            mcp.settings.port = args.port
        if args.auth_token:
            import uvicorn

            http_app = create_http_app(
                transport=args.transport,
                auth_token=args.auth_token,
            )
            uvicorn.run(http_app, host=args.host, port=args.port)
        elif hasattr(mcp, "settings"):
            mcp.run(transport=args.transport)
        else:
            mcp.run(transport=args.transport, host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio")
    return 0


__all__ = [
    "BearerAuthMiddleware",
    "ResponseFormat",
    "athlete_profile",
    "coach_context_today",
    "create_http_app",
    "create_structured_workout_json",
    "format_error_output",
    "format_tool_output",
    "get_activity_details",
    "get_athlete_profile",
    "get_athlete_profile_resource",
    "get_body_composition_and_biometrics",
    "get_client",
    "get_coach_context_today",
    "get_coach_context_today_resource",
    "get_coach_daily_briefing",
    "get_health_trends",
    "get_sleep_and_recovery",
    "get_training_status_and_load",
    "list_recent_activities",
    "main",
    "mcp",
    "morning_readiness_check",
    "post_workout_debrief",
    "read_athlete_profile",
    "read_coach_context_today",
    "set_client",
    "weekly_training_plan",
]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
