"""Cloud Assisted Navigation (CAN) API client for PS5.

Reverse engineered from PlayStation App 26.2.0 (index.android.bundle).

Base URL: https://m.np.playstation.com/api/cloudAssistedNavigation
Auth: PSN OAuth2 Bearer token
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

_BASE_URL = "https://m.np.playstation.com/api/cloudAssistedNavigation"

# Platform identifiers as used by CAN API
PLATFORM_PS5 = "PS5"
PLATFORM_PS4 = "PS4"

# Command types (from PS App decompilation)
CMD_LAUNCH_TITLE = "launchTitle"
CMD_ENTER_REST_MODE = "enterRestMode"
CMD_ENTER_WORKING_MODE = "enterWorkingMode"
CMD_KEEP_MAIN_ON_STANDBY = "keepMainOnStandby"
CMD_PREPARE_FOR_REMOTE_PLAY = "prepareForRemotePlay"
CMD_DELETE_TITLES = "deleteTitles"
CMD_SEND_GAME_INTENT = "sendGameIntent"


class CANError(Exception):
    """Error from the Cloud Assisted Navigation API."""


class CANClient:
    """Async client for the PlayStation Cloud Assisted Navigation API."""

    def __init__(
        self,
        access_token: str,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self._token = access_token
        self._session = session
        self._owns_session = session is None

    async def __aenter__(self) -> "CANClient":
        if self._owns_session:
            self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._owns_session and self._session:
            await self._session.close()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if self._session is None:
            raise RuntimeError("CANClient not initialised. Use as async context manager.")
        url = f"{_BASE_URL}{path}"
        async with self._session.request(
            method, url, headers=self._headers(), **kwargs
        ) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise CANError(f"CAN API {method} {path} failed [{resp.status}]: {text}")
            if resp.content_type == "application/json":
                return await resp.json()
            return {}

    async def get_clients(self, platform: str = PLATFORM_PS5) -> list[dict[str, Any]]:
        """Return list of connected consoles.

        Each entry contains 'duid', 'name', 'platform', 'status', etc.
        """
        data = await self._request(
            "GET",
            "/v2/users/me/clients",
            params={"platform": platform},
        )
        return data.get("clients", [])

    async def send_command(
        self,
        duid: str,
        command_type: str,
        parameters: dict[str, Any] | None = None,
        platform: str = PLATFORM_PS5,
    ) -> dict[str, Any]:
        """Send a command to the console. Returns the command response (includes commandId)."""
        command_detail: dict[str, Any] = {
            "platform": platform,
            "duid": duid,
            "commandType": command_type,
        }
        if parameters:
            command_detail["parameters"] = parameters
        body = {"commandDetail": command_detail}
        return await self._request("POST", "/v2/users/me/commands", json=body)

    async def launch_title(
        self,
        duid: str,
        title_id: str,
        platform: str = PLATFORM_PS5,
    ) -> dict[str, Any]:
        """Launch a game/app by title ID on the console."""
        return await self.send_command(
            duid,
            CMD_LAUNCH_TITLE,
            parameters={"titleIds": [title_id]},
            platform=platform,
        )

    async def enter_rest_mode(self, duid: str, platform: str = PLATFORM_PS5) -> dict[str, Any]:
        """Put the console into rest/standby mode."""
        return await self.send_command(duid, CMD_ENTER_REST_MODE, platform=platform)

    async def enter_working_mode(self, duid: str, platform: str = PLATFORM_PS5) -> dict[str, Any]:
        """Wake the console from rest mode."""
        return await self.send_command(duid, CMD_ENTER_WORKING_MODE, platform=platform)

    async def prepare_for_remote_play(
        self,
        duid: str,
        title_id: str | None = None,
        platform: str = PLATFORM_PS5,
    ) -> dict[str, Any]:
        """Prepare the console for Remote Play, optionally pre-launching a title."""
        parameters: dict[str, Any] | None = None
        if title_id:
            parameters = {
                "commandType": CMD_LAUNCH_TITLE,
                "parameters": {"titleIds": [title_id]},
            }
        return await self.send_command(
            duid, CMD_PREPARE_FOR_REMOTE_PLAY, parameters=parameters, platform=platform
        )

    async def get_command_status(
        self,
        command_id: str | None = None,
        platform: str = PLATFORM_PS5,
    ) -> list[dict[str, Any]]:
        """Poll command status. Optionally filter by commandId."""
        params: dict[str, str] = {
            "platform": platform,
            "includeFields": "actions,commandDetail",
            "commandStatus": "executing,completed",
        }
        if command_id:
            params["commandIds"] = command_id
        data = await self._request("GET", "/v2/users/me/commands", params=params)
        return data.get("commands", [])
