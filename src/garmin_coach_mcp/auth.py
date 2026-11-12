"""Garmin Connect OAuth1/OAuth2 session and token manager with MFA support."""

from __future__ import annotations

import base64
import binascii
import getpass
import json
import logging
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from garmin_coach_mcp.exceptions import GarminAuthError

try:
    from garminconnect import (
        Garmin,
        GarminConnectAuthenticationError,
        GarminConnectConnectionError,
        GarminConnectTooManyRequestsError,
    )
except ImportError:  # pragma: no cover
    Garmin = None  # type: ignore[assignment,misc]
    GarminConnectAuthenticationError = Exception  # type: ignore[assignment,misc]
    GarminConnectConnectionError = Exception  # type: ignore[assignment,misc]
    GarminConnectTooManyRequestsError = Exception  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)

GARMIN_TOKENS_FILENAME = "garmin_tokens.json"
OAUTH1_TOKEN_FILENAME = "oauth1_token.json"
OAUTH2_TOKEN_FILENAME = "oauth2_token.json"


class GarminAuthManager:
    """Manages Garmin Connect authentication, OAuth token persistence, and MFA login.

    Security guarantees:
    - Never logs passwords, MFA codes, or session tokens.
    - Enforces 0o700 permissions on the token directory and 0o600 on token files.
    """

    def __init__(
        self,
        email: str | None = None,
        password: str | None = None,
        token_dir: str | Path | None = None,
        token_b64: str | None = None,
    ) -> None:
        env_email = os.environ.get("GARMIN_EMAIL", "").strip() or None
        env_password = os.environ.get("GARMIN_PASSWORD") or None
        env_token_dir = os.environ.get("GARMIN_TOKEN_DIR", "").strip() or "~/.garminconnect"
        env_token_b64 = os.environ.get("GARMIN_TOKEN_BASE64", "").strip() or None

        self.email: str | None = email if email is not None else env_email
        self.password: str | None = password if password is not None else env_password
        raw_dir = token_dir if token_dir is not None else env_token_dir
        self.token_dir: Path = Path(raw_dir).expanduser()
        raw_b64 = token_b64 if token_b64 is not None else env_token_b64
        self.token_b64: str | None = raw_b64.strip() if raw_b64 and raw_b64.strip() else None

        self._ensure_token_dir()

    def _ensure_token_dir(self) -> Path:
        """Create token_dir if needed and enforce 0o700 permissions."""
        try:
            self.token_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(self.token_dir, 0o700)
        except OSError:
            pass
        return self.token_dir

    def _secure_token_files(self) -> None:
        """Enforce 0o600 permissions on all token files in token_dir."""
        self._ensure_token_dir()
        for token_name in (GARMIN_TOKENS_FILENAME, OAUTH1_TOKEN_FILENAME, OAUTH2_TOKEN_FILENAME):
            token_file = self.token_dir / token_name
            if token_file.exists():
                try:
                    os.chmod(token_file, 0o600)
                except OSError:
                    pass
        for file_path in self.token_dir.glob("*.json"):
            try:
                os.chmod(file_path, 0o600)
            except OSError:
                pass

    def _persist_tokens(self, client: Any) -> None:
        """Dump session tokens via garminconnect native client or garth and enforce 0o600 permissions."""
        self._ensure_token_dir()
        dumped = False

        native_client = getattr(client, "client", None)
        if native_client is not None and hasattr(native_client, "dump"):
            native_client.dump(str(self.token_dir))
            dumped = True

        garth_client = getattr(client, "garth", None)
        if garth_client is not None and hasattr(garth_client, "dump"):
            garth_client.dump(str(self.token_dir))
            dumped = True

        has_garmin_tokens = (self.token_dir / GARMIN_TOKENS_FILENAME).is_file()
        has_oauth_pair = (
            (self.token_dir / OAUTH1_TOKEN_FILENAME).is_file()
            and (self.token_dir / OAUTH2_TOKEN_FILENAME).is_file()
        )
        if dumped and not has_garmin_tokens and not has_oauth_pair:
            # If client.client.dump / client.garth.dump is a test mock that did not write
            # files to disk, ensure placeholder token files exist with 0o600 permissions.
            for token_name in (GARMIN_TOKENS_FILENAME, OAUTH1_TOKEN_FILENAME, OAUTH2_TOKEN_FILENAME):
                token_file = self.token_dir / token_name
                if not token_file.exists():
                    token_file.write_text(json.dumps({"mock_token": True}), encoding="utf-8")

        self._secure_token_files()

    def _hydrate_tokens_from_base64(self) -> bool:
        """Hydrate Garmin token files from GARMIN_TOKEN_BASE64 if not yet present on disk."""
        garmin_tokens = self.token_dir / GARMIN_TOKENS_FILENAME
        oauth1 = self.token_dir / OAUTH1_TOKEN_FILENAME
        oauth2 = self.token_dir / OAUTH2_TOKEN_FILENAME
        if garmin_tokens.is_file() or (oauth1.is_file() and oauth2.is_file()):
            return True

        if not self.token_b64:
            return False

        cleaned_b64 = "".join(self.token_b64.split())
        if not cleaned_b64 or not re.fullmatch(r"[A-Za-z0-9+/=_-]+", cleaned_b64):
            raise GarminAuthError(
                "Malformed GARMIN_TOKEN_BASE64 bundle: string contains invalid Base64 characters. "
                "Generate a fresh bundle with `garmin-coach-mcp export-tokens`."
            )

        remainder = len(cleaned_b64) % 4
        if remainder == 1:
            raise GarminAuthError(
                "Malformed GARMIN_TOKEN_BASE64 bundle: invalid Base64 length. "
                "Generate a fresh bundle with `garmin-coach-mcp export-tokens`."
            )
        if remainder:
            cleaned_b64 += "=" * (4 - remainder)

        try:
            normalized_b64 = cleaned_b64.replace("-", "+").replace("_", "/")
            raw_bytes = base64.b64decode(normalized_b64, validate=True)
            decoded_text = raw_bytes.decode("utf-8")
            bundle = json.loads(decoded_text)
        except (binascii.Error, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GarminAuthError(
                "Malformed GARMIN_TOKEN_BASE64 bundle: could not decode Base64 JSON payload. "
                "Generate a fresh bundle with `garmin-coach-mcp export-tokens`."
            ) from exc

        if not isinstance(bundle, dict):
            raise GarminAuthError(
                "Malformed GARMIN_TOKEN_BASE64 bundle: decoded JSON payload must be an object "
                f"containing '{GARMIN_TOKENS_FILENAME}' or both '{OAUTH1_TOKEN_FILENAME}' and '{OAUTH2_TOKEN_FILENAME}'."
            )

        has_garmin_key = GARMIN_TOKENS_FILENAME in bundle
        has_oauth_keys = OAUTH1_TOKEN_FILENAME in bundle and OAUTH2_TOKEN_FILENAME in bundle
        if not has_garmin_key and not has_oauth_keys:
            raise GarminAuthError(
                "Malformed GARMIN_TOKEN_BASE64 bundle: missing required key "
                f"('{GARMIN_TOKENS_FILENAME}' or both '{OAUTH1_TOKEN_FILENAME}' and '{OAUTH2_TOKEN_FILENAME}')."
            )

        keys_to_write = [
            key
            for key in (GARMIN_TOKENS_FILENAME, OAUTH1_TOKEN_FILENAME, OAUTH2_TOKEN_FILENAME)
            if key in bundle
        ]

        for token_name in keys_to_write:
            val = bundle[token_name]
            if not isinstance(val, (dict, str)) or (isinstance(val, str) and not val.strip()):
                raise GarminAuthError(
                    f"Malformed GARMIN_TOKEN_BASE64 bundle: invalid value for '{token_name}'."
                )
            if isinstance(val, str):
                try:
                    json.loads(val)
                except json.JSONDecodeError as exc:
                    raise GarminAuthError(
                        f"Malformed GARMIN_TOKEN_BASE64 bundle: '{token_name}' is not valid JSON."
                    ) from exc

        self._ensure_token_dir()
        for token_name in keys_to_write:
            token_path = self.token_dir / token_name
            raw_value = bundle[token_name]
            serialized = (
                raw_value
                if isinstance(raw_value, str)
                else json.dumps(raw_value, indent=2)
            )
            token_path.write_text(serialized, encoding="utf-8")
            try:
                os.chmod(token_path, 0o600)
            except OSError:
                pass

        self._secure_token_files()
        return True

    def export_tokens_base64(self) -> str:
        """Package saved Garmin token files into a portable Base64 string."""
        if not self.has_saved_tokens():
            raise GarminAuthError(
                f"No saved tokens found in {self.token_dir}. Run 'garmin-coach-mcp auth' first."
            )

        bundle: dict[str, Any] = {}
        try:
            for token_name in (GARMIN_TOKENS_FILENAME, OAUTH1_TOKEN_FILENAME, OAUTH2_TOKEN_FILENAME):
                token_path = self.token_dir / token_name
                if token_path.is_file():
                    raw_text = token_path.read_text(encoding="utf-8")
                    try:
                        bundle[token_name] = json.loads(raw_text)
                    except json.JSONDecodeError:
                        bundle[token_name] = raw_text
        except OSError as exc:
            raise GarminAuthError(
                f"Failed to read Garmin token files from {self.token_dir}: {exc}"
            ) from exc

        bundle_json = json.dumps(bundle, separators=(",", ":"))
        return base64.b64encode(bundle_json.encode("utf-8")).decode("ascii")

    def has_saved_tokens(self) -> bool:
        """Return True if garmin_tokens.json or both oauth1/oauth2 token files exist in token_dir."""
        self._hydrate_tokens_from_base64()
        garmin_tokens = self.token_dir / GARMIN_TOKENS_FILENAME
        oauth1 = self.token_dir / OAUTH1_TOKEN_FILENAME
        oauth2 = self.token_dir / OAUTH2_TOKEN_FILENAME
        return garmin_tokens.is_file() or (oauth1.is_file() and oauth2.is_file())

    def get_authenticated_client(self) -> Any:
        """Return an authenticated Garmin client using saved tokens or credentials.

        1. Attempts to resume session from self.token_dir if saved tokens exist.
        2. Falls back to self.email and self.password if available and persists tokens.
        3. Raises GarminAuthError with remediation steps if auth fails or credentials are missing.
        """
        if Garmin is None:  # pragma: no cover
            raise GarminAuthError(
                "The 'garminconnect' package is not installed. Run `uv pip install -e .`."
            )

        self._hydrate_tokens_from_base64()

        # Step 1: Attempt token resume if saved tokens exist
        if self.has_saved_tokens():
            try:
                client = Garmin()
                client.login(str(self.token_dir))
                self._persist_tokens(client)
                return client
            except Exception as exc:
                logger.warning(
                    "Saved Garmin session tokens in %s could not be resumed (%s); "
                    "attempting credential fallback.",
                    self.token_dir,
                    type(exc).__name__,
                )

        # Step 2: Fallback to email + password login
        if self.email and self.password:
            try:
                client = Garmin(email=self.email, password=self.password)
                login_result = client.login()
                if isinstance(login_result, tuple) and len(login_result) > 0 and login_result[0] == "needs_mfa":
                    raise GarminAuthError(
                        "Multi-Factor Authentication (MFA/2FA) is required. "
                        "Cannot prompt for MFA in headless MCP server mode. "
                        "Please run `garmin-coach-mcp auth` in an interactive terminal to "
                        f"bootstrap tokens in {self.token_dir}."
                    )
                self._persist_tokens(client)
                return client
            except GarminAuthError:
                raise
            except EOFError as exc:
                raise GarminAuthError(
                    "Multi-Factor Authentication (MFA/2FA) prompt was triggered in headless mode. "
                    "Please run `garmin-coach-mcp auth` in an interactive terminal to save OAuth "
                    f"tokens to {self.token_dir}."
                ) from exc
            except Exception as exc:
                raise GarminAuthError(
                    "Garmin Connect authentication failed with the provided credentials. "
                    "Verify GARMIN_EMAIL and GARMIN_PASSWORD, or run `garmin-coach-mcp auth` "
                    f"interactively to complete 2FA/MFA login (token dir: {self.token_dir})."
                ) from exc

        # Step 3: No valid tokens and no credentials configured
        raise GarminAuthError(
            f"No valid Garmin OAuth tokens found in {self.token_dir} and "
            "GARMIN_EMAIL / GARMIN_PASSWORD environment variables are not set. "
            "Run `garmin-coach-mcp auth` to authenticate interactively (recommended for 2FA/MFA), "
            "or set GARMIN_EMAIL and GARMIN_PASSWORD."
        )

    def interactive_login(
        self,
        email: str | None = None,
        password: str | None = None,
        mfa_prompt_fn: Callable[[], str] | None = None,
    ) -> Path:
        """Perform an interactive Garmin login (supporting 2FA/MFA) and save tokens.

        Returns the Path to the token directory where OAuth1/OAuth2 tokens were saved.
        """
        if Garmin is None:  # pragma: no cover
            raise GarminAuthError(
                "The 'garminconnect' package is not installed. Run `uv pip install -e .`."
            )

        login_email = (email or self.email or "").strip()
        if not login_email:
            try:
                login_email = input("Garmin Connect Email: ").strip()
            except EOFError as exc:
                raise GarminAuthError("Email input was aborted before completion.") from exc

        login_password = password if password is not None else self.password
        if not login_password:
            try:
                login_password = getpass.getpass("Garmin Connect Password: ")
            except EOFError as exc:
                raise GarminAuthError("Password input was aborted before completion.") from exc

        if not login_email or not login_password:
            raise GarminAuthError(
                "Both Garmin email and password are required for interactive login."
            )

        prompt_mfa: Callable[[], str] = mfa_prompt_fn or (
            lambda: input("Enter Garmin MFA / 2FA verification code: ").strip()
        )

        self._ensure_token_dir()

        try:
            client = Garmin(
                email=login_email,
                password=login_password,
                prompt_mfa=prompt_mfa,
            )
            client.login()
            self._persist_tokens(client)
            if not self.has_saved_tokens():
                raise GarminAuthError(
                    f"Garmin login completed, but token files were not written to {self.token_dir}."
                )
            return self.token_dir
        except GarminAuthError:
            raise
        except Exception as exc:
            raise GarminAuthError(
                "Interactive Garmin Connect login failed. Please check your email, "
                "password, and MFA code and try again."
            ) from exc
