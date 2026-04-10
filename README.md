# TrueNAS Integration for Home Assistant

Custom Home Assistant integration for TrueNAS SCALE using the modern **JSON-RPC 2.0 WebSocket API**.

## Features

### System Monitoring
- CPU usage & temperature
- Memory usage (used/free/percentage)
- System load averages (1/5/15 min)
- System uptime
- ZFS ARC size & hit ratio
- Active alerts count

### Storage
- **Pools**: Status, health, used/free/total space, usage %, fragmentation
- **Datasets**: Used/available space, usage percentage
- **Disks**: Temperature per disk

### Network
- Per-interface received/sent bytes (cumulative)

### Services, Apps & VMs
- Service status monitoring with start/stop switches
- Application status with start/stop control
- Virtual machine status with power control

### Tasks
- Replication task status & last run
- Snapshot task status & last run
- Cloud sync task status & last run

### System Control
- Reboot & shutdown buttons
- Create ZFS snapshots per dataset
- System update entity with release notes

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots menu → **Custom repositories**
3. Add `SurfHost/ha-truenas` with category **Integration**
4. Search for "TrueNAS" and install
5. Restart Home Assistant

### Manual

Copy the `custom_components/truenas` folder to your Home Assistant `custom_components/` directory and restart.

## Configuration

1. In TrueNAS, go to **System → API Keys** and create a new API key
2. In Home Assistant, go to **Settings → Integrations → Add Integration**
3. Search for **TrueNAS**
4. Enter your TrueNAS host/IP and API key
5. Optionally disable SSL verification (for self-signed certificates)

### Options

After setup, you can configure:
- **Update interval**: 10–300 seconds (default: 30s)

## Requirements

- TrueNAS SCALE with WebSocket API support
- Home Assistant 2024.3.0 or newer
- A TrueNAS API key

## Architecture

This integration uses TrueNAS's **JSON-RPC 2.0 WebSocket API** (`wss://{host}/api/current`) instead of the deprecated REST API. It maintains a persistent WebSocket connection with:

- Multi-frequency polling (30s for storage, 60s for alerts, 5min for tasks, 12h for system info)
- Partial failure tolerance — if one API call fails, cached data is preserved
- Automatic reconnection with exponential backoff
