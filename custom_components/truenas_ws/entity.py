"""Base entity for the TrueNAS integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TrueNASDataUpdateCoordinator


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

        if self._device_key == "system":
            return DeviceInfo(
                identifiers={(DOMAIN, entry_id)},
                name=hostname,
                manufacturer="iXsystems",
                model="TrueNAS",
                sw_version=sys_info.version if sys_info else None,
            )

        if self._device_key.startswith("pool_"):
            pool_name = self._device_key.removeprefix("pool_")
            return DeviceInfo(
                identifiers={(DOMAIN, f"{entry_id}_pool_{pool_name}")},
                name=f"Pool: {pool_name}",
                manufacturer="iXsystems",
                model="ZFS Pool",
                via_device=(DOMAIN, entry_id),
            )

        if self._device_key.startswith("disk_"):
            disk_name = self._device_key.removeprefix("disk_")
            disk = next(
                (d for d in (self.coordinator.data.disks if self.coordinator.data else [])
                 if d.name == disk_name),
                None,
            )
            return DeviceInfo(
                identifiers={(DOMAIN, f"{entry_id}_disk_{disk_name}")},
                name=f"Disk: {disk_name}",
                manufacturer=disk.model.split()[0] if disk and disk.model else None,
                model=disk.model if disk else None,
                serial_number=disk.serial if disk else None,
                via_device=(DOMAIN, entry_id),
            )

        if self._device_key.startswith("app_"):
            app_name = self._device_key.removeprefix("app_")
            return DeviceInfo(
                identifiers={(DOMAIN, f"{entry_id}_app_{app_name}")},
                name=f"App: {app_name}",
                manufacturer="iXsystems",
                model="Application",
                via_device=(DOMAIN, entry_id),
            )

        if self._device_key.startswith("vm_"):
            vm_name = self._device_key.removeprefix("vm_")
            return DeviceInfo(
                identifiers={(DOMAIN, f"{entry_id}_vm_{vm_name}")},
                name=f"VM: {vm_name}",
                manufacturer="iXsystems",
                model="Virtual Machine",
                via_device=(DOMAIN, entry_id),
            )

        return DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=hostname,
        )
