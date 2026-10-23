"""Benchmark runner. Matrix = runners x models x tasks x trials. Results appended to <out>/results.jsonl.

runners: tether (CLI under test; --tether-bin selects a version), naive (control loop), claude (Claude Code baseline).
"""
import argparse
import asyncio
import json
import os
import re
import shutil
import signal
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grade  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TASK_CFG = {  # tether tools / step cap / wall timeout
    "code-simple": ("edit,bash", 30, 600), "code-medium": ("edit,bash", 40, 900), "code-hard": ("edit,bash", 50, 1200),
    "qa": ("", 10, 300), "content": ("", 10, 300), "review": ("edit", 15, 420),
}


def group(model):
    return "nvidia" if model.startswith("openai/") else "ollama" if model.startswith("ollama/") else "claude" if model.startswith(("claude", "cc/")) else "nvidia"


_HELP = {}


def flags(tether_bin):
    if tether_bin not in _HELP:
        import subprocess
        _HELP[tether_bin] = subprocess.run([tether_bin, "run", "--help"], capture_output=True, text=True).stdout
    return _HELP[tether_bin]


def build_cmd(runner, model, task, goal, ws, rd, tether_bin, params=()):
    tools, steps, _ = TASK_CFG[task]
    if runner == "tether":
        h = flags(tether_bin)
        cmd = [tether_bin, "run", "--model", model, "--max-steps", str(steps), "--db", f"{rd}/t.db"]
        if "--result-file" in h:
            cmd += ["--result-file", f"{rd}/result.txt", "--json"]
        if tools:
            cmd += ["--tools", tools]
        for item in params:
            cmd += ["--param", item]
        return cmd + [goal]
    if runner == "naive":
        base, key = ("http://localhost:11435/v1", "") if model.startswith("ollama/") else ("https://integrate.api.nvidia.com/v1", "NVIDIA_API_KEY")
        return [sys.executable, f"{HERE}/naive_agent.py", "--base-url", base, "--model", model.split("/", 1)[1] if model.startswith("ollama/") else model.removeprefix("nvidia/"),
                "--key-env", key, "--ws", ws, "--goal", goal, "--max-turns", str(steps), "--result-file", f"{rd}/result.txt", "--stats-file", f"{rd}/stats.json"]
    if runner == "claude":
        return ["env", "-u", "ANTHROPIC_API_KEY", "claude", "-p", goal, "--model", model.removeprefix("cc/"), "--permission-mode", "bypassPermissions",
                "--output-format", "json", "--setting-sources", "", "--disable-slash-commands", "--no-session-persistence", "--max-budget-usd", "3"]
    raise SystemExit(f"unknown runner {runner}")


def is_infra(r):
    """Provider/network failure or a run that never got going: says nothing about model or harness."""
    if r["runner"] == "tether" and r.get("exit") == 5:
        try:
            t = open(r["dir"] + "/stdout.txt", errors="replace").read() + open(r["dir"] + "/stderr.txt", errors="replace").read()
        except OSError:
            t = ""
        return bool(re.search(r"unavailable after|ProviderError|429|503|Not Found", t))
    return r["runner"] != "claude" and r["run_status"] == "timeout" and (r.get("steps") or 0) <= 3


def tether_stats(db):
    out = {}
    try:
        c = sqlite3.connect(db)
        s = c.execute("select status, step_count, peak_tokens, total_prompt_tokens, total_completion_tokens from sessions where parent_id is null order by created_at limit 1").fetchone()
        if s:
            out.update(status=s[0], steps=s[1], peak_tokens=s[2], prompt_tokens=s[3], completion_tokens=s[4])
        ev = dict(c.execute("select event_type, count(*) from turns where event_type is not null group by 1").fetchall())
        out["events"] = {k: v for k, v in ev.items() if k not in ("ok", "completed")}
    except Exception as e:
        out["db_error"] = repr(e)
    return out


