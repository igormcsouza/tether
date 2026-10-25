"""Base provider protocol and 9B fallback tool-call parser."""

from __future__ import annotations

import ast
import asyncio
import hashlib
import json
import os
import re
import tempfile
import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX
    fcntl = None  # type: ignore[assignment]


@dataclass(slots=True)
class ActionCall:
    cmd: str
    stdin: str | None = None


@dataclass(slots=True)
class ModelResponse:
    content: str
    action: ActionCall | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    hint: str = ""  # shown to the model instead of the generic reminder when it sent no usable call


ProviderResponse = ModelResponse


class ModelProvider(Protocol):
    model_name: str

    async def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ModelResponse: ...


class ProviderError(RuntimeError):
    """A provider call failed after retries; the message names provider, model and timeout."""


def auth_message(
    provider: str, key_env: str | None, status: int | None = None, body: str = ""
) -> str:
    """Name the credential that failed (never its value) so 401/403 is actionable.

    403 means authenticated but denied, so it reports access denied plus the body start.
    """
    cred = f"`{key_env}`" if key_env else "the API key"
    if status == 403:
        return f"{provider} access denied (HTTP 403) for {cred}: {body[:120]!r}"
    code = f"HTTP {status}: " if status else ""
    return f"{provider} {code}{cred} is missing or rejected; set it to a valid key"


RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
# A server that rejects the model's own tool call (cut-off JSON) answers the same way every time.
MODEL_FAULT = "tool call"
REJECTED_CALL_HINT = (
    "Your last call was rejected: the tool-call JSON was invalid or cut off. "
    "Send a shorter call, e.g. write long files in smaller pieces."
)


def rejected_call(resp: httpx.Response) -> ModelResponse | None:
    """Turn a server's 500 about the model's own bad tool call into feedback for the model."""
    if resp.status_code == 500 and MODEL_FAULT in resp.text:
        return ModelResponse(content="", hint=REJECTED_CALL_HINT)
    return None


def context_overflow(resp: httpx.Response) -> bool:
    """True when Ollama drops the first (goal) message because prompt > num_ctx."""
    return resp.status_code == 500 and "No user query found" in resp.text


_TRANSIENT = (httpx.TimeoutException, httpx.NetworkError, TimeoutError)


class RateLimiter:
    """Sliding-window cap of `rpm` requests per 60 s.

    The window lives in a lock-protected file shared by every process using the same key, so
    parallel workers and sub-agents on one machine count against one budget. Without `fcntl`
    (non-POSIX) it falls back to a per-process window.
    """

    def __init__(self, rpm: int, key: str = "") -> None:
        self.rpm = rpm
        self._stamps: list[float] = []
        root = Path(os.environ.get("TETHER_RATE_DIR") or tempfile.gettempdir())
        root.mkdir(parents=True, exist_ok=True)
        self._path = (
            root / f"tether-rate-{os.getuid()}-{hashlib.sha1(key.encode()).hexdigest()[:12]}.json"
            if fcntl and key
            else None
        )

    def _claim(self) -> float:
        """Take a slot now (return 0) or return how long to wait for one."""
        now = time.time()
        if self._path is None:
            stamps = [t for t in self._stamps if now - t < 60.0]
            wait = 0.0 if len(stamps) < self.rpm else 60.0 - (now - stamps[0])
            self._stamps = stamps if wait else [*stamps, now]
            return wait
        with open(self._path, "a+") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            fh.seek(0)
            try:
                stamps = [t for t in json.loads(fh.read() or "[]") if now - t < 60.0]
            except ValueError:
                stamps = []
            wait = 0.0 if len(stamps) < self.rpm else 60.0 - (now - stamps[0])
            if not wait:
                stamps.append(now)
            fh.seek(0)
            fh.truncate()
            fh.write(json.dumps(stamps))
        return wait

    async def acquire(self) -> None:
        while wait := self._claim():
            await asyncio.sleep(wait)


_LIMITERS: dict[str, RateLimiter] = {}


def limiter_for(key: str, rpm: int | None) -> RateLimiter | None:
    """Process-wide limiter for `key` (provider + endpoint); None when no limit is configured."""
    if not rpm:
        return None
    return _LIMITERS.setdefault(f"{key}:{rpm}", RateLimiter(rpm, key))


