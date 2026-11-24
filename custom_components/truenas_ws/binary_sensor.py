"""Binary sensor platform for the TrueNAS integration."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# The package re-exports BinarySensorDeviceClass at runtime on every supported HA
# version, but the stubs do not declare it; const.py only gained it after 2026.8.0.
from homeassistant.components.binary_sensor import (  # type: ignore[attr-defined]
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import TrueNASConfigEntry
from .entity import DEVICE_KEY_NETWORK, DEVICE_KEY_STORAGE, DEVICE_KEY_SYSTEM, TrueNASEntity
from .models import TrueNASData

# Alert levels at or above CRITICAL.
CRITICAL_ALERT_LEVELS = frozenset({"CRITICAL", "ALERT", "EMERGENCY"})


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
        name="System problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:check-network",
        value_fn=lambda data: any(
            not a.dismissed and a.level in ("CRITICAL", "ERROR") for a in data.alerts
        ),
    ),
    TrueNASBinarySensorEntityDescription(
        key="update_available",
        translation_key="update_available",
        name="Update available",
        device_class=BinarySensorDeviceClass.UPDATE,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:update",
        value_fn=lambda data: data.update_info.available if data.update_info else None,
    ),
    TrueNASBinarySensorEntityDescription(
        key="reboot_required",
        translation_key="reboot_required",
        name="Reboot required",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:restart-alert",
        value_fn=lambda data: (
            bool(data.reboot_required_reasons) if data.reboot_required_reasons is not None else None
        ),
        extra_attrs_fn=lambda data: {"reasons": data.reboot_required_reasons or []},
    ),
    TrueNASBinarySensorEntityDescription(
        key="critical_alerts",
        translation_key="critical_alerts",
        name="Critical alerts",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:alert-octagram",
        value_fn=lambda data: any(
            not a.dismissed and a.level in CRITICAL_ALERT_LEVELS for a in data.alerts
        ),
        extra_attrs_fn=lambda data: {
            "messages": [
                a.message[:200]
                for a in data.alerts
                if not a.dismissed and a.level in CRITICAL_ALERT_LEVELS
            ][:5]
        },
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
        entities.append(TrueNASBinarySensor(coordinator, desc, DEVICE_KEY_SYSTEM))

    # Pool health
    for pool in coordinator.data.pools:
        entities.append(
            TrueNASBinarySensor(coordinator, _pool_problem_desc(pool.name), DEVICE_KEY_STORAGE)
        )

    # Disk SMART health
    for disk in coordinator.data.disks:
        entities.append(
            TrueNASBinarySensor(coordinator, _disk_smart_desc(disk.name), DEVICE_KEY_STORAGE)
        )

    # Network link per interface
    for iface in coordinator.data.network_interfaces:
        entities.append(
            TrueNASBinarySensor(coordinator, _interface_link_desc(iface.name), DEVICE_KEY_NETWORK)
        )

    async_add_entities(entities)


def _interface_link_desc(iface_name: str) -> TrueNASBinarySensorEntityDescription:
    """Create the link binary sensor description for a network interface."""

    def _find(data: TrueNASData) -> Any:
        return next((i for i in data.network_interfaces if i.name == iface_name), None)

    return TrueNASBinarySensorEntityDescription(
        key=f"interface_{iface_name}_link",
        name=f"{iface_name} link",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        icon="mdi:ethernet",
        value_fn=lambda data: i.state == "LINK_STATE_UP" if (i := _find(data)) else None,
        extra_attrs_fn=lambda data: (
            {
                "description": i.description,
                "mtu": i.mtu,
                "link_address": i.link_address,
            }
            if (i := _find(data))
            else {}
        ),
    )


def _pool_problem_desc(pool_name: str) -> TrueNASBinarySensorEntityDescription:
    """Create the problem binary sensor description for a pool."""

    def _find_pool(data: TrueNASData) -> Any:
        return next((x for x in data.pools if x.name == pool_name), None)

    return TrueNASBinarySensorEntityDescription(
        key=f"pool_{pool_name}_healthy",
        name=f"{pool_name} problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:database-check",
        value_fn=lambda data: not p.healthy if (p := _find_pool(data)) else None,
        extra_attrs_fn=lambda data: (
            {
                "status": p.status,
                "warning": p.warning,
            }
            if (p := _find_pool(data))
            else {}
        ),
    )


def _disk_smart_desc(disk_name: str) -> TrueNASBinarySensorEntityDescription:
    """Create the problem binary sensor description for a disk.

    Prefers SMART self-test verdicts where the API still exists (TrueNAS
    removed the entire smart.* namespace in 25.10). Otherwise falls back
    to active alerts that reference the disk, so the sensor reports OK
    when TrueNAS itself reports no issues.
    """
    name_re = re.compile(rf"\b{re.escape(disk_name)}\b")

    def _value(data: TrueNASData) -> bool:
        smart = data.disk_smart.get(disk_name)
        if smart is not None and smart.passed is not None:
            return not smart.passed
        return any(name_re.search(a.message) for a in data.alerts if not a.dismissed)

    return TrueNASBinarySensorEntityDescription(
        key=f"disk_{disk_name}_smart_healthy",
        name=f"{disk_name} problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:harddisk",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_value,
    )


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
