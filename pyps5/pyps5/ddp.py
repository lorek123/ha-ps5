"""Device Discovery Protocol (DDP) for PS4/PS5.

DDP runs over UDP port 9302 (console) / 987 (client send port).
Reverse engineered from ps4-waker and pyps4-2ndscreen.
"""

from __future__ import annotations

import asyncio
import logging
import socket
from typing import Any

_LOGGER = logging.getLogger(__name__)

DDP_PORT = 9302
DDP_VERSION = "00030010"
DDP_TYPE_SEARCH = "SRCH"
DDP_TYPE_WAKEUP = "WAKEUP"
DDP_TYPE_LAUNCH = "LAUNCH"

STATUS_ON = "Ok"
STATUS_STANDBY = "Standby"

BROADCAST_IP = "255.255.255.255"


def _make_ddp_message(msg_type: str, fields: dict[str, str] | None = None) -> bytes:
    """Build a DDP request packet."""
    lines = [f"{msg_type} * HTTP/1.1"]
    if fields:
        for key, value in fields.items():
            lines.append(f"{key}:{value}")
    lines.append("")
    lines.append("")
    return "\n".join(lines).encode()


def _parse_ddp_response(data: bytes) -> dict[str, Any]:
    """Parse a DDP response packet into a dict."""
    result: dict[str, Any] = {}
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return result
    lines = text.splitlines()
    if not lines:
        return result
    # First line: "HTTP/1.1 200 Ok" or "HTTP/1.1 620 Server Standby"
    first = lines[0].split(" ", 2)
    if len(first) >= 3:
        result["status"] = first[2]
    for line in lines[1:]:
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip()
    return result


class DDPProtocol(asyncio.DatagramProtocol):
    """Asyncio UDP protocol for DDP communication."""

    def __init__(self) -> None:
        self.responses: dict[str, dict[str, Any]] = {}
        self._transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:  # type: ignore[override]
        self._transport = transport
        sock = transport.get_extra_info("socket")
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        host = addr[0]
        parsed = _parse_ddp_response(data)
        if parsed:
            self.responses[host] = parsed

    def error_received(self, exc: Exception) -> None:
        _LOGGER.debug("DDP error: %s", exc)

    def connection_lost(self, exc: Exception | None) -> None:
        pass

    def send(self, data: bytes, addr: tuple[str, int]) -> None:
        if self._transport:
            self._transport.sendto(data, addr)


async def async_send_ddp_message(
    host: str,
    msg_type: str,
    fields: dict[str, str] | None = None,
    timeout: float = 3.0,
) -> dict[str, Any]:
    """Send a DDP message and return the response."""
    loop = asyncio.get_event_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        DDPProtocol,
        local_addr=("0.0.0.0", 0),  # noqa: S104
        family=socket.AF_INET,
    )
    try:
        data = _make_ddp_message(msg_type, fields)
        protocol.send(data, (host, DDP_PORT))
        await asyncio.sleep(timeout)
    finally:
        transport.close()
    return protocol.responses.get(host, {})


async def async_get_status(host: str, timeout: float = 3.0) -> dict[str, Any]:
    """Poll a console's status via DDP SRCH."""
    return await async_send_ddp_message(host, DDP_TYPE_SEARCH, timeout=timeout)


async def async_send_wakeup(host: str, credential: str) -> None:
    """Send DDP WAKEUP to power on a console."""
    fields = {
        "client-type": "a",
        "auth-type": "C",
        "user-credential": credential,
    }
    await async_send_ddp_message(host, DDP_TYPE_WAKEUP, fields, timeout=1.0)


async def async_discover(
    broadcast: str = BROADCAST_IP,
    timeout: float = 3.0,
) -> list[dict[str, Any]]:
    """Broadcast SRCH and collect all responding consoles."""
    loop = asyncio.get_event_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        DDPProtocol,
        local_addr=("0.0.0.0", 0),  # noqa: S104
        family=socket.AF_INET,
    )
    try:
        data = _make_ddp_message(DDP_TYPE_SEARCH)
        protocol.send(data, (broadcast, DDP_PORT))
        await asyncio.sleep(timeout)
    finally:
        transport.close()
    return [{"host": host, **info} for host, info in protocol.responses.items()]
