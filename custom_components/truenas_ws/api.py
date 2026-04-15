"""WebSocket API client for TrueNAS SCALE (JSON-RPC 2.0)."""

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


def _parse_update_status(result: Any) -> UpdateInfo:
    """Parse an ``update.status`` response into an ``UpdateInfo``.

    TrueNAS SCALE 25+ returns::

        {
          "code": "NORMAL" | "ERROR",
          "status": {
            "current_version": {"train": ..., "profile": ..., ...},
            "new_version": {"version": ..., "release_notes": ..., ...} | null,
          } | null,
          "error": {...} | null,
        }

    An update is available when ``status.new_version`` is not null.
    """
    empty = UpdateInfo(
        available=False, version=None, changelog=None, current_version=None
    )
    if not isinstance(result, dict):
        return empty

    status_obj = result.get("status")
    if not isinstance(status_obj, dict):
        return empty

    new_ver = status_obj.get("new_version")
    current_ver = status_obj.get("current_version")

    current_version: str | None = None
    if isinstance(current_ver, dict):
        current_version = current_ver.get("version") or current_ver.get("train")

    if not isinstance(new_ver, dict):
        return UpdateInfo(
            available=False,
            version=None,
            changelog=None,
            current_version=current_version,
        )

    return UpdateInfo(
        available=True,
        version=new_ver.get("version"),
        changelog=new_ver.get("release_notes") or new_ver.get("release_notes_url"),
        current_version=current_version,
    )


