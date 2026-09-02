"""Constants for the TrueNAS integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "truenas_ws"

CONF_API_KEY: Final = "api_key"

DEFAULT_SCAN_INTERVAL: Final = 120  # 2 min > base poll cycle
DEFAULT_DISK_POOL_INTERVAL: Final = 300  # 5 min for disks/pools/network
DEFAULT_DATASET_INTERVAL: Final = 900  # 15 min for datasets
DEFAULT_TASKS_INTERVAL: Final = 300  # 5 min for tasks
DEFAULT_UPDATE_CHECK_INTERVAL: Final = 43200  # 12 hours for the update check

# system.info is fetched every cycle, so a boot time derived from its
# uptime_seconds shifts by a second or two each time. For a TIMESTAMP sensor
# that is a brand new state on every poll, which floods the recorder and makes
# the history graph unreadable. Movement below this is the same boot; a real
# reboot moves it by far more.
BOOT_TIME_TOLERANCE: Final = 60  # seconds

ATTR_MODEL: Final = "model"
ATTR_SERIAL: Final = "serial"
ATTR_SIZE: Final = "size"
ATTR_POOL: Final = "pool"
ATTR_PATH: Final = "path"
ATTR_TYPE: Final = "type"
