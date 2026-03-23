"""Tests for PSN media player entities."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.components.media_player import MediaPlayerState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .conftest import DUID_1, DUID_2

ENTITY_ID = "media_player.my_ps5"


async def _setup(hass: HomeAssistant, config_entry, mock_can_client) -> None:
    config_entry.add_to_hass(hass)
    with patch("custom_components.psn.coordinator.CANClient", return_value=mock_can_client):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()


async def test_state_online(hass: HomeAssistant, config_entry, mock_can_client) -> None:
    await _setup(hass, config_entry, mock_can_client)
    assert hass.states.get(ENTITY_ID).state == MediaPlayerState.ON


async def test_state_offline(hass: HomeAssistant, config_entry, mock_can_client) -> None:
    mock_can_client.get_clients = AsyncMock(
        return_value=[
            {"duid": DUID_1, "name": "My PS5", "platform": "PS5", "status": "offline"},
        ]
    )
    await _setup(hass, config_entry, mock_can_client)
    assert hass.states.get(ENTITY_ID).state == MediaPlayerState.STANDBY


async def test_unique_id(hass: HomeAssistant, config_entry, mock_can_client) -> None:
    await _setup(hass, config_entry, mock_can_client)
    ent_reg = er.async_get(hass)
    entry = ent_reg.async_get(ENTITY_ID)
    assert entry is not None
    assert entry.unique_id == DUID_1


async def test_device_info(hass: HomeAssistant, config_entry, mock_can_client) -> None:
    await _setup(hass, config_entry, mock_can_client)
    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_device({("psn", DUID_1)})
    assert device is not None
    assert device.manufacturer == "Sony"
    assert device.model == "PS5"


async def test_turn_on_calls_can(hass: HomeAssistant, config_entry, mock_can_client) -> None:
    await _setup(hass, config_entry, mock_can_client)
    with (
        patch("custom_components.psn.media_player.CANClient", return_value=mock_can_client),
        patch("custom_components.psn.coordinator.CANClient", return_value=mock_can_client),
    ):
        await hass.services.async_call(
            "media_player", "turn_on", {"entity_id": ENTITY_ID}, blocking=True
        )
    mock_can_client.enter_working_mode.assert_awaited_once_with(DUID_1)


async def test_turn_off_calls_can(hass: HomeAssistant, config_entry, mock_can_client) -> None:
    await _setup(hass, config_entry, mock_can_client)
    with (
        patch("custom_components.psn.media_player.CANClient", return_value=mock_can_client),
        patch("custom_components.psn.coordinator.CANClient", return_value=mock_can_client),
    ):
        await hass.services.async_call(
            "media_player", "turn_off", {"entity_id": ENTITY_ID}, blocking=True
        )
    mock_can_client.enter_rest_mode.assert_awaited_once_with(DUID_1)


async def test_play_media_calls_can(hass: HomeAssistant, config_entry, mock_can_client) -> None:
    await _setup(hass, config_entry, mock_can_client)
    with (
        patch("custom_components.psn.media_player.CANClient", return_value=mock_can_client),
        patch("custom_components.psn.coordinator.CANClient", return_value=mock_can_client),
    ):
        await hass.services.async_call(
            "media_player",
            "play_media",
            {
                "entity_id": ENTITY_ID,
                "media_content_id": "PPSA01234_00",
                "media_content_type": "game",
            },
            blocking=True,
        )
    mock_can_client.launch_title.assert_awaited_once_with(DUID_1, "PPSA01234_00")


async def test_dynamic_device_added(hass: HomeAssistant, config_entry, mock_can_client) -> None:
    await _setup(hass, config_entry, mock_can_client)
    # Coordinator now returns a second device
    mock_can_client.get_clients = AsyncMock(
        return_value=[
            {"duid": DUID_1, "name": "My PS5", "platform": "PS5", "status": "online"},
            {"duid": DUID_2, "name": "PS5 Pro", "platform": "PS5", "status": "offline"},
        ]
    )
    with patch("custom_components.psn.coordinator.CANClient", return_value=mock_can_client):
        await config_entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
    ent_reg = er.async_get(hass)
    assert ent_reg.async_get_entity_id("media_player", "psn", DUID_2) is not None


async def test_can_error_logged(hass: HomeAssistant, config_entry, mock_can_client) -> None:
    await _setup(hass, config_entry, mock_can_client)
    from pyps5.can import CANError

    failing_client = AsyncMock()
    failing_client.__aenter__ = AsyncMock(side_effect=CANError("boom"))
    failing_client.__aexit__ = AsyncMock(return_value=False)
    with (
        patch("custom_components.psn.media_player.CANClient", return_value=failing_client),
        patch("custom_components.psn.coordinator.CANClient", return_value=mock_can_client),
    ):
        # Should not raise — errors are logged
        await hass.services.async_call(
            "media_player", "turn_on", {"entity_id": ENTITY_ID}, blocking=True
        )
    # Entity still exists and state unchanged
    assert hass.states.get(ENTITY_ID) is not None


async def test_state_unavailable_when_no_coordinator_data(
    hass: HomeAssistant, config_entry, mock_can_client
) -> None:
    """Cover _handle_coordinator_update early return and _client None branch."""
    await _setup(hass, config_entry, mock_can_client)
    coordinator = config_entry.runtime_data
    # Simulate coordinator losing its data (e.g. first refresh failed after setup)
    coordinator.data = None
    coordinator.async_update_listeners()
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == "unavailable"


async def test_stale_device_removed(hass: HomeAssistant, config_entry, mock_can_client) -> None:
    await _setup(hass, config_entry, mock_can_client)
    dev_reg = dr.async_get(hass)
    assert dev_reg.async_get_device({("psn", DUID_1)}) is not None
    # Coordinator returns empty list — console removed from account
    mock_can_client.get_clients = AsyncMock(return_value=[])
    with patch("custom_components.psn.coordinator.CANClient", return_value=mock_can_client):
        await config_entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
    assert dev_reg.async_get_device({("psn", DUID_1)}) is None
