"""pyps5 — Python library for PS5 control.

Exposes:
- Ps5Async: main console controller (DDP + CAN API)
- PSNAuth / TokenManager: PSN OAuth2 helpers
- async_discover: find consoles on local network
"""
from .auth import PSNAuth, TokenManager
from .ddp import async_discover, async_get_status
from .ps5 import Ps5Async, PS5Error

__all__ = [
    "Ps5Async",
    "PS5Error",
    "PSNAuth",
    "TokenManager",
    "async_discover",
    "async_get_status",
]
