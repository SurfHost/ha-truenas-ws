"""Update platform for the TrueNAS integration."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.components import persistent_notification
from homeassistant.components.update import (
    UpdateEntity,
    UpdateEntityDescription,
    UpdateEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import TrueNASConfigEntry, TrueNASDataUpdateCoordinator
from .entity import DEVICE_KEY_APPS, DEVICE_KEY_SYSTEM, TrueNASEntity
from .errors import TrueNASError, TrueNASJobError
from .models import AppInfo

_LOGGER = logging.getLogger(__name__)

# Seconds to wait before each recovery attempt after an upgrade hit a registry
# pull rate limit: 5, 10 and 20 minutes.
RATE_LIMIT_RETRY_DELAYS: tuple[float, ...] = (300.0, 600.0, 1200.0)


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
        if update and update.available and update.version and update.version != installed:
            return update.version
        return installed

    @property
    def in_progress(self) -> bool:
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
        # _installing stays True > cleared automatically when the
        # coordinator reconnects after the reboot and installed_version
        # matches latest_version.


class TrueNASAppUpdateEntity(TrueNASEntity, UpdateEntity):
    """Update entity for a TrueNAS application.

    Uses ``has_entity_name = False`` with an explicit name so the HA
    Updates dashboard shows the app name directly instead of prefixing
    the shared "Apps" device name.
    """

    _attr_has_entity_name = False
    _attr_supported_features = UpdateEntityFeature.INSTALL | UpdateEntityFeature.PROGRESS
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
        self._recovery_task: asyncio.Task[None] | None = None

    @property
    def _recovering(self) -> bool:
        """Return True while a rate-limit recovery is pending or running."""
        return self._recovery_task is not None and not self._recovery_task.done()

    @property
    def _notification_id(self) -> str:
        return f"truenas_ws_{self.coordinator.config_entry.entry_id}_{self._app_name}_upgrade"

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
    def in_progress(self) -> bool:
        """Return True while the app is being upgraded."""
        if self._recovering:
            # A failed upgrade already reports upgrade_available = False, so
            # the check below would clear the spinner too early.
            return True
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
        """Upgrade the application and wait for the TrueNAS job to finish.

        When the upgrade fails on a registry pull rate limit, TrueNAS has
        already switched the app to the new version but leaves it stopped.
        That case is not raised: a background task pulls the images again
        later and starts the app. Any other failure is raised.
        """
        if self._recovering:
            raise HomeAssistantError(f"{self._app_name} is still recovering from a failed upgrade")
        self._installing = True
        self.async_write_ha_state()
        try:
            await self.coordinator.client.upgrade_app(self._app_name)
        except TrueNASJobError as err:
            if not err.rate_limited:
                self._installing = False
                self.async_write_ha_state()
                raise
            _LOGGER.warning(
                "Upgrade of %s hit a registry pull rate limit; it will be retried "
                "in the background: %s",
                self._app_name,
                err.error,
            )
            self._recovery_task = self.coordinator.config_entry.async_create_background_task(
                self.hass,
                self._async_recover_from_rate_limit(),
                f"truenas_ws recover {self._app_name}",
            )
            self.async_write_ha_state()
            return
        except Exception:
            self._installing = False
            self.async_write_ha_state()
            raise
        persistent_notification.async_dismiss(self.hass, self._notification_id)
        # Trigger a refresh so the spinner clears when app.query reports
        # upgrade_available = False.
        await self.coordinator.async_request_refresh()

    async def _async_recover_from_rate_limit(self) -> None:
        """Pull the app's images again after a delay and start the app."""
        client = self.coordinator.client
        last_error = "pull rate limit"
        try:
            for attempt, delay in enumerate(RATE_LIMIT_RETRY_DELAYS, start=1):
                await asyncio.sleep(delay)
                try:
                    if await client.get_app_state(self._app_name) == "RUNNING":
                        _LOGGER.info("%s is running again", self._app_name)
                        break
                    await client.pull_app_images(self._app_name)
                    await client.start_app(self._app_name, wait=True)
                except TrueNASJobError as err:
                    last_error = err.error
                    if not err.rate_limited:
                        _LOGGER.error("Recovering %s failed: %s", self._app_name, err)
                        self._notify_failure(last_error)
                        return
                    _LOGGER.warning(
                        "Recovering %s: attempt %d of %d still rate limited",
                        self._app_name,
                        attempt,
                        len(RATE_LIMIT_RETRY_DELAYS),
                    )
                except TrueNASError as err:
                    last_error = str(err)
                    _LOGGER.warning(
                        "Recovering %s: attempt %d of %d failed: %s",
                        self._app_name,
                        attempt,
                        len(RATE_LIMIT_RETRY_DELAYS),
                        err,
                    )
                else:
                    _LOGGER.info(
                        "%s started after a rate-limited upgrade (attempt %d)",
                        self._app_name,
                        attempt,
                    )
                    break
            else:
                self._notify_failure(last_error)
                return
            persistent_notification.async_dismiss(self.hass, self._notification_id)
        except asyncio.CancelledError:
            # Integration unloading; the entity is going away, so don't write state.
            self._installing = False
            raise
        finally:
            self._recovery_task = None
        self._installing = False
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    def _notify_failure(self, error: str) -> None:
        """Tell the user the app stayed stopped after a failed upgrade."""
        self._installing = False
        self._recovery_task = None
        self.async_write_ha_state()
        persistent_notification.async_create(
            self.hass,
            f"The upgrade of TrueNAS app **{self._app_name}** failed and the app "
            f"is stopped. Retrying did not help.\n\nLast error: {error}\n\n"
            "Start the app in TrueNAS once the registry allows pulls again.",
            title=f"TrueNAS: {self._app_name} is stopped",
            notification_id=self._notification_id,
        )
