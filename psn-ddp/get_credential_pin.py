"""Get DDP credential via PS5 PIN registration (TCP 9295) with PSN auth.

Steps
-----
1. On PS5: Settings → System → Remote Play → Link Device (shows 8-digit PIN)
2. Run this script with the PIN and your npsso token.
3. The script tries registration with PSN Bearer token in various formats.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request

PS5_IP = "192.168.1.190"
TCP_PORT = 9295

_CLIENT_ID = "09515159-7237-4370-9b40-3806e67c0891"
_BASIC_AUTH = "Basic MDk1MTUxNTktNzIzNy00MzcwLTliNDAtMzgwNmU2N2MwODkxOnVjUGprYTV0bnRCMktxc1A="
_REDIRECT_URI = "com.scee.psxandroid.scecompcall://redirect"
_SCOPE = "psn:mobile.v2.core psn:clientapp"
_AUTH_URL = "https://ca.account.sony.com/api/authz/v3/oauth/authorize"
_TOKEN_URL = "https://ca.account.sony.com/api/authz/v3/oauth/token"
_UA = "com.sony.snei.np.android.sso.share.oauth.versa.USER_AGENT"


def _make_verifier() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()


def _get_access_token(npsso: str) -> str:
    verifier = _make_verifier()
    params = urllib.parse.urlencode({
        "access_type": "offline", "client_id": _CLIENT_ID,
        "redirect_uri": _REDIRECT_URI, "response_type": "code", "scope": _SCOPE,
    })

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **kw): return None

    req = urllib.request.Request(f"{_AUTH_URL}?{params}", headers={"Cookie": f"npsso={npsso}", "User-Agent": _UA})
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        opener.open(req)
    except urllib.error.HTTPError as e:
        location = e.headers.get("Location", "")
        match = re.search(r"[?&]code=([^&]+)", location)
        if not match:
            raise RuntimeError(f"npsso exchange failed: {location!r}") from e
        code = match.group(1)

    body = urllib.parse.urlencode({
        "code": code, "code_verifier": verifier, "grant_type": "authorization_code",
        "redirect_uri": _REDIRECT_URI, "token_format": "jwt",
    }).encode()
    req2 = urllib.request.Request(_TOKEN_URL, data=body, headers={
        "Authorization": _BASIC_AUTH, "Content-Type": "application/x-www-form-urlencoded", "User-Agent": _UA,
    }, method="POST")
    with urllib.request.urlopen(req2) as resp:
        return json.loads(resp.read())["access_token"]


def _did() -> str:
    return os.urandom(16).hex().upper()


def _try(host: str, pin: str, rp_version: str, extra_headers: dict[str, str]) -> bytes:
    headers = {
        "RP-Version": rp_version, "RP-Type": "ctrl", "RP-Did": _did(),
        "RP-AuthType": "C", "RP-Pin": pin, "Host": f"{host}:{TCP_PORT}", "Content-Length": "0",
    }
    headers.update(extra_headers)
    raw = "GET /sce/rp/regist HTTP/1.1\r\n"
    raw += "".join(f"{k}: {v}\r\n" for k, v in headers.items())
    raw += "\r\n"
    try:
        s = socket.create_connection((host, TCP_PORT), timeout=5)
        s.sendall(raw.encode())
        s.settimeout(3)
        resp = b""
        try:
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                resp += chunk
        except OSError:
            pass
        s.close()
        return resp
    except OSError as e:
        return f"CONNECT ERROR: {e}".encode()


def main() -> None:
    host = input(f"PS5 IP [{PS5_IP}]: ").strip() or PS5_IP
    pin = input("8-digit PIN from PS5 (Settings → System → Remote Play → Link Device): ").strip()
    if not pin.isdigit() or len(pin) != 8:
        print("ERROR: PIN must be exactly 8 digits.")
        sys.exit(1)
    npsso = input("npsso token (for PSN auth): ").strip()

    print("\nGetting PSN access token…")
    try:
        access_token = _get_access_token(npsso)
        print(f"  OK (token length={len(access_token)})")
    except Exception as e:
        print(f"  FAILED: {e}")
        access_token = ""

    attempts = [
        ("9.21, no auth",      "9.21", {}),
        ("9.21, Bearer",       "9.21", {"Authorization": f"Bearer {access_token}"}),
        ("9.21, RP-Auth",      "9.21", {"RP-Auth": access_token}),
        ("9.0,  Bearer",       "9.0",  {"Authorization": f"Bearer {access_token}"}),
        ("10.0, Bearer",       "10.0", {"Authorization": f"Bearer {access_token}"}),
        ("8.0,  Bearer",       "8.0",  {"Authorization": f"Bearer {access_token}"}),
    ]

    for label, version, extras in attempts:
        resp = _try(host, pin, version, extras)
        first_line = resp.split(b"\r\n")[0].decode(errors="replace") if resp else "(no response)"
        reason = ""
        for line in resp.decode(errors="replace").splitlines():
            if "Reason" in line or "regist" in line.lower() or "key" in line.lower():
                reason = line.strip()
        print(f"  [{label}]: {first_line}  {reason}")
        if b"200" in resp[:20]:
            print("\n[+] SUCCESS! Full response:")
            print(resp.decode(errors="replace"))
            break


if __name__ == "__main__":
    main()
