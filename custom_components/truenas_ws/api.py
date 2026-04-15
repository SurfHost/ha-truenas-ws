"""WebSocket API client for TrueNAS JSON-RPC 2.0."""

from __future__ import annotations

import asyncio
import logging
import ssl
import time
from typing import Any

import aiohttp

from .errors import (
    TrueNASAPIError,
    TrueNASAuthenticationError,
    TrueNASConnectionError,
    TrueNASTimeoutError,
)
from .models import (
    Alert,
    AppInfo,
    CloudSyncTask,
    DatasetInfo,
    DiskInfo,
    NetworkInterface,
    PoolInfo,
    ReplicationTask,
    RsyncTask,
    ServiceInfo,
    SnapshotTask,
    SystemInfo,
    SystemStats,
    UpdateInfo,
    VMInfo,
)

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = 30.0
RECONNECT_MIN_DELAY = 5.0
RECONNECT_MAX_DELAY = 300.0


def _parse_update_status(result: Any) -> UpdateInfo | None:
    """Parse ``update.status`` response into an ``UpdateInfo``.

    TrueNAS SCALE 25+ wraps the update info in ``{"status": {"code": ..., "new_version": {...}}}``.
    Returns ``None`` if the shape is unrecognised.
    """
    if not isinstance(result, dict):
        return None

    status_obj = result.get("status", result)
    if not isinstance(status_obj, dict):
        return None

    code = str(status_obj.get("code", status_obj.get("status", ""))).upper()
    new_ver = status_obj.get("new_version") or status_obj.get("version")

    available = code in ("AVAILABLE", "UPDATE_AVAILABLE", "REBOOT_REQUIRED")
    version: str | None = None
    changelog: str | None = None

    if isinstance(new_ver, dict):
        version = new_ver.get("version") or new_ver.get("name")
        changelog = new_ver.get("changelog") or new_ver.get("notes")
    elif isinstance(new_ver, str):
        version = new_ver

    if not available and version:
        available = True

    if not available and code == "":
        return None

    return UpdateInfo(
        available=available,
        version=version,
        changelog=changelog or result.get("changelog") or result.get("notes"),
        current_version=result.get("current_version")
        or status_obj.get("current_version"),
    )


