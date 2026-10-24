"""Test-wide configuration.

Process environment variables beat ``.env`` files, so pinning these here guarantees the
suite runs against the key-free default backend even if a developer has a local ``.env``.
"""

from __future__ import annotations

import os

os.environ["ANALYZER_BACKEND"] = "browser"
os.environ["DASHBOARD_TOKEN"] = ""
