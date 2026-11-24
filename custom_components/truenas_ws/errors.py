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


class TrueNASJobError(TrueNASAPIError):
    """A TrueNAS background job ended in FAILED or ABORTED."""

    def __init__(self, method: str, error: str) -> None:
        """Keep the job's own error text so callers can inspect it."""
        super().__init__(f"{method} failed: {error}")
        self.method = method
        self.error = error

    @property
    def rate_limited(self) -> bool:
        """Return True when the job failed on a container registry pull limit.

        TrueNAS reports it as "It appears you have reached your pull rate
        limit"; the registry itself answers "toomanyrequests".
        """
        text = self.error.lower()
        return "pull rate limit" in text or "toomanyrequests" in text
