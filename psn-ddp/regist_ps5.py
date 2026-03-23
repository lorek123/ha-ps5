"""PS5 Remote Play local PIN registration.

Implements the Chiaki-ng protocol for PS5 firmware 10+ local registration
(Settings → System → Remote Play → Link Device → 8-digit PIN).

Returns the ``PS5-RegistKey`` which is the DDP user-credential needed for
``WAKEUP`` packets on the local network.

Protocol (reversed from chiaki-ng lib/src/regist.c + lib/src/rpcrypt.c):
1. UDP "search": send ``SRC3\\x00`` to PS5:9295, wait for ``RES3\\x00``
2. TCP connect to PS5:9295
3. POST /sie/ps5/rp/sess/rgst  with encrypted binary payload
4. Decrypt response body, parse HTTP-like headers → PS5-RegistKey
"""

from __future__ import annotations

import base64
import hashlib
import hmac as _hmac
import os
import re
import socket
import struct
import sys

from Cryptodome.Cipher import AES as _AES

# ── constants extracted from chiaki-ng lib/src/rpcrypt.c ─────────────────────

# HMAC-SHA256 key used to generate the AES-CFB IV (PS5 variant)
_HMAC_KEY = bytes(
    [
        0x46,
        0x46,
        0x87,
        0xB3,
        0x49,
        0xCA,
        0x8C,
        0xE8,
        0x59,
        0xC5,
        0x27,
        0x0F,
        0x5D,
        0x7A,
        0x69,
        0xD6,
    ]
)