async def post_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    provider: str,
    model: str,
    timeout: float,
    key_env: str | None = None,
    retries: int = 2,
    backoff: float = 1.0,
    sleep: Callable[[float], Awaitable[None]] | None = None,
    limiter: RateLimiter | None = None,
    **kwargs: Any,
) -> httpx.Response:
    """POST with bounded retry on timeouts, network errors and 429/5xx.

    Other responses (incl. 4xx) are returned untouched for the caller to handle. When retries
    are exhausted a `ProviderError` names the provider, model and timeout, so `Worker error:`
    is readable. A 401/403 raises a `ProviderError` naming `key_env` (the variable, never its
    value) as missing or rejected. Extend `RETRY_STATUS` / `_TRANSIENT` to change what is
    transient.
    """
    sleep = sleep or asyncio.sleep  # resolved at call time so tests can patch it
    last = ""
    delay = 0.0
    attempt = -1
    while (attempt := attempt + 1) <= retries:
        if attempt:
            await sleep(delay)
        if limiter:
            await limiter.acquire()
        try:
            resp = await asyncio.wait_for(client.post(url, **kwargs), timeout)
        except _TRANSIENT as exc:
            last, delay = type(exc).__name__, backoff * 2**attempt
            continue
        if resp.status_code in (401, 403):
            raise ProviderError(auth_message(provider, key_env, resp.status_code, resp.text))
        if resp.status_code not in RETRY_STATUS or rejected_call(resp) or context_overflow(resp):
            return resp
        last = f"HTTP {resp.status_code}: {resp.text[:120]!r}"
        if resp.status_code == 429:  # rate limits reset per minute: wait longer, honor Retry-After
            ra = resp.headers.get("retry-after", "")
            delay = float(ra) if ra.isdigit() else min(30.0, max(backoff, 10.0) * 2**attempt)
            retries = max(retries, 4)
        else:
            delay = backoff * 2**attempt
    raise ProviderError(
        f"{provider} model `{model}` unavailable after {attempt} attempts "
        f"(timeout {timeout:g}s, last error: {last})"
    )


_ACT_CALL_RE = re.compile(
    r"act\(\s*(?P<args>.*)\s*\)",
    re.DOTALL,
)
_MULTILINE_ACT_RE = re.compile(
    r"act\(\s*(?:(?:cmd|command)\s*=\s*)?(?P<q1>\"\"\"|'''|\"|')(?P<cmd>.*?)(?P=q1)"
    r"(?:\s*,\s*(?:stdin\s*=\s*)?(?P<q2>\"\"\"|'''|\"|')(?P<stdin>[\s\S]*)(?P=q2))?\s*\)",
)
_TOOL_XML_RE = re.compile(
    r"<tool_call>\s*(?P<body>.*?)\s*</tool_call>",
    re.DOTALL,
)


def parse_tool_arguments(raw_args: str | dict[str, Any]) -> ActionCall | None:
    """Parse tool arguments from a dict or JSON string into an ActionCall."""
    data: dict[str, Any]
    if isinstance(raw_args, dict):
        data = raw_args
    else:
        try:
            parsed = json.loads(raw_args)
            if not isinstance(parsed, dict):
                return None
            data = parsed
        except Exception:
            return None

    # If the model called `act` with {"cmd": ..., "stdin": ...}
    if "cmd" in data:
        cmd = str(data.get("cmd") or "").strip()
        stdin = str(data["stdin"]) if data.get("stdin") is not None else None
        return ActionCall(cmd=cmd, stdin=stdin) if cmd else None

    if "command" in data:
        cmd = str(data.get("command") or "").strip()
        stdin = str(data["stdin"]) if data.get("stdin") is not None else None
        return ActionCall(cmd=cmd, stdin=stdin) if cmd else None

    return None


def parse_params(items: Iterable[str]) -> dict[str, Any]:
    """`["temperature=0", "think=false"]` -> `{"temperature": 0, "think": False}` (JSON values)."""
    out: dict[str, Any] = {}
    for item in items:
        key, sep, raw = item.partition("=")
        if not sep or not key.strip():
            raise ValueError(f"bad --param `{item}`: expected KEY=VALUE")
        try:
            out[key.strip()] = json.loads(raw)
        except ValueError:
            out[key.strip()] = raw
    return out


_TOOL_NAME_RE = re.compile(r"[A-Za-z_][\w.-]*")


