"""Tests for PS5 coordinator."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.core import HomeAssistant

from custom_components.ps5.coordinator import PS5Coordinator

from .conftest import HOST, make_status


async def test_update_returns_status(hass: HomeAssistant, config_entry) -> None:
    config_entry.add_to_hass(hass)
    coordinator = PS5Coordinator(hass, config_entry)
    with patch(
        "custom_components.ps5.coordinator.async_get_status",
        return_value=make_status(on=True),
    ):
        await coordinator.async_refresh()
    assert coordinator.data.available is True
    assert coordinator.data.on is True
    assert coordinator.data.host == HOST


async def test_update_unavailable(hass: HomeAssistant, config_entry) -> None:
    config_entry.add_to_hass(hass)
    coordinator = PS5Coordinator(hass, config_entry)
    with patch(
        "custom_components.ps5.coordinator.async_get_status",
        return_value=make_status(available=False, on=False),
    ):
        await coordinator.async_refresh()
    assert coordinator.data.available is False


async def test_update_standby(hass: HomeAssistant, config_entry) -> None:
    config_entry.add_to_hass(hass)
    coordinator = PS5Coordinator(hass, config_entry)
    with patch(
        "custom_components.ps5.coordinator.async_get_status",
        return_value=make_status(on=False, standby=True),
    ):
        await coordinator.async_refresh()
    assert coordinator.data.standby is True
    assert coordinator.data.on is False


async def test_update_raises_update_failed(hass: HomeAssistant, config_entry) -> None:
    config_entry.add_to_hass(hass)
    coordinator = PS5Coordinator(hass, config_entry)
    with patch(
        "custom_components.ps5.coordinator.async_get_status",
        side_effect=OSError("network error"),
    ):
        await coordinator.async_refresh()
    assert coordinator.last_update_success is False
