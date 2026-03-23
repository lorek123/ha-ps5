"""Tests for the async public API (async_get_status, async_discover, async_wakeup)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from psn_ddp import async_discover, async_get_status, async_wakeup
from psn_ddp.const import FIELD_HOST_NAME, FIELD_HOST_TYPE, STATUS_OK, STATUS_STANDBY
from psn_ddp.protocol import _DDPProtocol


def _make_response_bytes(status_code: int, fields: dict[str, str] | None = None) -> bytes:
    status_text = "Ok" if status_code == STATUS_OK else "Server Standby"
    lines = [f"HTTP/1.1 {status_code} {status_text}"]
    if fields:
        for k, v in fields.items():
            lines.append(f"{k}:{v}")
    lines.append("")
    return "\n".join(lines).encode()


def _make_protocol_with_response(
    host: str, status_code: int, fields: dict[str, str] | None = None
) -> _DDPProtocol:
    """Build a _DDPProtocol instance pre-populated with a fake response."""
    protocol = _DDPProtocol()
    data = _make_response_bytes(
        status_code, fields or {FIELD_HOST_TYPE: "PS5", FIELD_HOST_NAME: "Test PS5"}
    )
    protocol.datagram_received(data, (host, 9302))
    return protocol


def _mock_create_protocol(protocol: _DDPProtocol):
    """Return a patcher that injects *protocol* as the result of _create_protocol."""
    transport = MagicMock()
    transport.close = MagicMock()

    async def _fake_create(*args, **kwargs):
        return transport, protocol

    return patch("psn_ddp._create_protocol", side_effect=_fake_create)


# ---------------------------------------------------------------------------
# async_get_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_status_returns_on_when_console_responds():
    host = "192.168.1.50"
    protocol = _make_protocol_with_response(
        host,
        STATUS_OK,
        {
            FIELD_HOST_TYPE: "PS5",
            FIELD_HOST_NAME: "Living Room PS5",
        },
    )
    with _mock_create_protocol(protocol):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            status = await async_get_status(host)

    assert status.available is True
    assert status.on is True
    assert status.host == host
    assert status.host_type == "PS5"


@pytest.mark.asyncio
async def test_get_status_returns_unavailable_when_no_response():
    host = "192.168.1.99"
    protocol = _DDPProtocol()  # no responses injected
    with _mock_create_protocol(protocol):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            status = await async_get_status(host)

    assert status.available is False
    assert status.host == host


@pytest.mark.asyncio
async def test_get_status_standby():
    host = "192.168.1.51"
    protocol = _make_protocol_with_response(host, STATUS_STANDBY)
    with _mock_create_protocol(protocol):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            status = await async_get_status(host)

    assert status.standby is True
    assert status.on is False


# ---------------------------------------------------------------------------
# async_discover
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_discover_returns_all_responding_consoles():
    protocol = _DDPProtocol()
    # Simulate two consoles responding
    for host, host_type in [("192.168.1.50", "PS5"), ("192.168.1.51", "PS4")]:
        data = _make_response_bytes(STATUS_OK, {FIELD_HOST_TYPE: host_type})
        protocol.datagram_received(data, (host, 9302))

    with _mock_create_protocol(protocol):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            results = await async_discover()

    assert len(results) == 2
    hosts = {s.host for s in results}
    assert "192.168.1.50" in hosts
    assert "192.168.1.51" in hosts


@pytest.mark.asyncio
async def test_discover_returns_empty_list_when_no_consoles():
    protocol = _DDPProtocol()
    with _mock_create_protocol(protocol):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            results = await async_discover()

    assert results == []


# ---------------------------------------------------------------------------
# async_wakeup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wakeup_sends_packet():
    host = "192.168.1.50"
    credential = "x" * 64
    transport = MagicMock()
    protocol = _DDPProtocol()
    protocol._transport = transport

    async def _fake_create(*args, **kwargs):
        return transport, protocol

    with patch("psn_ddp._create_protocol", side_effect=_fake_create):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await async_wakeup(host, credential)

    # Verify sendto was called with the wakeup packet destined for the host
    assert transport.sendto.called
    call_args = transport.sendto.call_args
    packet: bytes = call_args[0][0]
    dest: tuple = call_args[0][1]

    assert dest[0] == host
    assert b"WAKEUP" in packet
    assert credential.encode() in packet
