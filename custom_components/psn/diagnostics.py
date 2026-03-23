"""Diagnostics for the PlayStation Network integration."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .coordinator import PSNCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: PSNCoordinator = entry.runtime_data
    data = coordinator.data

    return {
        "client_count": len(data.clients) if data else 0,
        "clients": [
            {
                "duid": client.duid,
                "name": client.name,
                "platform": client.platform,
                "status": client.status,
                "online": client.online,
            }
            for client in (data.clients.values() if data else [])
        ],
    }
