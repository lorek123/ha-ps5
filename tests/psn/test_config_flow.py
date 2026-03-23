"""Tests for PSN config flow."""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.psn.const import CONF_ACCESS_TOKEN, CONF_REFRESH_TOKEN, DOMAIN

from .conftest import ACCOUNT_ID, ACCESS_TOKEN, FAKE_TOKENS, REFRESH_TOKEN


async def test_user_step_shows_form(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_success(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.psn.config_flow.PSNAuth.from_npsso",
        return_value=FAKE_TOKENS,
    ), patch(
        "custom_components.psn.config_flow.account_id_from_access_token",
        return_value=ACCOUNT_ID,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}, data={"npsso": "mynpsso"}
        )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_ACCESS_TOKEN] == ACCESS_TOKEN
    assert result["data"][CONF_REFRESH_TOKEN] == REFRESH_TOKEN


async def test_invalid_npsso(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.psn.config_flow.PSNAuth.from_npsso",
        side_effect=ValueError("bad npsso"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}, data={"npsso": "bad"}
        )
    assert result["errors"]["base"] == "invalid_npsso"


async def test_cannot_connect(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.psn.config_flow.PSNAuth.from_npsso",
        side_effect=aiohttp.ClientError("timeout"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}, data={"npsso": "token"}
        )
    assert result["errors"]["base"] == "cannot_connect"


async def test_unknown_error(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.psn.config_flow.PSNAuth.from_npsso",
        side_effect=RuntimeError("unexpected"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}, data={"npsso": "token"}
        )
    assert result["errors"]["base"] == "unknown"


async def test_already_configured(hass: HomeAssistant, config_entry) -> None:
    config_entry.add_to_hass(hass)
    with patch(
        "custom_components.psn.config_flow.PSNAuth.from_npsso",
        return_value=FAKE_TOKENS,
    ), patch(
        "custom_components.psn.config_flow.account_id_from_access_token",
        return_value=ACCOUNT_ID,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}, data={"npsso": "mynpsso"}
        )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_invalid_npsso(hass: HomeAssistant, config_entry) -> None:
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reauth_flow(hass)
    with patch(
        "custom_components.psn.config_flow.PSNAuth.from_npsso",
        side_effect=ValueError("bad"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"npsso": "bad"}
        )
    assert result["errors"]["base"] == "invalid_npsso"


async def test_reconfigure_cannot_connect(hass: HomeAssistant, config_entry) -> None:
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reconfigure_flow(hass)
    with patch(
        "custom_components.psn.config_flow.PSNAuth.from_npsso",
        side_effect=aiohttp.ClientError("timeout"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"npsso": "token"}
        )
    assert result["errors"]["base"] == "cannot_connect"


async def test_reauth_cannot_connect(hass: HomeAssistant, config_entry) -> None:
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reauth_flow(hass)
    with patch(
        "custom_components.psn.config_flow.PSNAuth.from_npsso",
        side_effect=aiohttp.ClientError("timeout"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"npsso": "token"}
        )
    assert result["errors"]["base"] == "cannot_connect"


async def test_reauth_unknown_error(hass: HomeAssistant, config_entry) -> None:
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reauth_flow(hass)
    with patch(
        "custom_components.psn.config_flow.PSNAuth.from_npsso",
        side_effect=RuntimeError("unexpected"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"npsso": "token"}
        )
    assert result["errors"]["base"] == "unknown"


async def test_reconfigure_invalid_npsso(hass: HomeAssistant, config_entry) -> None:
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reconfigure_flow(hass)
    with patch(
        "custom_components.psn.config_flow.PSNAuth.from_npsso",
        side_effect=ValueError("bad npsso"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"npsso": "bad"}
        )
    assert result["errors"]["base"] == "invalid_npsso"


async def test_reconfigure_unknown_error(hass: HomeAssistant, config_entry) -> None:
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reconfigure_flow(hass)
    with patch(
        "custom_components.psn.config_flow.PSNAuth.from_npsso",
        side_effect=RuntimeError("unexpected"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"npsso": "token"}
        )
    assert result["errors"]["base"] == "unknown"


async def test_reauth_flow(hass: HomeAssistant, config_entry) -> None:
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    new_tokens = {
        "access_token": "new_access",
        "refresh_token": "new_refresh",
        "expires_at": time.time() + 3600,
    }
    with patch(
        "custom_components.psn.config_flow.PSNAuth.from_npsso",
        return_value=new_tokens,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"npsso": "fresh_npsso"}
        )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data[CONF_ACCESS_TOKEN] == "new_access"


async def test_reconfigure_flow(hass: HomeAssistant, config_entry) -> None:
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    new_tokens = {
        "access_token": "reconfigured_access",
        "refresh_token": "reconfigured_refresh",
        "expires_at": time.time() + 3600,
    }
    with patch(
        "custom_components.psn.config_flow.PSNAuth.from_npsso",
        return_value=new_tokens,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"npsso": "fresh_npsso"}
        )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.data[CONF_ACCESS_TOKEN] == "reconfigured_access"
