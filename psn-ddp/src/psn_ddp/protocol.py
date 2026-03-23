"""DDP packet building and parsing, and the asyncio UDP protocol implementation."""

from __future__ import annotations

import asyncio
import logging
import socket
from dataclasses import dataclass, field
from typing import Any

from psn_ddp.const import (
    DDP_PORT,
    DDP_VERSION,
    FIELD_HOST_ID,
    FIELD_HOST_NAME,
    FIELD_HOST_TYPE,
    FIELD_SYSTEM_VERSION,
    FIELD_TITLE_ID,
    FIELD_TITLE_NAME,
    STATUS_OK,
    STATUS_STANDBY,
)

_LOGGER = logging.getLogger(__name__)

_STATUS_CODE_FIELD = "status-code"


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class DDPStatus:
    """Parsed status from a DDP response packet.

    :param host: IP address of the responding console.
    :param available: True if the console responded at all.
    :param on: True if the console is fully powered on (status 200 / "Ok").
    :param standby: True if the console is in rest mode (status 620).
    :param host_type: ``"PS4"`` or ``"PS5"``.
    :param host_name: User-assigned console name.
    :param host_id: Unique console identifier.
    :param title_id: NP title ID of the currently running app, or ``None``.
    :param title_name: Display name of the running app, or ``None``.
    :param system_version: Firmware version string, or ``None``.
    :param raw: The full parsed field dict from the DDP response.
    """

    host: str
    available: bool = False
    on: bool = False
    standby: bool = False
    host_type: str = ""
    host_name: str = ""
    host_id: str = ""
    title_id: str | None = None
    title_name: str | None = None
    system_version: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def unavailable(cls, host: str) -> "DDPStatus":
        """Return a status object representing a console that did not respond."""
        return cls(host=host, available=False)


# ---------------------------------------------------------------------------
# Packet builders
# ---------------------------------------------------------------------------


def _build_packet(msg_type: str, fields: dict[str, str] | None = None) -> bytes:
    """Serialise a DDP request packet.

    DDP uses an HTTP/1.1-inspired text format::

        SRCH * HTTP/1.1\\n
        device-discovery-protocol-version:00030010\\n
        \\n

    """
    lines = [f"{msg_type} * HTTP/1.1"]
    lines.append(f"device-discovery-protocol-version:{DDP_VERSION}")
    if fields:
        for key, value in fields.items():
            lines.append(f"{key}:{value}")
    lines.append("")
    lines.append("")
    return "\n".join(lines).encode()


def build_srch_packet() -> bytes:
    """Build a DDP SRCH (search/status poll) packet."""
    return _build_packet("SRCH")


def build_wakeup_packet(credential: str) -> bytes:
    """Build a DDP WAKEUP packet.

    :param credential: The user credential string obtained during console registration.
    """
    return _build_packet("WAKEUP", {
        "client-type": "a",
        "auth-type": "C",
        "user-credential": credential,
    })


# ---------------------------------------------------------------------------
# Packet parser
# ---------------------------------------------------------------------------


def parse_response(data: bytes, host: str) -> DDPStatus:
    """Parse a raw DDP UDP response into a :class:`DDPStatus`.

    :param data: Raw bytes received from the console.
    :param host: IP address of the sender.
    :returns: Populated :class:`DDPStatus`.
    """
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        _LOGGER.debug("DDP response from %s could not be decoded", host)
        return DDPStatus.unavailable(host)

    lines = text.splitlines()
    if not lines:
        return DDPStatus.unavailable(host)

    # First line: "HTTP/1.1 200 Ok" or "HTTP/1.1 620 Server Standby"
    parts = lines[0].split(" ", 2)
    if len(parts) < 3:
        return DDPStatus.unavailable(host)

    try:
        status_code = int(parts[1])
    except ValueError:
        return DDPStatus.unavailable(host)

    raw: dict[str, Any] = {_STATUS_CODE_FIELD: status_code}
    for line in lines[1:]:
        if ":" in line:
            key, _, value = line.partition(":")
            raw[key.strip()] = value.strip()

    return DDPStatus(
        host=host,
        available=True,
        on=status_code == STATUS_OK,
        standby=status_code == STATUS_STANDBY,
        host_type=raw.get(FIELD_HOST_TYPE, ""),
        host_name=raw.get(FIELD_HOST_NAME, ""),
        host_id=raw.get(FIELD_HOST_ID, ""),
        title_id=raw.get(FIELD_TITLE_ID) or None,
        title_name=raw.get(FIELD_TITLE_NAME) or None,
        system_version=raw.get(FIELD_SYSTEM_VERSION),
        raw=raw,
    )


# ---------------------------------------------------------------------------
# asyncio UDP protocol
# ---------------------------------------------------------------------------


class _DDPProtocol(asyncio.DatagramProtocol):
    """Internal asyncio UDP protocol that collects DDP responses."""

    def __init__(self) -> None:
        self.responses: dict[str, DDPStatus] = {}
        self._transport: asyncio.DatagramTransport | None = None
        self.received = asyncio.Event()

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:  # type: ignore[override]
        self._transport = transport
        sock: socket.socket = transport.get_extra_info("socket")
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        host = addr[0]
        status = parse_response(data, host)
        if status.available:
            self.responses[host] = status
            self.received.set()
            _LOGGER.debug(
                "DDP response from %s: on=%s standby=%s title_id=%s",
                host, status.on, status.standby, status.title_id,
            )

    def error_received(self, exc: Exception) -> None:
        _LOGGER.debug("DDP socket error: %s", exc)

    def connection_lost(self, exc: Exception | None) -> None:
        pass

    def send(self, data: bytes, host: str, port: int = DDP_PORT) -> None:
        if self._transport:
            self._transport.sendto(data, (host, port))


async def _create_protocol(src_port: int = 0) -> tuple[asyncio.DatagramTransport, _DDPProtocol]:
    """Create a UDP transport/protocol pair with broadcast enabled.

    :param src_port: Source port to bind to. PS4/PS5 only responds to SRCH from
        port 987. Binding to 987 requires CAP_NET_BIND_SERVICE or root on Linux.
        Pass 0 to let the OS pick a random port (PS4/PS5 will not respond).
    """
    # Pre-create socket with SO_REUSEADDR so port 987 can be reused immediately
    # after a previous transport.close() without hitting EADDRINUSE.
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    sock.bind(("0.0.0.0", src_port))

    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        _DDPProtocol,
        sock=sock,
    )
    return transport, protocol  # type: ignore[return-value]
