"""Base entity for the TrueNAS integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TrueNASDataUpdateCoordinator

# Group device keys — all entities of the same type go under one device
DEVICE_KEY_SYSTEM = "system"
DEVICE_KEY_STORAGE = "storage"
DEVICE_KEY_APPS = "apps"
DEVICE_KEY_SERVICES = "services"
DEVICE_KEY_VMS = "vms"
DEVICE_KEY_TASKS = "tasks"


class TrueNASEntity(CoordinatorEntity[TrueNASDataUpdateCoordinator]):
    """Base entity for TrueNAS."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TrueNASDataUpdateCoordinator,
        description: EntityDescription,
        device_key: str,
        *,
        device_name: str | None = None,
    ) -> None:
        """Initialize the entity.

        ``device_key`` is a stable identifier for the device this entity
        belongs to (e.g. ``system``, ``apps``, or ``app:plex``). ``device_name``
        overrides the default device name when the device key is dynamic.
        """
        super().__init__(coordinator)
        self.entity_description = description
        self._device_key = device_key
        self._device_name_override = device_name
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{device_key}_{description.key}"
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        entry_id = self.coordinator.config_entry.entry_id
        sys_info = self.coordinator.data.system_info if self.coordinator.data else None
        hostname = sys_info.hostname if sys_info else self.coordinator.config_entry.title

        # Per-app devices (device_key format: "app:{app_name}")
        if self._device_key.startswith("app:"):
            app_name = self._device_key.split(":", 1)[1]
            return DeviceInfo(
                identifiers={(DOMAIN, f"{entry_id}_app_{app_name}")},
                name=self._device_name_override or app_name,
                manufacturer="iXsystems",
                model="TrueNAS App",
                via_device=(DOMAIN, f"{entry_id}_apps"),
            )

        if self._device_key == DEVICE_KEY_SYSTEM:
            return DeviceInfo(
                identifiers={(DOMAIN, f"{entry_id}_system")},
                name=f"{hostname}",
                manufacturer="iXsystems",
                model="TrueNAS",
                sw_version=sys_info.version if sys_info else None,
            )

        if self._device_key == DEVICE_KEY_STORAGE:
            return DeviceInfo(
                identifiers={(DOMAIN, f"{entry_id}_storage")},
                name="Storage",
                manufacturer="iXsystems",
                model="ZFS Storage",
                via_device=(DOMAIN, f"{entry_id}_system"),
            )

        if self._device_key == DEVICE_KEY_APPS:
            return DeviceInfo(
                identifiers={(DOMAIN, f"{entry_id}_apps")},
                name="Apps",
                manufacturer="iXsystems",
                model="Applications",
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

        if self._device_key == DEVICE_KEY_TASKS:
            return DeviceInfo(
                identifiers={(DOMAIN, f"{entry_id}_tasks")},
                name="Tasks",
                manufacturer="iXsystems",
                model="Scheduled Tasks",
                via_device=(DOMAIN, f"{entry_id}_system"),
            )

        # Fallback to system device
        return DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_system")},
            name=hostname,
        )
