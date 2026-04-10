# Changelog

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
