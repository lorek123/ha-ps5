"""Config flow for PlayStation Network integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pyps5.auth import PSNAuth, account_id_from_access_token

from .const import (
    CONF_ACCESS_TOKEN,
    CONF_ACCOUNT_ID,
    CONF_EXPIRES_AT,
    CONF_NPSSO,
    CONF_REFRESH_TOKEN,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema({vol.Required(CONF_NPSSO): str})


class PSNConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle PSN setup: npsso → OAuth tokens."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Single step: enter NPSSO token."""
        errors: dict[str, str] = {}

        if user_input is not None:
            npsso = user_input[CONF_NPSSO].strip()
            session = async_get_clientsession(self.hass)
            try:
                tokens = await PSNAuth.from_npsso(session, npsso)
            except ValueError as exc:
                _LOGGER.error("PSN NPSSO exchange failed: %s", exc)
                errors["base"] = "invalid_npsso"
            except aiohttp.ClientError as exc:
                _LOGGER.error("PSN network error: %s", exc)
                errors["base"] = "cannot_connect"
            except Exception as exc:
                _LOGGER.exception("PSN unexpected error: %s", exc)
                errors["base"] = "unknown"
            else:
                # Decode account_id from JWT for unique_id
                account_id = account_id_from_access_token(tokens.get("access_token", ""))
                await self.async_set_unique_id(account_id or tokens.get("access_token", "")[:16])
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title="PlayStation Network",
                    data={
                        CONF_ACCESS_TOKEN: tokens["access_token"],
                        CONF_REFRESH_TOKEN: tokens["refresh_token"],
                        CONF_EXPIRES_AT: tokens["expires_at"],
                        CONF_ACCOUNT_ID: account_id or "",
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            description_placeholders={
                "npsso_hint": (
                    "Get your NPSSO token from: "
                    "https://ca.account.sony.com/api/v1/ssocookie "
                    "after logging in at playstation.com."
                ),
            },
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Trigger reauthentication when PSN tokens expire."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Re-enter NPSSO to refresh tokens."""
        errors: dict[str, str] = {}

        if user_input is not None:
            npsso = user_input[CONF_NPSSO].strip()
            session = async_get_clientsession(self.hass)
            try:
                tokens = await PSNAuth.from_npsso(session, npsso)
            except ValueError as exc:
                _LOGGER.error("PSN reauth NPSSO exchange failed: %s", exc)
                errors["base"] = "invalid_npsso"
            except aiohttp.ClientError as exc:
                _LOGGER.error("PSN reauth network error: %s", exc)
                errors["base"] = "cannot_connect"
            except Exception as exc:
                _LOGGER.exception("PSN reauth unexpected error: %s", exc)
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(),
                    data_updates={
                        CONF_ACCESS_TOKEN: tokens["access_token"],
                        CONF_REFRESH_TOKEN: tokens["refresh_token"],
                        CONF_EXPIRES_AT: tokens["expires_at"],
                    },
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_NPSSO): str}),
            description_placeholders={
                "npsso_hint": (
                    "Your PSN session has expired. Get a fresh NPSSO token from: "
                    "https://ca.account.sony.com/api/v1/ssocookie"
                ),
            },
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow updating PSN credentials."""
        errors: dict[str, str] = {}

        if user_input is not None:
            npsso = user_input[CONF_NPSSO].strip()
            session = async_get_clientsession(self.hass)
            try:
                tokens = await PSNAuth.from_npsso(session, npsso)
            except ValueError as exc:
                _LOGGER.error("PSN reconfigure NPSSO exchange failed: %s", exc)
                errors["base"] = "invalid_npsso"
            except aiohttp.ClientError as exc:
                _LOGGER.error("PSN reconfigure network error: %s", exc)
                errors["base"] = "cannot_connect"
            except Exception as exc:
                _LOGGER.exception("PSN reconfigure unexpected error: %s", exc)
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    self._get_reconfigure_entry(),
                    data_updates={
                        CONF_ACCESS_TOKEN: tokens["access_token"],
                        CONF_REFRESH_TOKEN: tokens["refresh_token"],
                        CONF_EXPIRES_AT: tokens["expires_at"],
                    },
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({vol.Required(CONF_NPSSO): str}),
            description_placeholders={
                "npsso_hint": (
                    "Enter a fresh NPSSO token to update your PSN credentials. "
                    "Get it from: https://ca.account.sony.com/api/v1/ssocookie"
                ),
            },
            errors=errors,
        )