# 512-byte key table for AES key (bright) derivation – chiaki_rpcrypt_init_regist, PS5
_KEYS_0 = bytes(
    [
        0x24,
        0xD8,
        0xC2,
        0x69,
        0x4C,
        0x67,
        0x78,
        0x71,
        0xEE,
        0x31,
        0xBD,
        0x2B,
        0x83,
        0xB2,
        0x1D,
        0x61,
        0xC9,
        0xA7,
        0x8E,
        0xED,
        0x9A,
        0xD3,
        0x6A,
        0x6B,
        0x5C,
        0xC8,
        0x35,
        0x79,
        0xA7,
        0x24,
        0xE2,
        0x17,
        0x06,
        0x60,
        0x2E,
        0xDF,
        0xF4,
        0xDB,
        0x27,
        0x10,
        0x55,
        0xD9,
        0xEA,
        0x16,
        0x4E,
        0x90,
        0x0C,
        0xBF,
        0x40,
        0x6F,
        0x54,
        0xA5,
        0x31,
        0x70,
        0x2D,
        0x5D,
        0x1E,
        0x27,
        0xDF,
        0x37,
        0x40,
        0xBA,
        0x9D,
        0x5D,
        0xFF,
        0xE1,
        0x05,
        0x70,
        0x80,
        0xD4,
        0xB7,
        0xC2,
        0x96,
        0x7F,
        0x2F,
        0x42,
        0xEB,
        0x5A,
        0x08,
        0xDE,
        0xC1,
        0xB5,
        0x52,
        0x15,
        0xF6,
        0xB5,
        0xF2,
        0xD9,
        0x69,
        0xA5,
        0xC7,
        0xC4,
        0x7F,
        0x46,
        0x64,
        0xA4,
        0xFD,
        0x46,
        0x98,
        0xA7,
        0xE1,
        0x2A,
        0x8E,
        0x6F,
        0xAF,
        0x65,
        0x42,
        0x28,
        0xB9,
        0xC2,
        0x6F,
        0x3E,
        0xE3,
        0xE4,
        0x4E,
        0xE4,
        0x5B,
        0x9D,
        0x60,
        0x10,
        0xB8,
        0x5A,
        0xB0,
        0x7D,
        0x04,
        0x0C,
        0x4C,
        0x24,
        0x78,
        0xBD,
        0xB8,
        0xBA,
        0xDB,
        0x8F,
        0xE3,
        0xA0,
        0x75,
        0x6D,
        0x28,
        0xC2,
        0x33,
        0x5B,
        0x32,
        0x83,
        0xDD,
        0x51,
        0xB0,
        0xA5,
        0x8D,
        0x09,
        0x66,
        0xE4,
        0x5C,
        0xB8,
        0x70,
        0x0B,
        0xE6,
        0x82,
        0x14,
        0xB6,
        0xD2,
        0xB0,
        0xC2,
        0xE0,
        0x55,
        0xF3,
        0x84,
        0xAD,
        0x9D,
        0x3A,
        0xF8,
        0x77,
        0xF5,
        0x9D,
        0x9A,
        0xA9,
        0x7D,
        0xF1,
        0x45,
        0x1B,
        0x9B,
        0x55,
        0x25,
        0xD8,
        0xC1,
        0xFF,
        0x03,
        0xA5,
        0x48,
        0x0B,
        0x1B,
        0x19,
        0x0C,
        0xBD,
        0xE0,
        0xCD,
        0x48,
        0xF3,
        0x2C,
        0x99,
        0x19,
        0xD6,
        0xB8,
        0xBB,
        0xD6,
        0x35,
        0x43,
        0x6F,
        0x71,
        0xE3,
        0xEF,
        0x3E,
        0x97,
        0xB8,
        0xE9,
        0x40,
        0xA8,
        0x47,
        0xE0,
        0xE0,
        0x01,
        0x16,
        0x9D,
        0xA7,
        0xE5,
        0x94,
        0x4B,
        0x1D,
        0xD2,
        0x80,
        0xA2,
        0x7F,
        0xF2,
        0x98,
        0x10,
        0x38,
        0x0D,
        0xB8,
        0x56,
        0xC3,
        0x7A,
        0x4B,
        0x4C,
        0x85,
        0xEC,
        0x2F,
        0x23,
        0x89,
        0xAF,
        0xD5,
        0xBA,
        0x9A,
        0xAD,
        0xB0,
        0x61,
        0x9C,
        0x51,
        0xB4,
        0x6D,
        0x02,
        0x49,
        0x26,
        0xA4,
        0x34,
        0x84,
        0x20,
        0x35,
        0x30,
        0x23,
        0x0A,
        0x47,
        0x14,
        0x32,
        0x1A,
        0x96,
        0x0E,
        0xE8,
        0x0F,
        0x96,
        0x96,
        0xD4,
        0xBA,
        0x68,
        0x3A,
        0x67,
        0x15,
        0x74,
        0xE0,
        0xD6,
        0x60,
        0x4C,
        0x68,
        0x50,
        0x73,
        0x14,
        0x2F,
        0x11,
        0x59,
        0xAC,
        0xC8,
        0x32,
        0xD1,
        0xDB,
        0x4C,
        0x8A,
        0x94,
        0x75,
        0x33,
        0x61,
        0xD1,
        0xD4,
        0xFD,
        0xAA,
        0x6A,
        0x61,
        0x68,
        0xD8,
        0xAE,
        0x31,
        0x4F,
        0xB8,
        0x07,
        0x7B,
        0x27,
        0x0F,
        0xF9,
        0x0B,
        0xB0,
        0xC2,
        0x64,
        0xB3,
        0x72,
        0xEA,
        0x8B,
        0x87,
        0x40,
        0x09,
        0xB4,
        0x82,
        0xB4,
        0xAD,
        0x76,
        0xF9,
        0x36,
        0x05,
        0x60,
        0x89,
        0xC8,
        0x20,
        0xEB,
        0xA5,
        0xF1,
        0x51,
        0x0B,
        0x27,
        0xA7,
        0xF0,
        0x76,
        0x84,
        0x96,
        0xEB,
        0xB1,
        0x2E,
        0xC2,
        0x85,
        0x28,
        0xBC,
        0x48,
        0x34,
        0xD4,
        0x01,
        0x8D,
        0x5B,
        0x25,
        0x54,
        0xE0,
        0xC4,
        0x4F,
        0xA0,
        0xFA,
        0x99,
        0x8D,
        0x6D,
        0x7A,
        0x64,
        0xB1,
        0xA9,
        0x5D,
        0xA4,
        0xF9,
        0xF5,
        0x22,
        0xEB,
        0x9A,
        0xF4,
        0xA8,
        0x7A,
        0x78,
        0x4B,
        0x7F,
        0xE2,
        0x8B,
        0x04,
        0x50,
        0x43,
        0x7D,
        0x26,
        0x2D,
        0x19,
        0x98,
        0x38,
        0x6A,
        0x4F,
        0x2D,
        0x30,
        0x15,
        0x2E,
        0x4F,
        0xCD,
        0xB9,
        0xCE,
        0x9E,
        0x8D,
        0x12,
        0xC9,
        0xFE,
        0x33,
        0x8B,
        0x84,
        0xCE,
        0x5B,
        0x40,
        0xE3,
        0x7F,
        0x72,
        0x6D,
        0x6C,
        0x8A,
        0x6A,
        0x9E,
        0x54,
        0xF1,
        0xE3,
        0x64,
        0x5D,
        0x6E,
        0x7F,
        0xAC,
        0x1A,
        0xE7,
        0xF7,
        0xFA,
        0x00,
        0x22,
        0xED,
        0x2B,
        0x23,
        0xFA,
        0x58,
        0xC5,
        0xEB,
        0x44,
        0x92,
        0x5D,
        0xCC,
        0xAA,
        0x82,
        0x9F,
        0x23,
        0xFB,
        0xA6,
        0xC9,
        0x65,
        0x2A,
        0xE0,
        0x79,
        0x12,
        0x65,
        0x2C,
        0x34,
        0xC5,
        0x23,
        0x16,
        0xC9,
        0xCC,
        0x05,
        0x30,
        0xF3,
        0x96,
        0x0B,
        0x90,
        0x67,
        0x1A,
        0xA7,
        0x69,
        0x4C,
        0x3E,
        0x43,
        0x24,
        0x9D,
        0x4E,
        0x68,
        0xBD,
        0x8B,
        0x75,
        0x6E,
        0x9D,
        0x07,
        0x6F,
        0x1A,
        0x6A,
        0xBA,
    ]
)

