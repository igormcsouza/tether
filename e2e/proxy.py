"""Fault-injecting HTTP proxy between tether and ollama (stdlib server, threaded).

Per `/api/chat` request it can: pass through to the real model, answer a fault (status code,
stall, trickle a never-ending body), or *script* the reply (a fixed tool call, no model at all).
Everything it sees is recorded in `requests` / `responses` so scenarios can assert on what
tether actually sent. `/v1/chat/completions` always answers 401 (auth scenario).
"""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx


def _tool_call(cmd: str, stdin: str | None) -> dict[str, Any]:
    args: dict[str, Any] = {"cmd": cmd}
    if stdin is not None:
        args["stdin"] = stdin
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"function": {"name": "act", "arguments": args}}],
    }


class Chaos:
    def __init__(self, upstream: str) -> None:
        self.upstream = upstream.rstrip("/")
        self.requests: list[dict[str, Any]] = []
        self.responses: list[dict[str, Any]] = []
        self.faults: deque[dict[str, Any]] = deque()  # consumed one per /api/chat request
        self.stall_all = 0.0  # seconds to sleep before answering every request
        self._script: list[Any] | None = None
        self._lock = threading.Lock()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(self))
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    # --- programming the proxy -------------------------------------------------------------
    def script(self, *actions: Any) -> None:
        """Answer from a script, no model: each item is `"cmd"`, `("cmd", "stdin")` or
        `{"text": "plain answer without a tool call"}`. After the last item it answers `done ok`."""
        self._script = list(actions)

    def fault(self, kind: str, times: int = 1, **kw: Any) -> None:
        self.faults.extend({"kind": kind, **kw} for _ in range(times))

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    # --- used by the handler ----------------------------------------------------------------
    def next_fault(self) -> dict[str, Any] | None:
        with self._lock:
            return self.faults.popleft() if self.faults else None

    def scripted(self, index: int) -> dict[str, Any] | None:
        if self._script is None:
            return None
        item = self._script[index] if index < len(self._script) else ("done", "ok")
        if isinstance(item, dict):
            return {"role": "assistant", "content": item["text"]}
        item = (item,) if isinstance(item, str) else item
        return _tool_call(item[0], item[1] if len(item) > 1 else None)


def _handler(chaos: Chaos) -> type[BaseHTTPRequestHandler]:
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a: Any) -> None:  # silence
            pass

        def _send(
            self, code: int, body: dict[str, Any], headers: dict[str, str] | None = None
        ) -> None:
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data)))
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            r = httpx.get(chaos.upstream + self.path, timeout=30)
            self._send(r.status_code, r.json())

        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))) or b"{}")
            if self.path.startswith("/v1/"):
                return self._send(401, {"error": "invalid api key"})
            with chaos._lock:
                index = len(chaos.requests)
                chaos.requests.append(body)
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
            msg = chaos.scripted(index)
            if msg is not None:
                resp = {
                    "model": "scripted",
                    "message": msg,
                    "done": True,
                    "done_reason": "stop",
                    "prompt_eval_count": len(json.dumps(body["messages"])) // 4,
                    "eval_count": 10,
                }
            else:
                body.setdefault("options", {}).update({"temperature": 0, "seed": 1})
                resp = httpx.post(chaos.upstream + self.path, json=body, timeout=600).json()
            chaos.responses.append(resp)
            return self._send(200, resp)

    return H
