"""#135 review fixes: ModelResponse positional order; provider docs describe the retry."""

from __future__ import annotations

from pathlib import Path

from tether import ActionCall, ModelResponse


def test_new_field_does_not_shift_positional_arguments() -> None:
    resp = ModelResponse("text", ActionCall(cmd="done"))
    assert resp.action is not None and resp.action.cmd == "done"
    assert resp.empty is False


def test_provider_docs_describe_the_empty_reply_retry() -> None:
    root = Path(__file__).resolve().parents[1]
    providers = (root / "docs" / "reference" / "providers.md").read_text()
    assert "empty" in providers and "think=false" in providers
