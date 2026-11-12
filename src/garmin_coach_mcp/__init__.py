"""Garmin Coach MCP Server package."""

from __future__ import annotations

from garmin_coach_mcp.auth import GarminAuthManager
from garmin_coach_mcp.cache import TTLCache
from garmin_coach_mcp.client import GarminCoachClient
from garmin_coach_mcp.exceptions import (
    GarminAPIError,
    GarminAuthError,
    GarminCoachError,
    GarminRateLimitError,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "GarminAPIError",
    "GarminAuthError",
    "GarminAuthManager",
    "GarminCoachClient",
    "GarminCoachError",
    "GarminRateLimitError",
    "TTLCache",
]
