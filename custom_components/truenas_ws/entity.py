"""Base entity for the TrueNAS integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TrueNASDataUpdateCoordinator

# Group device keys — all entities of the same type go under one device
DEVICE_KEY_SYSTEM = "system"
DEVICE_KEY_APPS = "apps"
DEVICE_KEY_DISKS = "disks"
DEVICE_KEY_DATASETS = "datasets"
DEVICE_KEY_SERVICES = "services"
DEVICE_KEY_VMS = "vms"
DEVICE_KEY_REPLICATION = "replication"
DEVICE_KEY_SNAPSHOTS = "snapshot_tasks"
DEVICE_KEY_CLOUDSYNC = "cloudsync"


class TrueNASEntity(CoordinatorEntity[TrueNASDataUpdateCoordinator]):
    """Base entity for TrueNAS."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TrueNASDataUpdateCoordinator,
        description: EntityDescription,
        device_key: str,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._device_key = device_key
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{device_key}_{description.key}"
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        entry_id = self.coordinator.config_entry.entry_id
        sys_info = self.coordinator.data.system_info if self.coordinator.data else None
        hostname = sys_info.hostname if sys_info else self.coordinator.config_entry.title

        if self._device_key == DEVICE_KEY_SYSTEM:
            return DeviceInfo(
                identifiers={(DOMAIN, f"{entry_id}_system")},
                name=f"{hostname}",
                manufacturer="iXsystems",
                model="TrueNAS",
                sw_version=sys_info.version if sys_info else None,
            )

        if self._device_key == DEVICE_KEY_APPS:
            return DeviceInfo(
                identifiers={(DOMAIN, f"{entry_id}_apps")},
                name="Apps",
                manufacturer="iXsystems",
                model="Applications",
                via_device=(DOMAIN, f"{entry_id}_system"),
            )

        if self._device_key == DEVICE_KEY_DISKS:
            return DeviceInfo(
                identifiers={(DOMAIN, f"{entry_id}_disks")},
                name="Disks",
                manufacturer="iXsystems",
                model="Storage Disks",
                via_device=(DOMAIN, f"{entry_id}_system"),
            )

        if self._device_key == DEVICE_KEY_DATASETS:
            return DeviceInfo(
                identifiers={(DOMAIN, f"{entry_id}_datasets")},
                name="Datasets",
                manufacturer="iXsystems",
                model="ZFS Datasets",
                via_device=(DOMAIN, f"{entry_id}_system"),
            )

        if self._device_key.startswith("pool_"):
            pool_name = self._device_key.removeprefix("pool_")
            return DeviceInfo(
                identifiers={(DOMAIN, f"{entry_id}_pool_{pool_name}")},
                name=f"Pool: {pool_name}",
                manufacturer="iXsystems",
                model="ZFS Pool",
                via_device=(DOMAIN, f"{entry_id}_system"),
            )

        if self._device_key == DEVICE_KEY_SERVICES:
            return DeviceInfo(
                identifiers={(DOMAIN, f"{entry_id}_services")},
                name="Services",
                manufacturer="iXsystems",
                model="System Services",
                via_device=(DOMAIN, f"{entry_id}_system"),
            )

        if self._device_key == DEVICE_KEY_VMS:
            return DeviceInfo(
                identifiers={(DOMAIN, f"{entry_id}_vms")},
                name="Virtual Machines",
                manufacturer="iXsystems",
                model="VMs",
                via_device=(DOMAIN, f"{entry_id}_system"),
            )

        if self._device_key == DEVICE_KEY_REPLICATION:
            return DeviceInfo(
                identifiers={(DOMAIN, f"{entry_id}_replication")},
                name="Replication",
                manufacturer="iXsystems",
                model="Replication Tasks",
                via_device=(DOMAIN, f"{entry_id}_system"),
            )

        if self._device_key == DEVICE_KEY_SNAPSHOTS:
            return DeviceInfo(
                identifiers={(DOMAIN, f"{entry_id}_snapshot_tasks")},
                name="Snapshot Tasks",
                manufacturer="iXsystems",
                model="Periodic Snapshot Tasks",
                via_device=(DOMAIN, f"{entry_id}_system"),
            )

        if self._device_key == DEVICE_KEY_CLOUDSYNC:
            return DeviceInfo(
                identifiers={(DOMAIN, f"{entry_id}_cloudsync")},
                name="Cloud Sync",
                manufacturer="iXsystems",
                model="Cloud Sync Tasks",
                via_device=(DOMAIN, f"{entry_id}_system"),
            )

        # Fallback to system device
        return DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_system")},
            name=hostname,
        )
