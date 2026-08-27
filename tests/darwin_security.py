"""Shared marker for security contracts that require Darwin behavior."""

from __future__ import annotations

from collections.abc import Callable
import sys
from typing import TypeVar
import unittest


DARWIN_SECURITY_ATTRIBUTE = "_codex_darwin_security_contract"
_TestMethod = TypeVar("_TestMethod", bound=Callable[..., object])


def darwin_security_test(method: _TestMethod) -> _TestMethod:
    """Mark and platform-gate one test required by the Darwin CI producer."""

    decorated = unittest.skipUnless(
        sys.platform == "darwin", "Darwin security contract"
    )(method)
    setattr(decorated, DARWIN_SECURITY_ATTRIBUTE, True)
    return decorated
