"""Shared fixtures for PSN tests."""
from __future__ import annotations

import time
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.psn.const import (
    CONF_ACCESS_TOKEN,
    CONF_ACCOUNT_ID,
    CONF_EXPIRES_AT,
    CONF_REFRESH_TOKEN,
    DOMAIN,
)
from custom_components.psn.coordinator import PSNClient, PSNData

ACCOUNT_ID = "1234567890"
ACCESS_TOKEN = (
    "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9"
    "."
    + __import__("base64").urlsafe_b64encode(
        __import__("json").dumps({"account_id": ACCOUNT_ID}).encode()
    ).rstrip(b"=").decode()
    + ".fakesig"
)
REFRESH_TOKEN = "refresh_abc123"
DUID_1 = "device_duid_0001"
DUID_2 = "device_duid_0002"

FAKE_TOKENS = {
    "access_token": ACCESS_TOKEN,
    "refresh_token": REFRESH_TOKEN,
    "expires_at": time.time() + 3600,
}


def make_client(duid: str = DUID_1, name: str = "My PS5", status: str = "online") -> PSNClient:
    return PSNClient(duid=duid, name=name, platform="PS5", status=status)


def make_psn_data(clients: list[PSNClient] | None = None) -> PSNData:
    if clients is None:
        clients = [make_client()]
    return PSNData(clients={c.duid: c for c in clients})


@pytest.fixture
def config_entry():
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=ACCOUNT_ID,
        data={
            CONF_ACCESS_TOKEN: ACCESS_TOKEN,
            CONF_REFRESH_TOKEN: REFRESH_TOKEN,
            CONF_EXPIRES_AT: time.time() + 3600,
            CONF_ACCOUNT_ID: ACCOUNT_ID,
        },
        title="PlayStation Network",
    )


@pytest.fixture
def mock_can_client():
    """AsyncMock CANClient that returns one online PS5."""
    client = AsyncMock()
    client.get_clients = AsyncMock(return_value=[
        {"duid": DUID_1, "name": "My PS5", "platform": "PS5", "status": "online"},
    ])
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client
