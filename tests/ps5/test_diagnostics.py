"""Tests for PS5 diagnostics."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.core import HomeAssistant

from .conftest import HOST, make_status


async def test_diagnostics(hass: HomeAssistant, config_entry) -> None:
    config_entry.add_to_hass(hass)
    with patch(
        "custom_components.ps5.coordinator.async_get_status",
        return_value=make_status(title_id="PPSA01234_00", title_name="Elden Ring"),
    ):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    from custom_components.ps5.diagnostics import async_get_config_entry_diagnostics

    diag = await async_get_config_entry_diagnostics(hass, config_entry)
    assert diag["host"] == HOST
    assert diag["status"]["available"] is True
    assert diag["status"]["on"] is True
    assert diag["status"]["title_id"] == "PPSA01234_00"
    assert diag["status"]["title_name"] == "Elden Ring"
    assert diag["status"]["system_version"] == "09.00"
