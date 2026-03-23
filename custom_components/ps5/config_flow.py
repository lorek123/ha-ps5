"""Config flow for PlayStation 5 integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from pyps5.auth import PSNAuth, account_id_from_access_token

from psn_ddp import DDPStatus, async_discover, async_get_status

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_CREDENTIAL, DOMAIN
from .regist import RegistrationError, async_register

_LOGGER = logging.getLogger(__name__)

STEP_PIN_SCHEMA = vol.Schema(
    {
        vol.Required("pin"): str,
        vol.Required("npsso"): str,
    }
)


class PS5ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle PS5 setup: discover → PIN registration."""

    VERSION = 1

    def __init__(self) -> None:
        self._host: str | None = None
        self._discovered: list[DDPStatus] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: discover PS5 on the network or enter IP manually."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input.get("host", "").strip()
            if host:
                # Manual IP — verify it's reachable
                status = await async_get_status(host)
                if not status.available:
                    errors["host"] = "cannot_connect"
                else:
                    self._host = host
                    return await self.async_step_pin()
            else:
                # Auto-discover
                self._discovered = await async_discover()
                if not self._discovered:
                    errors["base"] = "no_devices_found"
                elif len(self._discovered) == 1:
                    self._host = self._discovered[0].host
                    return await self.async_step_pin()
                else:
                    return await self.async_step_pick_device()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Optional("host"): str}
            ),
            description_placeholders={
                "discover_hint": "Leave blank to auto-discover on your network."
            },
            errors=errors,
        )

    async def async_step_pick_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1b: multiple PS5s found, pick one."""
        if user_input is not None:
            self._host = user_input["host"]
            return await self.async_step_pin()

        options = {
            d.host: f"{d.host_name or 'PS5'} ({d.host})"
            for d in self._discovered
        }
        return self.async_show_form(
            step_id="pick_device",
            data_schema=vol.Schema({vol.Required("host"): vol.In(options)}),
        )

    async def async_step_pin(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: enter PIN + npsso, run registration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            pin_str = user_input["pin"].strip().replace(" ", "")
            npsso = user_input["npsso"].strip()

            if not pin_str.isdigit() or len(pin_str) != 8:
                errors["pin"] = "invalid_pin"
            else:
                assert self._host is not None
                try:
                    account_id = await self._get_account_id(npsso)
                    credential = await async_register(
                        self._host, int(pin_str), account_id
                    )
                except ValueError as exc:
                    _LOGGER.error("PSN NPSSO exchange failed: %s", exc)
                    errors["npsso"] = "invalid_npsso"
                except RegistrationError as exc:
                    _LOGGER.error("PS5 registration failed: %s", exc)
                    errors["base"] = "registration_failed"
                except Exception as exc:
                    _LOGGER.exception("Unexpected error during PS5 registration: %s", exc)
                    errors["base"] = "unknown"
                else:
                    # Get host-id for unique_id
                    status = await async_get_status(self._host)
                    host_id = status.host_id if status.available else self._host
                    await self.async_set_unique_id(host_id)
                    self._abort_if_unique_id_configured()

                    return self.async_create_entry(
                        title=status.host_name if status.available else "PlayStation 5",
                        data={
                            CONF_HOST: self._host,
                            CONF_CREDENTIAL: credential,
                        },
                    )

        return self.async_show_form(
            step_id="pin",
            data_schema=STEP_PIN_SCHEMA,
            description_placeholders={
                "host": self._host or "",
                "pin_hint": (
                    "On your PS5: Settings → System → Remote Play → Link Device. "
                    "Enter the 8-digit PIN shown. You have 60 seconds."
                ),
                "npsso_hint": (
                    "Your NPSSO token is only used once to identify your account "
                    "and is not stored. Get it from: "
                    "https://ca.account.sony.com/api/v1/ssocookie"
                ),
            },
            errors=errors,
        )

    async def _get_account_id(self, npsso: str) -> str:
        """Exchange NPSSO for account_id. Tokens not stored."""
        session = async_get_clientsession(self.hass)
        tokens = await PSNAuth.from_npsso(session, npsso)
        account_id = account_id_from_access_token(tokens["access_token"])
        if not account_id:
            raise ValueError("account_id not found in PSN JWT")
        return account_id

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow changing the PS5 IP address."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            status = await async_get_status(host)
            if not status.available:
                errors[CONF_HOST] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_HOST: host},
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {vol.Required(CONF_HOST, default=entry.data.get(CONF_HOST, "")): str}
            ),
            errors=errors,
        )