class TrueNASWebSocketClient:
    """JSON-RPC 2.0 WebSocket client for TrueNAS."""

    def __init__(
        self,
        host: str,
        api_key: str,
        session: aiohttp.ClientSession,
        *,
        verify_ssl: bool = True,
    ) -> None:
        """Initialize the client."""
        self._host = host
        self._api_key = api_key
        self._session = session
        self._verify_ssl = verify_ssl

        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._ws_url: str = ""
        self._is_legacy: bool = False  # True if using /websocket (DDP)
        self._next_id = 0
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._pending_str: dict[str, asyncio.Future[Any]] = {}
        self._listen_task: asyncio.Task[None] | None = None
        self._connected = False
        self._collection_callbacks: dict[
            str, list[Any]
        ] = {}

    @property
    def connected(self) -> bool:
        """Return True if connected."""
        return self._connected

    def _build_urls(self) -> list[str]:
        """Return WebSocket URLs to try, in order.

        Prefer /api/current (JSON-RPC 2.0) over /websocket (legacy DDP).
        Try both wss:// and ws:// for each endpoint before moving to the next.
        """
        urls: list[str] = [f"wss://{self._host}/api/current"]
        if not self._verify_ssl:
            urls.append(f"ws://{self._host}/api/current")
        urls.append(f"wss://{self._host}/websocket")
        if not self._verify_ssl:
            urls.append(f"ws://{self._host}/websocket")
        return urls

    async def connect(self) -> None:
        """Connect to TrueNAS WebSocket and authenticate."""
        if self._connected and self._ws is not None and not self._ws.closed:
            return

        await self._close_ws()

        ssl_context: ssl.SSLContext | bool | None = None
        if not self._verify_ssl:
            ssl_context = False

        last_err: Exception | None = None
        for url in self._build_urls():
            try:
                _LOGGER.debug("Trying WebSocket connection to %s", url)
                self._ws = await self._session.ws_connect(
                    url,
                    ssl=ssl_context if url.startswith("wss") else None,
                    heartbeat=30,
                    timeout=aiohttp.ClientWSTimeout(ws_close=10),
                )
                self._connected = True
                self._ws_url = url
                self._listen_task = asyncio.create_task(self._listen())
                _LOGGER.debug("Connected to %s", url)

                await self._authenticate()
                return
            except TrueNASAuthenticationError:
                # Auth failed — don't try other URLs, the credentials are wrong
                await self._close_ws()
                raise
            except (
                aiohttp.WSServerHandshakeError,
                aiohttp.ClientError,
                TimeoutError,
                OSError,
            ) as err:
                _LOGGER.debug("Failed to connect to %s: %s", url, err)
                last_err = err
                await self._close_ws()
                continue

        raise TrueNASConnectionError(
            f"Cannot connect to {self._host}: {last_err}"
        )

    async def disconnect(self) -> None:
        """Disconnect from TrueNAS."""
        await self._close_ws()

    async def _close_ws(self) -> None:
        """Close WebSocket and clean up."""
        self._connected = False

        if self._listen_task is not None and not self._listen_task.done():
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
            self._listen_task = None

        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        self._ws = None

        for future in self._pending.values():
            if not future.done():
                future.set_exception(
                    TrueNASConnectionError("WebSocket disconnected")
                )
        self._pending.clear()
        self._pending_str.clear()

    async def _authenticate(self) -> None:
        """Authenticate with API key."""
        self._is_legacy = "/websocket" in self._ws_url

        if self._is_legacy:
            await self._authenticate_legacy()
        else:
            await self._authenticate_jsonrpc()

    async def _authenticate_jsonrpc(self) -> None:
        """Authenticate using JSON-RPC 2.0 (TrueNAS 25.04+)."""
        try:
            result = await self._send_request(
                "auth.login_with_api_key", [self._api_key]
            )
        except TrueNASAPIError as err:
            raise TrueNASAuthenticationError(
                f"Authentication failed: {err}"
            ) from err

        if result is not True:
            raise TrueNASAuthenticationError("Authentication failed: invalid API key")

    async def _authenticate_legacy(self) -> None:
        """Authenticate using legacy DDP protocol (/websocket endpoint)."""
        if self._ws is None or self._ws.closed:
            raise TrueNASConnectionError("Not connected")

        # DDP connect handshake
        await self._ws.send_json({
            "msg": "connect",
            "version": "1",
            "support": ["1"],
        })

        # Wait for "connected" response
        try:
            resp = await asyncio.wait_for(self._ws.receive_json(), timeout=10)
        except TimeoutError as err:
            raise TrueNASConnectionError("DDP handshake timeout") from err

        if resp.get("msg") != "connected":
            _LOGGER.debug("DDP handshake response: %s", resp)
            raise TrueNASConnectionError(f"DDP handshake failed: {resp}")

        # Auth with API key
        auth_id = str(self._next_id)
        self._next_id += 1
        await self._ws.send_json({
            "msg": "method",
            "method": "auth.login_with_api_key",
            "id": auth_id,
            "params": [self._api_key],
        })

        try:
            resp = await asyncio.wait_for(self._ws.receive_json(), timeout=10)
        except TimeoutError as err:
            raise TrueNASAuthenticationError("Auth response timeout") from err

        if resp.get("msg") == "result" and resp.get("result") is True:
            _LOGGER.debug("Legacy DDP authentication successful")
            return

        _LOGGER.debug("Legacy auth response: %s", resp)
        raise TrueNASAuthenticationError(
            f"Authentication failed: {resp.get('error', 'invalid API key')}"
        )

    async def _send_request(
        self, method: str, params: list[Any] | None = None
    ) -> Any:
        """Send a request and wait for response (supports both JSON-RPC 2.0 and DDP)."""
        if not self._connected or self._ws is None or self._ws.closed:
            raise TrueNASConnectionError("Not connected")

        request_id = self._next_id
        self._next_id += 1

        if self._is_legacy:
            # DDP protocol
            str_id = str(request_id)
            message: dict[str, Any] = {
                "msg": "method",
                "method": method,
                "id": str_id,
            }
            if params is not None:
                message["params"] = params
        else:
            # JSON-RPC 2.0 protocol
            str_id = str(request_id)
            message = {
                "jsonrpc": "2.0",
                "method": method,
                "id": request_id,
            }
            if params is not None:
                message["params"] = params

        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        # Store with both int and str key for matching
        self._pending[request_id] = future
        self._pending_str[str_id] = future

        try:
            await self._ws.send_json(message)
        except (ConnectionError, TypeError) as err:
            self._pending.pop(request_id, None)
            self._pending_str.pop(str_id, None)
            raise TrueNASConnectionError(f"Failed to send request: {err}") from err

        try:
            return await asyncio.wait_for(future, timeout=REQUEST_TIMEOUT)
        except TimeoutError:
            self._pending.pop(request_id, None)
            self._pending_str.pop(str_id, None)
            raise TrueNASTimeoutError(
                f"Timeout waiting for response to {method}"
            ) from None

    async def _listen(self) -> None:
        """Listen for incoming WebSocket messages."""
        if self._ws is None:
            return
        try:
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    self._handle_message(msg.json())
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    _LOGGER.error(
                        "WebSocket error: %s", self._ws.exception()
                    )
                    break
                elif msg.type in (
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.CLOSING,
                ):
                    break
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception("WebSocket listener error")
        finally:
            self._connected = False
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(
                        TrueNASConnectionError("WebSocket disconnected")
                    )
            self._pending.clear()

    def _handle_message(self, data: dict[str, Any]) -> None:
        """Handle an incoming message (JSON-RPC 2.0 or DDP)."""
        msg_type = data.get("msg")

        if msg_type == "result":
            # DDP response
            msg_id = data.get("id")
            if msg_id is not None:
                future = self._pending_str.pop(str(msg_id), None)
                # Also clean int pending
                try:
                    self._pending.pop(int(msg_id), None)
                except (ValueError, TypeError):
                    pass
                if future is not None and not future.done():
                    if "error" in data:
                        error = data["error"]
                        err_msg = error.get("message", str(error)) if isinstance(
                            error, dict
                        ) else str(error)
                        future.set_exception(TrueNASAPIError(err_msg))
                    else:
                        future.set_result(data.get("result"))
        elif "id" in data and data["id"] is not None:
            # JSON-RPC 2.0 response
            future = self._pending.pop(data["id"], None)
            if future is not None and not future.done():
                if "error" in data:
                    error = data["error"]
                    err_msg = error.get("message", str(error)) if isinstance(
                        error, dict
                    ) else str(error)
                    future.set_exception(TrueNASAPIError(err_msg))
                else:
                    future.set_result(data.get("result"))
        elif data.get("method") == "collection_update" or msg_type == "changed":
            # Push notification (JSON-RPC or DDP)
            params = data.get("params", data.get("fields", {}))
            collection = data.get("collection", params.get("collection", ""))
            callbacks = self._collection_callbacks.get(collection, [])
            for callback in callbacks:
                try:
                    callback(collection, params)
                except Exception:
                    _LOGGER.exception(
                        "Error in collection_update callback for %s", collection
                    )
        elif msg_type in ("connected", "ping", "pong", "ready", "nosub", "updated"):
            # DDP control messages — ignore
            if msg_type == "ping":
                # Respond to DDP ping
                if self._ws and not self._ws.closed:
                    asyncio.create_task(self._ws.send_json({"msg": "pong"}))

    def register_callback(
        self,
        collection: str,
        callback: Any,
    ) -> None:
        """Register a callback for collection_update notifications."""
        self._collection_callbacks.setdefault(collection, []).append(callback)

    def unregister_callback(
        self,
        collection: str,
        callback: Any,
    ) -> None:
        """Unregister a callback."""
        if collection in self._collection_callbacks:
            try:
                self._collection_callbacks[collection].remove(callback)
            except ValueError:
                pass

    # ── Typed API methods ──────────────────────────────────────────

    async def get_system_info(self) -> SystemInfo:
        """Get system information."""
        result = await self._send_request("system.info")
        return SystemInfo.from_api(result)

    async def get_system_stats(self) -> SystemStats:
        """Get real-time system statistics using multiple API methods."""

        cpu_usage = 0.0
        mem_total = 0
        mem_used = 0
        mem_free = 0
        mem_pct = 0.0
        arc_size = 0
        arc_max = 0
        cpu_temp: float | None = None

        # Try reporting.realtime first
        realtime_worked = False
        try:
            result = await self._send_request("reporting.realtime")
            if isinstance(result, dict):
                realtime_worked = True
                # Log once at warning level for debugging
                # CPU usage
                cpu_raw = result.get("cpu", {})
                if isinstance(cpu_raw, dict):
                    total = 0.0
                    count = 0
                    for key, val in cpu_raw.items():
                        if key.isdigit() and isinstance(val, dict):
                            total += float(val.get("usage", 0))
                            count += 1
                        elif key == "usage":
                            cpu_usage = float(val)
                            count = 0
                            break
                    if count > 0:
                        cpu_usage = total / count

                # Memory from realtime
                mem_raw = result.get("memory", {})
                if isinstance(mem_raw, dict):
                    mem_total = int(mem_raw.get("physmem", mem_raw.get("total", 0)))
                    mem_used = int(mem_raw.get("used", 0))
                    mem_free = int(mem_raw.get("free", 0))
                    arc_size = int(mem_raw.get("arc_size", 0))
                    arc_max = int(mem_raw.get("arc_max", 0))

                    # Some TrueNAS versions put memory under 'classes'
                    if mem_used == 0 and "classes" in mem_raw:
                        classes = mem_raw["classes"]
                        if isinstance(classes, dict):
                            mem_used = int(classes.get("page_tables", 0)) + \
                                       int(classes.get("arc", 0)) + \
                                       int(classes.get("apps", 0))
                            mem_free = int(classes.get("free", 0))
                            arc_size = int(classes.get("arc", 0))

                # CPU temp from realtime
                cpu_temp_raw = result.get("cpu_temp")
                if isinstance(cpu_temp_raw, (int, float)):
                    cpu_temp = float(cpu_temp_raw)

        except (TrueNASAPIError, TrueNASTimeoutError):
            _LOGGER.debug("reporting.realtime not available")

        # Fallback: get system info for total memory and CPU
        if not realtime_worked or mem_total == 0:
            try:
                sysinfo = await self._send_request("system.info")
                if isinstance(sysinfo, dict):
                    if mem_total == 0:
                        mem_total = int(sysinfo.get("physmem", 0))

                    # Calculate CPU usage from load average
                    cores = int(sysinfo.get("cores", 1)) or 1
                    loadavg = sysinfo.get("loadavg", [0])
                    if isinstance(loadavg, list) and loadavg and cpu_usage == 0:
                        cpu_usage = round(float(loadavg[0]) / cores * 100, 1)
                        cpu_usage = min(cpu_usage, 100.0)
            except (TrueNASAPIError, TrueNASTimeoutError):
                pass

        # Fallback: get memory from reporting.get_data
        if mem_used == 0:
            now = int(time.time())
            try:
                mem_report = await self._send_request(
                    "reporting.get_data",
                    [[{"name": "memory"}], {"start": now - 120, "end": now}],
                )
                if isinstance(mem_report, list) and mem_report:
                    report = mem_report[0]
                    if isinstance(report, dict):
                        data_points = report.get("data", [])
                        legend = report.get("legend", [])
                        if data_points:
                            if legend:
                                # Multi-column format with legend
                                # FreeBSD/TrueNAS may use categories like:
                                # time, free, active, inactive, wired, cache,
                                # arc, laundry, buffers, used, etc.
                                FREE_COLS = {"free", "inactive", "laundry"}
                                USED_COLS = {"used", "active", "wired", "cache", "arc", "buffers"}
                                for row in reversed(data_points):
                                    if isinstance(row, list) and len(row) > 1:
                                        if any(v is not None for v in row[1:]):
                                            col_vals: dict[str, float] = {}
                                            for i, col in enumerate(legend):
                                                if i >= len(row) or row[i] is None:
                                                    continue
                                                col_vals[col.lower()] = float(row[i])

                                            # Direct "used" column
                                            if "used" in col_vals:
                                                mem_used = int(col_vals["used"])
                                            else:
                                                # Sum all non-free, non-time columns as "used"
                                                total_used = 0.0
                                                for col_name, val in col_vals.items():
                                                    if col_name in ("time",):
                                                        continue
                                                    if col_name not in FREE_COLS:
                                                        total_used += val
                                                if total_used > 0:
                                                    mem_used = int(total_used)

                                            if "free" in col_vals:
                                                mem_free = int(col_vals["free"])

                                            if "arc" in col_vals and arc_size == 0:
                                                arc_size = int(col_vals["arc"])

                                            break
                            else:
                                # Simple format: [[timestamp, value], ...]
                                # Value is used memory in bytes
                                for row in reversed(data_points):
                                    if isinstance(row, list) and len(row) >= 2:
                                        if row[1] is not None:
                                            mem_used = int(row[1])
                                            if mem_total > 0:
                                                mem_free = mem_total - mem_used
                                            break
            except (TrueNASAPIError, TrueNASTimeoutError):
                _LOGGER.debug("reporting.get_data(memory) not available")

        # Calculate memory percentage and fill in missing values
        if mem_total > 0 and mem_used > 0:
            mem_pct = round(mem_used / mem_total * 100, 1)
            if mem_free == 0:
                mem_free = mem_total - mem_used
        elif mem_total > 0 and mem_free > 0:
            mem_used = mem_total - mem_free
            mem_pct = round(mem_used / mem_total * 100, 1)

        # ARC stats from separate query if not yet populated
        if arc_size == 0:
            now = int(time.time())
            for graph_name in ("arcsize", "zfs_arc_size"):
                if arc_size > 0:
                    break
                try:
                    arc_report = await self._send_request(
                        "reporting.get_data",
                        [[{"name": graph_name}], {"start": now - 120, "end": now}],
                    )
                    if isinstance(arc_report, list) and arc_report:
                        report = arc_report[0]
                        if isinstance(report, dict):
                            data_points = report.get("data", [])
                            if data_points:
                                for row in reversed(data_points):
                                    if isinstance(row, list) and len(row) >= 2:
                                        if row[1] is not None:
                                            arc_size = int(row[1])
                                            break
                except (TrueNASAPIError, TrueNASTimeoutError):
                    pass

        # Try to get CPU temperature
        if cpu_temp is None:
            try:
                now = int(time.time())
                temps = await self._send_request("reporting.get_data", [
                    [{"name": "cputemp"}],
                    {"start": now - 120, "end": now},
                ])
                if isinstance(temps, list) and temps:
                    report = temps[0]
                    if isinstance(report, dict):
                        data_points = report.get("data", [])
                        if data_points:
                            for row in reversed(data_points):
                                if isinstance(row, list) and len(row) > 1:
                                    vals = [v for v in row[1:] if v is not None]
                                    if vals:
                                        cpu_temp = round(sum(vals) / len(vals), 1)
                                        break
            except (TrueNASAPIError, TrueNASTimeoutError):
                _LOGGER.debug("CPU temperature not available")

        return SystemStats(
            cpu_usage=cpu_usage,
            memory_usage_percent=mem_pct,
            memory_used_bytes=mem_used,
            memory_free_bytes=mem_free,
            arc_size=arc_size,
            arc_max=arc_max,
            arc_hit_ratio=0.0,
            cpu_temperature=cpu_temp,
        )

    async def get_disks(self) -> list[DiskInfo]:
        """Get disk information."""
        result = await self._send_request(
            "disk.query",
            [[], {"extra": {"pools": True}}],
        )
        return [DiskInfo.from_api(d) for d in result]

    async def get_disk_temperatures(self) -> dict[str, int | None]:
        """Get disk temperatures."""
        try:
            result = await self._send_request("disk.temperatures", [])
            if isinstance(result, dict):
                return {k: v for k, v in result.items()}
        except (TrueNASAPIError, TrueNASTimeoutError):
            _LOGGER.debug("Failed to get disk temperatures")
        return {}

    async def get_pools(self) -> list[PoolInfo]:
        """Get ZFS pool information including boot pool."""
        result = await self._send_request("pool.query")
        pools = [PoolInfo.from_api(p) for p in result]

        # Add boot pool — pool.query excludes it by default
        try:
            boot = await self._send_request("boot.get_state")
            if isinstance(boot, dict) and boot.get("name"):
                boot_pool = PoolInfo.from_boot_api(boot)
                # Only add if not already in the list
                if not any(p.name == boot_pool.name for p in pools):
                    pools.append(boot_pool)
        except (TrueNASAPIError, TrueNASTimeoutError):
            _LOGGER.debug("boot.get_state not available")

        return pools

    async def get_datasets(self) -> list[DatasetInfo]:
        """Get dataset information."""
        result = await self._send_request(
            "pool.dataset.query",
            [
                [],
                {
                    "extra": {
                        "flat": True,
                        "retrieve_children": True,
                        "properties": [
                            "used",
                            "available",
                            "quota",
                            "type",
                            "mountpoint",
                            "encryption",
                            "comments",
                        ],
                    }
                },
            ],
        )
        return [DatasetInfo.from_api(d) for d in result]

    async def get_network_interfaces(self) -> list[NetworkInterface]:
        """Get network interface information."""
        # Try both API method names
        try:
            result = await self._send_request("interface.query")
        except TrueNASAPIError:
            result = await self._send_request("network.interface.query")

        return [NetworkInterface.from_api(n) for n in result]

    async def get_services(self) -> list[ServiceInfo]:
        """Get service information."""
        result = await self._send_request("service.query")
        return [ServiceInfo.from_api(s) for s in result]

    async def get_apps(self) -> list[AppInfo]:
        """Get application information."""
        try:
            result = await self._send_request("app.query")
            return [AppInfo.from_api(a) for a in result]
        except TrueNASAPIError:
            try:
                result = await self._send_request("chart.release.query")
                return [AppInfo.from_api(a) for a in result]
            except TrueNASAPIError:
                _LOGGER.debug("Apps API not available")
                return []

    async def get_vms(self) -> list[VMInfo]:
        """Get virtual machine information."""
        try:
            result = await self._send_request("vm.query")
            return [VMInfo.from_api(v) for v in result]
        except TrueNASAPIError:
            _LOGGER.debug("VM API not available")
            return []

    async def get_replication_tasks(self) -> list[ReplicationTask]:
        """Get replication task information."""
        result = await self._send_request("replication.query")
        return [ReplicationTask.from_api(r) for r in result]

    async def get_snapshot_tasks(self) -> list[SnapshotTask]:
        """Get periodic snapshot task information."""
        result = await self._send_request("pool.snapshottask.query")
        return [SnapshotTask.from_api(s) for s in result]

    async def get_cloud_sync_tasks(self) -> list[CloudSyncTask]:
        """Get cloud sync task information."""
        result = await self._send_request("cloudsync.query")
        return [CloudSyncTask.from_api(c) for c in result]

    async def get_rsync_tasks(self) -> list[RsyncTask]:
        """Get rsync task information."""
        try:
            result = await self._send_request("rsynctask.query")
            return [RsyncTask.from_api(r) for r in result]
        except TrueNASAPIError:
            _LOGGER.debug("Rsync tasks API not available")
            return []

    async def get_alerts(self) -> list[Alert]:
        """Get system alerts."""
        result = await self._send_request("alert.list")
        return [Alert.from_api(a) for a in result]

    async def check_update(self) -> UpdateInfo:
        """Check for system updates.

        Tries multiple API methods — TrueNAS SCALE versions return different
        shapes for update status.
        """
        # 1. update.status (newer TrueNAS, returns status directly)
        try:
            result = await self._send_request("update.status")
            _LOGGER.warning("update.status response: %s", result)
            info = _parse_update_status(result)
            if info is not None:
                return info
        except TrueNASAPIError as err:
            _LOGGER.debug("update.status not available: %s", err)

        # 2. update.check_available (older method)
        try:
            result = await self._send_request("update.check_available")
            _LOGGER.warning("update.check_available response: %s", result)
            if isinstance(result, dict):
                return UpdateInfo.from_api(result)
        except TrueNASAPIError as err:
            _LOGGER.debug("update.check_available failed: %s", err)

        return UpdateInfo(
            available=False, version=None, changelog=None, current_version=None
        )

    # ── Action methods ──────────────────────────────────────────

    async def start_service(self, service_name: str) -> bool:
        """Start a service."""
        return await self._send_request("service.start", [service_name])

    async def stop_service(self, service_name: str) -> bool:
        """Stop a service."""
        return await self._send_request("service.stop", [service_name])

    async def start_vm(self, vm_id: int) -> None:
        """Start a virtual machine."""
        await self._send_request("vm.start", [vm_id])

    async def stop_vm(self, vm_id: int, force: bool = False) -> None:
        """Stop a virtual machine."""
        await self._send_request("vm.stop", [vm_id, force])

    async def start_app(self, app_name: str) -> None:
        """Start an application."""
        try:
            await self._send_request("app.start", [app_name])
        except TrueNASAPIError:
            await self._send_request("chart.release.scale", [app_name, {"replica_count": 1}])

    async def stop_app(self, app_name: str) -> None:
        """Stop an application."""
        try:
            await self._send_request("app.stop", [app_name])
        except TrueNASAPIError:
            await self._send_request("chart.release.scale", [app_name, {"replica_count": 0}])

    async def reboot(self) -> None:
        """Reboot the system."""
        await self._send_system_command("system.reboot")

    async def shutdown(self) -> None:
        """Shutdown the system."""
        await self._send_system_command("system.shutdown")

    async def _send_system_command(self, method: str) -> None:
        """Send a system command (reboot/shutdown).

        TrueNAS returns a job ID and acts on it asynchronously.
        The WebSocket may disconnect before we receive the response.
        """
        if not self._connected or self._ws is None or self._ws.closed:
            raise TrueNASConnectionError("Not connected")

        try:
            await asyncio.wait_for(
                self._send_request(method, ["Home Assistant"]),
                timeout=10.0,
            )
        except (TrueNASConnectionError, TrueNASTimeoutError, TimeoutError):
            # Expected: system disconnects as it reboots/shuts down
            pass

    async def create_snapshot(self, dataset: str, name: str) -> None:
        """Create a ZFS snapshot."""
        await self._send_request(
            "zfs.snapshot.create",
            [{"dataset": dataset, "name": name}],
        )

    async def install_system_update(self) -> None:
        """Download and apply the pending system update, then reboot.

        TrueNAS returns a job ID and applies the update asynchronously.
        The WebSocket will eventually disconnect as the system reboots.
        """
        if not self._connected or self._ws is None or self._ws.closed:
            raise TrueNASConnectionError("Not connected")

        try:
            await asyncio.wait_for(
                self._send_request("update.update", [{"reboot": True}]),
                timeout=30.0,
            )
        except (TrueNASConnectionError, TrueNASTimeoutError, TimeoutError):
            # Expected: system may disconnect during update/reboot
            pass

    async def upgrade_app(self, app_name: str) -> None:
        """Upgrade a TrueNAS application to the latest version."""
        try:
            await self._send_request("app.upgrade", [app_name])
        except TrueNASAPIError:
            # Fall back to the legacy chart.release API
            await self._send_request("chart.release.upgrade", [app_name])
