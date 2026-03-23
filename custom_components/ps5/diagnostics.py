"""Diagnostics for the PlayStation 5 integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .coordinator import PS5Coordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: PS5Coordinator = entry.runtime_data
    status = coordinator.data

    return {
        "host": entry.data.get(CONF_HOST),
        "status": {
            "available": status.available if status else False,
            "on": status.on if status else False,
            "standby": status.standby if status else False,
            "host_type": status.host_type if status else None,
            "host_name": status.host_name if status else None,
            "title_id": status.title_id if status else None,
            "title_name": status.title_name if status else None,
            "system_version": status.system_version if status else None,
        },
    }
