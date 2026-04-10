"""Binary sensor platform for the TrueNAS integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import TrueNASConfigEntry, TrueNASDataUpdateCoordinator
from .entity import TrueNASEntity
from .models import TrueNASData


@dataclass(frozen=True, kw_only=True)
class TrueNASBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes a TrueNAS binary sensor entity."""

    value_fn: Callable[[TrueNASData], bool | None] = lambda _: None
    extra_attrs_fn: Callable[[TrueNASData], dict[str, Any]] | None = None


# ── System binary sensors ─────────────────────────────────────────

SYSTEM_BINARY_SENSORS: tuple[TrueNASBinarySensorEntityDescription, ...] = (
    TrueNASBinarySensorEntityDescription(
        key="system_healthy",
        translation_key="system_healthy",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:check-network",
        value_fn=lambda data: len([a for a in data.alerts if not a.dismissed and a.level in ("CRITICAL", "ERROR")]) > 0,
    ),
    TrueNASBinarySensorEntityDescription(
        key="update_available",
        translation_key="update_available",
        device_class=BinarySensorDeviceClass.UPDATE,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:update",
        value_fn=lambda data: data.update_info.available
        if data.update_info
        else None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TrueNASConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up TrueNAS binary sensor entities."""
    coordinator = entry.runtime_data
    entities: list[TrueNASBinarySensor] = []

    # System binary sensors
    for desc in SYSTEM_BINARY_SENSORS:
        entities.append(TrueNASBinarySensor(coordinator, desc, "system"))

    # Pool health
    for pool in coordinator.data.pools:
        desc = TrueNASBinarySensorEntityDescription(
            key=f"pool_{pool.name}_healthy",
            translation_key="pool_healthy",
            device_class=BinarySensorDeviceClass.PROBLEM,
            icon="mdi:database-check",
            value_fn=lambda data, _name=pool.name: not p.healthy
            if (p := next((x for x in data.pools if x.name == _name), None))
            else None,
            extra_attrs_fn=lambda data, _name=pool.name: {
                "status": p.status,
                "warning": p.warning,
            }
            if (p := next((x for x in data.pools if x.name == _name), None))
            else {},
        )
        entities.append(TrueNASBinarySensor(coordinator, desc, f"pool_{pool.name}"))

    # Disk SMART health
    for disk in coordinator.data.disks:
        desc = TrueNASBinarySensorEntityDescription(
            key=f"disk_{disk.name}_smart_healthy",
            translation_key="disk_smart_healthy",
            device_class=BinarySensorDeviceClass.PROBLEM,
            icon="mdi:harddisk",
            entity_category=EntityCategory.DIAGNOSTIC,
            value_fn=lambda data, _name=disk.name: False,  # placeholder - SMART needs separate query
        )
        entities.append(
            TrueNASBinarySensor(coordinator, desc, f"disk_{disk.name}")
        )

    async_add_entities(entities)


class TrueNASBinarySensor(TrueNASEntity, BinarySensorEntity):
    """TrueNAS binary sensor entity."""

    entity_description: TrueNASBinarySensorEntityDescription

    @property
    def is_on(self) -> bool | None:
        """Return True if the binary sensor is on."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes."""
        if self.entity_description.extra_attrs_fn:
            return self.entity_description.extra_attrs_fn(self.coordinator.data)
        return None
