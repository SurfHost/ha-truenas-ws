"""Sensor platform for the TrueNAS integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfInformation,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .coordinator import TrueNASConfigEntry, TrueNASDataUpdateCoordinator
from .entity import (
    DEVICE_KEY_APPS,
    DEVICE_KEY_CLOUDSYNC,
    DEVICE_KEY_REPLICATION,
    DEVICE_KEY_SNAPSHOTS,
    DEVICE_KEY_STORAGE,
    DEVICE_KEY_SYSTEM,
    DEVICE_KEY_VMS,
    TrueNASEntity,
)
from .models import TrueNASData


@dataclass(frozen=True, kw_only=True)
class TrueNASSensorEntityDescription(SensorEntityDescription):
    """Describes a TrueNAS sensor entity."""

    value_fn: Callable[[TrueNASData], StateType | datetime] = lambda _: None
    extra_attrs_fn: Callable[[TrueNASData], dict[str, Any]] | None = None


# ── System sensors ────────────────────────────────────────────────

SYSTEM_SENSORS: tuple[TrueNASSensorEntityDescription, ...] = (
    TrueNASSensorEntityDescription(
        key="cpu_usage",
        translation_key="cpu_usage",
        name="CPU usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:cpu-64-bit",
        value_fn=lambda data: round(data.system_stats.cpu_usage, 1)
        if data.system_stats
        else None,
    ),
    TrueNASSensorEntityDescription(
        key="cpu_temperature",
        translation_key="cpu_temperature",
        name="CPU temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer",
        value_fn=lambda data: data.system_stats.cpu_temperature
        if data.system_stats and data.system_stats.cpu_temperature is not None
        else None,
    ),
    TrueNASSensorEntityDescription(
        key="memory_usage_percent",
        translation_key="memory_usage_percent",
        name="Memory usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:memory",
        value_fn=lambda data: data.system_stats.memory_usage_percent
        if data.system_stats and data.system_stats.memory_usage_percent > 0
        else None,
    ),
    TrueNASSensorEntityDescription(
        key="memory_used",
        translation_key="memory_used",
        name="Memory used",
        native_unit_of_measurement=UnitOfInformation.GIBIBYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:memory",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: round(data.system_stats.memory_used_bytes / (1024**3), 2)
        if data.system_stats and data.system_stats.memory_used_bytes > 0
        else None,
    ),
    TrueNASSensorEntityDescription(
        key="memory_free",
        translation_key="memory_free",
        name="Memory free",
        native_unit_of_measurement=UnitOfInformation.GIBIBYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:memory",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: round(data.system_stats.memory_free_bytes / (1024**3), 2)
        if data.system_stats and data.system_stats.memory_free_bytes > 0
        else None,
    ),
    TrueNASSensorEntityDescription(
        key="load_avg_1",
        translation_key="load_avg_1",
        name="Load average (1 min)",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:gauge",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.system_info.load_avg_1
        if data.system_info
        else None,
    ),
    TrueNASSensorEntityDescription(
        key="load_avg_5",
        translation_key="load_avg_5",
        name="Load average (5 min)",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:gauge",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.system_info.load_avg_5
        if data.system_info
        else None,
    ),
    TrueNASSensorEntityDescription(
        key="load_avg_15",
        translation_key="load_avg_15",
        name="Load average (15 min)",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:gauge",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.system_info.load_avg_15
        if data.system_info
        else None,
    ),
    TrueNASSensorEntityDescription(
        key="uptime",
        translation_key="uptime",
        name="Uptime",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-outline",
        value_fn=lambda data: (
            datetime.now(tz=UTC) - timedelta(seconds=data.system_info.uptime_seconds)
        )
        if data.system_info and data.system_info.uptime_seconds > 0
        else None,
    ),
    TrueNASSensorEntityDescription(
        key="arc_size",
        translation_key="arc_size",
        name="ARC size",
        native_unit_of_measurement=UnitOfInformation.GIBIBYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:database",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: round(data.system_stats.arc_size / (1024**3), 2)
        if data.system_stats and data.system_stats.arc_size > 0
        else None,
    ),
    TrueNASSensorEntityDescription(
        key="arc_hit_ratio",
        translation_key="arc_hit_ratio",
        name="ARC hit ratio",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:bullseye-arrow",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.system_stats.arc_hit_ratio
        if data.system_stats and data.system_stats.arc_hit_ratio > 0
        else None,
    ),
    TrueNASSensorEntityDescription(
        key="alerts",
        translation_key="alerts",
        name="Active alerts",
        icon="mdi:alert-circle",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: len([a for a in data.alerts if not a.dismissed]),
        extra_attrs_fn=lambda data: {
            "alerts": [
                {"level": a.level, "message": a.message}
                for a in data.alerts
                if not a.dismissed
            ]
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TrueNASConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up TrueNAS sensor entities."""
    coordinator = entry.runtime_data
    entities: list[TrueNASSensor] = []

    # System sensors
    for desc in SYSTEM_SENSORS:
        entities.append(TrueNASSensor(coordinator, desc, DEVICE_KEY_SYSTEM))

    # Pool sensors
    for pool in coordinator.data.pools:
        for desc in _pool_sensors(pool.name):
            entities.append(TrueNASSensor(coordinator, desc, DEVICE_KEY_STORAGE))

    # Disk sensors
    for disk in coordinator.data.disks:
        for desc in _disk_sensors(disk.name):
            entities.append(TrueNASSensor(coordinator, desc, DEVICE_KEY_STORAGE))

    # Dataset sensors (only enable top-level datasets by default, depth <= 1)
    for dataset in coordinator.data.datasets:
        depth = dataset.id.count("/")
        enabled = depth <= 1  # e.g. "nvme" (0) and "nvme/Docker" (1)
        for desc in _dataset_sensors(dataset.id, enabled_default=enabled):
            entities.append(TrueNASSensor(coordinator, desc, DEVICE_KEY_STORAGE))

    # Network interface sensors
    for iface in coordinator.data.network_interfaces:
        for desc in _network_sensors(iface.name):
            entities.append(TrueNASSensor(coordinator, desc, DEVICE_KEY_SYSTEM))

    # App sensors
    for app in coordinator.data.apps:
        for desc in _app_sensors(app.name):
            entities.append(TrueNASSensor(coordinator, desc, DEVICE_KEY_APPS))

    # VM sensors
    for vm in coordinator.data.vms:
        for desc in _vm_sensors(vm.name, vm.id):
            entities.append(TrueNASSensor(coordinator, desc, DEVICE_KEY_VMS))

    # Task sensors
    for task in coordinator.data.replication_tasks:
        for desc in _replication_sensors(task.id, task.name):
            entities.append(TrueNASSensor(coordinator, desc, DEVICE_KEY_REPLICATION))

    for task in coordinator.data.snapshot_tasks:
        for desc in _snapshot_task_sensors(task.id, task.dataset):
            entities.append(TrueNASSensor(coordinator, desc, DEVICE_KEY_SNAPSHOTS))

    for task in coordinator.data.cloud_sync_tasks:
        for desc in _cloudsync_sensors(task.id, task.description):
            entities.append(TrueNASSensor(coordinator, desc, DEVICE_KEY_CLOUDSYNC))

    async_add_entities(entities)


