"""PS5 media_player entity — DDP status + WAKEUP."""
from __future__ import annotations

import logging

from psn_ddp import DDPStatus, async_wakeup

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_CREDENTIAL, DOMAIN
from .coordinator import PS5Coordinator

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

SUPPORT_PS5 = MediaPlayerEntityFeature.TURN_ON


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PS5Coordinator = entry.runtime_data
    async_add_entities([PS5MediaPlayer(coordinator, entry)])


class PS5MediaPlayer(CoordinatorEntity[PS5Coordinator], MediaPlayerEntity):
    """Media player entity for a PS5 console via local DDP."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_device_class = MediaPlayerDeviceClass.RECEIVER

    def __init__(self, coordinator: PS5Coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._credential = entry.data[CONF_CREDENTIAL]
        self._host = entry.data[CONF_HOST]
        self._attr_unique_id = entry.unique_id
        self._attr_supported_features = SUPPORT_PS5

    @property
    def device_info(self) -> DeviceInfo:
        status: DDPStatus = self.coordinator.data
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.unique_id or "")},
            name=status.host_name or "PlayStation 5",
            manufacturer="Sony",
            model="PlayStation 5",
            sw_version=status.system_version,
        )

    @property
    def state(self) -> MediaPlayerState:
        status: DDPStatus = self.coordinator.data
        if not status.available:
            return MediaPlayerState.OFF
        if status.on:
            return MediaPlayerState.ON
        if status.standby:
            return MediaPlayerState.STANDBY
        return MediaPlayerState.OFF

    @property
    def media_title(self) -> str | None:
        return self.coordinator.data.title_name

    @property
    def media_content_id(self) -> str | None:
        return self.coordinator.data.title_id

    async def async_turn_on(self) -> None:
        await async_wakeup(self._host, credential=self._credential)
        await self.coordinator.async_request_refresh()
