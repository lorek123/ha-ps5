"""Capture a DDP user-credential from the PlayStation app on your phone.

How it works
------------
This script masquerades as a PS4 in standby on your local network.
When the PlayStation app (or PS4 Second Screen app) on your phone scans
for consoles, it will find this "PS4", then send a WAKEUP packet that
contains your user-credential. We capture and print it.

Steps
-----
1. Run this script on the same machine as your future HA instance:

       uv run python get_credential.py

2. On your phone, open the **PlayStation app** (or PS4 Second Screen app).
3. Go to: Connect to Console → PS4 (select PS4, not PS5 — uses same protocol).
4. The app will find "psn-ddp-pairing" on the network and attempt to wake it.
5. The credential will be printed here. Copy and save it.

Notes
-----
- The credential is a 64-character hex string tied to your PSN account.
- It works for both PS4 and PS5 DDP WAKEUP.
- You only need to do this once; store it in your HA config.
- Port 9302 must be free (stop HA temporarily if it's running the ps4 integration).
"""

from __future__ import annotations

import socket
import sys

DDP_PORT = 9302
DDP_VERSION = "00030010"
DEVICE_NAME = "psn-ddp-pairing"
HOST_ID = "AA11BB22CC33"


def _standby_response() -> bytes:
    fields = {
        "host-id": HOST_ID,
        "host-type": "PS4",
        "host-name": DEVICE_NAME,
        "host-request-port": "997",
        "device-discovery-protocol-version": DDP_VERSION,
    }
    lines = ["HTTP/1.1 620 Server Standby"]
    for k, v in fields.items():
        lines.append(f"{k}:{v}")
    lines.append("")
    return "\n".join(lines).encode()


def _parse_type(data: bytes) -> str | None:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if "SRCH" in text:
        return "search"
    if "WAKEUP" in text:
        return "wakeup"
    return None


def _extract_credential(data: bytes) -> str | None:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    for line in text.splitlines():
        if line.startswith("user-credential:"):
            return line.split(":", 1)[1].strip()
    return None


def main(timeout: int = 120) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(timeout)

    try:
        sock.bind(("0.0.0.0", DDP_PORT))
    except OSError as e:
        print(f"ERROR: Could not bind to port {DDP_PORT}: {e}")
        print("Make sure nothing else is using port 9302 (stop HA ps4 integration if running).")
        sys.exit(1)

    print(f"Listening on UDP port {DDP_PORT} as '{DEVICE_NAME}' (fake PS4 in standby).")
    print("Open the PlayStation app on your phone → Connect to Console → PS4")
    print(f"Waiting up to {timeout} seconds…\n")

    try:
        while True:
            try:
                data, addr = sock.recvfrom(1024)
            except TimeoutError:
                print("Timed out. No credential received.")
                sys.exit(1)

            pkt_type = _parse_type(data)

            if pkt_type == "search":
                print(f"  SRCH received from {addr[0]} — responding with standby status")
                sock.sendto(_standby_response(), addr)

            elif pkt_type == "wakeup":
                print(f"  WAKEUP received from {addr[0]}")
                cred = _extract_credential(data)
                if cred:
                    print(f"\n✓ Credential captured:\n\n  {cred}\n")
                    print("Save this in your HA config or psn-ddp wakeup calls.")
                    return
                else:
                    print("  WAKEUP received but no user-credential field found.")

    except KeyboardInterrupt:
        print("\nAborted.")
    finally:
        sock.close()


if __name__ == "__main__":
    main()
