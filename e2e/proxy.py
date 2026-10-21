"""Fault-injecting HTTP proxy between tether and ollama (stdlib server, threaded).

Per model request it can pass through to the real model, answer a fault (status code, stall,
trickle a never-ending body), or *script* the reply (a fixed tool call, no model at all). Scripts
can be global (`script`) or routed by goal text (`route`, so a spawned sub-agent gets its own), and
an item may be a callable that sees the request (e.g. to read a session id out of the last tool
result). It also speaks the OpenAI (`/openai/v1/chat/completions`) and Anthropic
(`/anthropic/v1/messages`) wire formats for scripted replies, serves static `pages` (SearXNG,
web fetch), and records every request, response and header set. `/v1/*` always answers 401.
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections import deque
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx

Item = Any  # "cmd" | ("cmd", "stdin") | {"text": str} | Callable[[dict], Item]


def goal_of(body: dict[str, Any]) -> str:
    for m in body.get("messages", []):
        c = m.get("content")
        if m.get("role") == "user" and isinstance(c, str) and c.startswith("Goal:"):
            return c
    return ""


def last_tool_text(body: dict[str, Any]) -> str:
    for m in reversed(body.get("messages", [])):
        if m.get("role") in ("tool", "user") and "Observation" not in str(m.get("content"))[:0]:
            c = m.get("content")
            if isinstance(c, str) and c and not c.startswith("Goal:"):
                return c
    return ""


def session_id_in(body: dict[str, Any]) -> str:
    found = re.findall(r"ses_[0-9a-f]+", json.dumps(body["messages"]))
    return found[-1] if found else "ses_missing"


class Chaos:
    def __init__(self, upstream: str) -> None:
        self.upstream = upstream.rstrip("/")
        self.requests: list[dict[str, Any]] = []
        self.responses: list[dict[str, Any]] = []
        self.headers: list[dict[str, str]] = []
        self.faults: deque[dict[str, Any]] = deque()  # consumed one per model request
        self.stall_all = 0.0  # seconds to sleep before answering every model request
        self.pages: dict[str, tuple[str, str]] = {}  # GET path -> (content-type, body)
        self._script: list[Item] | None = None
        self._routes: list[tuple[str, list[Item]]] = []
        self._route_hits: dict[int, int] = {}
        self._lock = threading.Lock()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(self))
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    # --- programming the proxy -------------------------------------------------------------
    def script(self, *actions: Item) -> None:
        """Answer from a script, no model; after the last item it answers `done ok`."""
        self._script = list(actions)

    def route(self, goal_contains: str, *actions: Item) -> None:
        """Script only requests whose goal contains `goal_contains` (own counter per route)."""
        self._routes.append((goal_contains, list(actions)))

    def fault(self, kind: str, times: int = 1, **kw: Any) -> None:
        self.faults.extend({"kind": kind, **kw} for _ in range(times))

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    # --- used by the handler ----------------------------------------------------------------
    def next_fault(self) -> dict[str, Any] | None:
        with self._lock:
            return self.faults.popleft() if self.faults else None

    def scripted(
        self, index: int, body: dict[str, Any]
    ) -> tuple[str, str | None] | dict[str, str] | None:
        items: list[Item] | None = self._script
        n = index
        goal = goal_of(body)
        with self._lock:
            for i, (needle, acts) in enumerate(self._routes):
                if needle in goal:
                    items, n = acts, self._route_hits.get(i, 0)
                    self._route_hits[i] = n + 1
                    break
        if items is None:
            return None
        item: Item = items[n] if n < len(items) else ("done", "ok")
        if callable(item):
            item = item(body)
        if isinstance(item, dict):
            return item
        item = (item,) if isinstance(item, str) else item
        return (item[0], item[1] if len(item) > 1 else None)


def _args(action: tuple[str, str | None]) -> dict[str, Any]:
    out: dict[str, Any] = {"cmd": action[0]}
    if action[1] is not None:
        out["stdin"] = action[1]
    return out


def _ollama(action: Any, n: int) -> dict[str, Any]:
    msg = (
        {"role": "assistant", "content": action["text"]}
        if isinstance(action, dict)
        else {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"function": {"name": "act", "arguments": _args(action)}}],
        }
    )
    return {
        "model": "scripted",
        "message": msg,
        "done": True,
        "done_reason": "stop",
        "prompt_eval_count": n,
        "eval_count": 10,
    }


def _openai(action: Any, n: int) -> dict[str, Any]:
    msg: dict[str, Any] = (
        {"role": "assistant", "content": action["text"]}
        if isinstance(action, dict)
        else {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "act", "arguments": json.dumps(_args(action))},
                }
            ],
        }
    )
    return {
        "choices": [{"index": 0, "message": msg, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": n, "completion_tokens": 10},
    }


def _anthropic(action: Any, n: int) -> dict[str, Any]:
    block = (
        {"type": "text", "text": action["text"]}
        if isinstance(action, dict)
        else {"type": "tool_use", "id": "toolu_1", "name": "act", "input": _args(action)}
    )
    return {
        "type": "message",
        "role": "assistant",
        "content": [block],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": n, "output_tokens": 10},
    }


_FORMATS: dict[str, Callable[[Any, int], dict[str, Any]]] = {
    "/api/chat": _ollama,
    "/openai/v1/chat/completions": _openai,
    "/anthropic/v1/messages": _anthropic,
}


def _handler(chaos: Chaos) -> type[BaseHTTPRequestHandler]:
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a: Any) -> None:  # silence
            pass

        def _send(
            self,
            code: int,
            body: Any,
            headers: dict[str, str] | None = None,
            ctype: str = "application/json",
        ) -> None:
            data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("content-type", ctype)
            self.send_header("content-length", str(len(data)))
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            path = self.path.split("?")[0]
            if path in chaos.pages:
                ctype, body = chaos.pages[path]
                return self._send(200, body, ctype=ctype)
            r = httpx.get(chaos.upstream + self.path, timeout=30)
            return self._send(r.status_code, r.json())

        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))) or b"{}")
            if self.path.startswith("/v1/"):
                return self._send(401, {"error": "invalid api key"})
            with chaos._lock:
                index = len(chaos.requests)
                chaos.requests.append(body)
                chaos.headers.append({k.lower(): v for k, v in self.headers.items()})
            if chaos.stall_all:
                time.sleep(chaos.stall_all)
            fault = chaos.next_fault()
            if fault and fault["kind"] == "status":
                hdrs = {"retry-after": str(fault["retry_after"])} if "retry_after" in fault else {}
                return self._send(fault["code"], {"error": fault.get("error", "fault")}, hdrs)
            if (
                fault and fault["kind"] == "trickle"
            ):  # bytes keep coming: httpx read timeout never fires
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("transfer-encoding", "chunked")
                self.end_headers()
                try:
                    for _ in range(int(fault.get("seconds", 60))):
                        self.wfile.write(b"1\r\n \r\n")
                        self.wfile.flush()
                        time.sleep(1)
                except OSError:
                    pass
                return None
            action = chaos.scripted(index, body)
            fmt = _FORMATS.get(self.path)
            if action is not None and fmt:
                resp = fmt(action, len(json.dumps(body.get("messages", []))) // 4)
            elif self.path == "/api/chat":
                body.setdefault("options", {}).update({"temperature": 0, "seed": 1})
                resp = httpx.post(chaos.upstream + self.path, json=body, timeout=600).json()
            else:
                return self._send(500, {"error": "no script for this endpoint"})
            chaos.responses.append(resp)
            return self._send(200, resp)

    return H