def action_from_tool_call(name: object, raw_args: str | dict[str, Any]) -> ActionCall | None:
    """Turn a native tool call into an ActionCall.

    `act` arguments parse as usual. A call to another name (`edit`, `bash`, or `edit<|channel|>x`
    with harmony markers) becomes `<name> --k 'v'` so the registry answers with its JIT usage
    instead of a silent nudge.
    """
    action = parse_tool_arguments(raw_args)
    if action is not None:
        return action
    match = _TOOL_NAME_RE.match(str(name or ""))
    fn = match.group(0) if match else ""
    if not fn or fn == "act":
        return None
    args = raw_args
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            args = {}
    if isinstance(args, dict) and args:
        return ActionCall(cmd=f"{fn} " + " ".join(f"--{k} {v!r}" for k, v in args.items()))
    return ActionCall(cmd=fn)


_PARAM_CMD_RE = re.compile(r'<parameter\s+name="cmd"\s*>(?P<value>.*?)</parameter>', re.DOTALL)
_PARAM_STDIN_RE = re.compile(r'<parameter\s+name="stdin"\s*>(?P<value>.*?)</parameter>', re.DOTALL)

Dialect = Callable[[str], "ActionCall | None"]


def _dialect_tool_call_json(text: str) -> ActionCall | None:
    """`<tool_call>{json}</tool_call>` blocks (common in Qwen models)."""
    match = _TOOL_XML_RE.search(text)
    if not match:
        return None
    try:
        payload = json.loads(match.group("body").strip())
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    args = payload.get("arguments") or payload.get("parameters") or payload
    return parse_tool_arguments(args)


def _dialect_raw_json(text: str) -> ActionCall | None:
    """A raw JSON object containing `"cmd"` somewhere in the text."""
    if '"cmd"' not in text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if 0 <= start < end:
        return parse_tool_arguments(text[start : end + 1])
    return None


def _dialect_parameter_tags(text: str) -> ActionCall | None:
    """`<parameter name="cmd">X</parameter>` with optional `stdin` parameter."""
    cmd_match = _PARAM_CMD_RE.search(text)
    if not cmd_match:
        return None
    cmd = cmd_match.group("value").strip()
    if not cmd:
        return None
    stdin_match = _PARAM_STDIN_RE.search(text)
    return ActionCall(cmd=cmd, stdin=stdin_match.group("value") if stdin_match else None)


def _act_from_ast(args: str) -> ActionCall | None:
    try:
        tree = ast.parse(f"f({args})", mode="eval")
    except SyntaxError:
        return None
    if not isinstance(tree.body, ast.Call):
        return None
    call = tree.body
    cmd_val: str | None = None
    stdin_val: str | None = None
    if call.args and isinstance(call.args[0], ast.Constant):
        cmd_val = str(call.args[0].value)
    if len(call.args) > 1 and isinstance(call.args[1], ast.Constant):
        stdin_val = str(call.args[1].value)
    for kw in call.keywords:
        if kw.arg in ("cmd", "command") and isinstance(kw.value, ast.Constant):
            cmd_val = str(kw.value.value)
        elif kw.arg == "stdin" and isinstance(kw.value, ast.Constant):
            stdin_val = str(kw.value.value)
    return ActionCall(cmd=cmd_val, stdin=stdin_val) if cmd_val else None


def _dialect_act_text(text: str) -> ActionCall | None:
    """Python-style `act("...", stdin="...")` call written in plain text."""
    ml_match = _MULTILINE_ACT_RE.search(text)
    if ml_match:
        cmd_str = ml_match.group("cmd").strip()
        if cmd_str:
            return ActionCall(cmd=cmd_str, stdin=ml_match.group("stdin"))
    act_match = _ACT_CALL_RE.search(text)
    if act_match:
        return _act_from_ast(act_match.group("args"))
    return None


DIALECTS: list[Dialect] = [
    _dialect_tool_call_json,
    _dialect_raw_json,
    _dialect_parameter_tags,
    _dialect_act_text,
]


def register_dialect(fn: Dialect) -> Dialect:
    """Append a custom tool-call dialect extractor to `DIALECTS`."""
    DIALECTS.append(fn)
    return fn


def extract_fallback_action(text: str, extra: Iterable[Dialect] = ()) -> ActionCall | None:
    """Extract an ActionCall when a small 9B model emits tool syntax inside plain text."""
    if not text:
        return None
    for dialect in (*DIALECTS, *extra):
        call = dialect(text)
        if call:
            return call
    return None
