"""Constants for the PlayStation Device Discovery Protocol (DDP)."""

from __future__ import annotations

# UDP port the console listens on
DDP_PORT: int = 9302

# Source port used by the 2nd Screen / Remote Play apps.
# The PS4/PS5 firmware only responds to SRCH packets originating from this port.
# Binding to it requires CAP_NET_BIND_SERVICE or root on Linux.
DDP_SRCH_PORT: int = 987

# DDP protocol version string embedded in packets
DDP_VERSION: str = "00030010"

# Request message types
MSG_TYPE_SRCH: str = "SRCH"
MSG_TYPE_WAKEUP: str = "WAKEUP"
MSG_TYPE_LAUNCH: str = "LAUNCH"

# HTTP-style status codes in DDP responses
STATUS_OK: int = 200        # console is on and running
STATUS_STANDBY: int = 620   # console is in rest/standby mode

# Human-readable status strings parsed from the response first line
STATUS_STRING_OK: str = "Ok"
STATUS_STRING_STANDBY: str = "Server Standby"

# Response field names
FIELD_STATUS: str = "status"
FIELD_STATUS_CODE: str = "status-code"
FIELD_TITLE_ID: str = "running-app-titleid"
FIELD_TITLE_NAME: str = "running-app-name"
FIELD_HOST_ID: str = "host-id"
FIELD_HOST_NAME: str = "host-name"
FIELD_HOST_TYPE: str = "host-type"
FIELD_SYSTEM_VERSION: str = "system-version"
FIELD_DEVICE_DISCOVERY_PROTOCOL_VERSION: str = "device-discovery-protocol-version"

# Host type values
HOST_TYPE_PS4: str = "PS4"
HOST_TYPE_PS5: str = "PS5"
