"""WebSocket API client for TrueNAS JSON-RPC 2.0."""

from __future__ import annotations

import asyncio
import logging
import ssl
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
        self._next_id = 0
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._listen_task: asyncio.Task[None] | None = None
        self._connected = False
        self._collection_callbacks: dict[
            str, list[Any]
        ] = {}

    @property
    def connected(self) -> bool:
        """Return True if connected."""
        return self._connected

    @property
    def ws_url(self) -> str:
        """Return the WebSocket URL."""
        scheme = "wss" if self._verify_ssl else "ws"
        return f"{scheme}://{self._host}/api/current"

    async def connect(self) -> None:
        """Connect to TrueNAS WebSocket and authenticate."""
        if self._connected and self._ws is not None and not self._ws.closed:
            return

        await self._close_ws()

        ssl_context: ssl.SSLContext | bool | None = None
        if not self._verify_ssl:
            ssl_context = False

        try:
            self._ws = await self._session.ws_connect(
                self.ws_url,
                ssl=ssl_context,
                heartbeat=30,
                timeout=aiohttp.ClientWSTimeout(ws_close=10),
            )
        except (
            aiohttp.WSServerHandshakeError,
            aiohttp.ClientError,
            TimeoutError,
            OSError,
        ) as err:
            raise TrueNASConnectionError(
                f"Cannot connect to {self._host}: {err}"
            ) from err

        self._connected = True
        self._listen_task = asyncio.create_task(self._listen())

        await self._authenticate()

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

    async def _authenticate(self) -> None:
        """Authenticate with API key."""
        try:
            result = await self._send_request(
                "auth.login_with_api_key", [self._api_key]
            )
        except TrueNASAPIError as err:
            await self._close_ws()
            raise TrueNASAuthenticationError(
                f"Authentication failed: {err}"
            ) from err

        if result is not True:
            await self._close_ws()
            raise TrueNASAuthenticationError("Authentication failed: invalid API key")

    async def _send_request(
        self, method: str, params: list[Any] | None = None
    ) -> Any:
        """Send a JSON-RPC 2.0 request and wait for response."""
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
        """Handle an incoming JSON-RPC message."""
        if "id" in data and data["id"] is not None:
            future = self._pending.pop(data["id"], None)
            if future is not None and not future.done():
                if "error" in data:
                    error = data["error"]
                    msg = error.get("message", str(error)) if isinstance(
                        error, dict
                    ) else str(error)
                    future.set_exception(TrueNASAPIError(msg))
                else:
                    future.set_result(data.get("result"))
        elif data.get("method") == "collection_update":
            params = data.get("params", {})
            collection = params.get("collection", "")
            callbacks = self._collection_callbacks.get(collection, [])
            for callback in callbacks:
                try:
                    callback(collection, params)
                except Exception:
                    _LOGGER.exception(
                        "Error in collection_update callback for %s", collection
                    )

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
        """Get real-time system statistics."""
        reporting_data: dict[str, Any] = {}
        memory_data: dict[str, Any] = {}

        try:
            reporting_result = await self._send_request(
                "reporting.realtime"
            )
            if isinstance(reporting_result, dict):
                reporting_data = reporting_result

                if "cpu" in reporting_data:
                    cpu_raw = reporting_data["cpu"]
                    if isinstance(cpu_raw, dict):
                        total_usage = 0.0
                        count = 0
                        for key, val in cpu_raw.items():
                            if key.isdigit() and isinstance(val, dict):
                                total_usage += float(val.get("usage", 0))
                                count += 1
                            elif key == "usage":
                                total_usage = float(val)
                                count = 1
                                break
                        if count > 0:
                            reporting_data["cpu"] = {"usage": total_usage / count}

                if "memory" in reporting_data:
                    mem = reporting_data["memory"]
                    if isinstance(mem, dict):
                        memory_data = {
                            "total": mem.get("physmem", mem.get("total", 0)),
                            "used": mem.get("used", 0),
                            "free": mem.get("free", 0),
                            "arc_size": mem.get("arc_size", 0),
                            "arc_max": mem.get("arc_max", 0),
                        }

                        total = int(memory_data.get("total", 0))
                        used = int(memory_data.get("used", 0))
                        arc_size = int(memory_data.get("arc_size", 0))
                        arc_max = int(memory_data.get("arc_max", 0))

                        if arc_max > 0 and arc_size > 0:
                            try:
                                arc_stats = await self._send_request(
                                    "cache.get", ["arc_stats"]
                                )
                                if isinstance(arc_stats, dict):
                                    hits = int(arc_stats.get("hits", 0))
                                    misses = int(arc_stats.get("misses", 0))
                                    total_acc = hits + misses
                                    if total_acc > 0:
                                        memory_data["arc_hit_ratio"] = round(
                                            hits / total_acc * 100, 1
                                        )
                            except (TrueNASAPIError, TrueNASTimeoutError):
                                if total > 0 and used > 0 and arc_size > 0:
                                    memory_data["arc_hit_ratio"] = 0

                if "cpu_temp" not in reporting_data:
                    try:
                        temps = await self._send_request(
                            "disk.temperatures", []
                        )
                        if isinstance(temps, dict):
                            reporting_data["cpu_temp"] = None
                    except (TrueNASAPIError, TrueNASTimeoutError):
                        pass

        except (TrueNASAPIError, TrueNASTimeoutError) as err:
            _LOGGER.debug("Failed to get realtime reporting: %s", err)

        return SystemStats.from_api(
            reporting_data=reporting_data,
            memory_data=memory_data,
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
        """Get ZFS pool information."""
        result = await self._send_request("pool.query")
        return [PoolInfo.from_api(p) for p in result]

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

    async def get_alerts(self) -> list[Alert]:
        """Get system alerts."""
        result = await self._send_request("alert.list")
        return [Alert.from_api(a) for a in result]

    async def check_update(self) -> UpdateInfo:
        """Check for system updates."""
        try:
            result = await self._send_request("update.check_available")
            return UpdateInfo.from_api(result)
        except TrueNASAPIError as err:
            _LOGGER.debug("Failed to check updates: %s", err)
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
        await self._send_request("system.reboot")

    async def shutdown(self) -> None:
        """Shutdown the system."""
        await self._send_request("system.shutdown")

    async def create_snapshot(self, dataset: str, name: str) -> None:
        """Create a ZFS snapshot."""
        await self._send_request(
            "zfs.snapshot.create",
            [{"dataset": dataset, "name": name}],
        )
