# Changelog

## [0.3.10] - 2026-04-15

### Changed

- App update entities now display as `{app_name}` (e.g. `dozzle`) instead of `Apps {app_name} update`. The HA Updates UI and custom dashboards show the app name cleanly.

### Fixed

- System update detection: try `update.status` (TrueNAS SCALE 25+) before falling back to `update.check_available`. Raw responses are logged at WARNING level for diagnostics.

## [0.3.9] - 2026-04-15

### Changed

- Reverted per-app device split from v0.3.8. All apps are again under a single **Apps** device, with each entity named after the app (e.g. `jellyfin update`, `sonarr update`) so they're easy to identify in the update UI.
- Stale per-app device entities from v0.3.8 are auto-cleaned on startup.

## [0.3.8] - 2026-04-15

### Changed

- **Each app is now its own device** named after the app (previously all apps were grouped under a single "Apps" device, making them indistinguishable). Each app device contains its Status sensor, Power switch, and Update entity. Old shared-device entities are auto-cleaned on startup.

### Fixed

- Added diagnostic logging for `update.check_available` so we can see what the API actually returns when a system update is pending but not detected

## [0.3.7] - 2026-04-15

### Added

- **Install** button on the system update entity — applies the pending TrueNAS update via `update.update` and reboots
- **Install** button on each app update entity — triggers `app.upgrade` to upgrade the application

## [0.3.6] - 2026-04-15

### Fixed

- System update entity now correctly detects available updates (modern TrueNAS returns `status` field instead of boolean `available`)
- Added update entities per application — available app updates now show in the HA update UI

## [0.3.5] - 2026-04-13

### Changed

- Default poll interval raised from 30s to 2 minutes to reduce database growth
- Tiered polling: system stats every 2 min, disks/pools every 5 min, datasets every 15 min
- Dataset sensors now disabled by default for all nested datasets (only root pool datasets enabled)
- Removed long-term statistics tracking from pool total size and fragmentation sensors
- Options flow scan interval range updated to 30–900 seconds (was 10–300)

### Fixed

- Fixed import typo: `DEFAULT_DEFAULT_TASKS_INTERVAL` → `DEFAULT_TASKS_INTERVAL`

## [0.3.4] - 2026-04-12

### Fixed

- Reboot and Shutdown buttons now work — send reason string parameter and use short timeout (TrueNAS returns a job ID then disconnects)
- Cloud Sync and Replication tasks now appear under Tasks device — fixed overly broad entity cleanup that was deleting new task entities on startup
- Code cleanup: removed all diagnostic logging, removed unused imports

## [0.3.0] - 2026-04-12

### Added

- Rsync task monitoring via `rsynctask.query` API
- All tasks (Snapshot, Cloud Sync, Replication, Rsync) now grouped under a single **Tasks** device

### Fixed

- Reboot and Shutdown buttons now work — catch expected connection loss after sending command
- Old per-type task devices (Replication, Snapshot Tasks, Cloud Sync) auto-cleaned on startup

### Removed

- ARC hit ratio sensor (TrueNAS API does not support this graph via WebSocket)

## [0.2.9] - 2026-04-12

### Removed

- ARC hit ratio sensor — TrueNAS reporting API does not support querying this graph via WebSocket
- ARC hit ratio entity auto-cleaned on startup

### Fixed

- Code cleanup: `_pending_str` dict properly initialized in `__init__` instead of lazy hasattr pattern
- Code cleanup: removed dead arc_hit variable and API parsing code
- Code cleanup: removed translation entries for arc_hit_ratio

## [0.2.8] - 2026-04-12

### Fixed

- ARC hit ratio: try 4 different API parameter formats to find what works for demanddatahitpercentage
- ARC hit ratio: log all errors at WARNING level (were at DEBUG, invisible in default log)

## [0.2.7] - 2026-04-12

### Fixed

- ARC hit ratio: only query actual hit percentage graphs (was matching arcsize which returned bytes as %)
- ARC hit ratio: try `identifier: graph_name` format (matching the pattern from successful arcsize query)
- Simplified ARC hit code — no more broad keyword matching or graph discovery overhead

## [0.2.6] - 2026-04-12

### Fixed

- ARC hit ratio: use `reporting.graphs` to discover ARC graph definitions including required identifiers
- ARC hit ratio: log both success and failure for each attempt (was silently swallowing all errors)
- ARC hit ratio: increased time window from 120s to 300s for graph queries

## [0.2.5] - 2026-04-12

### Fixed

- ARC hit ratio: graph requires pool identifier — now fetches pool names and tries each as identifier
- Boot pool: parser now reads size/allocated/free from top-level keys (confirmed fix from diagnostic)
- Network entity cleanup: broadened matching to also match on entity_id pattern (eno + received/sent)
- Removed stale diagnostic logs

## [0.2.4] - 2026-04-11

### Fixed

- Boot pool: read size/allocated/free from top-level keys (not under `properties` which is empty)
- ARC hit ratio: log the actual error when graph query fails (was silently swallowed)
- Removed diagnostic logs for boot pool and disk temperatures (debugging complete)

## [0.2.3] - 2026-04-11

### Fixed

- Auto-cleanup stale network entities (eno received/sent) that were removed in v0.2.0
- Added diagnostic logging for boot.get_state response to debug boot-pool 0.00 GiB
- Added diagnostic logging for disk.temperatures to debug missing disk temps

## [0.2.2] - 2026-04-11

### Added

- Boot pool monitoring via `boot.get_state` API (pool.query excludes the boot pool by default)
- Boot pool shows status, used/free/total space, usage percentage, fragmentation under Storage device

## [0.2.1] - 2026-04-11

### Fixed

- ARC hit ratio: handle multi-column legend format (e.g. hits/misses columns), added `demanddatahitspersecond` to fallback list
- ARC hit ratio: fix loop logic that prevented detection of valid 0% hit ratios
- Added diagnostic log for ARC hit report response to debug remaining issue

## [0.2.0] - 2026-04-11

### Fixed

- ARC hit ratio: use correct graph name `demanddatahitpercentage` (discovered from `reporting.graphs`)
- Memory free now calculated from total - used when not provided by API

### Changed

- Removed network per-interface traffic sensors (TrueNAS API returns empty data for interface reporting)
- Removed all one-time diagnostic WARNING logs (debugging complete)

## [0.1.9] - 2026-04-11

### Fixed

- Memory stats: handle FreeBSD memory categories (active, wired, cache, arc, etc.) — sum non-free columns when no "used" column exists
- Added diagnostic logging for `reporting.get_data(memory)` response to debug memory parsing
- Added one-time `reporting.graphs` discovery to identify available graph names
- ARC hit ratio: added "arc" to graph name fallback list, added diagnostic logging

## [0.1.8] - 2026-04-11

### Fixed

- Memory stats: handle simple `[[timestamp, value]]` format from `reporting.get_data` (no legend/multi-column)
- ARC hit ratio: added separate query for ARC hit rate data
- Network interfaces: added diagnostic logging to identify data format, handle simple data format
- Memory usage, memory free, memory used should now show actual values

## [0.1.7] - 2026-04-11

### Changed

- Simplified entity names: "nvme0n1" instead of "Disk nvme0n1 temperature", "nvme status" instead of "Pool nvme status"
- Added one-time warning-level logs for memory/reporting API responses to help debug missing memory stats

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
