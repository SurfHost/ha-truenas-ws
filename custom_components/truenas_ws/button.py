"""Button platform for the TrueNAS integration."""

from __future__ import annotations

# The package re-exports ButtonDeviceClass at runtime on every supported HA version,
# but the stubs do not declare it; const.py only gained it after 2026.8.0.
from homeassistant.components.button import (  # type: ignore[attr-defined]
    ButtonDeviceClass,
    ButtonEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import TrueNASConfigEntry, TrueNASDataUpdateCoordinator
from .entity import DEVICE_KEY_STORAGE, DEVICE_KEY_SYSTEM, TrueNASEntity


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

    # Scrub buttons per data pool. The boot pool (id 0) is scrubbed through
    # boot.scrub, which pool.scrub.scrub does not handle.
    for pool in coordinator.data.pools:
        if pool.id:
            for action in SCRUB_ACTIONS:
                entities.append(TrueNASScrubButton(coordinator, pool.name, action))

    # Dataset snapshot buttons
    for dataset in coordinator.data.datasets:
        if dataset.type == "FILESYSTEM":
            entities.append(TrueNASSnapshotButton(coordinator, dataset.id))

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
        super().__init__(coordinator, description, DEVICE_KEY_SYSTEM)

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
        super().__init__(coordinator, description, DEVICE_KEY_SYSTEM)

    async def async_press(self) -> None:
        """Shutdown the system."""
        await self.coordinator.client.shutdown()


# pool.scrub.scrub action > (label, icon). START also resumes a paused scrub.
SCRUB_ACTIONS: dict[str, tuple[str, str]] = {
    "START": ("start scrub", "mdi:play"),
    "PAUSE": ("pause scrub", "mdi:pause"),
    "STOP": ("stop scrub", "mdi:stop"),
}


class TrueNASScrubButton(TrueNASEntity, ButtonEntity):
    """Button to start (or resume), pause or stop a pool scrub."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: TrueNASDataUpdateCoordinator,
        pool_name: str,
        action: str,
    ) -> None:
        """Initialize the button."""
        label, icon = SCRUB_ACTIONS[action]
        description = EntityDescription(key=f"pool_{pool_name}_scrub_{action.lower()}")
        super().__init__(coordinator, description, DEVICE_KEY_STORAGE)
        self._pool_name = pool_name
        self._action = action
        self._attr_name = f"{pool_name} {label}"
        self._attr_icon = icon

    async def async_press(self) -> None:
        """Send the scrub action and refresh so the scrub sensors follow."""
        await self.coordinator.client.scrub_pool(self._pool_name, self._action)
        await self.coordinator.async_request_refresh()


class TrueNASSnapshotButton(TrueNASEntity, ButtonEntity):
    """Button to create a ZFS snapshot."""

    _attr_icon = "mdi:camera"
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: TrueNASDataUpdateCoordinator,
        dataset_id: str,
    ) -> None:
        """Initialize the button."""
        safe_id = dataset_id.replace("/", "_")
        description = EntityDescription(
            key=f"snapshot_{safe_id}",
            translation_key="create_snapshot",
        )
        super().__init__(coordinator, description, DEVICE_KEY_STORAGE)
        self._dataset_id = dataset_id

    @property
    def name(self) -> str:
        """Return the name."""
        return f"Snapshot: {self._dataset_id}"

    async def async_press(self) -> None:
        """Create a snapshot."""
        timestamp = dt_util.now().strftime("%Y%m%d-%H%M%S")
        name = f"ha-snapshot-{timestamp}"
        await self.coordinator.client.create_snapshot(self._dataset_id, name)
