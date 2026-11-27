"""`web fetch` of a JSON reply: JSON Pointer paths and an outline when it is too big (#173 gap
hunt: a 6 MB PyPI reply cost qwen3.5:9b 20 steps of `--from` guesses). Fakes only, no network."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from tether.tools.web import json_view, make_web_tool

URL = "https://pypi.org/pypi/ruff/json"
DATA = {
    "info": {"name": "ruff", "version": "0.17.6", "description": "x" * 9000},
    "releases": {f"0.{i}.0": [{"upload_time": f"2026-01-{i:02d}"}] for i in range(1, 41)},
    "a/b": 1,
}


@pytest.fixture(autouse=True)
def _fake(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TETHER_WEB_ALLOW_PRIVATE", "1")
    orig = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "application/json"}, json=DATA)

    def patched(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(handler)
        return orig(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched)


async def test_a_big_reply_shows_an_outline_with_the_next_command() -> None:
    out = await make_web_tool().invoke(["fetch", URL])
    assert out.startswith("[JSON at #/: {3 keys}")
    assert '"info": {3 keys}' in out and '"releases": {40 keys}' in out
    assert f"Open one: web fetch {URL}#/info" in out  # a real key as the example
    assert len(out) < 400


async def test_a_path_opens_a_value_and_lists_keep_first_and_last() -> None:
    tool = make_web_tool(max_fetch_chars=900)
    assert await tool.invoke(["fetch", f"{URL}#/info/version"]) == '[#/info/version]\n"0.17.6"'
    out = await tool.invoke(["fetch", f"{URL}#/releases"])
    assert '"0.1.0": [1 items]' in out and '"0.40.0": [1 items]' in out  # the last 5 always
    assert "... 10 more keys ..." in out
    last = await tool.invoke(["fetch", f"{URL}#/releases/0.40.0/-1/upload_time"])
    assert last.endswith('"2026-01-40"')
    assert (await tool.invoke(["fetch", f"{URL}#/a~1b"])).endswith("\n1")  # RFC 6901 escape


async def test_a_wrong_path_names_what_is_there() -> None:
    tool = make_web_tool()
    out = await tool.invoke(["fetch", f"{URL}#/info/nope"])
    assert out.startswith("Error: `nope` not found at #/info (keys: name, version, description)")
    assert f"Instead: web fetch {URL}#/info/name" in out
    assert "0 to 0" in await tool.invoke(["fetch", f"{URL}#/releases/0.1.0/5"])
    assert "a value:" in await tool.invoke(["fetch", f"{URL}#/info/name/x"])


async def test_from_still_searches_the_raw_text() -> None:
    out = await make_web_tool().invoke(["fetch", URL, "--from", '"version"'])
    assert out.startswith('"version":"0.17.6"')


def test_json_view_leaves_non_json_and_big_lists() -> None:
    assert json_view("<html>", "/x", URL, 100) is None
    big = json.dumps(list(range(500)))
    out = json_view(big, "", URL, 100) or ""
    assert out.startswith("[JSON at #/: [500 items]") and "499: 499" in out


async def test_loose_paths_qwen_typed_resolve() -> None:
    """web A/B: `#info`, `#info/version`, `#info#version` all fell back to the root outline, and
    qwen3.5:9b re-fetched it 25 times until its 30 steps ran out."""
    tool = make_web_tool()
    for path in ("info/version", "info#version", "info.version", "/info/version/"):
        assert await tool.invoke(["fetch", f"{URL}#{path}"]) == '[#/info/version]\n"0.17.6"'
    assert (await tool.invoke(["fetch", f"{URL}#releases#0.40.0#-1"])).startswith(
        "[#/releases/0.40.0/-1]"
    )
    assert json_view('{"a": []}', "a/0", URL, 100) == (
        "Error: `0` not found at #/a (an empty list). Instead: web fetch " + URL + "#/a/0"
    )
