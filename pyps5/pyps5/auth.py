"""PSN OAuth2 authentication.

Uses the PlayStation App's PKCE OAuth flow to obtain access tokens.
Reverse engineered from PS App and documented by the community (psnawp, ps5-mqtt).
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
import re
import time
from typing import Any
import json
from urllib.parse import urlencode

import aiohttp

_LOGGER = logging.getLogger(__name__)

# PlayStation App OAuth2 client credentials
# These are baked into the official PS App APK
_CLIENT_ID = "09515159-7237-4370-9b40-3806e67c0891"
_CLIENT_SECRET = "ucPjka5tntB2KqsP"
_REDIRECT_URI = "com.scee.psxandroid.scecompcall://redirect"
_SCOPE = "psn:mobile.v2.core psn:clientapp"

_AUTH_BASE = "https://ca.account.sony.com/api/authz/v3"
_TOKEN_URL = "https://ca.account.sony.com/api/authz/v3/oauth/token"

def account_id_from_access_token(access_token: str) -> str | None:
    """Extract account_id from a PSN JWT access token.

    Decodes the JWT payload without signature verification — we trust PSN.
    Returns None if the token is malformed or the claim is missing.
    """
    try:
        payload_b64 = access_token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload_b64))
        return str(claims["account_id"]) if "account_id" in claims else str(claims.get("sub", "")) or None
    except Exception:
        return None


def _generate_code_verifier() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()


def _code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


class PSNAuth:
    """PSN OAuth2 flow using PKCE.

    Usage (interactive – for config flow):
        auth = PSNAuth(session)
        url = await auth.get_login_url()
        # Direct user to url, they log in, get redirected to callback
        # Extract the ?code= param from the redirect URI
        tokens = await auth.exchange_code(code)

    Usage (npsso token – easier for HA):
        tokens = await PSNAuth.from_npsso(session, npsso_token)
    """

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session
        self._verifier = _generate_code_verifier()

    def get_login_url(self) -> str:
        """Return the PSN login URL. Direct user here in a browser."""
        params = {
            "access_type": "offline",
            "client_id": _CLIENT_ID,
            "code_challenge": _code_challenge(self._verifier),
            "code_challenge_method": "S256",
            "device_base_url": "https://web.np.playstation.com",
            "device_profile": "mobile",
            "prompt": "always",
            "redirect_uri": _REDIRECT_URI,
            "response_type": "code",
            "scope": _SCOPE,
            "ui": "pr",
        }
        return f"{_AUTH_BASE}/oauth/authorize?" + urlencode(params)

    async def exchange_code(self, code: str) -> dict[str, Any]:
        """Exchange an authorization code for access + refresh tokens."""
        data = {
            "code": code,
            "code_verifier": self._verifier,
            "grant_type": "authorization_code",
            "redirect_uri": _REDIRECT_URI,
            "token_format": "jwt",
        }
        return await self._post_token(data)

    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        """Use a refresh token to get a new access token."""
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "redirect_uri": _REDIRECT_URI,
            "scope": _SCOPE,
            "token_format": "jwt",
        }
        return await self._post_token(data)

    async def _post_token(self, data: dict[str, Any]) -> dict[str, Any]:
        async with self._session.post(
            _TOKEN_URL,
            data=data,
            auth=aiohttp.BasicAuth(_CLIENT_ID, _CLIENT_SECRET),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise ValueError(f"PSN token request failed [{resp.status}]: {text}")
            result = await resp.json()
            result["expires_at"] = time.time() + result.get("expires_in", 3600)
            return result

    @classmethod
    async def from_npsso(
        cls, session: aiohttp.ClientSession, npsso: str
    ) -> dict[str, Any]:
        """Obtain tokens from an NPSSO cookie (simplest method for end users).

        Users can get their NPSSO from: https://ca.account.sony.com/api/v1/ssocookie
        after logging in at playstation.com.
        """
        # Exchange NPSSO for auth code
        params = {
            "access_type": "offline",
            "client_id": _CLIENT_ID,
            "redirect_uri": _REDIRECT_URI,
            "response_type": "code",
            "scope": _SCOPE,
        }
        async with session.get(
            f"{_AUTH_BASE}/oauth/authorize",
            params=params,
            cookies={"npsso": npsso},
            allow_redirects=False,
        ) as resp:
            location = resp.headers.get("Location", "")
            code_match = re.search(r"[?&]code=([^&]+)", location)
            if not code_match:
                raise ValueError(
                    f"NPSSO exchange failed. Got redirect: {location!r}. "
                    "Make sure your NPSSO token is valid and not expired."
                )
            code = code_match.group(1)

        auth = cls(session)
        return await auth.exchange_code(code)


class TokenManager:
    """Manages PSN access/refresh tokens with auto-refresh."""

    def __init__(
        self,
        access_token: str,
        refresh_token: str,
        expires_at: float,
        session: aiohttp.ClientSession,
    ) -> None:
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_at = expires_at
        self._session = session

    @classmethod
    def from_token_response(
        cls, tokens: dict[str, Any], session: aiohttp.ClientSession
    ) -> "TokenManager":
        return cls(
            access_token=tokens["access_token"],
            refresh_token=tokens["refresh_token"],
            expires_at=tokens.get("expires_at", time.time() + tokens.get("expires_in", 3600)),
            session=session,
        )

    def is_expired(self, buffer: float = 60.0) -> bool:
        """Return True if the access token expires within `buffer` seconds."""
        return time.time() >= self.expires_at - buffer

    async def ensure_valid(self) -> str:
        """Return a valid access token, refreshing if necessary."""
        if self.is_expired():
            _LOGGER.debug("PSN access token expired, refreshing")
            auth = PSNAuth(self._session)
            tokens = await auth.refresh_access_token(self.refresh_token)
            self.access_token = tokens["access_token"]
            self.refresh_token = tokens.get("refresh_token", self.refresh_token)
            self.expires_at = tokens.get("expires_at", time.time() + tokens.get("expires_in", 3600))
        return self.access_token
