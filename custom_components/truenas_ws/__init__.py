"""TrueNAS integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.const import CONF_HOST, CONF_SCAN_INTERVAL, CONF_VERIFY_SSL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import TrueNASWebSocketClient
from .const import CONF_API_KEY, DEFAULT_SCAN_INTERVAL
from .coordinator import TrueNASConfigEntry, TrueNASDataUpdateCoordinator
from .entity import system_device_info

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.BUTTON,
    Platform.UPDATE,
]


async def async_setup_entry(hass: HomeAssistant, entry: TrueNASConfigEntry) -> bool:
    """Set up TrueNAS from a config entry."""
    session = async_get_clientsession(
        hass,
        verify_ssl=entry.data.get(CONF_VERIFY_SSL, True),
    )
    client = TrueNASWebSocketClient(
        host=entry.data[CONF_HOST],
        api_key=entry.data[CONF_API_KEY],
        session=session,
        verify_ssl=entry.data.get(CONF_VERIFY_SSL, True),
    )

    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator = TrueNASDataUpdateCoordinator(hass, entry, client, scan_interval)

    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    # Register the NAS device before the platforms load. The Storage, Apps,
    # Services, VMs and Tasks devices link to it by registry id (via_device_id),
    # and the registry rejects an id it does not know yet.
    system_info = coordinator.data.system_info if coordinator.data else None
    system_device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        **system_device_info(entry, system_info),
    )
    coordinator.system_device_id = system_device.id

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Clean up entities from removed/reorganized features
    _async_cleanup_stale_entities(hass, entry)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: TrueNASConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.client.disconnect()
    return unload_ok


def _async_cleanup_stale_entities(hass: HomeAssistant, entry: TrueNASConfigEntry) -> None:
    """Remove entities from reorganised features that no longer exist."""
    ent_reg = er.async_get(hass)
    entry_id = entry.entry_id
    stale_prefixes = (
        # Per-type task devices (merged into Tasks)
        f"{entry_id}_replication_",
        f"{entry_id}_snapshot_tasks_",
        f"{entry_id}_cloudsync_",
        # All-in-one per-app device (reverted in v0.3.9)
        f"{entry_id}_app:",
        # Per-app update device (reverted in v0.5.3 > back under shared Apps)
        f"{entry_id}_app_update:",
    )
    for entity in er.async_entries_for_config_entry(ent_reg, entry_id):
        uid = entity.unique_id or ""
        if uid.startswith(stale_prefixes) or "arc_hit_ratio" in uid:
            _LOGGER.info("Removing stale entity: %s", entity.entity_id)
            ent_reg.async_remove(entity.entity_id)


async def _async_update_listener(hass: HomeAssistant, entry: TrueNASConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)
