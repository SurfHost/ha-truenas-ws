# Changelog

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
