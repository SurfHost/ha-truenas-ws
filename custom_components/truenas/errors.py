"""Exceptions for the TrueNAS integration."""

from __future__ import annotations

from homeassistant.exceptions import HomeAssistantError


class TrueNASError(HomeAssistantError):
    """Base exception for TrueNAS."""


class TrueNASConnectionError(TrueNASError):
    """Cannot connect to TrueNAS."""


class TrueNASAuthenticationError(TrueNASError):
    """Authentication failed."""


class TrueNASAPIError(TrueNASError):
    """API returned an error."""


class TrueNASTimeoutError(TrueNASError):
    """Request timed out."""
