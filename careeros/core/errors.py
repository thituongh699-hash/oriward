"""Shared error types for the Career Twin Core.

All of them subclass ``ValueError`` so the existing CLI error boundary
(``except (ValueError, OSError, JSONDecodeError)``) keeps working unchanged.
"""
from __future__ import annotations


class CoreError(ValueError):
    """A Core rule was violated; the caller must not retry blindly."""


class ConflictError(CoreError):
    """An existing live assertion disagrees; an explicit revise is required."""


class NotFoundError(CoreError):
    """Referenced record does not exist."""
