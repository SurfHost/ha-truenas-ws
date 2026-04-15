"""DataUpdateCoordinator for the TrueNAS integration."""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import TrueNASWebSocketClient
from .const import (
    DEFAULT_DATASET_INTERVAL,
    DEFAULT_DISK_POOL_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SYSTEM_INFO_INTERVAL,
    DEFAULT_TASKS_INTERVAL,
    DOMAIN,
)
from .errors import (
    TrueNASAuthenticationError,
    TrueNASConnectionError,
    TrueNASError,
    TrueNASTimeoutError,
)
from .models import TrueNASData

_LOGGER = logging.getLogger(__name__)

type TrueNASConfigEntry = ConfigEntry[TrueNASDataUpdateCoordinator]



class TrueNASDataUpdateCoordinator(DataUpdateCoordinator[TrueNASData]):
    """Coordinator to manage fetching TrueNAS data."""

    config_entry: TrueNASConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        client: TrueNASWebSocketClient,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self._last_disk_pool: float = 0
        self._last_datasets: float = 0
        self._last_tasks: float = 0
        self._last_system_info: float = 0
        self._previous_network: dict[str, tuple[int, int, float]] = {}

    async def _async_setup(self) -> None:
        """Set up the coordinator."""
        try:
            await self.client.connect()
        except TrueNASAuthenticationError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except TrueNASConnectionError as err:
            raise UpdateFailed(f"Cannot connect: {err}") from err

    async def _async_update_data(self) -> TrueNASData:
        """Fetch data from TrueNAS."""
        if not self.client.connected:
            try:
                await self.client.connect()
            except TrueNASAuthenticationError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except TrueNASConnectionError as err:
                raise UpdateFailed(f"Cannot connect: {err}") from err

        data = self.data or TrueNASData()
        now = time.monotonic()

        try:
            # ── Fast tier: every cycle (2 min) ──────────────────────
            data.system_stats = await self._safe_fetch(
                self.client.get_system_stats, data.system_stats
            )
            data.alerts = await self._safe_fetch(
                self.client.get_alerts, data.alerts
            )
            data.services = await self._safe_fetch(
                self.client.get_services, data.services
            )
            data.apps = await self._safe_fetch(
                self.client.get_apps, data.apps
            )
            data.vms = await self._safe_fetch(
                self.client.get_vms, data.vms
            )

            # ── Medium tier: every ~5 min ───────────────────────────
            if not self._last_disk_pool or now - self._last_disk_pool > DEFAULT_DISK_POOL_INTERVAL:
                data.disks = await self._safe_fetch(
                    self.client.get_disks, data.disks
                )
                disk_names = [d.name for d in data.disks if d.name]
                temps = await self._safe_fetch(
                    lambda: self.client.get_disk_temperatures(disk_names), {}
                )
                if temps:
                    from dataclasses import replace

                    updated_disks = []
                    for disk in data.disks:
                        temp = temps.get(disk.name)
                        if temp is not None and temp != disk.temperature:
                            updated_disks.append(replace(disk, temperature=temp))
                        else:
                            updated_disks.append(disk)
                    data.disks = updated_disks

                data.pools = await self._safe_fetch(
                    self.client.get_pools, data.pools
                )
                data.network_interfaces = await self._safe_fetch(
                    self.client.get_network_interfaces, data.network_interfaces
                )
                self._last_disk_pool = now

            # ── Slow tier: every ~15 min ────────────────────────────
            if not self._last_datasets or now - self._last_datasets > DEFAULT_DATASET_INTERVAL:
                data.datasets = await self._safe_fetch(
                    self.client.get_datasets, data.datasets
                )
                self._last_datasets = now

            # ── Tasks: every ~5 min ─────────────────────────────────
            if not self._last_tasks or now - self._last_tasks > DEFAULT_TASKS_INTERVAL:
                data.replication_tasks = await self._safe_fetch(
                    self.client.get_replication_tasks, data.replication_tasks
                )
                data.snapshot_tasks = await self._safe_fetch(
                    self.client.get_snapshot_tasks, data.snapshot_tasks
                )
                data.cloud_sync_tasks = await self._safe_fetch(
                    self.client.get_cloud_sync_tasks, data.cloud_sync_tasks
                )
                data.rsync_tasks = await self._safe_fetch(
                    self.client.get_rsync_tasks, data.rsync_tasks
                )
                self._last_tasks = now

            # ── System info + update check: every 12 hours ──────────
            if (
                data.system_info is None
                or now - self._last_system_info > DEFAULT_SYSTEM_INFO_INTERVAL
            ):
                data.system_info = await self._safe_fetch(
                    self.client.get_system_info, data.system_info
                )
                data.update_info = await self._safe_fetch(
                    self.client.check_update, data.update_info
                )
                self._last_system_info = now

        except TrueNASAuthenticationError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except (TrueNASConnectionError, TrueNASTimeoutError) as err:
            raise UpdateFailed(f"Communication error: {err}") from err

        return data

    async def _safe_fetch(
        self,
        fetch_fn: Any,
        fallback: Any,
    ) -> Any:
        """Fetch data, returning fallback on non-critical error."""
        try:
            return await fetch_fn()
        except TrueNASAuthenticationError:
            raise
        except TrueNASError as err:
            _LOGGER.debug(
                "Failed to fetch %s, using cached data: %s",
                getattr(fetch_fn, "__name__", "fetch"),
                err,
            )
            return fallback
