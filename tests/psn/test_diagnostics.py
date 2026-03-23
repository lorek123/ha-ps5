"""Tests for PSN diagnostics."""
from __future__ import annotations

from unittest.mock import patch

from homeassistant.core import HomeAssistant

from .conftest import DUID_1


async def test_diagnostics(hass: HomeAssistant, config_entry, mock_can_client) -> None:
    config_entry.add_to_hass(hass)
    with patch("custom_components.psn.coordinator.CANClient", return_value=mock_can_client):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    from custom_components.psn.diagnostics import async_get_config_entry_diagnostics

    diag = await async_get_config_entry_diagnostics(hass, config_entry)
    assert diag["client_count"] == 1
    assert diag["clients"][0]["duid"] == DUID_1
    assert diag["clients"][0]["name"] == "My PS5"
    assert diag["clients"][0]["online"] is True
