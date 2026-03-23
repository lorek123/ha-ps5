"""psn-ddp — async PlayStation Device Discovery Protocol (DDP) library.

Supports PS4 and PS5 (identical DDP protocol on both).

Public API::

    from psn_ddp import async_get_status, async_discover, async_wakeup, DDPStatus

    # Poll a single console
    status = await async_get_status("192.168.1.50")
    print(status.on, status.title_id)

    # Discover all consoles on the LAN
    consoles = await async_discover()
    for s in consoles:
        print(s.host, s.host_type, s.host_name)

    # Wake a console from rest mode
    await async_wakeup("192.168.1.50", credential="<64-char credential>")

"""

from __future__ import annotations

import asyncio
import socket

from psn_ddp.const import DDP_SRCH_PORT
from psn_ddp.protocol import (
    DDPStatus,
    _create_protocol,
    build_srch_packet,
    build_wakeup_packet,
)

__all__ = [
    "DDPStatus",
    "async_discover",
    "async_get_status",
    "async_wakeup",
]

_BROADCAST = "255.255.255.255"
_DEFAULT_TIMEOUT = 3.0


def _local_broadcast() -> str:
    """Return the directed /24 subnet broadcast for the default outbound interface.

    Many PS5 firmwares ignore the limited broadcast (255.255.255.255) but respond
    to the directed broadcast (e.g. 192.168.1.255). We derive this by connecting a
    throwaway UDP socket (no packets sent) and reading the local IP, then replacing
    the last octet with 255.
    Falls back to ``"255.255.255.255"`` if the local IP cannot be determined.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))  # no packets sent; just picks the route
            local_ip: str = s.getsockname()[0]
        parts = local_ip.split(".")
        parts[-1] = "255"
        return ".".join(parts)
    except Exception:
        return _BROADCAST


async def async_get_status(
    host: str, timeout: float = _DEFAULT_TIMEOUT, src_port: int = DDP_SRCH_PORT
) -> DDPStatus:
    """Poll a single console's DDP status.

    Sends a SRCH packet directly to *host* and waits up to *timeout* seconds
    for a response.

    :param host: IP address of the console.
    :param timeout: Seconds to wait for a response. Defaults to 3.

    :returns: A :class:`~psn_ddp.protocol.DDPStatus`.  If the console does not
        respond within *timeout*, returns an unavailable status (``available=False``).

    .. code-block:: python

        status = await async_get_status("192.168.1.50")
        if status.on:
            print("Playing:", status.title_id)

    """
    transport, protocol = await _create_protocol(src_port)
    try:
        protocol.send(build_srch_packet(), host)
        try:
            await asyncio.wait_for(protocol.received.wait(), timeout=timeout)
        except TimeoutError:
            pass
    finally:
        transport.close()

    return protocol.responses.get(host, DDPStatus.unavailable(host))


async def async_discover(
    broadcast: str | None = None,
    timeout: float = _DEFAULT_TIMEOUT,
    src_port: int = DDP_SRCH_PORT,
) -> list[DDPStatus]:
    """Discover all PlayStation consoles on the local network.

    Broadcasts a SRCH packet and collects responses for *timeout* seconds.

    :param broadcast: Broadcast address. Defaults to the directed subnet broadcast
        derived from the machine's default outbound interface (e.g. ``"192.168.1.255"``).
        Pass ``"255.255.255.255"`` to use the limited broadcast explicitly.
    :param timeout: Seconds to collect responses. Defaults to 3.

    :returns: List of :class:`~psn_ddp.protocol.DDPStatus` objects, one per
        responding console.

    .. code-block:: python

        for console in await async_discover():
            print(console.host, console.host_type, console.host_name)

    """
    target = broadcast if broadcast is not None else _local_broadcast()
    transport, protocol = await _create_protocol(src_port)
    try:
        protocol.send(build_srch_packet(), target)
        await asyncio.sleep(timeout)
    finally:
        transport.close()

    return list(protocol.responses.values())


async def async_wakeup(host: str, credential: str) -> None:
    """Send a DDP WAKEUP packet to wake a console from rest mode.

    .. note::

        This wakes a console that is in **rest/standby mode** (status 620).
        A console that is fully powered off cannot be woken via DDP alone —
        it requires Wake-on-LAN (magic packet) or physical interaction.

    :param host: IP address of the console.
    :param credential: The 64-character user credential string associated with
        the console (obtained during the PSN pairing/registration flow).

    .. code-block:: python

        await async_wakeup("192.168.1.50", credential="abc123...")

    """
    transport, protocol = await _create_protocol()
    try:
        protocol.send(build_wakeup_packet(credential), host)
        # No response expected for WAKEUP — give the packet time to send
        await asyncio.sleep(0.1)
    finally:
        transport.close()
