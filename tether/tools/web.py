"""Zero-config web search (DuckDuckGo Lite + Brave/Tavily/SearXNG env override) and reader."""

from __future__ import annotations

import asyncio
import html
import ipaddress
import json
import os
import re
import socket
import urllib.parse
from html.parser import HTMLParser
from typing import Any

import httpx

from tether.decorator import ToolSpec, build_tool_spec


class PrivateAddressError(PermissionError):
    """Raised when `web fetch` targets a loopback/private/link-local address (SSRF guard)."""


class HostNotAllowedError(PermissionError):
    """Raised when `web` targets a host outside the configured domain allowlist."""


def host_allowed(host: str, allow: tuple[str, ...]) -> bool:
    """Match a host against allowlist entries; IP literals are never allowed by name."""
    host = host.lower().rstrip(".")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return False
    if ":" in host:
        return False
    for entry in allow:
        if entry.startswith("*."):
            if host.endswith("." + entry[2:]):
                return True
        elif host == entry or host.endswith("." + entry):
            return True
    return False


async def assert_public_url(request: httpx.Request) -> None:
    """Block fetches that resolve to non-global IPs (localhost, RFC1918, cloud metadata).

    Runs as an httpx request hook, so every redirect hop is checked too.
    Opt out with TETHER_WEB_ALLOW_PRIVATE=1.
    """
    if os.environ.get("TETHER_WEB_ALLOW_PRIVATE") == "1":
        return
    host = request.url.host
    # ponytail: resolve-then-connect leaves a DNS-rebinding window; pin the IP if that matters.
    infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    for info in infos:
        ip = ipaddress.ip_address(str(info[4][0]).split("%")[0])
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if not ip.is_global:
            raise PrivateAddressError(
                f"blocked: `{host}` resolves to non-public address {ip} "
                "(set TETHER_WEB_ALLOW_PRIVATE=1 to allow)"
            )


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


def html_to_text(raw_html: str) -> str:
    """Convert raw HTML to compact text, uncut."""
    parser = _HTMLToTextParser()
    parser.feed(raw_html)
    return parser.get_text()


# Void elements never get an end tag, so they must not stay on the open-element stack.
_VOID_TAGS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)


class _MainContentParser(_HTMLToTextParser):
    """Keeps only the text inside <main>, <article> or [role=main] elements."""

    def __init__(self) -> None:
        super().__init__()
        # Open elements as (tag, is_main); a stack keeps nested divs
        # from closing a main region early.
        self._stack: list[tuple[str, bool]] = []
        self._found_main = False

    def _main_open(self) -> bool:
        return any(is_main for _, is_main in self._stack)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t not in _VOID_TAGS:
            is_main = t in ("main", "article") or ("role", "main") in attrs
            self._stack.append((t, is_main))
            self._found_main = self._found_main or is_main
        super().handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == t:
                del self._stack[i:]
                break
        super().handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self._main_open():
            super().handle_data(data)


def extract_main_content(raw_html: str) -> str | None:
    """Extract text from <main>, <article>, or [role=main] if present.
    Returns None if no main content element found.
    """
    parser = _MainContentParser()
    parser.feed(raw_html)
    if parser._found_main:
        return parser.get_text()
    return None


def _clip(text: str, max_chars: int, url: str) -> str:
    """Cut text to max_chars and say how to read on from a few words further down."""
    if len(text) <= max_chars:
        return text
    # quotes are dropped so the hint stays one shell-style argument
    hint = " ".join(text[max_chars:].split()[:4]).replace("'", "")
    return (
        f"{text[:max_chars]}\n... [cut {len(text) - max_chars:,} chars. "
        f"Continue: web fetch {url} --from '{hint}']"
    )


JSON_KEYS_SHOWN = 30  # keys listed in an outline of a big JSON object (the last 5 always)


def _kind(value: Any) -> str:
    """One-line shape of a JSON value for an outline."""
    if isinstance(value, dict):
        return f"{{{len(value)} keys}}"
    if isinstance(value, list):
        return f"[{len(value)} items]"
    return json.dumps(value, ensure_ascii=False)[:80]