# 512-byte key table for aeropause – chiaki_rpcrypt_aeropause, PS5
_KEYS_1 = bytes(
    [
        0x79,
        0x4D,
        0x78,
        0x30,
        0xFE,
        0x10,
        0x52,
        0x4C,
        0xA8,
        0x90,
        0x5B,
        0x9A,
        0x7E,
        0x5F,
        0xD3,
        0xE1,
        0x13,
        0xE0,
        0xF1,
        0x0F,
        0xA3,
        0xE7,
        0xBB,
        0x45,
        0x7F,
        0xDC,
        0x8E,
        0xD5,
        0xF1,
        0x04,
        0x5C,
        0x78,
        0x51,
        0xEF,
        0xF8,
        0x65,
        0x59,
        0x03,
        0x39,
        0x84,
        0x37,
        0xAE,
        0x59,
        0xDF,
        0x23,
        0xB6,
        0x60,
        0x34,
        0xE6,
        0x4B,
        0xE2,
        0xF5,
        0x4C,
        0x13,
        0xC6,
        0xDA,
        0xF9,
        0xFD,
        0xB3,
        0x65,
        0x84,
        0xD6,
        0x45,
        0xEC,
        0x2C,
        0x00,
        0xF2,
        0xED,
        0xDC,
        0xCB,
        0x93,
        0x6E,
        0x61,
        0x46,
        0xE5,
        0xD6,
        0x01,
        0x94,
        0xEE,
        0x78,
        0x85,
        0x0E,
        0x68,
        0x5E,
        0xB5,
        0x5B,
        0xCD,
        0xD3,
        0x63,
        0x41,
        0xFC,
        0x81,
        0x43,
        0x1C,
        0x6F,
        0x7C,
        0xBA,
        0xE8,
        0xBD,
        0x86,
        0x31,
        0xD5,
        0x70,
        0x7F,
        0xB5,
        0x4A,
        0x90,
        0x3E,
        0x84,
        0xE1,
        0x71,
        0xE0,
        0x02,
        0x99,
        0xF4,
        0x71,
        0xE7,
        0x02,
        0xED,
        0x36,
        0xAF,
        0xDE,
        0x56,
        0xC2,
        0x90,
        0xE0,
        0xAE,
        0xC2,
        0xF9,
        0xAF,
        0x53,
        0xC6,
        0xD8,
        0x62,
        0x16,
        0x32,
        0x27,
        0xFB,
        0x6E,
        0x9B,
        0x48,
        0xC6,
        0xEA,
        0xFF,
        0x6F,
        0x78,
        0x02,
        0x22,
        0x98,
        0x2C,
        0x1F,
        0xBF,
        0xB0,
        0x8E,
        0xA9,
        0x39,
        0xBC,
        0xDF,
        0x17,
        0xDE,
        0xD7,
        0x0E,
        0xE1,
        0x7A,
        0x01,
        0x0E,
        0xC3,
        0x87,
        0xFC,
        0xAA,
        0xE4,
        0x6B,
        0x0F,
        0x5B,
        0x0A,
        0xF1,
        0x18,
        0x19,
        0x8A,
        0xE5,
        0x2C,
        0x36,
        0x9B,
        0x40,
        0x30,
        0x99,
        0x24,
        0x94,
        0x48,
        0xD7,
        0x47,
        0xB2,
        0xAF,
        0x6B,
        0x8C,
        0x40,
        0x9E,
        0x4D,
        0x6D,
        0x34,
        0x07,
        0xC1,
        0x26,
        0x2F,
        0xBB,
        0x14,
        0xF7,
        0xBC,
        0x36,
        0x52,
        0xBD,
        0x84,
        0xFE,
        0x4A,
        0x9A,
        0xF4,
        0x8A,
        0xDB,
        0x34,
        0x89,
        0xAA,
        0xF1,
        0x0D,
        0x94,
        0x0B,
        0x92,
        0xF4,
        0x1C,
        0xE4,
        0x6C,
        0x79,
        0x2D,
        0x6E,
        0xC0,
        0x19,
        0x0A,
        0xD5,
        0x55,
        0x94,
        0x14,
        0x05,
        0x13,
        0xC2,
        0x62,
        0x23,
        0xB3,
        0xD4,
        0x26,
        0xC4,
        0x44,
        0x56,
        0x7A,
        0xCD,
        0x1C,
        0xEA,
        0xD4,
        0x74,
        0xB9,
        0x36,
        0x40,
        0x9F,
        0x08,
        0xFB,
        0x49,
        0x62,
        0x05,
        0x92,
        0x98,
        0xAD,
        0x1D,
        0x9F,
        0x8A,
        0x76,
        0x8B,
        0xD4,
        0x0F,
        0x21,
        0x40,
        0x76,
        0xB6,
        0x16,
        0x91,
        0x45,
        0x93,
        0x66,
        0xCC,
        0x12,
        0xEA,
        0x4D,
        0xF4,
        0x09,
        0xE2,
        0xAC,
        0x33,
        0xD0,
        0x6F,
        0x43,
        0x51,
        0x07,
        0x3E,
        0xD7,
        0x95,
        0x2C,
        0x1E,
        0x1F,
        0x0C,
        0x24,
        0xB3,
        0x0E,
        0x3A,
        0xEF,
        0x95,
        0xF5,
        0xEB,
        0x77,
        0xDD,
        0x20,
        0xF2,
        0x35,
        0x98,
        0xF2,
        0xAE,
        0xA9,
        0x66,
        0xE6,
        0x13,
        0xEF,
        0x5D,
        0x3A,
        0x2D,
        0x66,
        0xED,
        0xE2,
        0x1E,
        0xE9,
        0x32,
        0x4A,
        0x40,
        0xBF,
        0x37,
        0xC6,
        0x70,
        0x29,
        0xD9,
        0x8C,
        0xA1,
        0x61,
        0x4A,
        0x29,
        0x3D,
        0xC7,
        0x55,
        0x9C,
        0x94,
        0x9E,
        0xC9,
        0x11,
        0x45,
        0x10,
        0x28,
        0xA7,
        0x27,
        0xD1,
        0xD3,
        0xD0,
        0x84,
        0x79,
        0xC7,
        0xA9,
        0xB0,
        0xF6,
        0xAF,
        0x45,
        0x8C,
        0x3C,
        0xD4,
        0xDF,
        0x3B,
        0xF7,
        0x0D,
        0xA2,
        0x4F,
        0x13,
        0x97,
        0x78,
        0x27,
        0xF0,
        0x48,
        0xC0,
        0xA5,
        0xAB,
        0x83,
        0x01,
        0x05,
        0xD0,
        0x12,
        0xD7,
        0x1E,
        0x12,
        0x3A,
        0x4E,
        0x98,
        0x77,
        0xAE,
        0xBA,
        0xB1,
        0x4E,
        0xB5,
        0x3B,
        0x59,
        0xCA,
        0x6D,
        0xA5,
        0x11,
        0x80,
        0x91,
        0x9C,
        0x07,
        0x69,
        0x59,
        0x5A,
        0x53,
        0x70,
        0x7C,
        0x95,
        0x97,
        0x11,
        0x6D,
        0x66,
        0x8D,
        0xA3,
        0xBD,
        0xBB,
        0x2D,
        0xB0,
        0xBF,
        0x9B,
        0x10,
        0xCB,
        0xC7,
        0x0F,
        0x5B,
        0x7E,
        0x67,
        0xE2,
        0xB0,
        0x4B,
        0xBA,
        0x10,
        0x12,
        0xB9,
        0xBC,
        0x97,
        0xFD,
        0x48,
        0xE4,
        0x8A,
        0xC1,
        0x0F,
        0xA1,
        0x30,
        0x9D,
        0x56,
        0x20,
        0x24,
        0x1A,
        0x7D,
        0x5B,
        0xA0,
        0xB4,
        0xBE,
        0x9D,
        0x38,
        0x4F,
        0xB4,
        0x56,
        0xA8,
        0x4D,
        0x13,
        0x7C,
        0x44,
        0xE8,
        0x84,
        0x97,
        0xEB,
        0x78,
        0x2C,
        0x52,
        0x85,
        0xE4,
        0xA2,
        0xF6,
        0xF3,
        0xD9,
        0x71,
        0x9E,
        0xEE,
        0xB8,
        0x11,
        0x47,
        0xFB,
        0xA9,
        0x1B,
        0xC7,
        0x40,
        0xC6,
        0xE1,
        0x19,
        0x6D,
        0x50,
        0xA1,
        0x2A,
    ]
)

