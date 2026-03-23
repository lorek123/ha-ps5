"""Live test script for psn-ddp.

Usage:
    uv run python test_live.py                    # discover all consoles
    uv run python test_live.py 192.168.1.50       # poll a specific IP
    uv run python test_live.py 192.168.1.50 wake  # wake from rest mode (needs credential)
"""

from __future__ import annotations

import asyncio
import sys

from psn_ddp import DDPStatus, async_discover, async_get_status, async_wakeup


def _fmt(status: DDPStatus) -> str:
    state = "ON" if status.on else ("STANDBY" if status.standby else "OFF/no response")
    lines = [
        f"  host       : {status.host}",
        f"  state      : {state}",
        f"  type       : {status.host_type or '?'}",
        f"  name       : {status.host_name or '?'}",
        f"  host-id    : {status.host_id or '?'}",
    ]
    if status.title_id:
        lines.append(f"  playing    : {status.title_name} ({status.title_id})")
    if status.system_version:
        lines.append(f"  fw version : {status.system_version}")
    return "\n".join(lines)


async def main() -> None:
    args = sys.argv[1:]

    # --- discover ---
    if not args:
        print("Scanning LAN for PlayStation consoles (3 s)…")
        found = await async_discover()
        if not found:
            print("No consoles found. Make sure you're on the same network.")
            return
        for s in found:
            print(_fmt(s))
            print()
        return

    host = args[0]

    # --- wakeup ---
    if len(args) >= 2 and args[1] == "wake":
        credential = input(
            "Paste your 64-char DDP credential (from get_ddp_credential.py):\n> "
        ).strip()
        print(f"Sending WAKEUP to {host}…")
        await async_wakeup(host, credential)
        print("Sent. Polling every 5 s for up to 30 s…")
        for _ in range(6):
            await asyncio.sleep(5)
            status = await async_get_status(host)
            state = "ON" if status.on else ("STANDBY" if status.standby else "unavailable")
            print(f"  → {state}")
            if status.on:
                break

    # --- status poll ---
    print(f"Polling {host}…")
    status = await async_get_status(host)
    if not status.available:
        print(f"No response from {host}. Console may be fully powered off or unreachable.")
    else:
        print(_fmt(status))


asyncio.run(main())
