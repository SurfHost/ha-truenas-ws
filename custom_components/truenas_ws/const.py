"""Constants for the TrueNAS integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "truenas_ws"

CONF_API_KEY: Final = "api_key"

DEFAULT_SCAN_INTERVAL: Final = 30
DEFAULT_SYSTEM_INFO_INTERVAL: Final = 43200  # 12 hours in seconds

ATTR_MODEL: Final = "model"
ATTR_SERIAL: Final = "serial"
ATTR_SIZE: Final = "size"
ATTR_POOL: Final = "pool"
ATTR_PATH: Final = "path"
ATTR_TYPE: Final = "type"