# Client-Type for PS5 / PS4 firmware 10+ — from regist.c
_CLIENT_TYPE = "dabfa2ec873de5839bee8d3f4c0239c4282c07c25c6077a2931afcf0adc0d34f"

_RP_VERSION = "1.0"  # PS5 (chiaki_rp_version_string for CHIAKI_TARGET_PS5_1)
_REGIST_PATH = "/sie/ps5/rp/sess/rgst"
_INNER_HEADER_OFFSET = 0x1E0  # first 0x1E0 bytes are random prefix

_PORT = 9295
_WURZELBERT_PS5 = 0xD3  # uint8_t(-0x2D)


# ── crypto helpers ────────────────────────────────────────────────────────────


def _derive_bright(ambassador: bytes, key_0_off: int, pin: int) -> bytes:
    """Derive 16-byte AES key (bright) from ambassador + pin (chiaki_rpcrypt_init_regist)."""
    bright = bytearray(16)
    for i in range(16):
        bright[i] = _KEYS_0[i * 0x20 + key_0_off]
    bright[0xC] ^= (pin >> 24) & 0xFF
    bright[0xD] ^= (pin >> 16) & 0xFF
    bright[0xE] ^= (pin >> 8) & 0xFF
    bright[0xF] ^= pin & 0xFF
    return bytes(bright)