async def one(sem, rec, args, results):
    runner, model, task, trial = rec
    name = f"{runner}__{model.replace('/', '_').replace(':', '-')}__{task}__t{trial}"
    rd = os.path.join(args.out, name)
    ws = os.path.join(rd, "ws")
    if os.path.exists(f"{rd}/done.json") and not args.force:
        old = json.load(open(f"{rd}/done.json"))
        if not (args.redo_infra and is_infra(old)):
            results.append(old)
            return
    async with sem[group(model)]:
        shutil.rmtree(rd, ignore_errors=True)
        os.makedirs(rd)
        shutil.copytree(f"{HERE}/tasks/{task}/ws", ws)
        goal = open(f"{HERE}/tasks/{task}/goal.txt").read().strip()
        cmd = build_cmd(runner, model, task, goal, ws, rd, args.tether_bin, args.param)
        env = dict(os.environ, OLLAMA_HOST="http://localhost:11435", PYTHONDONTWRITEBYTECODE="1")
        if model.startswith("openai/"):  # old tether has no providers.yaml: route openai/ to NVIDIA's OpenAI-compatible API
            env.update(OPENAI_BASE_URL="https://integrate.api.nvidia.com/v1", OPENAI_API_KEY=os.environ.get("NVIDIA_API_KEY", ""))
        t0 = time.time()
        p = await asyncio.create_subprocess_exec(*cmd, cwd=ws, env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, start_new_session=True)
        status = "ok"
        try:
            out, err = await asyncio.wait_for(p.communicate(), TASK_CFG[task][2])
        except asyncio.TimeoutError:
            os.killpg(p.pid, signal.SIGKILL)
            out, err = await p.communicate()
            status = "timeout"
        wall = round(time.time() - t0, 1)
        open(f"{rd}/stdout.txt", "wb").write(out)
        open(f"{rd}/stderr.txt", "wb").write(err)
        info = {"runner": runner, "model": model, "task": task, "trial": trial, "wall_s": wall, "exit": p.returncode, "run_status": status}
        result = ""
        if runner == "claude":
            try:
                j = json.loads(out.decode())
                result = j.get("result") or ""
                u = j.get("usage") or {}
                info.update(steps=j.get("num_turns"), cost_usd=j.get("total_cost_usd"), is_error=j.get("is_error"),
                            prompt_tokens=(u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0)),
                            completion_tokens=u.get("output_tokens"))
            except Exception:
                info["parse_error"] = True
        elif runner == "naive":
            try:
                info.update(json.load(open(f"{rd}/stats.json")))
                result = open(f"{rd}/result.txt").read()
            except Exception:
                info["parse_error"] = True
        else:
            result = open(f"{rd}/result.txt").read() if os.path.exists(f"{rd}/result.txt") else out.decode(errors="replace")
            info.update(tether_stats(f"{rd}/t.db"))
        if not os.path.exists(f"{rd}/result.txt"):
            open(f"{rd}/result.txt", "w").write(result)
        info.update(grade.grade(task, ws, result))
        info["dir"] = rd
        json.dump(info, open(f"{rd}/done.json", "w"))
        with open(f"{args.out}/results.jsonl", "a") as f:
            f.write(json.dumps(info) + "\n")
        results.append(info)
        print(f"[{len(results)}] {name}: score={info['score']} pass={info['pass']} {wall}s steps={info.get('steps')}", flush=True)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runners", default="tether")
    ap.add_argument("--models", required=True)
    ap.add_argument("--tasks", default=",".join(TASK_CFG))
    ap.add_argument("--trials", type=int, default=1)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tether-bin", default="tether")
    ap.add_argument("--param", action="append", default=[], help="forwarded to `tether run --param`")
    ap.add_argument("--par", default="nvidia=4,ollama=1,claude=3")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--redo-infra", action="store_true", help="rerun cells that failed on provider errors")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    sem = {k: asyncio.Semaphore(int(v)) for k, v in (x.split("=") for x in args.par.split(","))}
    recs = [(r, m, t, k) for r in args.runners.split(",") for m in args.models.split(",") for t in args.tasks.split(",") for k in range(args.trials)
            if (r == "claude") == m.startswith("cc/")]
    print(f"{len(recs)} runs", flush=True)
    results = []
    await asyncio.gather(*(one(sem, r, args, results) for r in recs))


asyncio.run(main())
