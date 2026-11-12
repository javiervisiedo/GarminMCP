"""Custom exception hierarchy for Garmin Coach MCP."""

from __future__ import annotations


class GarminCoachError(Exception):
    """Base exception for all Garmin Coach MCP errors."""


class GarminAuthError(GarminCoachError):
    """Raised when Garmin credentials/tokens are missing, expired, or MFA is required in headless mode."""


class GarminRateLimitError(GarminCoachError):
    """Raised on HTTP 429 / Garmin Connect API rate limit errors."""


class GarminAPIError(GarminCoachError):
    """Raised on upstream Garmin Connect API failures."""