def _open(url: str, at: str, node: Any) -> str:
    """The command that opens a child of `node` at `at`, with a real key as the example."""
    if not isinstance(node, (dict, list)):
        return f"web fetch {url}{at}"
    first = next(iter(node), "<key>") if isinstance(node, dict) else "0"
    return f"web fetch {url}{at.rstrip('/')}/{first}"


def json_view(text: str, pointer: str, url: str, max_chars: int) -> str | None:
    """A JSON reply at a JSON Pointer (`#/info/version`, RFC 6901; `-1` is a list's last item).

    A value that fits is shown pretty-printed; a bigger one as an outline of its keys or items
    with the command that opens one, so a 6 MB API reply is read in two small steps. None when
    `text` is not JSON.
    """
    try:
        node = json.loads(text)
    except ValueError:
        return None
    # qwen3.5:9b typed `#info`, `#info/version` and `#info#version`: the leading `/` is optional,
    # `#` separates too, and a dotted segment that is not a key (`info.version`) is split
    parts = [p.replace("~1", "/").replace("~0", "~") for p in re.split(r"[/#]", pointer) if p]
    i = 0
    while i < len(parts):
        part = parts[i]
        here = "#/" + "/".join(parts[:i])
        if isinstance(node, dict) and part not in node and "." in part.strip("."):
            parts[i : i + 1] = [p for p in part.split(".") if p]
            continue
        i += 1
        if isinstance(node, dict) and part in node:
            node = node[part]
        elif (
            isinstance(node, list)
            and re.fullmatch(r"-?\d+", part)
            and -len(node) <= int(part) < len(node)
        ):
            node = node[int(part)]
        else:
            if isinstance(node, dict):
                shape = f"keys: {', '.join(list(node)[:JSON_KEYS_SHOWN])}"
            elif isinstance(node, list):
                shape = f"{len(node)} items, 0 to {len(node) - 1}" if node else "an empty list"
            else:
                shape = f"a value: {_kind(node)}"
            return (
                f"Error: `{part}` not found at {here} ({shape}). Instead: {_open(url, here, node)}"
            )
    at = "#/" + "/".join(parts)
    body = json.dumps(node, indent=1, ensure_ascii=False)
    if len(body) <= max_chars:
        return f"[{at}]\n{body}" if parts else body
    if isinstance(node, dict):
        keys = list(node)
        shown = keys if len(keys) <= JSON_KEYS_SHOWN else [*keys[: JSON_KEYS_SHOWN - 5], *keys[-5:]]
        lines = [f'"{k}": {_kind(node[k])}' for k in shown]
        if len(keys) > len(shown):
            lines.insert(JSON_KEYS_SHOWN - 5, f"... {len(keys) - len(shown)} more keys ...")
    else:
        lines = [
            f"{i}: {_kind(node[i])}" for i in sorted({0, 1, 2, len(node) - 1}) if i < len(node)
        ]
    return _clip(
        f"[JSON at {at}: {_kind(node)}, {len(body):,} chars; outline]\n"
        + "\n".join(lines)
        + f"\nOpen one: {_open(url, at, node)}",
        max_chars,
        url,
    )


def _anchor_start(raw_html: str, anchor: str) -> int | None:
    """Offset of the tag carrying id=anchor or name=anchor, or None when absent."""
    pattern = re.compile(
        r"""<[^>]*\s(?:id|name)\s*=\s*["']?""" + re.escape(anchor) + r"""["'\s>/]"""
    )
    match = pattern.search(raw_html)
    return match.start() if match else None


def html_to_markdown(raw_html: str, max_chars: int = 8000, url: str = "<url>") -> str:
    """Convert raw HTML into compact markdown-friendly text."""
    return _clip(html_to_text(raw_html), max_chars, url)


def _unwrap_ddg_url(href: str) -> str:
    if "uddg=" in href:
        parsed = urllib.parse.urlparse(href)
        qs = urllib.parse.parse_qs(parsed.query)
        if "uddg" in qs and qs["uddg"]:
            return urllib.parse.unquote(qs["uddg"][0])
    return href


def _format_http_error_from_response(resp: httpx.Response, url: str) -> str:
    """Format an HTTP error from a response with a helpful hint."""
    status = resp.status_code
    reason = resp.reason_phrase or ""
    return _format_http_error_status(url, status, reason)


