"""Scrub state, network traffic, UPS readings, reboot reasons and alert levels."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from custom_components.truenas_ws.api import TrueNASWebSocketClient
from custom_components.truenas_ws.binary_sensor import SYSTEM_BINARY_SENSORS
from custom_components.truenas_ws.coordinator import TrueNASDataUpdateCoordinator
from custom_components.truenas_ws.models import Alert, PoolInfo, TrueNASData
from custom_components.truenas_ws.sensor import _alert_attrs, _scrub_progress, _scrub_state

MS = 1_793_535_187_000  # 2026-11-01, epoch milliseconds as TrueNAS sends them


def _pool(name: str = "tank", **scan: Any) -> PoolInfo:
    return PoolInfo.from_api({"id": 1, "name": name, "scan": scan or None})


def _client(response: Any) -> TrueNASWebSocketClient:
    client = TrueNASWebSocketClient(host="nas", api_key="key", session=MagicMock())
    client._send_request = AsyncMock(return_value=response)  # type: ignore[method-assign]
    return client


def test_scrub_states() -> None:
    finished = _pool(function="SCRUB", state="FINISHED", end_time={"$date": MS}, errors=0)
    assert _scrub_state(finished) == "finished"
    assert _scrub_progress(finished) == 100.0
    assert finished.last_scrub is not None and finished.last_scrub.year == 2026

    running = _pool(function="SCRUB", state="SCANNING", percentage=42.37, pause=None)
    assert _scrub_state(running) == "scrubbing"
    assert _scrub_progress(running) == 42.4
    assert running.last_scrub is None

    paused = _pool(function="SCRUB", state="SCANNING", percentage=10, pause={"$date": MS})
    assert _scrub_state(paused) == "paused"
    assert _scrub_state(_pool(function="RESILVER", state="SCANNING")) == "resilvering"
    assert _scrub_state(_pool()) == "none"
    assert _scrub_progress(_pool()) is None


def test_last_scrub_survives_a_new_scrub() -> None:
    before = [_pool(function="SCRUB", state="FINISHED", end_time={"$date": MS})]
    during = [_pool(function="SCRUB", state="SCANNING", percentage=5)]
    carried = TrueNASDataUpdateCoordinator._carry_last_scrub(during, before)
    assert carried[0].last_scrub == before[0].last_scrub
    assert carried[0].scan.state == "SCANNING"


async def test_live_reporting_traffic_and_ups() -> None:
    report = [
        {
            "name": "interface",
            "identifier": "eno2",
            "legend": ["time", "received", "sent"],
            "data": [[1, 30.5, 2.0], [2, None, None]],
        },
        {"name": "upscharge", "legend": ["time", "charge"], "data": [[1, 100]]},
        {"name": "upsruntime", "legend": ["time", "runtime"], "data": [[1, 1575]]},
        {"name": "upsload", "legend": ["time", "load"], "data": [[1, 19]]},
        {"name": "upsfrequency", "legend": ["time", "frequency", "nominal"], "data": [[1, 0, 0]]},
    ]
    traffic, ups = await _client(report).get_live_reporting(["eno2"], ups=True)
    # The trailing all-null row is skipped in favour of the last real reading.
    assert traffic["eno2"].received == 30.5
    assert traffic["eno2"].sent == 2.0
    assert ups is not None
    assert (ups.charge, ups.runtime, ups.load) == (100.0, 1575.0, 19.0)
    # 0 Hz and a missing voltage graph mean "not reported".
    assert ups.frequency is None
    assert ups.input_voltage is None


async def test_live_reporting_without_ups_or_interfaces() -> None:
    client = _client([])
    assert await client.get_live_reporting([], ups=False) == ({}, None)
    client._send_request.assert_not_awaited()  # type: ignore[attr-defined]


async def test_reboot_reasons() -> None:
    info = {"boot_id": "x", "reboot_required_reasons": [{"code": "FIPS", "reason": "FIPS"}]}
    assert await _client(info).get_reboot_required_reasons() == ["FIPS"]
    empty = {"boot_id": "x", "reboot_required_reasons": []}
    assert await _client(empty).get_reboot_required_reasons() == []


def _alert(level: str, dismissed: bool = False) -> Alert:
    return Alert.from_api({"id": level, "level": level, "formatted": level, "dismissed": dismissed})


def test_alert_levels_and_critical_sensor() -> None:
    data = TrueNASData(
        alerts=[_alert("WARNING"), _alert("ALERT"), _alert("EMERGENCY", dismissed=True)]
    )
    attrs = _alert_attrs(data)
    assert attrs["highest_level"] == "ALERT"
    assert attrs["alert"] == 1
    assert attrs["warning"] == 1
    assert attrs["emergency"] == 0

    critical = next(d for d in SYSTEM_BINARY_SENSORS if d.key == "critical_alerts")
    assert critical.value_fn(data) is True
    assert critical.value_fn(TrueNASData(alerts=[_alert("WARNING")])) is False

    reboot = next(d for d in SYSTEM_BINARY_SENSORS if d.key == "reboot_required")
    assert reboot.value_fn(TrueNASData()) is None
    assert reboot.value_fn(TrueNASData(reboot_required_reasons=[])) is False
    assert reboot.value_fn(TrueNASData(reboot_required_reasons=["FIPS"])) is True
