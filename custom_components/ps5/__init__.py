"""PlayStation 5 integration — local DDP control."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import PS5Coordinator

PLATFORMS = [Platform.MEDIA_PLAYER]

type PS5ConfigEntry = ConfigEntry[PS5Coordinator]


async def async_setup_entry(hass: HomeAssistant, entry: PS5ConfigEntry) -> bool:
    coordinator = PS5Coordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PS5ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
