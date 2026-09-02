"""DataUpdateCoordinator for the TrueNAS integration."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import TrueNASWebSocketClient
from .const import (
    BOOT_TIME_TOLERANCE,
    DEFAULT_DATASET_INTERVAL,
    DEFAULT_DISK_POOL_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TASKS_INTERVAL,
    DEFAULT_UPDATE_CHECK_INTERVAL,
    DOMAIN,
)
from .errors import (
    TrueNASAuthenticationError,
    TrueNASConnectionError,
    TrueNASError,
    TrueNASTimeoutError,
)
from .models import SystemInfo, TrueNASData

_LOGGER = logging.getLogger(__name__)

type TrueNASConfigEntry = ConfigEntry[TrueNASDataUpdateCoordinator]


class TrueNASDataUpdateCoordinator(DataUpdateCoordinator[TrueNASData]):
    """Coordinator to manage fetching TrueNAS data."""

    config_entry: TrueNASConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: TrueNASConfigEntry,
        client: TrueNASWebSocketClient,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self._last_disk_pool: float = 0
        self._last_datasets: float = 0
        self._last_tasks: float = 0
        self._last_update_check: float = 0
        self._force_update_check = False

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
        reconnected = False
        if not self.client.connected:
            try:
                await self.client.connect()
            except TrueNASAuthenticationError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except TrueNASConnectionError as err:
                raise UpdateFailed(f"Cannot connect: {err}") from err
            reconnected = True

        data = self.data or TrueNASData()
        now = time.monotonic()

        # After a reconnect (e.g. a system reboot following an update), the
        # installed version may have changed > force the update check on the
        # tier below. This used to set the timer back to 0 and rely on
        # "now - 0 > 12h", but now is time.monotonic(), which only exceeds 12
        # hours once the HA host itself has been up that long. On a freshly
        # started HA the forced refresh silently did nothing.
        if reconnected:
            self._force_update_check = True

        try:
            # ── Fast tier: every cycle (2 min) ──────────────────────
            # system.info carries the boot time and the load averages, both of
            # which are worthless when they are 12 hours old. It is one cheap
            # local call, and get_system_stats needs the same payload for its
            # memory and CPU fallbacks, so it is fetched once and passed along.
            data.system_info = self._stable_boot_time(
                await self._safe_fetch(self.client.get_system_info, data.system_info),
                data.system_info,
            )
            system_info = data.system_info
            self._sync_device_version(system_info)
            data.system_stats = await self._safe_fetch(
                lambda: self.client.get_system_stats(system_info), data.system_stats
            )
            data.alerts = await self._safe_fetch(self.client.get_alerts, data.alerts)
            data.services = await self._safe_fetch(self.client.get_services, data.services)
            data.apps = await self._safe_fetch(self.client.get_apps, data.apps)
            data.vms = await self._safe_fetch(self.client.get_vms, data.vms)

            # ── Medium tier: every ~5 min ───────────────────────────
            if not self._last_disk_pool or now - self._last_disk_pool > DEFAULT_DISK_POOL_INTERVAL:
                data.disks = await self._safe_fetch(self.client.get_disks, data.disks)
                disk_names = [d.name for d in data.disks if d.name]
                temps: dict[str, int | None] = await self._safe_fetch(
                    lambda: self.client.get_disk_temperatures(disk_names), {}
                )
                if temps:
                    updated_disks = []
                    for disk in data.disks:
                        temp = temps.get(disk.name)
                        if temp is not None and temp != disk.temperature:
                            updated_disks.append(replace(disk, temperature=temp))
                        else:
                            updated_disks.append(disk)
                    data.disks = updated_disks

                data.disk_smart = await self._safe_fetch(
                    lambda: self.client.get_disk_smart(disk_names),
                    data.disk_smart,
                )
                data.pools = await self._safe_fetch(self.client.get_pools, data.pools)
                data.network_interfaces = await self._safe_fetch(
                    self.client.get_network_interfaces, data.network_interfaces
                )
                self._last_disk_pool = now

            # ── Slow tier: every ~15 min ────────────────────────────
            if not self._last_datasets or now - self._last_datasets > DEFAULT_DATASET_INTERVAL:
                data.datasets = await self._safe_fetch(self.client.get_datasets, data.datasets)
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

            # ── Update check: every 12 hours ────────────────────────
            if (
                self._force_update_check
                or not self._last_update_check
                or now - self._last_update_check > DEFAULT_UPDATE_CHECK_INTERVAL
            ):
                data.update_info = await self._safe_fetch(
                    self.client.check_update, data.update_info
                )
                self._last_update_check = now
                self._force_update_check = False

        except TrueNASAuthenticationError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except (TrueNASConnectionError, TrueNASTimeoutError) as err:
            raise UpdateFailed(f"Communication error: {err}") from err

        return data

    def _sync_device_version(self, system_info: SystemInfo | None) -> None:
        """Push a changed TrueNAS version into the device registry.

        ``device_info`` is only read when entities are added, so after a
        TrueNAS upgrade the system device went on advertising the version it
        was set up with until the config entry was reloaded.
        """
        if system_info is None or not system_info.version:
            return
        registry = dr.async_get(self.hass)
        device = registry.async_get_device(
            identifiers={(DOMAIN, f"{self.config_entry.entry_id}_system")}
        )
        if device is not None and device.sw_version != system_info.version:
            registry.async_update_device(device.id, sw_version=system_info.version)

    @staticmethod
    def _stable_boot_time(
        current: SystemInfo | None,
        previous: SystemInfo | None,
    ) -> SystemInfo | None:
        """Hold the reported boot time still while the NAS stays up.

        When TrueNAS does not hand out a real ``boottime`` the value is derived
        from ``uptime_seconds``, which lands a second or two away from the
        previous answer on every poll. Reporting that as a new state each cycle
        would churn the recorder for no information, so anything inside
        BOOT_TIME_TOLERANCE keeps the value already on show. A reboot moves it
        by minutes or hours and comes straight through.
        """
        if current is None or previous is None or previous.boot_time is None:
            return current
        if current.boot_time is None:
            # A payload with neither boottime nor uptime_seconds says nothing
            # about when the NAS booted. Carry the known answer forward instead
            # of blanking the sensor and re-pinning to a new value next cycle.
            return replace(current, boot_time=previous.boot_time)
        drift = abs((current.boot_time - previous.boot_time).total_seconds())
        if drift < BOOT_TIME_TOLERANCE:
            return replace(current, boot_time=previous.boot_time)
        return current

    async def _safe_fetch[T](
        self,
        fetch_fn: Callable[[], Awaitable[T]],
        fallback: T,
    ) -> T:
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
