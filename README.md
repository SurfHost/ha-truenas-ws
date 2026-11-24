# TrueNAS Integration for Home Assistant

[![Validate](https://github.com/SurfHost/ha-truenas-ws/actions/workflows/validate.yml/badge.svg)](https://github.com/SurfHost/ha-truenas-ws/actions/workflows/validate.yml)
[![Marketplace](https://img.shields.io/badge/Marketplace-Custom_repository-41BDF5.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=SurfHost&repository=ha-truenas-ws&category=integration)

Custom Home Assistant integration for TrueNAS SCALE using the **JSON-RPC 2.0 WebSocket API**. Fully compatible with TrueNAS SCALE 25 and 26+.

## Features

### System Monitoring
- CPU usage & temperature
- Memory usage (used/free/percentage)
- System load averages (1/5/15 min)
- System uptime
- ZFS ARC size
- Active alerts count, with a count per alert level and the highest active level
- Critical alerts (CRITICAL, ALERT or EMERGENCY)
- Reboot required, with the reasons

### Storage
- **Pools**: Status, health, used/free/total space, usage %, fragmentation (includes boot pool)
- **Datasets**: Used/available space, usage percentage
- **Disks**: Temperature per disk
- **Scrubs**: State, progress, last finished scrub and errors per pool; start, pause and stop buttons for data pools

### Network
- Received and sent traffic per interface
- Link state per interface

### UPS
- Battery charge, battery runtime and load of the UPS that TrueNAS monitors
- Input voltage and frequency, if the UPS reports them

### Services, Apps & VMs
- Service status monitoring with start/stop switches
- Application status with start/stop control
- Virtual machine status with power control

### Tasks
- Replication task status & last run
- Snapshot task status & last run
- Cloud sync task status & last run
- Rsync task status & last run

### System Control
- Reboot & shutdown buttons
- Create ZFS snapshots per dataset
- System update entity with release notes

## Installation

### Marketplace (recommended)

Since Home Assistant 2026.11, HACS is built into Home Assistant as the **Marketplace**. An existing HACS installation of this integration moves over by itself and keeps receiving updates.

[![Open your Home Assistant instance and open this repository in the Marketplace.](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=SurfHost&repository=ha-truenas-ws&category=integration)

Or manually:

1. Go to **Settings > Marketplace**
2. Open the menu and choose **Custom repositories**
3. Add `SurfHost/ha-truenas-ws` with category **Integration**
4. Search for "TrueNAS" and install
5. Restart Home Assistant

On Home Assistant before 2026.11, use HACS the same way.

### Manual

1. Download the `custom_components/truenas_ws` folder
2. Place it in your Home Assistant `config/custom_components/` directory
3. Restart Home Assistant

## Configuration

[![Add Integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=truenas_ws)

Or manually:

1. In TrueNAS, go to **System > API Keys** and create a new API key
2. In Home Assistant, go to **Settings > Integrations > Add Integration**
3. Search for **TrueNAS**
4. Enter your TrueNAS host/IP and API key
5. Optionally disable SSL verification (for self-signed certificates)

### Options

After setup, you can configure:
- **Update interval**: 30 > 900 seconds (default: 120s)

### System update entity & update profile

The System update entity mirrors the **Update Profile** configured in TrueNAS (Settings > Update). If the profile is set to a pre-release track (`Developer`/`Nightly`), the entity will offer beta versions when you press **Install**. To avoid beta upgrades, set the profile to `Mission Critical` or `Release` in TrueNAS before installing updates from Home Assistant.

The current profile is exposed as an attribute on the System update entity so you can see which track you're on.

## Requirements

- **TrueNAS SCALE 25.04 or newer** (uses the JSON-RPC 2.0 API at `/api/current`)
- Home Assistant 2026.8.0 or newer (the device registry APIs this integration uses, `async_get_device_by_identifier` and `DeviceInfo.via_device_id`, first shipped in 2026.8.0)
- A TrueNAS API key

## Architecture

This integration uses TrueNAS's **JSON-RPC 2.0 WebSocket API** (`wss://{host}/api/current`) instead of the deprecated REST API. It maintains a persistent WebSocket connection with:

- Multi-frequency polling (2 min for system info, stats, alerts, apps, VMs,
  network traffic and UPS readings;
  5 min for disks, pools, network and tasks; 15 min for datasets; 12 h for the update check)
- Partial failure tolerance > if one API call fails, cached data is preserved
- Automatic reconnection with exponential backoff
