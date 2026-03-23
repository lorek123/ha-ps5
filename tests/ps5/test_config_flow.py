"""Tests for PS5 config flow."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.ps5.const import CONF_CREDENTIAL, DOMAIN
from custom_components.ps5.regist import RegistrationError

from .conftest import CREDENTIAL, FAKE_JWT, HOST, make_status


async def test_user_step_shows_form(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_manual_ip_cannot_connect(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.ps5.config_flow.async_get_status",
        return_value=make_status(available=False, on=False),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}, data={"host": HOST}
        )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["host"] == "cannot_connect"


async def test_manual_ip_proceeds_to_pin(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.ps5.config_flow.async_get_status",
        return_value=make_status(),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}, data={"host": HOST}
        )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "pin"


async def test_autodiscover_none_found(hass: HomeAssistant) -> None:
    with patch("custom_components.ps5.config_flow.async_discover", return_value=[]):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}, data={"host": ""}
        )
    assert result["errors"]["base"] == "no_devices_found"


async def test_autodiscover_one_found(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.ps5.config_flow.async_discover",
        return_value=[make_status()],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}, data={"host": ""}
        )
    assert result["step_id"] == "pin"


async def test_autodiscover_multiple(hass: HomeAssistant) -> None:
    devices = [make_status(), make_status()]
    with patch("custom_components.ps5.config_flow.async_discover", return_value=devices):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}, data={"host": ""}
        )
    assert result["step_id"] == "pick_device"


async def test_pin_invalid_format(hass: HomeAssistant) -> None:
    with patch("custom_components.ps5.config_flow.async_get_status", return_value=make_status()):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}, data={"host": HOST}
        )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"pin": "123", "npsso": "token"}
    )
    assert result["errors"]["pin"] == "invalid_pin"


async def test_pin_empty_account_id(hass: HomeAssistant) -> None:
    with patch("custom_components.ps5.config_flow.async_get_status", return_value=make_status()):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}, data={"host": HOST}
        )
    with (
        patch(
            "custom_components.ps5.config_flow.PSNAuth.from_npsso",
            return_value={"access_token": FAKE_JWT},
        ),
        patch(
            "custom_components.ps5.config_flow.account_id_from_access_token",
            return_value="",  # empty → raises ValueError in _get_account_id
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"pin": "12345678", "npsso": "token"}
        )
    assert result["errors"]["npsso"] == "invalid_npsso"


async def test_pin_invalid_npsso(hass: HomeAssistant) -> None:
    with patch("custom_components.ps5.config_flow.async_get_status", return_value=make_status()):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}, data={"host": HOST}
        )
    with patch(
        "custom_components.ps5.config_flow.PSNAuth.from_npsso",
        side_effect=ValueError("bad token"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"pin": "12345678", "npsso": "bad"}
        )
    assert result["errors"]["npsso"] == "invalid_npsso"


async def test_pin_registration_failed(hass: HomeAssistant) -> None:
    with patch("custom_components.ps5.config_flow.async_get_status", return_value=make_status()):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}, data={"host": HOST}
        )
    with (
        patch(
            "custom_components.ps5.config_flow.PSNAuth.from_npsso",
            return_value={"access_token": FAKE_JWT},
        ),
        patch(
            "custom_components.ps5.config_flow.account_id_from_access_token",
            return_value="123",
        ),
        patch(
            "custom_components.ps5.config_flow.async_register",
            side_effect=RegistrationError("failed"),
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"pin": "12345678", "npsso": "token"}
        )
    assert result["errors"]["base"] == "registration_failed"


async def test_full_flow_success(hass: HomeAssistant) -> None:
    with patch("custom_components.ps5.config_flow.async_get_status", return_value=make_status()):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}, data={"host": HOST}
        )
    with (
        patch(
            "custom_components.ps5.config_flow.PSNAuth.from_npsso",
            return_value={"access_token": FAKE_JWT},
        ),
        patch(
            "custom_components.ps5.config_flow.account_id_from_access_token",
            return_value="123",
        ),
        patch("custom_components.ps5.config_flow.async_register", return_value=CREDENTIAL),
        patch("custom_components.ps5.config_flow.async_get_status", return_value=make_status()),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"pin": "12345678", "npsso": "token"}
        )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_CREDENTIAL] == CREDENTIAL


async def test_already_configured(hass: HomeAssistant, config_entry) -> None:
    config_entry.add_to_hass(hass)
    with patch("custom_components.ps5.config_flow.async_get_status", return_value=make_status()):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}, data={"host": HOST}
        )
    with (
        patch(
            "custom_components.ps5.config_flow.PSNAuth.from_npsso",
            return_value={"access_token": FAKE_JWT},
        ),
        patch(
            "custom_components.ps5.config_flow.account_id_from_access_token",
            return_value="123",
        ),
        patch("custom_components.ps5.config_flow.async_register", return_value=CREDENTIAL),
        patch("custom_components.ps5.config_flow.async_get_status", return_value=make_status()),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"pin": "12345678", "npsso": "token"}
        )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_pin_unknown_error(hass: HomeAssistant) -> None:
    with patch("custom_components.ps5.config_flow.async_get_status", return_value=make_status()):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}, data={"host": HOST}
        )
    with (
        patch(
            "custom_components.ps5.config_flow.PSNAuth.from_npsso",
            return_value={"access_token": FAKE_JWT},
        ),
        patch(
            "custom_components.ps5.config_flow.account_id_from_access_token",
            return_value="123",
        ),
        patch(
            "custom_components.ps5.config_flow.async_register",
            side_effect=RuntimeError("unexpected"),
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"pin": "12345678", "npsso": "token"}
        )
    assert result["errors"]["base"] == "unknown"


async def test_pick_device_submit(hass: HomeAssistant) -> None:
    devices = [make_status(), make_status()]
    with patch("custom_components.ps5.config_flow.async_discover", return_value=devices):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}, data={"host": ""}
        )
    assert result["step_id"] == "pick_device"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": HOST})
    assert result["step_id"] == "pin"


async def test_reconfigure_cannot_connect(hass: HomeAssistant, config_entry) -> None:
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    with patch(
        "custom_components.ps5.config_flow.async_get_status",
        return_value=make_status(available=False, on=False),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": "10.0.0.99"}
        )
    assert result["errors"]["host"] == "cannot_connect"


async def test_reconfigure_success(hass: HomeAssistant, config_entry) -> None:
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reconfigure_flow(hass)
    new_host = "10.0.0.50"
    with patch(
        "custom_components.ps5.config_flow.async_get_status",
        return_value=make_status(),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": new_host}
        )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.data["host"] == new_host