def _aeropause(ambassador: bytes, key_1_off: int) -> bytes:
    """Compute 16-byte aeropause from ambassador (chiaki_rpcrypt_aeropause, PS5)."""
    out = bytearray(16)
    for i in range(16):
        k = _KEYS_1[i * 0x20 + key_1_off]
        out[i] = ((ambassador[i] ^ k) + _WURZELBERT_PS5 + i) & 0xFF
    return bytes(out)


def _generate_iv(ambassador: bytes, counter: int) -> bytes:
    """Generate AES-CFB IV = HMAC-SHA256(hmac_key, ambassador || counter_be64)[0:16]."""
    data = ambassador + struct.pack(">Q", counter)
    return _hmac.new(_HMAC_KEY, data, hashlib.sha256).digest()[:16]


def _aes_cfb128_encrypt(key: bytes, iv: bytes, plaintext: bytes) -> bytes:
    # segment_size=128 → CFB-128, same as OpenSSL EVP_aes_128_cfb128()
    cipher = _AES.new(key, _AES.MODE_CFB, iv=iv, segment_size=128)
    return cipher.encrypt(plaintext)


def _aes_cfb128_decrypt(key: bytes, iv: bytes, ciphertext: bytes) -> bytes:
    cipher = _AES.new(key, _AES.MODE_CFB, iv=iv, segment_size=128)
    return cipher.decrypt(ciphertext)