class TrueNASWebSocketClient:
    """JSON-RPC 2.0 WebSocket client for TrueNAS SCALE 25+."""

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
        self._next_id = 0
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._listen_task: asyncio.Task[None] | None = None
        self._connected = False
        self._realtime_logged = False  # one-shot diagnostic

    @property
    def connected(self) -> bool:
        """Return True if connected."""
        return self._connected

    def _build_urls(self) -> list[str]:
        """Return WebSocket URLs to try (wss preferred, ws as fallback)."""
        urls = [f"wss://{self._host}/api/current"]
        if not self._verify_ssl:
            urls.append(f"ws://{self._host}/api/current")
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
                self._listen_task = asyncio.create_task(self._listen())
                _LOGGER.debug("Connected to %s", url)
                await self._authenticate()
                return
            except TrueNASAuthenticationError:
                # Credentials are wrong — no point trying other URLs
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

        raise TrueNASConnectionError(
            f"Cannot connect to {self._host}: {last_err}"
        )

    async def disconnect(self) -> None:
        """Disconnect from TrueNAS."""
        await self._close_ws()

    async def _close_ws(self) -> None:
        """Close WebSocket and cancel pending requests."""
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

    async def _authenticate(self) -> None:
        """Authenticate with the API key."""
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

    async def _send_request(
        self, method: str, params: list[Any] | None = None
    ) -> Any:
        """Send a JSON-RPC 2.0 request and wait for the response."""
        if not self._connected or self._ws is None or self._ws.closed:
            raise TrueNASConnectionError("Not connected")

        request_id = self._next_id
        self._next_id += 1

        message: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
            "id": request_id,
        }
        if params is not None:
            message["params"] = params

        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        self._pending[request_id] = future

        try:
            await self._ws.send_json(message)
        except (ConnectionError, TypeError) as err:
            self._pending.pop(request_id, None)
            raise TrueNASConnectionError(f"Failed to send request: {err}") from err

        try:
            return await asyncio.wait_for(future, timeout=REQUEST_TIMEOUT)
        except TimeoutError:
            self._pending.pop(request_id, None)
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
                    _LOGGER.error("WebSocket error: %s", self._ws.exception())
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
        """Handle an incoming JSON-RPC 2.0 message."""
        if "id" not in data or data["id"] is None:
            return

        future = self._pending.pop(data["id"], None)
        if future is None or future.done():
            return

        if "error" in data:
            error = data["error"]
            err_msg = (
                error.get("message", str(error)) if isinstance(error, dict)
                else str(error)
            )
            future.set_exception(TrueNASAPIError(err_msg))
        else:
            future.set_result(data.get("result"))

    # ── Typed API methods ──────────────────────────────────────────

    async def get_system_info(self) -> SystemInfo:
        """Get system information."""
        result = await self._send_request("system.info")
        return SystemInfo.from_api(result)

    async def get_system_stats(self) -> SystemStats:
        """Get real-time system statistics."""
        cpu_usage = 0.0
        mem_total = 0
        mem_used = 0
        mem_free = 0
        arc_size = 0
        arc_max = 0
        cpu_temp: float | None = None

        # Primary source: reporting.realtime (TrueNAS SCALE live stats)
        try:
            result = await self._send_request("reporting.realtime")
        except (TrueNASAPIError, TrueNASTimeoutError):
            result = None

        # One-shot diagnostic log so we can see what this particular TrueNAS
        # returns. Only fires until we've logged one successful response.
        if result is not None and not self._realtime_logged:
            keys = list(result.keys()) if isinstance(result, dict) else type(result).__name__
            _LOGGER.warning("reporting.realtime keys: %s | raw: %s", keys, result)
            self._realtime_logged = True

        if isinstance(result, dict):
            cpu_raw = result.get("cpu", {})
            if isinstance(cpu_raw, dict):
                if "usage" in cpu_raw:
                    cpu_usage = float(cpu_raw["usage"])
                elif "average" in cpu_raw and isinstance(cpu_raw["average"], dict):
                    # Newer SCALE: cpu.average = {usage: ..., user: ..., system: ...}
                    cpu_usage = float(cpu_raw["average"].get("usage", 0))
                else:
                    core_usages = [
                        float(v.get("usage", 0))
                        for k, v in cpu_raw.items()
                        if k.isdigit() and isinstance(v, dict)
                    ]
                    if core_usages:
                        cpu_usage = sum(core_usages) / len(core_usages)
            elif isinstance(cpu_raw, (int, float)):
                cpu_usage = float(cpu_raw)

            virtual_mem = result.get("virtual_memory")
            if isinstance(virtual_mem, dict):
                # Newer SCALE: virtual_memory = {total, available, used, free, ...}
                mem_total = int(virtual_mem.get("total", 0))
                mem_used = int(virtual_mem.get("used", 0))
                mem_free = int(
                    virtual_mem.get("available", virtual_mem.get("free", 0))
                )

            mem_raw = result.get("memory", {})
            if isinstance(mem_raw, dict):
                if mem_total == 0:
                    mem_total = int(mem_raw.get("physmem", mem_raw.get("total", 0)))
                classes = mem_raw.get("classes")
                if isinstance(classes, dict):
                    if mem_used == 0:
                        mem_used = (
                            int(classes.get("page_tables", 0))
                            + int(classes.get("arc", 0))
                            + int(classes.get("apps", 0))
                        )
                    if mem_free == 0:
                        mem_free = int(classes.get("free", 0))
                    arc_size = int(classes.get("arc", 0))
                else:
                    if mem_used == 0:
                        mem_used = int(mem_raw.get("used", 0))
                    if mem_free == 0:
                        mem_free = int(mem_raw.get("free", 0))
                    arc_size = int(mem_raw.get("arc_size", 0))
                    arc_max = int(mem_raw.get("arc_max", 0))

            cpu_temp_raw = result.get("cpu_temp")
            if isinstance(cpu_temp_raw, (int, float)):
                cpu_temp = float(cpu_temp_raw)

        # Fallback for total memory via system.info
        sysinfo: dict[str, Any] | None = None
        if mem_total == 0:
            try:
                sysinfo_raw = await self._send_request("system.info")
                if isinstance(sysinfo_raw, dict):
                    sysinfo = sysinfo_raw
                    mem_total = int(sysinfo.get("physmem", 0))
            except (TrueNASAPIError, TrueNASTimeoutError):
                pass

        # Fallback CPU usage from load average if realtime gave us nothing
        if cpu_usage == 0 and sysinfo is not None:
            cores = int(sysinfo.get("cores", 1)) or 1
            loadavg = sysinfo.get("loadavg") or []
            if loadavg:
                cpu_usage = min(round(float(loadavg[0]) / cores * 100, 1), 100.0)

        # Fill in derived values
        if mem_total > 0 and mem_used > 0 and mem_free == 0:
            mem_free = mem_total - mem_used
        if mem_total > 0 and mem_free > 0 and mem_used == 0:
            mem_used = mem_total - mem_free

        mem_pct = (
            round(mem_used / mem_total * 100, 1)
            if mem_total > 0 and mem_used > 0
            else 0.0
        )

        # ARC size from reporting graph if realtime didn't provide it
        if arc_size == 0:
            arc_size = await self._fetch_latest_graph_value("arcsize")

        # CPU temperature fallback
        if cpu_temp is None:
            cpu_temp = await self._fetch_avg_graph_value("cputemp")

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

    async def _fetch_latest_graph_value(self, graph_name: str) -> int:
        """Return the latest non-null integer value from a reporting graph."""
        now = int(time.time())
        try:
            report = await self._send_request(
                "reporting.get_data",
                [[{"name": graph_name}], {"start": now - 120, "end": now}],
            )
        except (TrueNASAPIError, TrueNASTimeoutError):
            return 0

        if not isinstance(report, list) or not report:
            return 0
        data_points = report[0].get("data", []) if isinstance(report[0], dict) else []
        for row in reversed(data_points):
            if isinstance(row, list) and len(row) >= 2 and row[1] is not None:
                return int(row[1])
        return 0

    async def _fetch_avg_graph_value(self, graph_name: str) -> float | None:
        """Return the latest averaged float value across graph columns."""
        now = int(time.time())
        try:
            report = await self._send_request(
                "reporting.get_data",
                [[{"name": graph_name}], {"start": now - 120, "end": now}],
            )
        except (TrueNASAPIError, TrueNASTimeoutError):
            return None

        if not isinstance(report, list) or not report:
            return None
        data_points = report[0].get("data", []) if isinstance(report[0], dict) else []
        for row in reversed(data_points):
            if isinstance(row, list) and len(row) > 1:
                vals = [v for v in row[1:] if v is not None]
                if vals:
                    return round(sum(vals) / len(vals), 1)
        return None

    async def get_disks(self) -> list[DiskInfo]:
        """Get disk information."""
        result = await self._send_request(
            "disk.query", [[], {"extra": {"pools": True}}]
        )
        return [DiskInfo.from_api(d) for d in result]

    async def get_disk_temperatures(
        self, disk_names: list[str]
    ) -> dict[str, int | None]:
        """Get disk temperatures keyed by disk name.

        ``disk.temperatures`` requires a list of disk names — without it
        the method rejects the call. Results are cached by TrueNAS for
        up to 5 minutes.
        """
        if not disk_names:
            return {}
        try:
            result = await self._send_request("disk.temperatures", [disk_names])
        except (TrueNASAPIError, TrueNASTimeoutError):
            return {}
        return dict(result) if isinstance(result, dict) else {}

    async def get_pools(self) -> list[PoolInfo]:
        """Get ZFS pool information including the boot pool."""
        result = await self._send_request("pool.query")
        pools = [PoolInfo.from_api(p) for p in result]

        try:
            boot = await self._send_request("boot.get_state")
        except (TrueNASAPIError, TrueNASTimeoutError):
            boot = None

        if isinstance(boot, dict) and boot.get("name"):
            boot_pool = PoolInfo.from_boot_api(boot)
            if not any(p.name == boot_pool.name for p in pools):
                pools.append(boot_pool)

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
        result = await self._send_request("interface.query")
        return [NetworkInterface.from_api(n) for n in result]

    async def get_services(self) -> list[ServiceInfo]:
        """Get service information."""
        result = await self._send_request("service.query")
        return [ServiceInfo.from_api(s) for s in result]

    async def get_apps(self) -> list[AppInfo]:
        """Get application information."""
        try:
            result = await self._send_request("app.query")
        except TrueNASAPIError:
            return []
        return [AppInfo.from_api(a) for a in result]

    async def get_vms(self) -> list[VMInfo]:
        """Get virtual machine information."""
        try:
            result = await self._send_request("vm.query")
        except TrueNASAPIError:
            return []
        return [VMInfo.from_api(v) for v in result]

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
        except TrueNASAPIError:
            return []
        return [RsyncTask.from_api(r) for r in result]

    async def get_alerts(self) -> list[Alert]:
        """Get system alerts."""
        result = await self._send_request("alert.list")
        return [Alert.from_api(a) for a in result]

    async def check_update(self) -> UpdateInfo:
        """Check for system updates via ``update.status``."""
        try:
            result = await self._send_request("update.status")
        except TrueNASAPIError as err:
            _LOGGER.debug("update.status failed: %s", err)
            return UpdateInfo(
                available=False, version=None, changelog=None, current_version=None
            )
        _LOGGER.debug("update.status response: %s", result)
        return _parse_update_status(result)

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
        await self._send_request("vm.stop", [vm_id, {"force": force}])

    async def start_app(self, app_name: str) -> None:
        """Start an application."""
        await self._send_request("app.start", [app_name])

    async def stop_app(self, app_name: str) -> None:
        """Stop an application."""
        await self._send_request("app.stop", [app_name])

    async def upgrade_app(self, app_name: str) -> None:
        """Upgrade an application to the latest version."""
        await self._send_request("app.upgrade", [app_name])

    async def reboot(self) -> None:
        """Reboot the system."""
        await self._send_system_command("system.reboot")

    async def shutdown(self) -> None:
        """Shut down the system."""
        await self._send_system_command("system.shutdown")

    async def _send_system_command(self, method: str) -> None:
        """Send reboot/shutdown — tolerate the disconnect that follows."""
        if not self._connected or self._ws is None or self._ws.closed:
            raise TrueNASConnectionError("Not connected")

        try:
            await asyncio.wait_for(
                self._send_request(method, ["Home Assistant"]),
                timeout=10.0,
            )
        except (TrueNASConnectionError, TrueNASTimeoutError, TimeoutError):
            # Expected — system disconnects as it reboots/shuts down
            pass

    async def create_snapshot(self, dataset: str, name: str) -> None:
        """Create a ZFS snapshot."""
        await self._send_request(
            "zfs.snapshot.create",
            [{"dataset": dataset, "name": name}],
        )

    async def install_system_update(self) -> None:
        """Download, apply and reboot for the pending system update.

        Uses ``update.run`` — TrueNAS SCALE 25+ job that installs the latest
        version from the current update profile. The WebSocket will
        disconnect as the system reboots.
        """
        if not self._connected or self._ws is None or self._ws.closed:
            raise TrueNASConnectionError("Not connected")

        try:
            await asyncio.wait_for(
                self._send_request("update.run", [{"reboot": True}]),
                timeout=30.0,
            )
        except (TrueNASConnectionError, TrueNASTimeoutError, TimeoutError):
            pass
