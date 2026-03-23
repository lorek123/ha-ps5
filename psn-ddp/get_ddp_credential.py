"""Derive the DDP user-credential from a PSN npsso token.

How it works
------------
The DDP ``user-credential`` (64-char hex in WAKEUP packets) is SHA-256 of the
PSN account's numeric account ID.  This script:

1. Exchanges your npsso cookie for an OAuth authorization code (one redirect).
2. Exchanges the code + PKCE verifier for an access token.
3. Calls the PSN account info API to get the numeric account ID.
4. SHA-256 hashes it → the credential.

No phone app required.

Usage
-----
    uv run python get_ddp_credential.py

Get your npsso by visiting this URL while logged into PSN in a browser:
    https://ca.account.sony.com/api/v1/ssocookie
Copy only the value field (not the whole JSON).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

# ---- PSN OAuth constants (PS App client) -----------------------------------

_CLIENT_ID = "09515159-7237-4370-9b40-3806e67c0891"
# Basic base64(client_id:client_secret) — sourced from psnawp
_BASIC_AUTH = "Basic MDk1MTUxNTktNzIzNy00MzcwLTliNDAtMzgwNmU2N2MwODkxOnVjUGprYTV0bnRCMktxc1A="
_REDIRECT_URI = "com.scee.psxandroid.scecompcall://redirect"
_SCOPE = "psn:mobile.v2.core psn:clientapp"

_AUTH_URL = "https://ca.account.sony.com/api/authz/v3/oauth/authorize"
_TOKEN_URL = "https://ca.account.sony.com/api/authz/v3/oauth/token"
_ACCOUNT_URL = "https://dms.api.playstation.com/api/v1/devices/accounts/me"

_UA = "com.sony.snei.np.android.sso.share.oauth.versa.USER_AGENT"


# ---- PKCE helpers ----------------------------------------------------------


def _make_verifier() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()


def _make_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


# ---- OAuth steps -----------------------------------------------------------


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Prevent urllib from following any redirect."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # don't follow


def _get_auth_code(npsso: str) -> str:
    """Exchange npsso cookie for an OAuth authorization code."""
    params = urllib.parse.urlencode(
        {
            "access_type": "offline",
            "client_id": _CLIENT_ID,
            "redirect_uri": _REDIRECT_URI,
            "response_type": "code",
            "scope": _SCOPE,
        }
    )
    req = urllib.request.Request(
        f"{_AUTH_URL}?{params}",
        headers={"Cookie": f"npsso={npsso}", "User-Agent": _UA},
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        opener.open(req)
    except urllib.error.HTTPError as e:
        location = e.headers.get("Location", "")
        match = re.search(r"[?&]code=([^&]+)", location)
        if match:
            return match.group(1)
        raise RuntimeError(
            f"npsso exchange failed. Redirect was: {location!r}\n"
            "Make sure your npsso token is valid and not expired."
        ) from e
    raise RuntimeError("Authorization server did not redirect — npsso may be invalid.")


def _get_access_token(code: str, verifier: str) -> str:
    """Exchange authorization code + PKCE verifier for an access token."""
    body = urllib.parse.urlencode(
        {
            "code": code,
            "code_verifier": verifier,
            "grant_type": "authorization_code",
            "redirect_uri": _REDIRECT_URI,
            "token_format": "jwt",
        }
    ).encode()
    req = urllib.request.Request(
        _TOKEN_URL,
        data=body,
        headers={
            "Authorization": _BASIC_AUTH,
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": _UA,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())["access_token"]
    except urllib.error.HTTPError as e:
        body_text = e.read().decode(errors="replace")
        raise RuntimeError(f"Token exchange failed [{e.code}]: {body_text}") from e


def _get_account_id(access_token: str) -> str:
    req = urllib.request.Request(
        _ACCOUNT_URL,
        headers={"Authorization": f"Bearer {access_token}", "User-Agent": _UA},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())["accountId"]


def derive_credential(npsso: str) -> str:
    verifier = _make_verifier()

    print("  [1/3] Exchanging npsso for authorization code…")
    code = _get_auth_code(npsso)

    print("  [2/3] Exchanging code for access token…")
    access_token = _get_access_token(code, verifier)

    print("  [3/3] Fetching PSN account ID…")
    account_id = _get_account_id(access_token)
    print(f"         account_id = {account_id!r}")

    return hashlib.sha256(account_id.encode()).hexdigest()


def main() -> None:
    print("PSN DDP credential derivation")
    print("=" * 40)
    print()
    print("Get your npsso by visiting this URL while logged into PSN:")
    print("  https://ca.account.sony.com/api/v1/ssocookie")
    print("Copy only the token value (not the whole JSON).")
    print()
    npsso = input("Paste npsso token: ").strip()
    # Accept pasted JSON too
    if npsso.startswith("{"):
        try:
            npsso = json.loads(npsso)["npsso"]
        except Exception:
            pass
    if not npsso:
        print("ERROR: npsso token is required.")
        sys.exit(1)

    print()
    try:
        credential = derive_credential(npsso)
    except Exception as e:
        print(f"\nERROR: {e}")
        sys.exit(1)

    print()
    print(f"DDP credential:\n\n  {credential}\n")
    print("Store this in your HA config or pass it to async_wakeup().")


if __name__ == "__main__":
    main()
