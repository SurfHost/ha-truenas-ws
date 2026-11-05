"""Shared fixtures for the TrueNAS WS tests."""

from __future__ import annotations

import sys

import pytest

if sys.platform == "win32":
    # HA's test plugin blocks AF_INET sockets, but asyncio on Windows builds its
    # self-pipe from an AF_INET socketpair. Only connections are still limited to
    # 127.0.0.1 via socket_allow_hosts, so real hosts stay blocked.
    import pytest_socket

    pytest_socket.disable_socket = lambda allow_unix_socket=False: None


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load custom_components/ in every test."""
