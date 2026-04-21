"""Update platform for the TrueNAS integration."""

from __future__ import annotations

import logging

from homeassistant.components.update import (
    UpdateEntity,
    UpdateEntityDescription,
    UpdateEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import TrueNASConfigEntry, TrueNASDataUpdateCoordinator
from .entity import DEVICE_KEY_APPS, DEVICE_KEY_SYSTEM, TrueNASEntity
from .models import AppInfo

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TrueNASConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up TrueNAS update entities."""
    coordinator = entry.runtime_data
    entities: list[UpdateEntity] = [TrueNASSystemUpdateEntity(coordinator)]

    for app in coordinator.data.apps:
        entities.append(TrueNASAppUpdateEntity(coordinator, app.name))

    async_add_entities(entities)


class TrueNASSystemUpdateEntity(TrueNASEntity, UpdateEntity):
    """Update entity for TrueNAS system updates."""

    _attr_supported_features = (
        UpdateEntityFeature.INSTALL
        | UpdateEntityFeature.PROGRESS
        | UpdateEntityFeature.RELEASE_NOTES
    )

    def __init__(self, coordinator: TrueNASDataUpdateCoordinator) -> None:
        """Initialize the update entity."""
        description = UpdateEntityDescription(
            key="system_update",
            name="System update",
        )
        super().__init__(coordinator, description, DEVICE_KEY_SYSTEM)
        self._installing = False

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
        installed = self.installed_version
        if (
            update
            and update.available
            and update.version
            and update.version != installed
        ):
            return update.version
        return installed

    @property
    def in_progress(self) -> bool | int:
        """Return True while the system update is being installed."""
        if self._installing:
            # Auto-clear when the installed version catches up
            if self.installed_version == self.latest_version:
                self._installing = False
                return False
            return True
        return False

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        """Surface the active update profile and train."""
        update = self.coordinator.data.update_info
        if update is None:
            return None
        attrs: dict[str, str] = {}
        if update.profile:
            attrs["profile"] = update.profile
        if update.train:
            attrs["train"] = update.train
        return attrs or None

    async def async_release_notes(self) -> str | None:
        """Return the release notes."""
        update = self.coordinator.data.update_info
        if update and update.changelog:
            return update.changelog
        return None

    async def async_install(
        self,
        version: str | None,
        backup: bool,
        **kwargs: object,
    ) -> None:
        """Install the pending system update."""
        self._installing = True
        self.async_write_ha_state()
        try:
            await self.coordinator.client.install_system_update()
        except Exception:
            self._installing = False
            self.async_write_ha_state()
            raise
        # _installing stays True — cleared automatically when the
        # coordinator reconnects after the reboot and installed_version
        # matches latest_version.


class TrueNASAppUpdateEntity(TrueNASEntity, UpdateEntity):
    """Update entity for a TrueNAS application.

    Uses ``has_entity_name = False`` with an explicit name so the HA
    Updates dashboard shows the app name directly instead of prefixing
    the shared "Apps" device name.
    """

    _attr_has_entity_name = False
    _attr_supported_features = (
        UpdateEntityFeature.INSTALL | UpdateEntityFeature.PROGRESS
    )
    _attr_icon = "mdi:application-cog"

    def __init__(
        self,
        coordinator: TrueNASDataUpdateCoordinator,
        app_name: str,
    ) -> None:
        """Initialize the update entity."""
        description = UpdateEntityDescription(
            key=f"app_{app_name}_update",
        )
        super().__init__(coordinator, description, DEVICE_KEY_APPS)
        self._app_name = app_name
        self._attr_name = f"{app_name} update"
        self._installing = False

    def _find_app(self) -> AppInfo | None:
        """Return the current app data from the coordinator, if present."""
        return next(
            (a for a in self.coordinator.data.apps if a.name == self._app_name),
            None,
        )

    @property
    def installed_version(self) -> str | None:
        """Return the installed version."""
        app = self._find_app()
        if app is None:
            return None
        return app.human_version or app.version or None

    @property
    def latest_version(self) -> str | None:
        """Return the latest version."""
        app = self._find_app()
        if app is None:
            return None
        if app.upgrade_available:
            return app.latest_version or "available"
        return self.installed_version

    @property
    def in_progress(self) -> bool | int:
        """Return True while the app is being upgraded."""
        if self._installing:
            # Auto-clear once TrueNAS reports upgrade_available = False
            app = self._find_app()
            if app is not None and not app.upgrade_available:
                self._installing = False
                return False
            return True
        return False

    async def async_install(
        self,
        version: str | None,
        backup: bool,
        **kwargs: object,
    ) -> None:
        """Upgrade the application to the latest version."""
        self._installing = True
        self.async_write_ha_state()
        try:
            await self.coordinator.client.upgrade_app(self._app_name)
        except Exception:
            self._installing = False
            self.async_write_ha_state()
            raise
        # Trigger a refresh so the spinner clears when app.query reports
        # upgrade_available = False.
        await self.coordinator.async_request_refresh()