# ── payload builder ───────────────────────────────────────────────────────────


def _build_payload(account_id_str: str, pin: int) -> tuple[bytes, bytes, bytes]:
    """Build registration payload.

    Returns ``(payload, bright, ambassador)`` for decrypting the response.
    """
    # account_id is stored as little-endian 8-byte int (matches Chiaki GUI)
    account_id_bin = int(account_id_str).to_bytes(8, "little")
    account_id_b64 = base64.b64encode(account_id_bin).decode()

    ambassador = os.urandom(16)

    # 0x1E0-byte prefix, random but two offsets are derived from specific bytes
    prefix = bytearray(os.urandom(_INNER_HEADER_OFFSET))
    key_0_off = prefix[0x18D] & 0x1F
    key_1_off = prefix[0] >> 3

    bright = _derive_bright(ambassador, key_0_off, pin)
    aero = _aeropause(ambassador, key_1_off)

    # Embed aeropause into prefix at fixed offsets
    prefix[0xC7:0xCF] = aero[8:16]
    prefix[0x191:0x199] = aero[0:8]

    # Inner header (plaintext before encryption)
    inner = (f"Client-Type: {_CLIENT_TYPE}\r\nNp-AccountId: {account_id_b64}\r\n").encode()

    iv = _generate_iv(ambassador, 0)
    encrypted_inner = _aes_cfb128_encrypt(bright, iv, inner)

    payload = bytes(prefix) + encrypted_inner
    return payload, bright, ambassador


# ── network helpers ───────────────────────────────────────────────────────────


