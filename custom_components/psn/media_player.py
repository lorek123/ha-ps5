"""PSN media_player entities — one per PS5 console in the CAN client list."""
from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ACCESS_TOKEN, DOMAIN
from .coordinator import PSNClient, PSNCoordinator
from pyps5.can import CANClient, CANError, PLATFORM_PS5

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

SUPPORT_PSN = (
    MediaPlayerEntityFeature.TURN_ON
    | MediaPlayerEntityFeature.TURN_OFF
    | MediaPlayerEntityFeature.PLAY_MEDIA
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PSNCoordinator = entry.runtime_data
    known_duids: set[str] = set()

    def _handle_coordinator_update() -> None:
        if not coordinator.data:
            return

        # Add entities for newly discovered consoles
        new_duids = set(coordinator.data.clients) - known_duids
        if new_duids:
            known_duids.update(new_duids)
            async_add_entities([
                PSNMediaPlayer(coordinator, entry, duid)
                for duid in new_duids
            ])

        # Remove device registry entries for consoles no longer on the account
        current_duids = set(coordinator.data.clients)
        dev_reg = dr.async_get(hass)
        for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
            device_duid = next(
                (ident[1] for ident in device.identifiers if ident[0] == DOMAIN),
                None,
            )
            if device_duid and device_duid not in current_duids:
                dev_reg.async_remove_device(device.id)

    _handle_coordinator_update()
    entry.async_on_unload(coordinator.async_add_listener(_handle_coordinator_update))


class PSNMediaPlayer(CoordinatorEntity[PSNCoordinator], MediaPlayerEntity):
    """Media player entity for a PS5 console managed via PSN CAN API."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_device_class = MediaPlayerDeviceClass.RECEIVER
    _attr_supported_features = SUPPORT_PSN

    def __init__(
        self,
        coordinator: PSNCoordinator,
        entry: ConfigEntry,
        duid: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._duid = duid
        self._attr_unique_id = duid

    def _client(self) -> PSNClient | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.clients.get(self._duid)

    @property
    def device_info(self) -> DeviceInfo:
        client = self._client()
        return DeviceInfo(
            identifiers={(DOMAIN, self._duid)},
            name=client.name if client else "PlayStation 5",
            manufacturer="Sony",
            model=client.platform if client else PLATFORM_PS5,
        )

    @property
    def state(self) -> MediaPlayerState:
        client = self._client()
        if client is None:
            return MediaPlayerState.OFF
        return MediaPlayerState.ON if client.online else MediaPlayerState.STANDBY

    @property
    def available(self) -> bool:
        return self._client() is not None

    async def _can(
        self,
        action: Callable[[CANClient, str], Coroutine[Any, Any, Any]],
    ) -> None:
        session = async_get_clientsession(self.hass)
        token = self._entry.data[CONF_ACCESS_TOKEN]
        try:
            async with CANClient(token, session) as can:
                await action(can, self._duid)
        except CANError as exc:
            _LOGGER.error("PSN CAN command failed for %s: %s", self._duid, exc)
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        await self._can(lambda can, duid: can.enter_working_mode(duid))

    async def async_turn_off(self) -> None:
        await self._can(lambda can, duid: can.enter_rest_mode(duid))

    async def async_play_media(
        self, media_type: str, media_id: str, **kwargs: Any
    ) -> None:
        """Launch a title by title ID (media_id)."""
        await self._can(lambda can, duid: can.launch_title(duid, media_id))
