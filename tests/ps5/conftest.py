"""Shared fixtures for PS5 tests."""

from __future__ import annotations

import pytest
from psn_ddp.protocol import DDPStatus
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ps5.const import CONF_CREDENTIAL, DOMAIN

HOST = "192.168.1.100"
CREDENTIAL = "a" * 64
HOST_ID = "AABBCCDDEEFF112233"
HOST_NAME = "My PS5"
FAKE_JWT = (
    "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9"
    "."
    + __import__("base64")
    .urlsafe_b64encode(__import__("json").dumps({"account_id": "123456789"}).encode())
    .rstrip(b"=")
    .decode()
    + ".fakesig"
)


def make_status(
    *,
    available: bool = True,
    on: bool = True,
    standby: bool = False,
    title_id: str | None = None,
    title_name: str | None = None,
) -> DDPStatus:
    """Build a DDPStatus for use in tests."""
    return DDPStatus(
        host=HOST,
        available=available,
        on=on,
        standby=standby,
        host_type="PS5",
        host_name=HOST_NAME,
        host_id=HOST_ID,
        title_id=title_id,
        title_name=title_name,
        system_version="09.00",
    )


@pytest.fixture
def config_entry():
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=HOST_ID,
        data={"host": HOST, CONF_CREDENTIAL: CREDENTIAL},
        title=HOST_NAME,
    )
