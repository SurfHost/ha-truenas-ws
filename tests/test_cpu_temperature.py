"""CPU temperature from the reporting graph."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from custom_components.truenas_ws.api import TrueNASWebSocketClient

LEGEND = ["time", "cpu0", "cpu1", "cpu2", "cpu3", "cpu"]


def _client(report: Any) -> TrueNASWebSocketClient:
    client = TrueNASWebSocketClient(host="nas", api_key="key", session=MagicMock())
    client._send_request = AsyncMock(return_value=report)  # type: ignore[method-assign]
    return client


async def test_average_of_latest_row() -> None:
    rows = [[1, 30, 30, 30, 30, 30], [2, 38, 39, 40, 39, 39]]
    client = _client([{"legend": LEGEND, "data": rows}])
    assert await client._fetch_avg_graph_value("cputemp") == 39.0


async def test_placeholder_zeros_are_no_reading() -> None:
    """TrueNAS answers a stalled chart with zero rows and empty aggregations."""
    rows = [[ts, 0, 0, 0, 0, 0] for ts in range(120)]
    report = [{"legend": LEGEND, "data": rows, "aggregations": {"min": {}, "mean": {}}}]
    assert await _client(report)._fetch_avg_graph_value("cputemp") is None


async def test_trailing_zero_rows_fall_back_to_last_real_row() -> None:
    rows = [[1, 38, 39, 38, 39, 38], [2, 0, 0, 0, 0, 0], [3, 0, 0, 0, 0, 0]]
    client = _client([{"legend": LEGEND, "data": rows}])
    assert await client._fetch_avg_graph_value("cputemp") == 38.4
