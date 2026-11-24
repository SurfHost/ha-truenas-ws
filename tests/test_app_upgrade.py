"""App upgrades: waiting for the TrueNAS job and recovering from pull rate limits."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.truenas_ws import update as update_module
from custom_components.truenas_ws.api import TrueNASWebSocketClient
from custom_components.truenas_ws.errors import TrueNASJobError
from custom_components.truenas_ws.update import TrueNASAppUpdateEntity

RATE_LIMIT = (
    "[EFAULT] Failed 'up' action for 'immich' app. It appears you have reached "
    "your pull rate limit. Please try again later."
)


def _client(responses: list[Any]) -> TrueNASWebSocketClient:
    client = TrueNASWebSocketClient(host="nas", api_key="key", session=MagicMock())
    client._send_request = AsyncMock(side_effect=responses)  # type: ignore[method-assign]
    return client


@pytest.fixture(autouse=True)
def fast_poll() -> Any:
    with patch("custom_components.truenas_ws.api.JOB_POLL_INTERVAL", 0):
        yield


async def test_job_is_polled_until_success() -> None:
    client = _client([42, [{"id": 42, "state": "RUNNING"}], [{"id": 42, "state": "SUCCESS"}]])
    await client.upgrade_app("immich")
    calls = client._send_request.await_args_list  # type: ignore[attr-defined]
    assert calls[0].args == ("app.upgrade", ["immich"])
    assert calls[2].args == ("core.get_jobs", [[["id", "=", 42]]])


async def test_failed_job_raises_with_rate_limit_flag() -> None:
    client = _client([7, [{"id": 7, "state": "FAILED", "error": RATE_LIMIT}]])
    with pytest.raises(TrueNASJobError) as exc:
        await client.upgrade_app("immich")
    assert exc.value.rate_limited
    assert not TrueNASJobError("app.upgrade", "disk full").rate_limited


def _entity(hass: HomeAssistant, client: MagicMock) -> TrueNASAppUpdateEntity:
    coordinator = MagicMock()
    coordinator.client = client
    coordinator.data.apps = []
    coordinator.async_request_refresh = AsyncMock()
    coordinator.config_entry.entry_id = "entry"
    coordinator.config_entry.async_create_background_task = lambda hass, coro, name: (
        hass.async_create_background_task(coro, name)
    )
    entity = TrueNASAppUpdateEntity.__new__(TrueNASAppUpdateEntity)
    entity.coordinator = coordinator
    entity.hass = hass
    entity._app_name = "immich"
    entity._installing = False
    entity._recovery_task = None
    entity.async_write_ha_state = MagicMock()  # type: ignore[method-assign]
    return entity


async def test_rate_limited_upgrade_recovers_in_background(hass: HomeAssistant) -> None:
    client = MagicMock()
    client.upgrade_app = AsyncMock(side_effect=TrueNASJobError("app.upgrade", RATE_LIMIT))
    client.get_app_state = AsyncMock(return_value="STOPPED")
    client.pull_app_images = AsyncMock(
        side_effect=[TrueNASJobError("app.pull_images", "toomanyrequests"), None]
    )
    client.start_app = AsyncMock()
    entity = _entity(hass, client)

    with patch.object(update_module, "RATE_LIMIT_RETRY_DELAYS", (0, 0, 0)):
        await entity.async_install(None, False)  # does not raise
        assert entity.in_progress
        task = entity._recovery_task
        assert task is not None
        await task

    assert client.pull_app_images.await_count == 2
    client.start_app.assert_awaited_once_with("immich", wait=True)
    assert not entity.in_progress


async def test_recovery_gives_up_with_notification(hass: HomeAssistant) -> None:
    client = MagicMock()
    client.upgrade_app = AsyncMock(side_effect=TrueNASJobError("app.upgrade", RATE_LIMIT))
    client.get_app_state = AsyncMock(return_value="STOPPED")
    client.pull_app_images = AsyncMock(
        side_effect=TrueNASJobError("app.pull_images", "toomanyrequests")
    )
    client.start_app = AsyncMock()
    entity = _entity(hass, client)

    with (
        patch.object(update_module, "RATE_LIMIT_RETRY_DELAYS", (0, 0)),
        patch.object(update_module.persistent_notification, "async_create") as notify,
    ):
        await entity.async_install(None, False)
        assert entity._recovery_task is not None
        await entity._recovery_task
        await asyncio.sleep(0)

    notify.assert_called_once()
    client.start_app.assert_not_awaited()
    assert not entity.in_progress


async def test_other_upgrade_failures_are_raised(hass: HomeAssistant) -> None:
    client = MagicMock()
    client.upgrade_app = AsyncMock(side_effect=TrueNASJobError("app.upgrade", "disk full"))
    entity = _entity(hass, client)

    with pytest.raises(TrueNASJobError):
        await entity.async_install(None, False)
    assert entity._recovery_task is None
    assert not entity.in_progress
