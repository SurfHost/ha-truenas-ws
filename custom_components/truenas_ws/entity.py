"""Base entity for the TrueNAS integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TrueNASConfigEntry, TrueNASDataUpdateCoordinator
from .models import SystemInfo

# Group device keys > all entities of the same type go under one device
DEVICE_KEY_SYSTEM = "system"
DEVICE_KEY_STORAGE = "storage"
DEVICE_KEY_APPS = "apps"
DEVICE_KEY_SERVICES = "services"
DEVICE_KEY_VMS = "vms"
DEVICE_KEY_TASKS = "tasks"


# Devices grouped under the NAS: device key > (name, model). The identifier is
# f"{entry_id}_{key}", so the keys must not change or existing devices are lost.
_SUB_DEVICES: dict[str, tuple[str, str]] = {
    DEVICE_KEY_STORAGE: ("Storage", "ZFS Storage"),
    DEVICE_KEY_APPS: ("Apps", "Applications"),
    DEVICE_KEY_SERVICES: ("Services", "System Services"),
    DEVICE_KEY_VMS: ("Virtual Machines", "VMs"),
    DEVICE_KEY_TASKS: ("Tasks", "Scheduled Tasks"),
}


def system_device_info(entry: TrueNASConfigEntry, system_info: SystemInfo | None) -> DeviceInfo:
    """Return the device info of the NAS itself, the parent of all other devices.

    async_setup_entry registers the device with this before the platforms load,
    and the system entities report it again, so both must agree on every field.
    """
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_system")},
        name=system_info.hostname if system_info else entry.title,
        manufacturer="iXsystems",
        model="TrueNAS",
        sw_version=system_info.version if system_info else None,
    )


class TrueNASEntity(CoordinatorEntity[TrueNASDataUpdateCoordinator]):
    """Base entity for TrueNAS."""

    # The homeassistant-stubs declare this as Incomplete (Any); re-declare
    # so subclasses get proper typing on self.coordinator.
    coordinator: TrueNASDataUpdateCoordinator

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
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{device_key}_{description.key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        entry = self.coordinator.config_entry
        entry_id = entry.entry_id
        sys_info = self.coordinator.data.system_info if self.coordinator.data else None
        # The registry id of the NAS device, registered in async_setup_entry before
        # any platform loads. via_device_id needs that id, not an identifier tuple.
        parent_id = self.coordinator.system_device_id

        if self._device_key == DEVICE_KEY_SYSTEM:
            return system_device_info(entry, sys_info)

        if (sub_device := _SUB_DEVICES.get(self._device_key)) is not None:
            name, model = sub_device
            info = DeviceInfo(
                identifiers={(DOMAIN, f"{entry_id}_{self._device_key}")},
                name=name,
                manufacturer="iXsystems",
                model=model,
            )
            # Always set by the time entities exist; the guard only keeps a
            # missing id from being passed as an explicit "no parent".
            if parent_id is not None:
                info["via_device_id"] = parent_id
            return info

        # Fallback to system device
        return system_device_info(entry, sys_info)
