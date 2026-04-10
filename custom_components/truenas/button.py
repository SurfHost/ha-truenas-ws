"""Button platform for the TrueNAS integration."""

from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import TrueNASConfigEntry, TrueNASDataUpdateCoordinator
from .entity import TrueNASEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TrueNASConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up TrueNAS button entities."""
    coordinator = entry.runtime_data
    entities: list[ButtonEntity] = []

    # System buttons
    entities.append(TrueNASRebootButton(coordinator))
    entities.append(TrueNASShutdownButton(coordinator))

    # Dataset snapshot buttons
    for dataset in coordinator.data.datasets:
        if dataset.type == "FILESYSTEM":
            entities.append(
                TrueNASSnapshotButton(coordinator, dataset.id, dataset.pool)
            )

    async_add_entities(entities)


class TrueNASRebootButton(TrueNASEntity, ButtonEntity):
    """Button to reboot TrueNAS."""

    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:restart"

    def __init__(self, coordinator: TrueNASDataUpdateCoordinator) -> None:
        """Initialize the button."""
        description = EntityDescription(
            key="system_reboot",
            translation_key="system_reboot",
        )
        super().__init__(coordinator, description, "system")

    @property
    def name(self) -> str:
        """Return the name."""
        return "Reboot"

    async def async_press(self) -> None:
        """Reboot the system."""
        await self.coordinator.client.reboot()


class TrueNASShutdownButton(TrueNASEntity, ButtonEntity):
    """Button to shutdown TrueNAS."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:power"

    def __init__(self, coordinator: TrueNASDataUpdateCoordinator) -> None:
        """Initialize the button."""
        description = EntityDescription(
            key="system_shutdown",
            translation_key="system_shutdown",
        )
        super().__init__(coordinator, description, "system")

    @property
    def name(self) -> str:
        """Return the name."""
        return "Shutdown"

    async def async_press(self) -> None:
        """Shutdown the system."""
        await self.coordinator.client.shutdown()


class TrueNASSnapshotButton(TrueNASEntity, ButtonEntity):
    """Button to create a ZFS snapshot."""

    _attr_icon = "mdi:camera"

    def __init__(
        self,
        coordinator: TrueNASDataUpdateCoordinator,
        dataset_id: str,
        pool_name: str,
    ) -> None:
        """Initialize the button."""
        safe_id = dataset_id.replace("/", "_")
        description = EntityDescription(
            key=f"snapshot_{safe_id}",
            translation_key="create_snapshot",
        )
        super().__init__(coordinator, description, f"pool_{pool_name}")
        self._dataset_id = dataset_id

    @property
    def name(self) -> str:
        """Return the name."""
        return f"Snapshot: {self._dataset_id}"

    async def async_press(self) -> None:
        """Create a snapshot."""
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        name = f"ha-snapshot-{timestamp}"
        await self.coordinator.client.create_snapshot(self._dataset_id, name)
