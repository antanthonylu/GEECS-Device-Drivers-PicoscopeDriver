"""Thin re-export: the real client now lives in ``picoscope_driver.client``.

Kept so existing test imports (``from .geecs_test_client import
GeecsTestClient``) don't need to change, and to make clear the client used
in tests is the exact same one the lab demo scripts use — not a separate
test-only implementation.
"""

from picoscope_driver.client import GeecsClient as GeecsTestClient
from picoscope_driver.client import GeecsCommandError, SubscriptionReader

__all__ = ["GeecsTestClient", "GeecsCommandError", "SubscriptionReader"]
