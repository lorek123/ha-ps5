"""Tests for PS5 registration helpers (pure functions — no network needed)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ps5.regist import (
    RegistrationError,
    _aeropause,
    _aes_cfb128,
    _build_payload,
    _derive_bright,
    _generate_iv,
    _parse_response,
    _udp_search,
    async_register,
)

# ── pure crypto helpers ──────────────────────────────────────────────────────


def test_derive_bright_returns_16_bytes() -> None:
    result = _derive_bright(b"\x00" * 16, key_0_off=0, pin=12345678)
    assert len(result) == 16


def test_derive_bright_xors_pin() -> None:
    r1 = _derive_bright(b"\x00" * 16, key_0_off=0, pin=0)
    r2 = _derive_bright(b"\x00" * 16, key_0_off=0, pin=0x01020304)
    # bytes 0xC..0xF differ
    assert r1[:12] == r2[:12]
    assert r1[12:] != r2[12:]


def test_aeropause_returns_16_bytes() -> None:
    result = _aeropause(b"\xab" * 16, key_1_off=0)
    assert len(result) == 16


def test_generate_iv_returns_16_bytes() -> None:
    iv = _generate_iv(b"\x00" * 16, counter=0)
    assert len(iv) == 16


def test_generate_iv_changes_with_counter() -> None:
    iv0 = _generate_iv(b"\x00" * 16, counter=0)
    iv1 = _generate_iv(b"\x00" * 16, counter=1)
    assert iv0 != iv1


def test_aes_cfb128_roundtrip() -> None:
    key = b"\x00" * 16
    iv = b"\x01" * 16
    plaintext = b"hello world!!!!!"  # 16 bytes
    ciphertext = _aes_cfb128(key, iv, plaintext, encrypt=True)
    recovered = _aes_cfb128(key, iv, ciphertext, encrypt=False)
    assert recovered == plaintext


def test_aes_cfb128_produces_different_output() -> None:
    key = b"\x00" * 16
    iv = b"\x00" * 16
    data = b"\xff" * 16
    assert _aes_cfb128(key, iv, data, encrypt=True) != data


def test_build_payload_returns_three_bytes_objects() -> None:
    payload, bright, ambassador = _build_payload("123456789", pin=12345678)
    assert isinstance(payload, bytes)
    assert isinstance(bright, bytes)
    assert isinstance(ambassador, bytes)
    assert len(bright) == 16
    assert len(ambassador) == 16


def test_build_payload_length() -> None:
    payload, _, _ = _build_payload("123456789", pin=12345678)
    # prefix is 0x1E0 bytes + encrypted inner
    assert len(payload) > 0x1E0


def test_udp_search_no_response() -> None:
    """_udp_search gracefully handles recv timeout."""
    mock_sock = MagicMock()
    mock_sock.recv.side_effect = OSError("timed out")
    with patch("custom_components.ps5.regist.socket.socket", return_value=mock_sock):
        _udp_search("192.168.1.100")  # should not raise
    mock_sock.close.assert_called_once()


def test_udp_search_with_response() -> None:
    """_udp_search handles a response without raising."""
    mock_sock = MagicMock()
    mock_sock.recv.return_value = b"response"
    with patch("custom_components.ps5.regist.socket.socket", return_value=mock_sock):
        _udp_search("192.168.1.100")
    mock_sock.send.assert_called_once()
    mock_sock.close.assert_called_once()


# ── _parse_response ──────────────────────────────────────────────────────────


def test_parse_response_no_header_raises() -> None:
    with pytest.raises(RegistrationError, match="No HTTP header"):
        _parse_response(b"garbage data without double crlf")


def test_parse_response_ok() -> None:
    raw = b"HTTP/1.1 200 OK\r\nRP-Nonce: AAAA\r\n\r\n" + b"\x00" * 32
    status, headers, body = _parse_response(raw)
    assert status == 200
    assert headers["RP-Nonce"] == "AAAA"
    assert len(body) == 32


def test_parse_response_non_200_status() -> None:
    raw = b"HTTP/1.1 500 Error\r\n\r\n"
    status, _headers, _body = _parse_response(raw)
    assert status == 500


def test_parse_response_malformed_status_line() -> None:
    """HTTP/ line that doesn't match the status regex → status stays 0."""
    raw = b"HTTP/bad\r\nRP-Nonce: X\r\n\r\n"
    status, headers, _body = _parse_response(raw)
    assert status == 0
    assert headers["RP-Nonce"] == "X"


