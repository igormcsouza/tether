"""Zero-config web search (DuckDuckGo Lite + Brave/Tavily/SearXNG env override) and reader."""

from __future__ import annotations

import html
import os
import re
import urllib.parse
from html.parser import HTMLParser

import httpx

from tether.decorator import ToolSpec, build_tool_spec


class _HTMLToTextParser(HTMLParser):
    """Lightweight stdlib HTML-to-Markdown/text extractor."""

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t in ("script", "style", "noscript", "svg", "head", "nav", "footer"):
            self._skip_depth += 1
            return
        if self._skip_depth > 0:
            return
        if t in ("h1", "h2", "h3", "h4"):
            level = int(t[1])
            self._parts.append(f"\n\n{'#' * level} ")
        elif t in ("p", "div", "section", "article", "br", "tr"):
            self._parts.append("\n")
        elif t == "li":
            self._parts.append("\n- ")

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in ("script", "style", "noscript", "svg", "head", "nav", "footer"):
            self._skip_depth = max(0, self._skip_depth - 1)
        elif self._skip_depth == 0 and t in ("p", "h1", "h2", "h3", "h4", "ul", "ol"):
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            cleaned = re.sub(r"[ \t]+", " ", data)
            self._parts.append(cleaned)

    def get_text(self) -> str:
        raw = "".join(self._parts)
        lines = [line.strip() for line in raw.splitlines()]
        collapsed = "\n".join(lines)
        return re.sub(r"\n{3,}", "\n\n", collapsed).strip()


def html_to_markdown(raw_html: str, max_chars: int = 8000) -> str:
    """Convert raw HTML into compact markdown-friendly text."""
    parser = _HTMLToTextParser()
    parser.feed(raw_html)
    text = parser.get_text()
    if len(text) > max_chars:
        return f"{text[:max_chars]}\n... [truncated {len(text) - max_chars:,} chars]"
    return text


def _unwrap_ddg_url(href: str) -> str:
    if "uddg=" in href:
        parsed = urllib.parse.urlparse(href)
        qs = urllib.parse.parse_qs(parsed.query)
        if "uddg" in qs and qs["uddg"]:
            return urllib.parse.unquote(qs["uddg"][0])
    return href


async def search_web_backend(query: str, max_results: int = 5) -> str:
    """Search the web via SearXNG/Brave/Tavily if configured, else DuckDuckGo HTML."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        )
    }

    searx_url = os.environ.get("SEARXNG_URL")
    brave_key = os.environ.get("BRAVE_API_KEY")
    tavily_key = os.environ.get("TAVILY_API_KEY")

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers=headers) as client:
        if searx_url:
            resp = await client.get(
                f"{searx_url.rstrip('/')}/search",
                params={"q": query, "format": "json"},
            )
            resp.raise_for_status()
            items = (resp.json().get("results") or [])[:max_results]
            return _format_results(
                [(i.get("title", ""), i.get("url", ""), i.get("content", "")) for i in items]
            )

        if brave_key:
            resp = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": max_results},
                headers={"X-Subscription-Token": brave_key, "Accept": "application/json"},
            )
            resp.raise_for_status()
            items = ((resp.json().get("web") or {}).get("results") or [])[:max_results]
            return _format_results(
                [(i.get("title", ""), i.get("url", ""), i.get("description", "")) for i in items]
            )

        if tavily_key:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={"api_key": tavily_key, "query": query, "max_results": max_results},
            )
            resp.raise_for_status()
            items = (resp.json().get("results") or [])[:max_results]
            return _format_results(
                [(i.get("title", ""), i.get("url", ""), i.get("content", "")) for i in items]
            )

        # Default zero-config DuckDuckGo HTML endpoint
        resp = await client.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
        )
        resp.raise_for_status()
        body = resp.text

    link_re = re.compile(
        r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        re.DOTALL,
    )
    snip_re = re.compile(
        r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>',
        re.DOTALL,
    )
    links = link_re.findall(body)
    snippets = snip_re.findall(body)

    results: list[tuple[str, str, str]] = []
    for idx, (raw_href, raw_title) in enumerate(links[:max_results]):
        title = html.unescape(re.sub(r"<[^>]+>", "", raw_title)).strip()
        url = _unwrap_ddg_url(html.unescape(raw_href).strip())
        snippet = ""
        if idx < len(snippets):
            snippet = html.unescape(re.sub(r"<[^>]+>", "", snippets[idx])).strip()
        results.append((title, url, snippet))

    return _format_results(results)


def _format_results(items: list[tuple[str, str, str]]) -> str:
    if not items:
        return "No search results found."
    out: list[str] = []
    for idx, (title, url, snippet) in enumerate(items, 1):
        out.append(f"{idx}. {title}\n   URL: {url}\n   {snippet}".strip())
    return "\n\n".join(out)


def make_web_tool(max_fetch_chars: int = 8000) -> ToolSpec:
    help_str = (
        "Usage: web search <query> [--max 5] | web fetch <url>\n"
        "Desc : Search the web or fetch clean markdown text from a URL."
    )

    async def _web(args: list[str], stdin: str | None = None) -> str:
        if not args or args[0] in ("--help", "-h"):
            return help_str
        sub = args[0]
        if sub == "search":
            max_res = 5
            query_parts: list[str] = []
            i = 1
            while i < len(args):
                if args[i] == "--max" and i + 1 < len(args):
                    try:
                        max_res = int(args[i + 1])
                    except ValueError:
                        return "Error: `--max` expects an integer."
                    i += 2
                else:
                    query_parts.append(args[i])
                    i += 1
            query = " ".join(query_parts).strip() or (stdin or "").strip()
            if not query:
                return f"Error: missing `<query>`.\n{help_str}"
            return await search_web_backend(query, max_results=max_res)

        if sub == "fetch":
            if len(args) < 2:
                return f"Error: missing `<url>`.\n{help_str}"
            url = args[1].strip()
            if not url.startswith(("http://", "https://")):
                return "Error: URL must start with http:// or https://."
            headers = {"User-Agent": "Tether-MicroHarness/0.1"}
            async with httpx.AsyncClient(
                timeout=20.0, follow_redirects=True, headers=headers
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                ctype = resp.headers.get("content-type", "")
                if "html" in ctype.lower() or "<html" in resp.text[:500].lower():
                    return html_to_markdown(resp.text, max_chars=max_fetch_chars)
                text = resp.text.strip()
                if len(text) > max_fetch_chars:
                    return f"{text[:max_fetch_chars]}\n... [truncated]"
                return text

        return f"Error: unknown subcommand `{sub}`.\n{help_str}"

    return build_tool_spec(
        _web,
        name="web",
        description="Search the web or fetch clean URL text",
        custom_help=help_str,
        raw_dispatch=True,
    )