def _format_http_error_status(url: str, status: int, reason: str) -> str:
    """Format an HTTP error with a helpful hint based on status code."""
    hints = {
        429: "wait a minute or fetch another source",
        401: "the page needs a login; fetch another source",
        403: "the page needs a login; fetch another source",
        404: "the page does not exist; search for the right URL",
        410: "the page does not exist; search for the right URL",
    }
    # 5xx errors
    if 500 <= status < 600:
        hint = "the site failed; try again later or fetch another source"
    else:
        hint = hints.get(status, "try again or fetch another source")

    reason_str = f" {reason}" if reason else ""
    return f"Error: {url} answered {status}{reason_str}. Instead: {hint}"


def _format_network_error(host: str, reason: str) -> str:
    """Format a network error with a helpful hint."""
    return (
        f"Error: could not reach {host} ({reason}). Instead: check the URL or fetch another source."
    )


SEARCH_REFUSED = (
    "Error: the search engine refused the request (rate limit or bot check). "
    "Instead: wait a minute, fetch a URL you know with `web fetch`, "
    "or set BRAVE_API_KEY, TAVILY_API_KEY or SEARXNG_URL."
)


async def search_web_backend(
    query: str, max_results: int = 5, web_allow: tuple[str, ...] | None = None
) -> str:
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
            items = resp.json().get("results") or []
            return _render_results(
                [(i.get("title", ""), i.get("url", ""), i.get("content", "")) for i in items],
                web_allow,
                max_results,
            )

        if brave_key:
            resp = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": max_results},
                headers={"X-Subscription-Token": brave_key, "Accept": "application/json"},
            )
            resp.raise_for_status()
            items = (resp.json().get("web") or {}).get("results") or []
            return _render_results(
                [(i.get("title", ""), i.get("url", ""), i.get("description", "")) for i in items],
                web_allow,
                max_results,
            )

        if tavily_key:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={"api_key": tavily_key, "query": query, "max_results": max_results},
            )
            resp.raise_for_status()
            items = resp.json().get("results") or []
            return _render_results(
                [(i.get("title", ""), i.get("url", ""), i.get("content", "")) for i in items],
                web_allow,
                max_results,
            )

        # Default zero-config DuckDuckGo HTML endpoint
        resp = await client.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
        )
        resp.raise_for_status()
        # DDG answers 202 with a bot-check page once a client sends too many queries
        if resp.status_code == 202:
            return SEARCH_REFUSED
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
    if not links and re.search(r"anomaly|challenge", body, re.IGNORECASE):
        return SEARCH_REFUSED
    snippets = snip_re.findall(body)

    results: list[tuple[str, str, str]] = []
    for idx, (raw_href, raw_title) in enumerate(links):
        title = html.unescape(re.sub(r"<[^>]+>", "", raw_title)).strip()
        url = _unwrap_ddg_url(html.unescape(raw_href).strip())
        snippet = ""
        if idx < len(snippets):
            snippet = html.unescape(re.sub(r"<[^>]+>", "", snippets[idx])).strip()
        results.append((title, url, snippet))

    return _render_results(results, web_allow, max_results)


def _render_results(
    items: list[tuple[str, str, str]], web_allow: tuple[str, ...] | None, max_results: int
) -> str:
    """Format backend hits, dropping and counting any host outside the allowlist."""
    if web_allow is None:
        return _format_results(items[:max_results])
    kept, blocked = _filter_results_by_host(items, web_allow)
    note = _blocked_note(blocked, web_allow) if blocked else ""
    return _format_results(kept[:max_results]) + note


def _filter_results_by_host(
    results: list[tuple[str, str, str]], allow: tuple[str, ...]
) -> tuple[list[tuple[str, str, str]], int]:
    kept: list[tuple[str, str, str]] = []
    blocked = 0
    for item in results:
        host = urllib.parse.urlparse(item[1]).hostname or ""
        if host and host_allowed(host, allow):
            kept.append(item)
        else:
            blocked += 1
    return kept, blocked


def _blocked_note(blocked: int, allow: tuple[str, ...]) -> str:
    return (
        f"\n\n[{blocked} result(s) hidden: host not allowed. "
        f"Instead: use one of: {', '.join(allow) or '(none)'}]"
    )


