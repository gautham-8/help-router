"""Integration fixtures: fresh in-memory state per test.

Kept out of the top-level conftest on purpose: Hypothesis rejects function-scoped
fixtures on ``@given`` tests, and the property tests are stateless anyway.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.config import get_settings
from app.main import reset_state


@pytest.fixture(autouse=True)
def fresh_state() -> Iterator[None]:
    get_settings.cache_clear()
    reset_state()
    yield
    get_settings.cache_clear()
    reset_state()