class TrueNASSensor(TrueNASEntity, SensorEntity):
    """TrueNAS sensor entity."""

    entity_description: TrueNASSensorEntityDescription

    @property
    def native_value(self) -> StateType | datetime:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes."""
        if self.entity_description.extra_attrs_fn:
            return self.entity_description.extra_attrs_fn(self.coordinator.data)
        return None


# ── Per-resource sensor description factories ─────────────────────


def _pool_sensors(pool_name: str) -> tuple[TrueNASSensorEntityDescription, ...]:
    """Create sensor descriptions for a pool."""

    def _find_pool(data: TrueNASData) -> Any:
        return next((p for p in data.pools if p.name == pool_name), None)

    return (
        TrueNASSensorEntityDescription(
            key=f"pool_{pool_name}_status",
            name=f"Pool {pool_name} status",
            icon="mdi:database",
            value_fn=lambda data, _p=pool_name: (
                p.status if (p := _find_pool(data)) else None
            ),
            extra_attrs_fn=lambda data, _p=pool_name: {
                "scan_state": p.scan_state,
                "scan_percentage": p.scan_percentage,
                "autotrim": p.autotrim,
            }
            if (p := _find_pool(data))
            else {},
        ),
        TrueNASSensorEntityDescription(
            key=f"pool_{pool_name}_used",
            name=f"Pool {pool_name} used",
            native_unit_of_measurement=UnitOfInformation.GIBIBYTES,
            device_class=SensorDeviceClass.DATA_SIZE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=2,
            icon="mdi:database",
            value_fn=lambda data, _p=pool_name: round(p.allocated / (1024**3), 2)
            if (p := _find_pool(data))
            else None,
        ),
        TrueNASSensorEntityDescription(
            key=f"pool_{pool_name}_free",
            name=f"Pool {pool_name} free",
            native_unit_of_measurement=UnitOfInformation.GIBIBYTES,
            device_class=SensorDeviceClass.DATA_SIZE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=2,
            icon="mdi:database",
            value_fn=lambda data, _p=pool_name: round(p.free / (1024**3), 2)
            if (p := _find_pool(data))
            else None,
        ),
        TrueNASSensorEntityDescription(
            key=f"pool_{pool_name}_total",
            name=f"Pool {pool_name} total",
            native_unit_of_measurement=UnitOfInformation.GIBIBYTES,
            device_class=SensorDeviceClass.DATA_SIZE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=2,
            icon="mdi:database",
            entity_category=EntityCategory.DIAGNOSTIC,
            value_fn=lambda data, _p=pool_name: round(p.size / (1024**3), 2)
            if (p := _find_pool(data))
            else None,
        ),
        TrueNASSensorEntityDescription(
            key=f"pool_{pool_name}_usage",
            name=f"Pool {pool_name} usage",
            native_unit_of_measurement=PERCENTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
            icon="mdi:gauge",
            value_fn=lambda data, _p=pool_name: round(
                p.allocated / p.size * 100, 1
            )
            if (p := _find_pool(data)) and p.size > 0
            else None,
        ),
        TrueNASSensorEntityDescription(
            key=f"pool_{pool_name}_fragmentation",
            name=f"Pool {pool_name} fragmentation",
            native_unit_of_measurement=PERCENTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:chart-bubble",
            entity_category=EntityCategory.DIAGNOSTIC,
            value_fn=lambda data, _p=pool_name: p.fragmentation
            if (p := _find_pool(data))
            else None,
        ),
    )


def _disk_sensors(disk_name: str) -> tuple[TrueNASSensorEntityDescription, ...]:
    """Create sensor descriptions for a disk."""

    def _find_disk(data: TrueNASData) -> Any:
        return next((d for d in data.disks if d.name == disk_name), None)

    return (
        TrueNASSensorEntityDescription(
            key=f"disk_{disk_name}_temperature",
            name=f"Disk {disk_name} temperature",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:thermometer",
            value_fn=lambda data, _d=disk_name: d.temperature
            if (d := _find_disk(data)) and d.temperature is not None
            else None,
            extra_attrs_fn=lambda data, _d=disk_name: {
                "model": d.model,
                "serial": d.serial,
                "type": d.type,
            }
            if (d := _find_disk(data))
            else {},
        ),
    )


def _dataset_sensors(
    dataset_id: str,
    enabled_default: bool = True,
) -> tuple[TrueNASSensorEntityDescription, ...]:
    """Create sensor descriptions for a dataset."""
    safe_id = dataset_id.replace("/", "_")
    short_name = dataset_id.rsplit("/", 1)[-1]

    def _find_dataset(data: TrueNASData) -> Any:
        return next((d for d in data.datasets if d.id == dataset_id), None)

    return (
        TrueNASSensorEntityDescription(
            key=f"dataset_{safe_id}_used",
            name=f"{dataset_id} used",
            native_unit_of_measurement=UnitOfInformation.GIBIBYTES,
            device_class=SensorDeviceClass.DATA_SIZE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=2,
            icon="mdi:folder",
            entity_registry_enabled_default=enabled_default,
            value_fn=lambda data, _id=dataset_id: round(
                ds.used_bytes / (1024**3), 2
            )
            if (ds := _find_dataset(data))
            else None,
            extra_attrs_fn=lambda data, _id=dataset_id: {
                "dataset": ds.id,
                "type": ds.type,
                "mountpoint": ds.mountpoint,
                "encrypted": ds.encrypted,
            }
            if (ds := _find_dataset(data))
            else {},
        ),
        TrueNASSensorEntityDescription(
            key=f"dataset_{safe_id}_available",
            name=f"{dataset_id} available",
            native_unit_of_measurement=UnitOfInformation.GIBIBYTES,
            device_class=SensorDeviceClass.DATA_SIZE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=2,
            icon="mdi:folder",
            entity_registry_enabled_default=enabled_default,
            value_fn=lambda data, _id=dataset_id: round(
                ds.available_bytes / (1024**3), 2
            )
            if (ds := _find_dataset(data))
            else None,
        ),
        TrueNASSensorEntityDescription(
            key=f"dataset_{safe_id}_usage",
            name=f"{dataset_id} usage",
            native_unit_of_measurement=PERCENTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
            icon="mdi:gauge",
            entity_registry_enabled_default=enabled_default,
            value_fn=lambda data, _id=dataset_id: round(
                ds.used_bytes / (ds.used_bytes + ds.available_bytes) * 100, 1
            )
            if (ds := _find_dataset(data))
            and (ds.used_bytes + ds.available_bytes) > 0
            else None,
        ),
    )


def _network_sensors(
    iface_name: str,
) -> tuple[TrueNASSensorEntityDescription, ...]:
    """Create sensor descriptions for a network interface."""

    def _find_iface(data: TrueNASData) -> Any:
        return next(
            (n for n in data.network_interfaces if n.name == iface_name), None
        )

    return (
        TrueNASSensorEntityDescription(
            key=f"net_{iface_name}_received",
            name=f"{iface_name} received",
            native_unit_of_measurement=UnitOfInformation.GIBIBYTES,
            device_class=SensorDeviceClass.DATA_SIZE,
            state_class=SensorStateClass.TOTAL_INCREASING,
            suggested_display_precision=2,
            icon="mdi:download-network",
            entity_category=EntityCategory.DIAGNOSTIC,
            value_fn=lambda data, _n=iface_name: round(
                n.received_bytes / (1024**3), 2
            )
            if (n := _find_iface(data))
            else None,
        ),
        TrueNASSensorEntityDescription(
            key=f"net_{iface_name}_sent",
            name=f"{iface_name} sent",
            native_unit_of_measurement=UnitOfInformation.GIBIBYTES,
            device_class=SensorDeviceClass.DATA_SIZE,
            state_class=SensorStateClass.TOTAL_INCREASING,
            suggested_display_precision=2,
            icon="mdi:upload-network",
            entity_category=EntityCategory.DIAGNOSTIC,
            value_fn=lambda data, _n=iface_name: round(
                n.sent_bytes / (1024**3), 2
            )
            if (n := _find_iface(data))
            else None,
        ),
    )


def _app_sensors(app_name: str) -> tuple[TrueNASSensorEntityDescription, ...]:
    """Create sensor descriptions for an app."""

    def _find_app(data: TrueNASData) -> Any:
        return next((a for a in data.apps if a.name == app_name), None)

    return (
        TrueNASSensorEntityDescription(
            key=f"app_{app_name}_status",
            name=f"{app_name}",
            icon="mdi:application",
            value_fn=lambda data, _a=app_name: a.state
            if (a := _find_app(data))
            else None,
            extra_attrs_fn=lambda data, _a=app_name: {
                "version": a.human_version,
                "upgrade_available": a.upgrade_available,
            }
            if (a := _find_app(data))
            else {},
        ),
    )


def _vm_sensors(
    vm_name: str, vm_id: int
) -> tuple[TrueNASSensorEntityDescription, ...]:
    """Create sensor descriptions for a VM."""

    def _find_vm(data: TrueNASData) -> Any:
        return next((v for v in data.vms if v.id == vm_id), None)

    return (
        TrueNASSensorEntityDescription(
            key=f"vm_{vm_id}_status",
            name=f"{vm_name}",
            icon="mdi:monitor",
            value_fn=lambda data, _id=vm_id: v.status
            if (v := _find_vm(data))
            else None,
            extra_attrs_fn=lambda data, _id=vm_id: {
                "vcpus": v.vcpus,
                "memory_mb": v.memory,
                "autostart": v.autostart,
            }
            if (v := _find_vm(data))
            else {},
        ),
    )


def _replication_sensors(
    task_id: int, task_name: str
) -> tuple[TrueNASSensorEntityDescription, ...]:
    """Create sensor descriptions for a replication task."""

    def _find_task(data: TrueNASData) -> Any:
        return next(
            (t for t in data.replication_tasks if t.id == task_id), None
        )

    return (
        TrueNASSensorEntityDescription(
            key=f"replication_{task_id}_status",
            name=f"{task_name}",
            icon="mdi:swap-horizontal",
            value_fn=lambda data, _id=task_id: t.state
            if (t := _find_task(data))
            else None,
            extra_attrs_fn=lambda data, _id=task_id: {
                "name": t.name,
                "direction": t.direction,
                "last_run": t.last_run,
                "enabled": t.enabled,
            }
            if (t := _find_task(data))
            else {},
        ),
    )


def _snapshot_task_sensors(
    task_id: int, dataset: str
) -> tuple[TrueNASSensorEntityDescription, ...]:
    """Create sensor descriptions for a snapshot task."""

    def _find_task(data: TrueNASData) -> Any:
        return next(
            (t for t in data.snapshot_tasks if t.id == task_id), None
        )

    return (
        TrueNASSensorEntityDescription(
            key=f"snapshottask_{task_id}_status",
            name=f"{dataset}",
            icon="mdi:camera",
            value_fn=lambda data, _id=task_id: t.state
            if (t := _find_task(data))
            else None,
            extra_attrs_fn=lambda data, _id=task_id: {
                "dataset": t.dataset,
                "last_run": t.last_run,
                "enabled": t.enabled,
                "recursive": t.recursive,
            }
            if (t := _find_task(data))
            else {},
        ),
    )


def _cloudsync_sensors(
    task_id: int, description: str
) -> tuple[TrueNASSensorEntityDescription, ...]:
    """Create sensor descriptions for a cloud sync task."""

    def _find_task(data: TrueNASData) -> Any:
        return next(
            (t for t in data.cloud_sync_tasks if t.id == task_id), None
        )

    return (
        TrueNASSensorEntityDescription(
            key=f"cloudsync_{task_id}_status",
            name=f"{description or f'Task {task_id}'}",
            icon="mdi:cloud-sync",
            value_fn=lambda data, _id=task_id: t.state
            if (t := _find_task(data))
            else None,
            extra_attrs_fn=lambda data, _id=task_id: {
                "description": t.description,
                "direction": t.direction,
                "last_run": t.last_run,
                "enabled": t.enabled,
                "path": t.path,
            }
            if (t := _find_task(data))
            else {},
        ),
    )
