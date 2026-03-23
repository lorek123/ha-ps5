"""Tests for DDP packet building and parsing."""

from __future__ import annotations

from psn_ddp.const import (
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
from psn_ddp.protocol import (
    DDPStatus,
    build_srch_packet,
    build_wakeup_packet,
    parse_response,
)

# ---------------------------------------------------------------------------
# Packet builders
# ---------------------------------------------------------------------------


def test_srch_packet_starts_with_srch():
    pkt = build_srch_packet().decode()
    assert pkt.startswith("SRCH * HTTP/1.1")


def test_srch_packet_contains_version():
    pkt = build_srch_packet().decode()
    assert DDP_VERSION in pkt


def test_wakeup_packet_contains_credential():
    cred = "a" * 64
    pkt = build_wakeup_packet(cred).decode()
    assert "WAKEUP * HTTP/1.1" in pkt
    assert f"user-credential:{cred}" in pkt
    assert "client-type:a" in pkt
    assert "auth-type:C" in pkt


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def _make_response(status_code: int, fields: dict[str, str] | None = None) -> bytes:
    status_text = "Ok" if status_code == STATUS_OK else "Server Standby"
    lines = [f"HTTP/1.1 {status_code} {status_text}"]
    if fields:
        for k, v in fields.items():
            lines.append(f"{k}:{v}")
    lines.append("")
    return "\n".join(lines).encode()


def test_parse_console_on():
    data = _make_response(
        STATUS_OK,
        {
            FIELD_HOST_TYPE: "PS5",
            FIELD_HOST_NAME: "Living Room PS5",
            FIELD_HOST_ID: "AABBCCDDEEFF",
            FIELD_TITLE_ID: "PPSA01284_00",
            FIELD_TITLE_NAME: "Marvel's Spider-Man 2",
            FIELD_SYSTEM_VERSION: "09000000",
        },
    )
    status = parse_response(data, "192.168.1.50")

    assert status.available is True
    assert status.on is True
    assert status.standby is False
    assert status.host == "192.168.1.50"
    assert status.host_type == "PS5"
    assert status.host_name == "Living Room PS5"
    assert status.host_id == "AABBCCDDEEFF"
    assert status.title_id == "PPSA01284_00"
    assert status.title_name == "Marvel's Spider-Man 2"
    assert status.system_version == "09000000"


def test_parse_console_standby():
    data = _make_response(
        STATUS_STANDBY,
        {
            FIELD_HOST_TYPE: "PS5",
            FIELD_HOST_NAME: "My PS5",
            FIELD_HOST_ID: "112233445566",
        },
    )
    status = parse_response(data, "192.168.1.51")

    assert status.available is True
    assert status.on is False
    assert status.standby is True
    assert status.title_id is None
    assert status.title_name is None


def test_parse_ps4_response():
    data = _make_response(
        STATUS_OK,
        {
            FIELD_HOST_TYPE: "PS4",
            FIELD_HOST_NAME: "My PS4",
            FIELD_HOST_ID: "DEADBEEF1234",
            FIELD_TITLE_ID: "CUSA07408_00",
            FIELD_TITLE_NAME: "God of War",
        },
    )
    status = parse_response(data, "192.168.1.52")

    assert status.host_type == "PS4"
    assert status.title_id == "CUSA07408_00"


def test_parse_empty_title_id_returns_none():
    data = _make_response(
        STATUS_OK,
        {
            FIELD_HOST_TYPE: "PS5",
            FIELD_TITLE_ID: "",
        },
    )
    status = parse_response(data, "192.168.1.50")
    assert status.title_id is None


def test_parse_invalid_data_returns_unavailable():
    status = parse_response(b"\xff\xfe garbage", "192.168.1.99")
    assert status.available is False
    assert status.on is False


def test_parse_malformed_status_line_returns_unavailable():
    status = parse_response(b"NOT HTTP AT ALL", "192.168.1.99")
    assert status.available is False


def test_parse_empty_bytes_returns_unavailable():
    status = parse_response(b"", "192.168.1.99")
    assert status.available is False


def test_unavailable_factory():
    status = DDPStatus.unavailable("10.0.0.1")
    assert status.host == "10.0.0.1"
    assert status.available is False
    assert status.on is False
    assert status.standby is False


# ---------------------------------------------------------------------------
# DDPStatus properties
# ---------------------------------------------------------------------------


def test_ddp_status_raw_contains_all_fields():
    data = _make_response(
        STATUS_OK,
        {
            FIELD_HOST_TYPE: "PS5",
            FIELD_HOST_NAME: "Test",
            FIELD_SYSTEM_VERSION: "09000000",
        },
    )
    status = parse_response(data, "1.2.3.4")
    assert status.raw[FIELD_HOST_TYPE] == "PS5"
    assert status.raw[FIELD_SYSTEM_VERSION] == "09000000"
