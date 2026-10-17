"""Unit tests for tether/__init__.py public exports and version."""

from __future__ import annotations

import tether


def test_version_and_public_exports() -> None:
    """Verify package __version__ and public SDK symbols."""
    assert tether.__version__ == "0.0.3"
    for symbol in tether.__all__:
        assert hasattr(tether, symbol)
