"""Control harness: plain OpenAI-compatible tool loop (bash/read_file/write_file), append-only history,
stop when the model answers without a tool call. Same model, different harness => isolates tether's effect."""
import argparse
import json
import os
import subprocess
import time

import httpx

TOOLS = [
    {"type": "function", "function": {"name": "bash", "description": "Run a shell command in the workspace.",
     "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "read_file", "description": "Read a text file.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "write_file", "description": "Create or overwrite a file.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                    "required": ["path", "content"]}}},
]
SYSTEM = ("You are a capable assistant working in a project directory with tools. Use the tools to do the task. "
          "When finished, reply with a plain-text final answer and no tool call.")


def run_tool(name, args, ws):
    try:
        if name == "bash":
            p = subprocess.run(args["command"], shell=True, cwd=ws, capture_output=True, text=True, timeout=60)
            return (p.stdout + p.stderr)[-10000:] or f"(exit {p.returncode})"
        if name == "read_file":
            return open(os.path.join(ws, args["path"])).read()[:20000]
        if name == "write_file":
            p = os.path.join(ws, args["path"])
            os.makedirs(os.path.dirname(p) or ws, exist_ok=True)
            open(p, "w").write(args["content"])
            return "ok"
        return f"unknown tool {name}"
    except Exception as e:
        return f"error: {e}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--key-env", default="")
    ap.add_argument("--ws", required=True)
    ap.add_argument("--goal", required=True)
    ap.add_argument("--max-turns", type=int, default=40)
    ap.add_argument("--result-file", required=True)
    ap.add_argument("--stats-file", required=True)
    a = ap.parse_args()
    hdr = {"Authorization": f"Bearer {os.environ.get(a.key_env, 'x')}"}
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": a.goal}]
    pt = ct = turns = 0
    peak = 0
    final, status = "", "max_turns"
    t0 = time.time()
    with httpx.Client(timeout=300) as c:
        for turns in range(1, a.max_turns + 1):
            for attempt in range(4):
                r = c.post(f"{a.base_url}/chat/completions", headers=hdr,
                           json={"model": a.model, "messages": msgs, "tools": TOOLS, "temperature": 0.2})
                if r.status_code in (429, 500, 502, 503, 504) and attempt < 3:
                    time.sleep(2 * (attempt + 1))
                    continue
                break
            if r.status_code != 200:
                status, final = "http_error", f"HTTP {r.status_code}: {r.text[:300]}"
                break
            d = r.json()
            u = d.get("usage") or {}
            pt += u.get("prompt_tokens", 0)
            ct += u.get("completion_tokens", 0)
            peak = max(peak, u.get("prompt_tokens", 0))
            m = d["choices"][0]["message"]
            msgs.append({k: v for k, v in m.items() if k in ("role", "content", "tool_calls") and v is not None})
            if not m.get("tool_calls"):
                final, status = m.get("content") or "", "completed"
                break
            for tc in m["tool_calls"]:
                try:
                    args = json.loads(tc["function"]["arguments"] or "{}")
                except ValueError:
                    args = {}
                msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": run_tool(tc["function"]["name"], args, a.ws)})
    open(a.result_file, "w").write(final)
    json.dump({"status": status, "steps": turns, "prompt_tokens": pt, "completion_tokens": ct, "peak_tokens": peak,
               "wall_s": round(time.time() - t0, 1)}, open(a.stats_file, "w"))


if __name__ == "__main__":
    main()
