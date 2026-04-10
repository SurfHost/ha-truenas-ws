# Changelog

## [0.1.6] - 2026-04-11

### Fixed

- Update entity crash: use `UpdateEntityDescription` instead of `EntityDescription` (fixes `display_precision` AttributeError spamming every 30s)

## [0.1.5] - 2026-04-11

### Fixed

- Network interface query: try both `interface.query` and `network.interface.query` API methods
- Network byte counters: fall back to `reporting.get_data` per interface when state doesn't include counters

## [0.1.4] - 2026-04-11

### Fixed

- Entity names now actually show resource names (removed `translation_key` from per-resource descriptions which was overriding the `name` field)
- Storage sensors show: "Pool nvme status", "Disk sda temperature", "nvme/Docker used", etc.
- App sensors show: "mealie", "sonarr", etc. instead of generic "Status"

## [0.1.3] - 2026-04-11

### Fixed

- Entity names now include the resource name (app name, disk name, dataset path, etc.) so they are identifiable within grouped devices
- Uptime sensor: return proper datetime object instead of string (fixes "niet beschikbaar" error)
- Memory/ARC stats: improved fallback chain with multiple reporting API formats (reporting.realtime, reporting.get_data, reporting.netdata_get_data)
- Memory sensors: fixed value checks that treated 0 as unavailable

### Changed

- Combined Disks, Pools, and Datasets into a single "Storage" device
- Service switch names simplified (removed "Service:" prefix since they're under the Services device)
- Added debug logging for system stats to help diagnose data fetching issues

## [0.1.2] - 2026-04-10

### Changed

- Device grouping: entities are now grouped by category (Apps, Disks, Datasets, Services, VMs, Replication, Snapshot Tasks, Cloud Sync) instead of individual devices per resource
- Apps, VMs, disks, datasets, services, and tasks all appear under their respective group device
- Pools still have their own individual device per pool
- Much cleaner device list matching the old integration layout

## [0.1.1] - 2026-04-10

### Fixed

- Connection: always try wss:// first, support both `/api/current` (JSON-RPC 2.0) and `/websocket` (legacy DDP)
- CPU/memory stats: fallback chain using system.info and reporting.get_data when reporting.realtime unavailable
- CPU temperature: fetch from reporting cputemp data
- Parse boottime as dict format from TrueNAS API

### Changed

- Snapshot buttons disabled by default (enable per dataset as needed)
- Deep dataset sensors (depth > 2) disabled by default to reduce clutter
- Top-level datasets still enabled automatically

## [0.1.0] - 2026-04-10

### Added

- Initial release using TrueNAS JSON-RPC 2.0 WebSocket API
- **System monitoring**: CPU usage, CPU temperature, memory usage, load averages, uptime, ARC stats, active alerts
- **Storage**: Pool status/health/usage/fragmentation, dataset usage, disk temperatures
- **Network**: Per-interface received/sent bytes
- **Services**: Monitor and start/stop system services via switches
- **Applications**: Status monitoring and start/stop control
- **Virtual Machines**: Status monitoring and start/stop control
- **Tasks**: Replication, snapshot, and cloud sync task status monitoring
- **System control**: Reboot and shutdown buttons
- **Snapshots**: Create ZFS snapshots via button press
- **System updates**: Update entity showing available TrueNAS updates
- **Config flow**: Setup wizard with API key authentication and SSL toggle
- **Options flow**: Configurable update interval (10-300 seconds)
- **Resilient design**: Multi-frequency polling, partial failure tolerance, cached fallback data
