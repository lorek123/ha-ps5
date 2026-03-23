"""Tests for PS5 media player entity."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.components.media_player import MediaPlayerState
from homeassistant.core import HomeAssistant

from .conftest import CREDENTIAL, HOST, HOST_ID, HOST_NAME, make_status

ENTITY_ID = f"media_player.{HOST_NAME.lower().replace(' ', '_')}"


async def _setup(hass: HomeAssistant, config_entry, status=None) -> None:
    if status is None:
        status = make_status()
    config_entry.add_to_hass(hass)
    with patch(
        "custom_components.ps5.coordinator.async_get_status",
        return_value=status,
    ):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()


async def test_state_on(hass: HomeAssistant, config_entry) -> None:
    await _setup(hass, config_entry, make_status(on=True))
    assert hass.states.get(ENTITY_ID).state == MediaPlayerState.ON


async def test_state_standby(hass: HomeAssistant, config_entry) -> None:
    await _setup(hass, config_entry, make_status(on=False, standby=True))
    assert hass.states.get(ENTITY_ID).state == MediaPlayerState.STANDBY


async def test_state_off(hass: HomeAssistant, config_entry) -> None:
    await _setup(hass, config_entry, make_status(available=False, on=False))
    assert hass.states.get(ENTITY_ID).state == MediaPlayerState.OFF


async def test_media_title(hass: HomeAssistant, config_entry) -> None:
    await _setup(hass, config_entry, make_status(title_name="Elden Ring"))
    assert hass.states.get(ENTITY_ID).attributes["media_title"] == "Elden Ring"


async def test_media_content_id(hass: HomeAssistant, config_entry) -> None:
    await _setup(hass, config_entry, make_status(title_id="PPSA01234_00"))
    assert hass.states.get(ENTITY_ID).attributes["media_content_id"] == "PPSA01234_00"


async def test_unique_id(hass: HomeAssistant, config_entry) -> None:
    await _setup(hass, config_entry)
    from homeassistant.helpers import entity_registry as er
    ent_reg = er.async_get(hass)
    entry = ent_reg.async_get(ENTITY_ID)
    assert entry is not None
    assert entry.unique_id == HOST_ID


async def test_device_info(hass: HomeAssistant, config_entry) -> None:
    await _setup(hass, config_entry)
    from homeassistant.helpers import device_registry as dr
    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_device({("ps5", HOST_ID)})
    assert device is not None
    assert device.manufacturer == "Sony"
    assert device.model == "PlayStation 5"
    assert device.name == HOST_NAME


async def test_state_off_available_not_on_not_standby(hass: HomeAssistant, config_entry) -> None:
    """Cover the final `return MediaPlayerState.OFF` branch (available but not on/standby)."""
    await _setup(hass, config_entry, make_status(available=True, on=False, standby=False))
    assert hass.states.get(ENTITY_ID).state == MediaPlayerState.OFF


async def test_turn_on(hass: HomeAssistant, config_entry) -> None:
    await _setup(hass, config_entry, make_status(on=False, standby=True))
    with patch(
        "custom_components.ps5.media_player.async_wakeup"
    ) as mock_wake, patch(
        "custom_components.ps5.coordinator.async_get_status",
        return_value=make_status(on=True),
    ):
        await hass.services.async_call(
            "media_player", "turn_on", {"entity_id": ENTITY_ID}, blocking=True
        )
    mock_wake.assert_awaited_once_with(HOST, credential=CREDENTIAL)
