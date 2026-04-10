"""Update platform for the TrueNAS integration."""

from __future__ import annotations

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import TrueNASConfigEntry, TrueNASDataUpdateCoordinator
from .entity import DEVICE_KEY_SYSTEM, TrueNASEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TrueNASConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up TrueNAS update entity."""
    coordinator = entry.runtime_data
    async_add_entities([TrueNASUpdateEntity(coordinator)])


class TrueNASUpdateEntity(TrueNASEntity, UpdateEntity):
    """Update entity for TrueNAS system updates."""

    _attr_supported_features = UpdateEntityFeature.RELEASE_NOTES

    def __init__(self, coordinator: TrueNASDataUpdateCoordinator) -> None:
        """Initialize the update entity."""
        description = EntityDescription(
            key="system_update",
            translation_key="system_update",
        )
        super().__init__(coordinator, description, DEVICE_KEY_SYSTEM)

    @property
    def name(self) -> str:
        """Return the name."""
        return "System update"

    @property
    def installed_version(self) -> str | None:
        """Return the installed version."""
        if self.coordinator.data.system_info:
            return self.coordinator.data.system_info.version
        return None

    @property
    def latest_version(self) -> str | None:
        """Return the latest version."""
        update = self.coordinator.data.update_info
        if update and update.available and update.version:
            return update.version
        return self.installed_version

    async def async_release_notes(self) -> str | None:
        """Return the release notes."""
        update = self.coordinator.data.update_info
        if update and update.changelog:
            return update.changelog
        return None
