"""Data models for the TrueNAS integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Self


def _parse_fragmentation(value: Any) -> int:
    """Parse a fragmentation value from TrueNAS.

    The API may return an int, a string like ``"5"``/``"5%"`` or a legacy
    dict ``{"value": "5"}``. Returns ``0`` if the value can't be parsed.
    """
    if isinstance(value, dict):
        value = value.get("value", 0)
    if value is None:
        return 0
    try:
        return int(str(value).rstrip("%"))
    except (ValueError, TypeError):
        return 0


@dataclass(frozen=True, slots=True)
class SystemInfo:
    """System information from TrueNAS."""

    hostname: str
    version: str
    uptime_seconds: int
    cpu_model: str
    cpu_cores: int
    physical_cores: int
    memory_total_bytes: int
    load_avg_1: float
    load_avg_5: float
    load_avg_15: float
    timezone: str

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Self:
        """Create from API response."""
        loadavg = data.get("loadavg") or [0.0, 0.0, 0.0]
        return cls(
            hostname=data.get("hostname", ""),
            version=data.get("version", ""),
            uptime_seconds=int(data.get("uptime_seconds", 0)),
            cpu_model=data.get("model", ""),
            cpu_cores=int(data.get("cores", 0)),
            physical_cores=int(data.get("physical_cores", 0)),
            memory_total_bytes=int(data.get("physmem", 0)),
            load_avg_1=float(loadavg[0]),
            load_avg_5=float(loadavg[1]),
            load_avg_15=float(loadavg[2]),
            timezone=data.get("timezone", "UTC"),
        )


@dataclass(frozen=True, slots=True)
class SystemStats:
    """Real-time system statistics."""

    cpu_usage: float
    memory_usage_percent: float
    memory_used_bytes: int
    memory_free_bytes: int
    arc_size: int
    arc_max: int
    arc_hit_ratio: float
    cpu_temperature: float | None

    @classmethod
    def from_api(
        cls,
        reporting_data: dict[str, Any] | None = None,
        memory_data: dict[str, Any] | None = None,
    ) -> Self:
        """Create from reporting/stats API responses."""
        cpu_usage = 0.0
        if reporting_data and "cpu" in reporting_data:
            cpu_data = reporting_data["cpu"]
            if isinstance(cpu_data, dict) and "usage" in cpu_data:
                cpu_usage = float(cpu_data["usage"])

        mem_total = 0
        mem_used = 0
        mem_free = 0
        mem_pct = 0.0
        arc_size = 0
        arc_max = 0
        cpu_temp: float | None = None

        if memory_data:
            mem_total = int(memory_data.get("total", 0))
            mem_used = int(memory_data.get("used", 0))
            mem_free = int(memory_data.get("free", 0))
            if mem_total > 0:
                mem_pct = round(mem_used / mem_total * 100, 1)
            arc_size = int(memory_data.get("arc_size", 0))
            arc_max = int(memory_data.get("arc_max", 0))

        if reporting_data and "cpu_temp" in reporting_data:
            temp = reporting_data["cpu_temp"]
            if temp is not None:
                cpu_temp = float(temp)

        return cls(
            cpu_usage=cpu_usage,
            memory_usage_percent=mem_pct,
            memory_used_bytes=mem_used,
            memory_free_bytes=mem_free,
            arc_size=arc_size,
            arc_max=arc_max,
            arc_hit_ratio=0.0,
            cpu_temperature=cpu_temp,
        )


@dataclass(frozen=True, slots=True)
class DiskInfo:
    """Disk information."""

    identifier: str
    name: str
    serial: str
    model: str
    size: int
    temperature: int | None
    type: str
    description: str
    pool: str | None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Self:
        """Create from API response."""
        return cls(
            identifier=data.get("identifier", ""),
            name=data.get("name", ""),
            serial=data.get("serial", ""),
            model=data.get("model", ""),
            size=int(data.get("size", 0)),
            temperature=data.get("temperature"),
            type=data.get("type", ""),
            description=data.get("description", ""),
            pool=data.get("pool"),
        )


@dataclass(frozen=True, slots=True)
class DiskSmartInfo:
    """Disk SMART status."""

    disk_name: str
    passed: bool | None
    temperature: int | None

    @classmethod
    def from_api(cls, disk_name: str, data: dict[str, Any]) -> Self:
        """Create from API response."""
        return cls(
            disk_name=disk_name,
            passed=data.get("passed"),
            temperature=data.get("temperature"),
        )


@dataclass(frozen=True, slots=True)
class PoolInfo:
    """ZFS pool information."""

    id: int
    name: str
    guid: str
    status: str
    healthy: bool
    warning: bool
    size: int
    allocated: int
    free: int
    fragmentation: int
    is_decrypted: bool
    scan_state: str | None
    scan_percentage: float | None
    autotrim: bool
    path: str

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Self:
        """Create from API response."""
        scan = data.get("scan")
        scan_state: str | None = None
        scan_pct: float | None = None
        if scan:
            scan_state = scan.get("state")
            scan_pct = scan.get("percentage")

        autotrim_raw = data.get("autotrim", {})
        if isinstance(autotrim_raw, dict):
            autotrim = autotrim_raw.get("value") == "on"
        else:
            autotrim = bool(autotrim_raw)

        return cls(
            id=int(data.get("id", 0)),
            name=data.get("name", ""),
            guid=data.get("guid", ""),
            status=data.get("status", "UNKNOWN"),
            healthy=bool(data.get("healthy", False)),
            warning=bool(data.get("warning", False)),
            size=int(data.get("size", 0)),
            allocated=int(data.get("allocated", 0)),
            free=int(data.get("free", 0)),
            fragmentation=_parse_fragmentation(data.get("fragmentation")),
            is_decrypted=bool(data.get("is_decrypted", True)),
            scan_state=scan_state,
            scan_percentage=scan_pct,
            autotrim=autotrim,
            path=data.get("path", ""),
        )

    @classmethod
    def from_boot_api(cls, data: dict[str, Any]) -> Self:
        """Create from boot.get_state response.

        boot.get_state returns size/allocated/free/fragmentation/autotrim
        at the top level (not under 'properties').
        """
        scan = data.get("scan")
        scan_state: str | None = None
        scan_pct: float | None = None
        if scan:
            scan_state = scan.get("state")
            scan_pct = scan.get("percentage")

        # Size/allocated/free are at top level
        size = int(data.get("size") or 0)
        allocated = int(data.get("allocated") or 0)
        free = int(data.get("free") or 0)

        frag = _parse_fragmentation(data.get("fragmentation"))

        status = data.get("status", "UNKNOWN")
        healthy = bool(data.get("healthy", status == "ONLINE"))

        autotrim_raw = data.get("autotrim", {})
        if isinstance(autotrim_raw, dict):
            autotrim = autotrim_raw.get("value") == "on"
        else:
            autotrim = bool(autotrim_raw)

        return cls(
            id=0,
            name=data.get("name", "boot-pool"),
            guid=data.get("guid", ""),
            status=status,
            healthy=healthy,
            warning=bool(data.get("warning", not healthy)),
            size=size,
            allocated=allocated,
            free=free,
            fragmentation=frag,
            is_decrypted=True,
            scan_state=scan_state,
            scan_percentage=scan_pct,
            autotrim=autotrim,
            path=data.get("path", ""),
        )


@dataclass(frozen=True, slots=True)
class DatasetInfo:
    """Dataset information."""

    id: str
    name: str
    pool: str
    type: str
    used_bytes: int
    available_bytes: int
    quota_bytes: int
    mountpoint: str | None
    encrypted: bool
    comments: str

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Self:
        """Create from API response."""

        def _prop_val(prop_name: str, default: int = 0) -> int:
            prop = data.get(prop_name)
            if isinstance(prop, dict):
                raw = prop.get("rawvalue", prop.get("value", default))
            else:
                raw = prop if prop is not None else default
            try:
                return int(raw)
            except (ValueError, TypeError):
                return default

        dataset_id = data.get("id", "")
        pool = dataset_id.split("/")[0] if "/" in dataset_id else dataset_id

        comments_raw = data.get("comments")
        if isinstance(comments_raw, dict):
            comments = comments_raw.get("value", "")
        else:
            comments = comments_raw or ""

        return cls(
            id=dataset_id,
            name=data.get("name", dataset_id.rsplit("/", 1)[-1]),
            pool=pool,
            type=data.get("type", "FILESYSTEM"),
            used_bytes=_prop_val("used"),
            available_bytes=_prop_val("available"),
            quota_bytes=_prop_val("quota"),
            mountpoint=data.get("mountpoint"),
            encrypted=bool(data.get("encrypted", False)),
            comments=comments,
        )


@dataclass(frozen=True, slots=True)
class NetworkInterface:
    """Network interface information."""

    id: str
    name: str
    description: str
    state: str
    mtu: int
    link_address: str
    received_bytes: int
    sent_bytes: int
    received_errors: int
    sent_errors: int

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Self:
        """Create from API response."""
        state = data.get("state", {})
        if isinstance(state, str):
            link_state = state
            link_addr = ""
            rx_bytes = 0
            tx_bytes = 0
            rx_errors = 0
            tx_errors = 0
            mtu_val = 0
        else:
            link_state = state.get("link_state", "UNKNOWN")
            link_addr = state.get("link_address", "")
            rx_bytes = int(state.get("received_bytes", 0))
            tx_bytes = int(state.get("sent_bytes", 0))
            rx_errors = int(state.get("received_errors", 0))
            tx_errors = int(state.get("sent_errors", 0))
            mtu_val = int(state.get("mtu", data.get("mtu", 0)))

        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            state=link_state,
            mtu=mtu_val,
            link_address=link_addr,
            received_bytes=rx_bytes,
            sent_bytes=tx_bytes,
            received_errors=rx_errors,
            sent_errors=tx_errors,
        )


@dataclass(frozen=True, slots=True)
class ServiceInfo:
    """Service information."""

    id: int
    service: str
    state: str
    enable: bool

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Self:
        """Create from API response."""
        return cls(
            id=int(data.get("id", 0)),
            service=data.get("service", ""),
            state=data.get("state", "STOPPED"),
            enable=bool(data.get("enable", False)),
        )


@dataclass(frozen=True, slots=True)
class AppInfo:
    """Application information."""

    name: str
    id: str
    state: str
    version: str
    human_version: str
    latest_version: str | None
    upgrade_available: bool
    metadata: dict[str, Any]

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Self:
        """Create from API response."""
        metadata = data.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
        return cls(
            name=data.get("name", ""),
            id=data.get("id", data.get("name", "")),
            state=data.get("state", "UNKNOWN"),
            version=data.get("version", ""),
            human_version=data.get("human_version", data.get("version", "")),
            latest_version=data.get("latest_version")
            or metadata.get("latest_version"),
            upgrade_available=bool(data.get("upgrade_available", False)),
            metadata=metadata,
        )


@dataclass(frozen=True, slots=True)
class VMInfo:
    """Virtual machine information."""

    id: int
    name: str
    description: str
    status: str
    vcpus: int
    memory: int
    autostart: bool

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Self:
        """Create from API response."""
        status_data = data.get("status", {})
        if isinstance(status_data, dict):
            status = status_data.get("state", "STOPPED")
        else:
            status = str(status_data)
        return cls(
            id=int(data.get("id", 0)),
            name=data.get("name", ""),
            description=data.get("description", ""),
            status=status,
            vcpus=int(data.get("vcpus", 0)),
            memory=int(data.get("memory", 0)),
            autostart=bool(data.get("autostart", False)),
        )


@dataclass(frozen=True, slots=True)
class ReplicationTask:
    """Replication task information."""

    id: int
    name: str
    state: str
    last_run: str | None
    enabled: bool
    direction: str
    source_datasets: list[str]
    target_dataset: str

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Self:
        """Create from API response."""
        job = data.get("job")
        state = "UNKNOWN"
        last_run: str | None = None
        if isinstance(job, dict):
            state = job.get("state", "UNKNOWN")
            last_run = job.get("time_finished") or job.get("time_started")

        return cls(
            id=int(data.get("id", 0)),
            name=data.get("name", ""),
            state=data.get("state", {}).get("state", state)
            if isinstance(data.get("state"), dict)
            else state,
            last_run=last_run,
            enabled=bool(data.get("enabled", True)),
            direction=data.get("direction", ""),
            source_datasets=data.get("source_datasets", []),
            target_dataset=data.get("target_dataset", ""),
        )


@dataclass(frozen=True, slots=True)
class SnapshotTask:
    """Periodic snapshot task information."""

    id: int
    dataset: str
    state: str
    last_run: str | None
    enabled: bool
    lifetime_value: int
    lifetime_unit: str
    naming_schema: str
    recursive: bool

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Self:
        """Create from API response."""
        state = "UNKNOWN"
        last_run: str | None = None
        state_data = data.get("state", {})
        if isinstance(state_data, dict):
            state = state_data.get("state", "UNKNOWN")
            last_run = state_data.get("datetime", {}).get("$date") if isinstance(
                state_data.get("datetime"), dict
            ) else state_data.get("datetime")

        return cls(
            id=int(data.get("id", 0)),
            dataset=data.get("dataset", ""),
            state=state,
            last_run=last_run,
            enabled=bool(data.get("enabled", True)),
            lifetime_value=int(data.get("lifetime_value", 0)),
            lifetime_unit=data.get("lifetime_unit", ""),
            naming_schema=data.get("naming_schema", ""),
            recursive=bool(data.get("recursive", False)),
        )


@dataclass(frozen=True, slots=True)
class CloudSyncTask:
    """Cloud sync task information."""

    id: int
    description: str
    state: str
    last_run: str | None
    enabled: bool
    direction: str
    transfer_mode: str
    path: str

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Self:
        """Create from API response."""
        job = data.get("job")
        state = "UNKNOWN"
        last_run: str | None = None
        if isinstance(job, dict):
            state = job.get("state", "UNKNOWN")
            last_run = job.get("time_finished") or job.get("time_started")

        return cls(
            id=int(data.get("id", 0)),
            description=data.get("description", ""),
            state=state,
            last_run=last_run,
            enabled=bool(data.get("enabled", True)),
            direction=data.get("direction", ""),
            transfer_mode=data.get("transfer_mode", ""),
            path=data.get("path", ""),
        )


@dataclass(frozen=True, slots=True)
class RsyncTask:
    """Rsync task information."""

    id: int
    path: str
    remote_host: str
    remote_path: str
    state: str
    last_run: str | None
    enabled: bool
    direction: str
    description: str

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Self:
        """Create from API response."""
        job = data.get("job")
        state = "UNKNOWN"
        last_run: str | None = None
        if isinstance(job, dict):
            state = job.get("state", "UNKNOWN")
            last_run = job.get("time_finished") or job.get("time_started")

        return cls(
            id=int(data.get("id", 0)),
            path=data.get("path", ""),
            remote_host=data.get("remotehost", ""),
            remote_path=data.get("remotepath", ""),
            state=state,
            last_run=last_run,
            enabled=bool(data.get("enabled", True)),
            direction=data.get("direction", "PUSH"),
            description=data.get("desc", data.get("description", "")),
        )


@dataclass(frozen=True, slots=True)
class Alert:
    """System alert."""

    id: str
    level: str
    message: str
    dismissed: bool
    klass: str
    datetime_raw: str | None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Self:
        """Create from API response."""
        dt = data.get("datetime")
        datetime_str: str | None = None
        if isinstance(dt, dict):
            datetime_str = dt.get("$date")
        elif isinstance(dt, str):
            datetime_str = dt

        return cls(
            id=data.get("id", data.get("uuid", "")),
            level=data.get("level", "INFO"),
            message=data.get("formatted", data.get("message", "")),
            dismissed=bool(data.get("dismissed", False)),
            klass=data.get("klass", ""),
            datetime_raw=datetime_str,
        )


@dataclass(frozen=True, slots=True)
class UpdateInfo:
    """System update information."""

    available: bool
    version: str | None
    changelog: str | None
    current_version: str | None
    profile: str | None = None
    train: str | None = None


@dataclass(slots=True)
class TrueNASData:
    """Aggregated TrueNAS data container."""

    system_info: SystemInfo | None = None
    system_stats: SystemStats | None = None
    disks: list[DiskInfo] = field(default_factory=list)
    disk_smart: dict[str, DiskSmartInfo] = field(default_factory=dict)
    pools: list[PoolInfo] = field(default_factory=list)
    datasets: list[DatasetInfo] = field(default_factory=list)
    network_interfaces: list[NetworkInterface] = field(default_factory=list)
    services: list[ServiceInfo] = field(default_factory=list)
    apps: list[AppInfo] = field(default_factory=list)
    vms: list[VMInfo] = field(default_factory=list)
    replication_tasks: list[ReplicationTask] = field(default_factory=list)
    snapshot_tasks: list[SnapshotTask] = field(default_factory=list)
    cloud_sync_tasks: list[CloudSyncTask] = field(default_factory=list)
    rsync_tasks: list[RsyncTask] = field(default_factory=list)
    alerts: list[Alert] = field(default_factory=list)
    update_info: UpdateInfo | None = None
