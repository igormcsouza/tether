"""Automatic fold window (#205): fold just enough, oldest first; --fold-after N keeps the cliff.

Scripted (the proxy replies; the model is never called).
"""

from __future__ import annotations

import json
import re

from e2e.conftest import Tether

BIG = [f"bash python3 -c \"print('y'*{1200 + i})\"" for i in range(9)]  # distinct: no stall


def _folded(req: dict) -> list[int]:
    return [int(n) for n in re.findall(r"\[obs_(\d+) folded", json.dumps(req["messages"]))]


def _run(tether: Tether, chaos, *flags: str) -> list[list[int]]:
    chaos.requests.clear()
    chaos.script(*BIG, ("done", "ok"))
    d = tether.run(
        "fold", "--tools", "bash", "--context-tokens", "4000", "--max-steps", "12", *flags
    )
    assert d["rc"] == 0, d
    return [_folded(r) for r in chaos.requests]


def test_auto_folds_a_small_oldest_prefix_explicit_keeps_the_cliff(tether: Tether, chaos) -> None:
    auto = _run(tether, chaos)
    explicit = _run(tether, chaos, "--fold-after", "2")
    assert auto[0] == [] and auto[1] == [], "small histories fold nothing"
    last_auto, last_explicit = auto[-1], explicit[-1]
    assert last_auto, f"auto must fold once over half the window: {auto}"
    assert len(last_auto) < len(last_explicit), (auto, explicit)
    assert last_auto == sorted(last_auto) and last_auto == list(
        range(last_auto[0], last_auto[0] + len(last_auto))
    ), f"auto folds a contiguous oldest prefix: {last_auto}"
    first = next(i for i, f in enumerate(auto) if f)
    assert len(auto[first]) < len(explicit[first]), (
        f"no cliff at the crossing: auto {auto[first]} vs explicit {explicit[first]}"
    )
    assert all(len(a) <= len(e) for a, e in zip(auto, explicit, strict=False)), (auto, explicit)
