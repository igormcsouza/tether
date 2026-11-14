"""Search refusals and fetch anchors / --from (F2). Fakes only: httpx is mocked, no network."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from tether.tools.web import make_web_tool

REFUSED = (
    "Error: the search engine refused the request (rate limit or bot check). "
    "Instead: wait a minute, fetch a URL you know with `web fetch`, "
    "or set BRAVE_API_KEY, TAVILY_API_KEY or SEARXNG_URL."
)
DOCS = "https://docs.example.org/x"


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TETHER_WEB_ALLOW_PRIVATE", "1")
    for var in ("SEARXNG_URL", "BRAVE_API_KEY", "TAVILY_API_KEY"):
        monkeypatch.delenv(var, raising=False)


def _serve(monkeypatch: pytest.MonkeyPatch, handler: Any) -> list[httpx.Request]:
    """Route httpx clients through a MockTransport; return every request seen."""
    seen: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    orig = httpx.AsyncClient

    def patched(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(recording)
        return orig(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched)
    return seen


def _page(body: str, ctype: str = "text/html") -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": ctype}, text=body)

    return handler


def _long(anchor_html: str) -> str:
    filler = "<p>" + "filler " * 2000 + "</p>"  # more than 8,000 chars before the anchor
    return f"<html><body>{filler}{anchor_html}<p>Splits on line boundaries.</p></body></html>"


async def test_ddg_202_says_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch, lambda r: httpx.Response(202, text="<html>bot</html>"))
    assert await make_web_tool().invoke(["search", "python"]) == REFUSED


async def test_ddg_anomaly_page_says_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch, _page("<html><body>Unusual Anomaly detected</body></html>"))
    assert await make_web_tool().invoke(["search", "python"]) == REFUSED


async def test_ddg_challenge_page_says_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch, _page("<p>Please complete the Challenge</p>"))
    assert await make_web_tool().invoke(["search", "python"]) == REFUSED


async def test_ddg_real_empty_page_is_not_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch, _page("<html><body>no hits for that</body></html>"))
    assert await make_web_tool().invoke(["search", "python"]) == "No search results found."


async def test_fetch_anchor_starts_at_id(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _serve(monkeypatch, _page(_long('<h2 id="splitlines">splitlines</h2>')))
    out = await make_web_tool().invoke(["fetch", f"{DOCS}#splitlines"])
    assert out.startswith("[from #splitlines]\n## splitlines")
    assert "Splits on line boundaries." in out
    assert "filler" not in out
    assert "#" not in str(seen[0].url)


async def test_fetch_anchor_matches_name_attribute(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch, _page(_long('<a name="old-anchor"></a><h3>Old section</h3>')))
    out = await make_web_tool().invoke(["fetch", f"{DOCS}#old-anchor"])
    assert out.startswith("[from #old-anchor]\n")
    assert "Old section" in out


async def test_missing_anchor_returns_page_start(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch, _page(_long('<h2 id="other">Other</h2>')))
    out = await make_web_tool(max_fetch_chars=50).invoke(["fetch", f"{DOCS}#nope"])
    assert out.startswith("[#nope not found; page start shown]\n")
    assert "filler" in out


async def test_from_starts_at_text_in_html(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch, _page("<p>Alpha intro</p><p>The Splitlines method splits text.</p>"))
    out = await make_web_tool().invoke(["fetch", DOCS, "--from", "splitlines method"])
    assert out == "Splitlines method splits text."


async def test_from_not_found_says_how_to_recover(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch, _page("<p>Hello</p>"))
    out = await make_web_tool().invoke(["fetch", DOCS, "--from", "missing words"])
    assert out.startswith("Error: `missing words` not found in the page (5 chars).")
    assert "Instead: fetch without --from, or try another word." in out


async def test_from_works_on_plain_text(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch, _page("first line\nsecond NEEDLE here", ctype="text/plain"))
    out = await make_web_tool().invoke(["fetch", DOCS, "--from", "needle here"])
    assert out == "NEEDLE here"


async def test_from_without_text_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch, _page("<p>x</p>"))
    out = await make_web_tool().invoke(["fetch", DOCS, "--from"])
    assert out == "Error: `--from` expects text."


async def test_cut_page_says_how_to_continue(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch, _page("<p>" + "word " * 2000 + "</p>"))
    out = await make_web_tool().invoke(["fetch", DOCS])
    assert "... [cut " in out
    assert f"Continue: web fetch {DOCS} --from 'word word word word']" in out


async def test_cut_plain_text_says_how_to_continue(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch, _page("abc def " * 1000, ctype="text/plain"))
    out = await make_web_tool(max_fetch_chars=20).invoke(["fetch", DOCS])
    assert "[cut " in out
    assert "--from 'def abc def abc']" in out


async def test_help_names_anchor_and_from_within_budget() -> None:
    help_text = await make_web_tool().invoke(["--help"])
    assert "#anchor" in help_text
    assert "--from" in help_text
    assert len(help_text) // 4 <= 60
