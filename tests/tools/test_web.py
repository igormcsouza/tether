"""Unit tests for tether/tools/web.py (DDG Lite, SearXNG, Brave, Tavily search & HTML reader)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from tether.tools.web import _format_results, _unwrap_ddg_url, html_to_markdown, make_web_tool


async def test_web_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify HTML-to-markdown conversion, search engines (DDG/SearXNG/Brave/Tavily), and fetch."""
    md = html_to_markdown(
        "<html><head><title>Ignore</title></head><body>"
        "<script>var x=1;</script><h1>Title</h1><p>Hello   world</p>"
        "<ul><li>Item 1</li></ul></body></html>",
        max_chars=20,
    )
    assert "truncated" in md
    assert _unwrap_ddg_url("https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com") == (
        "https://example.com"
    )
    assert _unwrap_ddg_url("https://example.com") == "https://example.com"
    assert _format_results([]) == "No search results found."

    def mock_http_handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "searx" in url:
            return httpx.Response(
                200,
                json={"results": [{"title": "SearX", "url": "https://sx.org", "content": "Snip"}]},
            )
        if "brave.com" in url:
            return httpx.Response(
                200,
                json={
                    "web": {
                        "results": [
                            {"title": "Brave", "url": "https://br.org", "description": "BSnip"}
                        ]
                    }
                },
            )
        if "tavily.com" in url:
            return httpx.Response(
                200,
                json={
                    "results": [{"title": "Tavily", "url": "https://tv.org", "content": "TSnip"}]
                },
            )
        if "duckduckgo.com" in url:
            return httpx.Response(
                200,
                text=(
                    '<a class="result__a" href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fddg.org">'
                    "<b>DDG Title</b></a>"
                    '<a class="result__snippet">DDG Snippet</a>'
                ),
            )
        if "page.html" in url:
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text="<html><body><h2>Heading</h2><p>Body text</p></body></html>",
            )
        if "short.txt" in url:
            return httpx.Response(
                200,
                headers={"content-type": "text/plain"},
                text="short_ok",
            )
        return httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            text="A" * 100,
        )

    orig_async_client = httpx.AsyncClient

    def patched_client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(mock_http_handler)
        return orig_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched_client)

    wspec = make_web_tool(max_fetch_chars=30)
    assert "Usage: web" in await wspec.invoke(["--help"])
    assert "Error: `--max`" in await wspec.invoke(["search", "--max", "bad", "ai"])
    assert "Error: missing `<query>`" in await wspec.invoke(["search"])
    assert "DDG Title" in await wspec.invoke(["search", "--max", "2", "ai"])

    monkeypatch.setenv("TAVILY_API_KEY", "tv_key")
    assert "Tavily" in await wspec.invoke(["search", "ai"])
    monkeypatch.setenv("BRAVE_API_KEY", "br_key")
    assert "Brave" in await wspec.invoke(["search", "ai"])
    monkeypatch.setenv("SEARXNG_URL", "https://searx.example.com")
    assert "SearX" in await wspec.invoke(["search", "ai"])

    assert "Error: missing `<url>`" in await wspec.invoke(["fetch"])
    assert "Error: URL must start" in await wspec.invoke(["fetch", "ftp://bad"])
    assert "## Heading" in await wspec.invoke(["fetch", "https://example.com/page.html"])
    assert "truncated" in await wspec.invoke(["fetch", "https://example.com/plain.txt"])
    assert await wspec.invoke(["fetch", "https://example.com/short.txt"]) == "short_ok"
    assert "Error: unknown subcommand" in await wspec.invoke(["bogus"])
