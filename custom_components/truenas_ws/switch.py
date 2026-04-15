"""Switch platform for the TrueNAS integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import TrueNASConfigEntry, TrueNASDataUpdateCoordinator
from .entity import DEVICE_KEY_SERVICES, DEVICE_KEY_VMS, TrueNASEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TrueNASConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up TrueNAS switch entities."""
    coordinator = entry.runtime_data
    entities: list[SwitchEntity] = []

    # Service switches
    for service in coordinator.data.services:
        entities.append(
            TrueNASServiceSwitch(coordinator, service.service, service.id)
        )

    # VM switches
    for vm in coordinator.data.vms:
        entities.append(TrueNASVMSwitch(coordinator, vm.name, vm.id))

    # App switches
    for app in coordinator.data.apps:
        entities.append(TrueNASAppSwitch(coordinator, app.name))

    async_add_entities(entities)


class TrueNASServiceSwitch(TrueNASEntity, SwitchEntity):
    """Switch to control a TrueNAS service."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:cog"

    def __init__(
        self,
        coordinator: TrueNASDataUpdateCoordinator,
        service_name: str,
        service_id: int,
    ) -> None:
        """Initialize the switch."""
        description = EntityDescription(
            key=f"service_{service_name}",
            translation_key="service",
        )
        super().__init__(coordinator, description, DEVICE_KEY_SERVICES)
        self._service_name = service_name
        self._service_id = service_id
        self._attr_translation_placeholders = {"service_name": service_name}

    @property
    def name(self) -> str:
        """Return the name of the switch."""
        return f"{self._service_name}"

    @property
    def is_on(self) -> bool:
        """Return True if the service is running."""
        service = next(
            (
                s
                for s in self.coordinator.data.services
                if s.service == self._service_name
            ),
            None,
        )
        return service.state == "RUNNING" if service else False

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start the service."""
        await self.coordinator.client.start_service(self._service_name)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Stop the service."""
        await self.coordinator.client.stop_service(self._service_name)
        await self.coordinator.async_request_refresh()


class TrueNASVMSwitch(TrueNASEntity, SwitchEntity):
    """Switch to control a TrueNAS virtual machine."""

    _attr_icon = "mdi:monitor"

    def __init__(
        self,
        coordinator: TrueNASDataUpdateCoordinator,
        vm_name: str,
        vm_id: int,
    ) -> None:
        """Initialize the switch."""
        description = EntityDescription(
            key=f"vm_{vm_id}_power",
            translation_key="vm_power",
        )
        super().__init__(coordinator, description, DEVICE_KEY_VMS)
        self._vm_name = vm_name
        self._vm_id = vm_id

    @property
    def name(self) -> str:
        """Return the name of the switch."""
        return f"{self._vm_name}"

    @property
    def is_on(self) -> bool:
        """Return True if the VM is running."""
        vm = next(
            (v for v in self.coordinator.data.vms if v.id == self._vm_id),
            None,
        )
        return vm.status == "RUNNING" if vm else False

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start the VM."""
        await self.coordinator.client.start_vm(self._vm_id)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Stop the VM."""
        await self.coordinator.client.stop_vm(self._vm_id)
        await self.coordinator.async_request_refresh()


class TrueNASAppSwitch(TrueNASEntity, SwitchEntity):
    """Switch to control a TrueNAS application."""

    _attr_icon = "mdi:application"

    def __init__(
        self,
        coordinator: TrueNASDataUpdateCoordinator,
        app_name: str,
    ) -> None:
        """Initialize the switch."""
        description = EntityDescription(
            key=f"app_{app_name}_power",
            translation_key="app_power",
        )
        super().__init__(
            coordinator,
            description,
            f"app:{app_name}",
            device_name=app_name,
        )
        self._app_name = app_name

    @property
    def name(self) -> str:
        """Return the name of the switch."""
        return "Power"

    @property
    def is_on(self) -> bool:
        """Return True if the app is running."""
        app = next(
            (a for a in self.coordinator.data.apps if a.name == self._app_name),
            None,
        )
        if app is None:
            return False
        return app.state.upper() in ("RUNNING", "ACTIVE", "DEPLOYING", "DEPLOYED")

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start the app."""
        await self.coordinator.client.start_app(self._app_name)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Stop the app."""
        await self.coordinator.client.stop_app(self._app_name)
        await self.coordinator.async_request_refresh()