def _format_results(items: list[tuple[str, str, str]]) -> str:
    if not items:
        return "No search results found."
    out: list[str] = []
    for idx, (title, url, snippet) in enumerate(items, 1):
        out.append(f"{idx}. {title}\n   URL: {url}\n   {snippet}".strip())
    return "\n\n".join(out)


async def assert_allowed_host(request: httpx.Request, allow: tuple[str, ...]) -> None:
    """Refuse hosts outside the allowlist; runs before the SSRF guard on every redirect hop."""
    host = request.url.host
    if not host_allowed(host, allow):
        options = ", ".join(allow) or "(none)"
        message = f"web fetch blocked: host {host} not allowed. Instead: use one of: {options}"
        raise HostNotAllowedError(message)


def make_web_tool(
    max_fetch_chars: int = 8000, web_allow: tuple[str, ...] | None = None
) -> ToolSpec:
    help_str = (
        "Usage: web search <query> [--max 5] | web fetch <url>[#anchor|#/json/key] [--from <t>]\n"
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
            return await search_web_backend(query, max_results=max_res, web_allow=web_allow)

        if sub == "fetch":
            if len(args) < 2:
                return f"Error: missing `<url>`.\n{help_str}"
            url, _, anchor = args[1].strip().partition("#")
            anchor = urllib.parse.unquote(anchor)
            if not url.startswith(("http://", "https://")):
                return "Error: URL must start with http:// or https://."
            rest = args[2:]
            from_text: str | None = None
            if "--from" in rest:
                pos = rest.index("--from")
                from_text = " ".join(rest[pos + 1 :]).strip()
                if not from_text:
                    return "Error: `--from` expects text."
            headers = {"User-Agent": "Tether-MicroHarness/0.1"}
            hooks: list[Any] = [assert_public_url]
            if web_allow is not None:
                allow = web_allow

                async def _allow_hook(request: httpx.Request) -> None:
                    await assert_allowed_host(request, allow)

                hooks.insert(0, _allow_hook)
            async with httpx.AsyncClient(
                timeout=20.0,
                follow_redirects=True,
                headers=headers,
                event_hooks={"request": hooks},
            ) as client:
                try:
                    resp = await client.get(url)
                except (PrivateAddressError, HostNotAllowedError) as exc:
                    return f"Error: {exc}"
                except httpx.RequestError as exc:
                    host = urllib.parse.urlparse(url).hostname or "unknown"
                    reason = (
                        "timeout"
                        if isinstance(exc, httpx.TimeoutException)
                        else (str(exc).splitlines() or [type(exc).__name__])[0][:120]
                    )
                    return _format_network_error(host, reason)

                # Check for HTTP error status
                if resp.status_code >= 400:
                    return _format_http_error_from_response(resp, url)

                ctype = resp.headers.get("content-type", "")
                is_html = "html" in ctype.lower() or "<html" in resp.text[:500].lower()
                source, head = resp.text, ""
                if is_html and anchor:
                    start = _anchor_start(source, anchor)
                    if start is None:
                        head = f"[#{anchor} not found; page start shown]\n"
                    else:
                        source = source[start:]
                        head = f"[from #{anchor}]\n"

                # Extract main content if HTML
                if is_html:
                    main_text = extract_main_content(source)
                    if main_text is not None:
                        full = main_text
                    else:
                        full = html_to_text(source)
                else:
                    full = source.strip()
                    # a JSON reply is navigated by path, not cut at max chars (`#/info/version`)
                    big = len(full) > max_fetch_chars
                    if from_text is None and (anchor or big):
                        view = json_view(full, anchor, url, max_fetch_chars)
                        if view is not None:
                            return view

                # Check for empty content
                if not full:
                    return (
                        f"Error: {url} has no readable text (maybe built by JavaScript). "
                        "Instead: fetch another source."
                    )

                if from_text is not None:
                    at = full.lower().find(from_text.lower())
                    if at < 0:
                        return (
                            f"Error: `{from_text}` not found in the page "
                            f"({len(full):,} chars). Instead: fetch without --from, "
                            "or try another word."
                        )
                    full = full[at:]
                return head + _clip(full, max_fetch_chars, url)

        return f"Error: unknown subcommand `{sub}`.\n{help_str}"

    return build_tool_spec(
        _web,
        name="web",
        description="Search the web or fetch clean URL text",
        custom_help=help_str,
        raw_dispatch=True,
    )