def test_parse_response_header_line_without_colon() -> None:
    """A header line with no ': ' and not starting HTTP/ is silently skipped."""
    raw = b"HTTP/1.1 200 OK\r\nX-Junk-No-Colon\r\nRP-Nonce: Y\r\n\r\n"
    status, headers, _body = _parse_response(raw)
    assert status == 200
    assert "X-Junk-No-Colon" not in headers
    assert headers["RP-Nonce"] == "Y"


# ── async_register (mocked TCP) ──────────────────────────────────────────────


async def test_async_register_success() -> None:
    """Test happy path by mocking both network and AES decryption."""
    # The regist key is a hex-encoded ASCII hex value; _regist_key_to_credential decodes it.
    # hex("deadbeef") -> "6465616462656566" -> int(0xdeadbeef) -> credential
    regist_key_hex = bytes("deadbeef", "ascii").hex()  # "6465616462656566"
    expected_credential = str(int("deadbeef", 16))  # "3735928559"

    # Mock response: 200 OK with any body (crypto is mocked away)
    response = b"HTTP/1.1 200 OK\r\nContent-Length: 32\r\n\r\n" + b"\xab" * 32

    mock_reader = AsyncMock()
    mock_writer = MagicMock()
    mock_writer.drain = AsyncMock()
    mock_writer.close = MagicMock()
    mock_writer.wait_closed = AsyncMock()
    mock_reader.read = AsyncMock(return_value=response)

    # Patch the AES decryption to return plaintext containing PS5-RegistKey
    # Include a blank line to cover the `if ": " in line` False branch
    decrypted = f"PS5-RegistKey: {regist_key_hex}\r\nno-colon-here\r\n".encode()

    with (
        patch(
            "custom_components.ps5.regist.asyncio.open_connection",
            return_value=(mock_reader, mock_writer),
        ),
        patch("custom_components.ps5.regist._aes_cfb128", return_value=decrypted),
    ):
        result = await async_register("192.168.1.100", pin=12345678, account_id_str="123456789")

    assert result == expected_credential


async def test_async_register_connection_error() -> None:
    with patch(
        "custom_components.ps5.regist.asyncio.open_connection", side_effect=OSError("refused")
    ):
        with pytest.raises(RegistrationError):
            await async_register("192.168.1.100", pin=12345678, account_id_str="123456789")


async def test_async_register_timeout() -> None:
    """Reader times out → RegistrationError about no response."""
    mock_reader = AsyncMock()
    mock_writer = MagicMock()
    mock_writer.drain = AsyncMock()
    mock_writer.close = MagicMock()
    mock_writer.wait_closed = AsyncMock()
    mock_reader.read = AsyncMock(side_effect=TimeoutError())

    with patch(
        "custom_components.ps5.regist.asyncio.open_connection",
        return_value=(mock_reader, mock_writer),
    ):
        with pytest.raises(RegistrationError, match="No response"):
            await async_register("192.168.1.100", pin=12345678, account_id_str="123456789")


async def test_async_register_missing_regist_key() -> None:
    """Decrypted body has no PS5-RegistKey header → RegistrationError."""
    response = b"HTTP/1.1 200 OK\r\nContent-Length: 32\r\n\r\n" + b"\xab" * 32
    mock_reader = AsyncMock()
    mock_writer = MagicMock()
    mock_writer.drain = AsyncMock()
    mock_writer.close = MagicMock()
    mock_writer.wait_closed = AsyncMock()
    mock_reader.read = AsyncMock(return_value=response)

    with (
        patch(
            "custom_components.ps5.regist.asyncio.open_connection",
            return_value=(mock_reader, mock_writer),
        ),
        patch("custom_components.ps5.regist._aes_cfb128", return_value=b"SomeHeader: value\r\n"),
    ):
        with pytest.raises(RegistrationError, match="PS5-RegistKey missing"):
            await async_register("192.168.1.100", pin=12345678, account_id_str="123456789")


async def test_async_register_bad_challenge_response() -> None:
    mock_reader = AsyncMock()
    mock_writer = MagicMock()
    mock_writer.drain = AsyncMock()
    mock_writer.close = MagicMock()
    mock_writer.wait_closed = AsyncMock()
    # Return a non-200 response to the challenge
    mock_reader.read = AsyncMock(return_value=b"HTTP/1.1 401 Unauthorized\r\n\r\n")

    with patch(
        "custom_components.ps5.regist.asyncio.open_connection",
        return_value=(mock_reader, mock_writer),
    ):
        with pytest.raises(RegistrationError):
            await async_register("192.168.1.100", pin=12345678, account_id_str="123456789")
