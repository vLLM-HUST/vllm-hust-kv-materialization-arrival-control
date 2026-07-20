"""Closed parser for the KVPlane prefix-cache write carrier."""

from __future__ import annotations


def allows_prefix_cache_write(value: object) -> bool:
    """Default only absence to engine behavior; malformed controls deny."""
    if value is None:
        return True
    if type(value) is bool:
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "allow", "admit"}:
            return True
        if normalized in {"0", "false", "no", "deny", "skip"}:
            return False
    return False
