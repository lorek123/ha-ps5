"""Tests for PSN coordinator."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from pyps5.can import CANError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.psn.const import (
    CONF_ACCESS_TOKEN,
    CONF_EXPIRES_AT,
    CONF_REFRESH_TOKEN,
    DOMAIN,
)
from custom_components.psn.coordinator import PSNCoordinator

from .conftest import ACCESS_TOKEN, ACCOUNT_ID, DUID_1, FAKE_TOKENS, REFRESH_TOKEN


async def test_update_returns_clients(hass: HomeAssistant, config_entry, mock_can_client) -> None:
    config_entry.add_to_hass(hass)
    coordinator = PSNCoordinator(hass, config_entry)
    with patch("custom_components.psn.coordinator.CANClient", return_value=mock_can_client):
        await coordinator.async_refresh()
    assert DUID_1 in coordinator.data.clients
    assert coordinator.data.clients[DUID_1].name == "My PS5"
    assert coordinator.data.clients[DUID_1].online is True


async def test_update_filters_empty_duid(
    hass: HomeAssistant, config_entry, mock_can_client
) -> None:
    config_entry.add_to_hass(hass)
    coordinator = PSNCoordinator(hass, config_entry)
    mock_can_client.get_clients = AsyncMock(
        return_value=[
            {"duid": DUID_1, "name": "Good", "platform": "PS5", "status": "online"},
            {"duid": "", "name": "Bad", "platform": "PS5", "status": "online"},
        ]
    )
    with patch("custom_components.psn.coordinator.CANClient", return_value=mock_can_client):
        await coordinator.async_refresh()
    assert len(coordinator.data.clients) == 1


async def test_token_refresh_when_expired(hass: HomeAssistant, mock_can_client) -> None:
    expired_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=ACCOUNT_ID,
        data={
            CONF_ACCESS_TOKEN: ACCESS_TOKEN,
            CONF_REFRESH_TOKEN: REFRESH_TOKEN,
            CONF_EXPIRES_AT: time.time() - 100,  # expired
        },
    )
    expired_entry.add_to_hass(hass)
    coordinator = PSNCoordinator(hass, expired_entry)
    with (
        patch("custom_components.psn.coordinator.PSNAuth") as mock_auth_cls,
        patch("custom_components.psn.coordinator.CANClient", return_value=mock_can_client),
    ):
        mock_auth = mock_auth_cls.return_value
        mock_auth.refresh_access_token = AsyncMock(return_value=FAKE_TOKENS)
        await coordinator.async_refresh()
    mock_auth.refresh_access_token.assert_awaited_once_with(REFRESH_TOKEN)


async def test_token_refresh_updates_entry(hass: HomeAssistant, mock_can_client) -> None:
    new_access = "new_access_token_xyz"
    new_refresh = "new_refresh_token_xyz"
    expired_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=ACCOUNT_ID,
        data={
            CONF_ACCESS_TOKEN: ACCESS_TOKEN,
            CONF_REFRESH_TOKEN: REFRESH_TOKEN,
            CONF_EXPIRES_AT: time.time() - 100,
        },
    )
    expired_entry.add_to_hass(hass)
    coordinator = PSNCoordinator(hass, expired_entry)
    new_tokens = {
        "access_token": new_access,
        "refresh_token": new_refresh,
        "expires_at": time.time() + 3600,
    }
    with (
        patch("custom_components.psn.coordinator.PSNAuth") as mock_auth_cls,
        patch("custom_components.psn.coordinator.CANClient", return_value=mock_can_client),
    ):
        mock_auth = mock_auth_cls.return_value
        mock_auth.refresh_access_token = AsyncMock(return_value=new_tokens)
        await coordinator.async_refresh()
    assert expired_entry.data[CONF_ACCESS_TOKEN] == new_access
    assert expired_entry.data[CONF_REFRESH_TOKEN] == new_refresh


async def test_token_refresh_no_write_when_unchanged(hass: HomeAssistant, mock_can_client) -> None:
    expired_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=ACCOUNT_ID,
        data={
            CONF_ACCESS_TOKEN: ACCESS_TOKEN,
            CONF_REFRESH_TOKEN: REFRESH_TOKEN,
            CONF_EXPIRES_AT: time.time() - 100,
        },
    )
    expired_entry.add_to_hass(hass)
    coordinator = PSNCoordinator(hass, expired_entry)
    same_tokens = {
        "access_token": ACCESS_TOKEN,
        "refresh_token": REFRESH_TOKEN,
        "expires_at": time.time() + 3600,
    }
    with (
        patch("custom_components.psn.coordinator.PSNAuth") as mock_auth_cls,
        patch("custom_components.psn.coordinator.CANClient", return_value=mock_can_client),
        patch.object(hass.config_entries, "async_update_entry") as mock_update,
    ):
        mock_auth = mock_auth_cls.return_value
        mock_auth.refresh_access_token = AsyncMock(return_value=same_tokens)
        await coordinator.async_refresh()
    mock_update.assert_not_called()


async def test_auth_failed_raises_config_entry_auth_failed(
    hass: HomeAssistant,
) -> None:
    expired_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=ACCOUNT_ID,
        data={
            CONF_ACCESS_TOKEN: ACCESS_TOKEN,
            CONF_REFRESH_TOKEN: REFRESH_TOKEN,
            CONF_EXPIRES_AT: time.time() - 100,
        },
    )
    expired_entry.add_to_hass(hass)
    coordinator = PSNCoordinator(hass, expired_entry)
    with patch("custom_components.psn.coordinator.PSNAuth") as mock_auth_cls:
        mock_auth = mock_auth_cls.return_value
        mock_auth.refresh_access_token = AsyncMock(
            side_effect=ValueError("PSN token request failed [401]: Unauthorized")
        )
        await coordinator.async_refresh()
    assert coordinator.last_update_success is False
    assert isinstance(coordinator.last_exception, ConfigEntryAuthFailed)


async def test_network_error_during_refresh_raises_update_failed(
    hass: HomeAssistant,
) -> None:
    expired_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=ACCOUNT_ID,
        data={
            CONF_ACCESS_TOKEN: ACCESS_TOKEN,
            CONF_REFRESH_TOKEN: REFRESH_TOKEN,
            CONF_EXPIRES_AT: time.time() - 100,
        },
    )
    expired_entry.add_to_hass(hass)
    coordinator = PSNCoordinator(hass, expired_entry)
    with patch("custom_components.psn.coordinator.PSNAuth") as mock_auth_cls:
        mock_auth = mock_auth_cls.return_value
        mock_auth.refresh_access_token = AsyncMock(side_effect=OSError("network unreachable"))
        await coordinator.async_refresh()
    assert coordinator.last_update_success is False


async def test_can_error_raises_update_failed(
    hass: HomeAssistant, config_entry, mock_can_client
) -> None:
    config_entry.add_to_hass(hass)
    coordinator = PSNCoordinator(hass, config_entry)
    mock_can_client.__aenter__ = AsyncMock(side_effect=CANError("API down"))
    with patch("custom_components.psn.coordinator.CANClient", return_value=mock_can_client):
        await coordinator.async_refresh()
    assert coordinator.last_update_success is False