def _udp_search(host: str, timeout: float = 3.0) -> None:
    """Send SRC3 UDP search and wait for RES3 (required by PS5 before TCP registration)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, _PORT))
        sock.send(b"SRC3\x00")
        try:
            data = sock.recv(64)
            if data and data[:4] == b"RES3":
                return  # success
        except OSError:
            pass
    finally:
        sock.close()


def _recv_all(sock: socket.socket, timeout: float = 3.0) -> bytes:
    sock.settimeout(timeout)
    buf = b""
    try:
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
    except OSError:
        pass
    return buf


def _parse_http_response(raw: bytes) -> tuple[int, dict[str, str], bytes]:
    """Split raw HTTP response into (status_code, headers, body)."""
    header_end = raw.find(b"\r\n\r\n")
    if header_end < 0:
        raise ValueError("No HTTP header terminator found")
    header_section = raw[:header_end].decode(errors="replace")
    body = raw[header_end + 4 :]

    lines = header_section.split("\r\n")
    status_line = lines[0]
    m = re.match(r"HTTP/\S+\s+(\d+)", status_line)
    status = int(m.group(1)) if m else 0

    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ": " in line:
            k, _, v = line.partition(": ")
            headers[k.strip()] = v.strip()

    return status, headers, body


def register_ps5(host: str, pin: int, account_id_str: str) -> str:
    """Register with a PS5 and return the DDP user-credential (PS5-RegistKey).

    :param host: PS5 IP address.
    :param pin: 8-digit PIN shown on PS5 (Settings → System → Remote Play → Link Device).
    :param account_id_str: PSN account_id as a decimal string (from JWT ``account_id`` claim).
    :returns: 64-character hex DDP user-credential.
    :raises RuntimeError: On registration failure.
    """
    payload, bright, ambassador = _build_payload(account_id_str, pin)

    host_header = f"{host}:{_PORT}"
    http_header = (
        f"POST {_REGIST_PATH} HTTP/1.1\r\n HTTP/1.1\r\n"
        f"HOST: {host_header}\r\n"
        f"User-Agent: remoteplay Windows\r\n"
        f"Connection: close\r\n"
        f"Content-Length: {len(payload)}\r\n"
        f"RP-Version: {_RP_VERSION}\r\n"
        f"\r\n"
    ).encode()

    # Step 1: UDP search (PS5 expects this before accepting TCP registration)
    print("  UDP search (SRC3)...", end=" ", flush=True)
    _udp_search(host)
    print("done")

    # Step 2: TCP register
    print("  TCP connecting to registration endpoint...", end=" ", flush=True)
    sock = socket.create_connection((host, _PORT), timeout=5)
    print("connected")

    print("  Sending registration request...", end=" ", flush=True)
    sock.sendall(http_header + payload)
    print("sent")

    raw = _recv_all(sock)
    sock.close()

    if not raw:
        raise RuntimeError("No response from PS5")

    status, resp_headers, body = _parse_http_response(raw)
    print(f"  HTTP {status}")

    if status != 200:
        reason = resp_headers.get("RP-Application-Reason", "")
        raise RuntimeError(f"Registration failed: HTTP {status}  RP-Application-Reason: {reason}")

    # Decrypt response body
    content_len = int(resp_headers.get("Content-Length", len(body)))
    body = body[:content_len]
    iv = _generate_iv(ambassador, 0)
    plaintext = _aes_cfb128_decrypt(bright, iv, body)

    # Parse decrypted payload as HTTP-like headers
    result_headers: dict[str, str] = {}
    for line in plaintext.decode(errors="replace").splitlines():
        if ": " in line:
            k, _, v = line.partition(": ")
            result_headers[k.strip()] = v.strip()

    regist_key = result_headers.get("PS5-RegistKey")
    if not regist_key:
        raise RuntimeError(
            f"PS5-RegistKey not found in response. Keys: {list(result_headers.keys())}"
        )

    return regist_key


# ── CLI ───────────────────────────────────────────────────────────────────────


def main() -> None:
    PS5_IP = "192.168.1.190"

    host = input(f"PS5 IP [{PS5_IP}]: ").strip() or PS5_IP
    pin_str = input("8-digit PIN (Settings → System → Remote Play → Link Device): ").strip()
    if not pin_str.isdigit() or len(pin_str) != 8:
        print("ERROR: PIN must be exactly 8 digits.")
        sys.exit(1)
    pin = int(pin_str)

    account_id = input("PSN account_id (decimal, from JWT): ").strip()
    if not account_id.isdigit():
        print("ERROR: account_id must be a decimal integer.")
        sys.exit(1)

    print("\nRegistering with PS5...")
    try:
        credential = register_ps5(host, pin, account_id)
    except RuntimeError as e:
        print(f"\n[FAILED] {e}")
        sys.exit(1)

    print("\n[SUCCESS] DDP user-credential (PS5-RegistKey):")
    print(f"  {credential}")
    print("\nSave this in your HA integration config as the DDP credential.")


if __name__ == "__main__":
    main()
