"""Device registry wiring: the NAS device and the devices grouped under it."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_VERIFY_SSL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.truenas_ws.const import CONF_API_KEY, DOMAIN
from custom_components.truenas_ws.coordinator import TrueNASDataUpdateCoordinator
from custom_components.truenas_ws.models import (
    AppInfo,
    PoolInfo,
    ReplicationTask,
    ServiceInfo,
    SystemInfo,
    TrueNASData,
    VMInfo,
)

SUB_DEVICE_KEYS = ("storage", "apps", "services", "vms", "tasks")


def _system_info(version: str = "25.04.2") -> SystemInfo:
    return SystemInfo.from_api({"hostname": "nas", "version": version, "uptime_seconds": 60})


def _data(version: str = "25.04.2") -> TrueNASData:
    """One item for every device group, so each sub-device gets entities."""
    return TrueNASData(
        system_info=_system_info(version),
        pools=[PoolInfo.from_api({"id": 1, "name": "tank", "status": "ONLINE", "healthy": True})],
        services=[ServiceInfo.from_api({"id": 1, "service": "ssh", "state": "RUNNING"})],
        apps=[AppInfo.from_api({"name": "jellyfin", "state": "RUNNING", "version": "1.0"})],
        vms=[VMInfo.from_api({"id": 1, "name": "vm1", "status": {"state": "RUNNING"}})],
        replication_tasks=[ReplicationTask.from_api({"id": 1, "name": "backup"})],
    )


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="nas",
        data={CONF_HOST: "192.0.2.1", CONF_API_KEY: "key", CONF_VERIFY_SSL: False},
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def mock_truenas() -> Generator[dict[str, Any]]:
    """Replace the network layer: no websocket, the refresh returns fixed data."""
    state: dict[str, Any] = {"data": _data()}

    async def _update(self: TrueNASDataUpdateCoordinator) -> TrueNASData:
        data: TrueNASData = state["data"]
        self._sync_device_version(data.system_info)
        return data

    with (
        patch("custom_components.truenas_ws.TrueNASWebSocketClient.connect", new=AsyncMock()),
        patch("custom_components.truenas_ws.TrueNASWebSocketClient.disconnect", new=AsyncMock()),
        patch.object(TrueNASDataUpdateCoordinator, "_async_update_data", _update),
    ):
        yield state


async def test_system_device_registered_before_platforms(
    hass: HomeAssistant, entry: MockConfigEntry, mock_truenas: dict[str, Any]
) -> None:
    """The NAS device exists, and is on the coordinator, when the platforms load."""
    registry = dr.async_get(hass)
    seen: dict[str, Any] = {}
    original = hass.config_entries.async_forward_entry_setups

    async def _spy(*args: Any, **kwargs: Any) -> None:
        seen["device"] = registry.async_get_device_by_identifier(
            (DOMAIN, f"{entry.entry_id}_system"), entry.entry_id
        )
        seen["coordinator_id"] = entry.runtime_data.system_device_id
        await original(*args, **kwargs)

    with patch.object(hass.config_entries, "async_forward_entry_setups", _spy):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    device = seen["device"]
    assert device is not None
    assert seen["coordinator_id"] == device.id
    assert device.name == "nas"
    assert device.manufacturer == "iXsystems"
    assert device.model == "TrueNAS"
    assert device.sw_version == "25.04.2"


async def test_sub_devices_link_to_system_device(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    mock_truenas: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Storage, Apps, Services, VMs and Tasks sit under the NAS by registry id."""
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = dr.async_get(hass)
    system = registry.async_get_device_by_identifier(
        (DOMAIN, f"{entry.entry_id}_system"), entry.entry_id
    )
    assert system is not None
    assert system.via_device_id is None
    for key in SUB_DEVICE_KEYS:
        device = registry.async_get_device_by_identifier(
            (DOMAIN, f"{entry.entry_id}_{key}"), entry.entry_id
        )
        assert device is not None, key
        assert device.via_device_id == system.id, key

    # Exactly the NAS plus its five groups, so no duplicate NAS device appeared.
    devices = dr.async_entries_for_config_entry(registry, entry.entry_id)
    assert len(devices) == 1 + len(SUB_DEVICE_KEYS)
    # Neither deprecation from HA's device registry is reported any more.
    assert "async_get_device`" not in caplog.text
    assert "deprecated `via_device`" not in caplog.text


async def test_sync_device_version_updates_sw_version(
    hass: HomeAssistant, entry: MockConfigEntry, mock_truenas: dict[str, Any]
) -> None:
    """A TrueNAS upgrade reaches the device page without a reload."""
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    mock_truenas["data"] = _data("25.10.0")
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, f"{entry.entry_id}_system"), entry.entry_id
    )
    assert device is not None
    assert device.sw_version == "25.10.0"
