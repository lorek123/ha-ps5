"""PSN coordinator — polls CAN client list on a fixed interval."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from pyps5.auth import PSNAuth
from pyps5.can import CANClient, CANError, PLATFORM_PS5

from .const import CLIENT_STATUS_ONLINE

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_ACCESS_TOKEN,
    CONF_EXPIRES_AT,
    CONF_REFRESH_TOKEN,
    DOMAIN,
    POLL_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

_TOKEN_EXPIRY_BUFFER = 60.0  # seconds


@dataclass
class PSNClient:
    """A single PlayStation console returned by the CAN client list."""

    duid: str
    name: str
    platform: str
    status: str
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def online(self) -> bool:
        return self.status == CLIENT_STATUS_ONLINE


@dataclass
class PSNData:
    """All data fetched in one coordinator update cycle."""

    clients: dict[str, PSNClient] = field(default_factory=dict)


class PSNCoordinator(DataUpdateCoordinator[PSNData]):
    """Polls CAN client list every POLL_INTERVAL seconds."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"PSN {entry.entry_id[:8]}",
            update_interval=timedelta(seconds=POLL_INTERVAL),
        )
        self._entry = entry

    async def _async_update_data(self) -> PSNData:
        entry = self._entry
        session = async_get_clientsession(self.hass)

        # Refresh access token if it expires within the buffer window
        expires_at: float = entry.data.get(CONF_EXPIRES_AT, 0.0)
        access_token: str = entry.data[CONF_ACCESS_TOKEN]

        if time.time() >= expires_at - _TOKEN_EXPIRY_BUFFER:
            _LOGGER.debug("PSN access token expired, refreshing")
            try:
                auth = PSNAuth(session)
                tokens = await auth.refresh_access_token(entry.data[CONF_REFRESH_TOKEN])
            except ValueError as exc:
                raise ConfigEntryAuthFailed("PSN credentials expired") from exc
            except Exception as exc:
                raise UpdateFailed(f"PSN token refresh failed: {exc}") from exc

            new_access = tokens["access_token"]
            new_refresh = tokens.get("refresh_token", entry.data[CONF_REFRESH_TOKEN])
            if new_access != entry.data[CONF_ACCESS_TOKEN] or new_refresh != entry.data[CONF_REFRESH_TOKEN]:
                self.hass.config_entries.async_update_entry(entry, data={
                    **entry.data,
                    CONF_ACCESS_TOKEN: new_access,
                    CONF_REFRESH_TOKEN: new_refresh,
                    CONF_EXPIRES_AT: tokens["expires_at"],
                })
            access_token = new_access

        try:
            async with CANClient(access_token, session) as can:
                raw_clients = await can.get_clients(PLATFORM_PS5)
        except CANError as exc:
            raise UpdateFailed(f"CAN API error: {exc}") from exc

        clients = {
            c["duid"]: PSNClient(
                duid=c["duid"],
                name=c.get("name", "PlayStation 5"),
                platform=c.get("platform", PLATFORM_PS5),
                status=c.get("status", "offline"),
                raw=c,
            )
            for c in raw_clients
            if c.get("duid")
        }
        return PSNData(clients=clients)
