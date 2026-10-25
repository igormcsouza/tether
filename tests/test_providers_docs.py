"""The providers page is the one canonical copy of how to add a model backend (#60, #62)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "docs" / "reference" / "providers.md").read_text()


def test_location_override_and_trust_rule_are_stated_up_front() -> None:
    head = PAGE[:3500]
    assert "~/.tether/providers.yaml" in head
    assert "TETHER_PROVIDERS" in head
    assert "never read from the workspace" in head


def test_each_kind_has_a_generic_yaml_example() -> None:
    blocks = re.findall(r"```yaml\n(.*?)```", PAGE, re.DOTALL)
    for kind in ("openai", "ollama", "anthropic", "command"):
        assert any(f"kind: {kind}" in b for b in blocks), kind


def test_python_route_and_verification_are_shown() -> None:
    assert "register_provider(" in PAGE and "provider=" in PAGE
    assert re.search(r"^## .*(Verify|verify|Check)", PAGE, re.MULTILINE)
    assert "tether run --model" in PAGE


def test_other_pages_link_instead_of_copying() -> None:
    for rel in ("README.md", "docs/tutorial/agent-interface.md", "docs/extending.md"):
        text = (ROOT / rel).read_text()
        assert "kind: openai" not in text and "kind: command" not in text, rel
        assert "async def generate" not in text, rel  # the Python example lives on the page
        assert "reference/providers" in text or "/providers/" in text, rel
