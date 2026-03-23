"""Main Ps5Async class — top-level API for PS5 control."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .auth import TokenManager
from .can import PLATFORM_PS5, CANClient
from .ddp import (
    STATUS_ON,
    STATUS_STANDBY,
    async_get_status,
    async_send_wakeup,
)

_LOGGER = logging.getLogger(__name__)

# DDP status field names
STATUS_FIELD = "status"
TITLE_ID_FIELD = "running-app-titleid"
TITLE_NAME_FIELD = "running-app-name"
HOST_ID_FIELD = "host-id"
HOST_NAME_FIELD = "host-name"
SYSTEM_VERSION_FIELD = "system-version"


class PS5Error(Exception):
    """Generic PS5 library error."""


class Ps5Async:
    """Async controller for a PS5 console.

    Combines:
    - DDP for local discovery/status polling and wake-up
    - CAN API for game launching and remote power commands

    Args:
        host: IP address of the PS5 console.
        credential: DDP user-credential string (from pairing, used for wakeup).
        token_manager: PSN token manager for CAN API calls.
        duid: Console device unique ID (fetched from CAN /v2/users/me/clients).
        session: Optional shared aiohttp session.
    """

    def __init__(
        self,
        host: str,
        credential: str,
        token_manager: TokenManager,
        duid: str | None = None,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self.host = host
        self._credential = credential
        self._token_manager = token_manager
        self._duid = duid
        self._session = session
        self._owns_session = session is None
        self._status: dict[str, Any] = {}

    async def async_init(self) -> None:
        """Initialise the aiohttp session and resolve duid if needed."""
        if self._owns_session:
            self._session = aiohttp.ClientSession()
        if not self._duid:
            await self._resolve_duid()

    async def close(self) -> None:
        if self._owns_session and self._session:
            await self._session.close()

    async def _resolve_duid(self) -> None:
        """Fetch the duid for this console from the CAN client list."""
        token = await self._token_manager.ensure_valid()
        async with CANClient(token, self._session) as can:
            clients = await can.get_clients(PLATFORM_PS5)
        # Match by host IP if possible, otherwise take the first PS5
        for client in clients:
            if client.get("remoteAddress", "").startswith(self.host):
                self._duid = client["duid"]
                return
        if clients:
            self._duid = clients[0]["duid"]
            _LOGGER.warning(
                "Could not match PS5 at %s by IP; using first client duid=%s",
                self.host,
                self._duid,
            )
        else:
            raise PS5Error(f"No PS5 clients found in CAN API for host {self.host}")

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    async def get_status(self) -> dict[str, Any]:
        """Poll status via DDP and cache it."""
        self._status = await async_get_status(self.host)
        return self._status

    @property
    def status(self) -> dict[str, Any]:
        """Last cached DDP status."""
        return self._status

    @property
    def is_on(self) -> bool:
        return self._status.get(STATUS_FIELD) == STATUS_ON

    @property
    def is_standby(self) -> bool:
        return self._status.get(STATUS_FIELD) == STATUS_STANDBY

    @property
    def running_title_id(self) -> str | None:
        return self._status.get(TITLE_ID_FIELD)

    @property
    def running_title_name(self) -> str | None:
        return self._status.get(TITLE_NAME_FIELD)

    @property
    def host_id(self) -> str | None:
        return self._status.get(HOST_ID_FIELD)

    @property
    def host_name(self) -> str | None:
        return self._status.get(HOST_NAME_FIELD)

    @property
    def system_version(self) -> str | None:
        return self._status.get(SYSTEM_VERSION_FIELD)

    # ------------------------------------------------------------------
    # Power
    # ------------------------------------------------------------------

    async def wakeup(self) -> None:
        """Wake the PS5 from rest/off via DDP WAKEUP."""
        await async_send_wakeup(self.host, self._credential)

    async def standby(self) -> None:
        """Put the PS5 into rest mode via CAN API."""
        await self._can_command("enter_rest_mode")

    # ------------------------------------------------------------------
    # Media / game control
    # ------------------------------------------------------------------

    async def start_title(self, title_id: str, _current_title_id: str | None = None) -> None:
        """Launch a game or app by title ID.

        `_current_title_id` is accepted for API compatibility with pyps4-2ndscreen
        but is not used — the CAN API handles title switching natively.
        """
        await self._can_command("launch_title", title_id=title_id)

    async def prepare_for_remote_play(self, title_id: str | None = None) -> None:
        """Prepare the PS5 for Remote Play, optionally pre-launching a title."""
        await self._can_command("prepare_for_remote_play", title_id=title_id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _can_command(self, method: str, **kwargs: Any) -> Any:
        """Execute a CANClient method with a fresh token."""
        if not self._duid:
            await self._resolve_duid()
        token = await self._token_manager.ensure_valid()
        async with CANClient(token, self._session) as can:
            return await getattr(can, method)(self._duid, **kwargs)
