"""Deterministic graders. grade(task, ws, result_text) -> {"score": 0..1, "pass": bool, "detail": {...}}"""
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TASKS = os.path.join(HERE, "tasks")


def _tree_hash(path):
    h = hashlib.sha256()
    for root, _, files in sorted(os.walk(path)):
        for f in sorted(files):
            if f.endswith(".pyc"):
                continue
            p = os.path.join(root, f)
            h.update(os.path.relpath(p, path).encode())
            h.update(open(p, "rb").read())
    return h.hexdigest()


def _code(task, ws, _result):
    tmp = tempfile.mkdtemp(prefix="g_")
    try:
        shutil.copytree(ws, tmp, dirs_exist_ok=True)
        orig_tests = os.path.join(TASKS, task, "ws", "tests")
        tampered = os.path.isdir(orig_tests) and _tree_hash(orig_tests) != _tree_hash(os.path.join(ws, "tests"))
        shutil.copy(os.path.join(TASKS, task, "hidden", "test_hidden.py"), os.path.join(tmp, "_hidden_test.py"))
        try:
            p = subprocess.run([sys.executable, "-m", "unittest", "-v", "_hidden_test"], cwd=tmp, capture_output=True,
                               text=True, timeout=90)
            out = p.stderr + p.stdout
        except subprocess.TimeoutExpired:
            return {"score": 0.0, "pass": False, "detail": {"error": "hidden tests timed out"}}
        ok = len(re.findall(r"\.\.\. ok$", out, re.M))
        bad = len(re.findall(r"\.\.\. (FAIL|ERROR)$", out, re.M))
        total = ok + bad
        score = ok / total if total else 0.0
        if tampered:
            return {"score": 0.0, "pass": False, "detail": {"tampered_tests": True, "hidden_ok": ok, "hidden_total": total}}
        return {"score": round(score, 3), "pass": total > 0 and bad == 0, "detail": {"hidden_ok": ok, "hidden_total": total}}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _json_array(text):
    m = re.search(r"\[.*\]", text or "", re.S)
    if not m:
        return None
    for parse in (json.loads, ast.literal_eval):
        try:
            v = parse(m.group(0))
            return v if isinstance(v, list) else None
        except (ValueError, SyntaxError):
            pass
    return None


def _qa(_task, _ws, result):
    arr = _json_array(result)
    checks = [
        lambda a: "17:25" in a,
        lambda a: re.search(r"\b391(\.0+)?\b", a) is not None,
        lambda a: "canberra" in a.lower(),
        lambda a: re.sub(r"\s", "", a) == "[1,3]",
        lambda a: re.search(r"\b(10|ten)\b", a.lower()) is not None,
        lambda a: ("1024" in a or "2**10" in a.replace(" ", "") or "2^10" in a.replace(" ", "")) and re.search(r"\b24\b", a) is not None,
    ]
    if arr is None or len(arr) != 6:
        return {"score": 0.0, "pass": False, "detail": {"error": "not a JSON array of 6"}}
    got = [bool(c(str(a))) for c, a in zip(checks, arr)]
    return {"score": round(sum(got) / 6, 3), "pass": all(got), "detail": {"correct": got}}


def _content(_task, _ws, result):
    t = (result or "").strip()
    words = len(re.findall(r"\S+", t))
    lines = [ln for ln in t.splitlines() if ln.strip()]
    sentences = re.split(r"(?<=[.?])\s+", t.replace("\n", " "))
    last = sentences[-1] if sentences else ""
    c = {
        "<=120 words": words <= 120 and words > 0,
        "3 bullets": sum(1 for ln in lines if ln.startswith("- ")) == 3,
        "snapshot": "snapshot" in t.lower(),
        "rollback": "rollback" in t.lower(),
        "CTA last": "tidepool.dev" in last.lower(),
        "no !": "!" not in t,
        "no banned": not re.search(r"revolutionary|game-changing", t, re.I),
    }
    return {"score": round(sum(c.values()) / len(c), 3), "pass": all(c.values()), "detail": {"checks": c, "words": words}}


FLAWS = {
    "selection/no-randomisation": r"random|self-select|selection bias|volunteer|chose to install|non-?random|assign",
    "causal-overreach": r"causal|causation|\bcause|correlat|overreach|overstat",
    "tiny-sample/generalise": r"small sample|sample size|n\s*=\s*1[12]|23 (student|participant)|under-?power|low power|generali[sz]|single (university|course)|one (course|university)",
    "multiple-comparisons": r"multiple (comparison|testing|outcome|test)|bonferroni|family-?wise|false[- ]positive|correction|cherry|selective",
    "number-inconsistency": r"inconsisten|discrepan|mismatch|contradict|12\.4.{0,80}(8\.1|7\.2)|(8\.1|7\.2).{0,80}12\.4",
    "baseline-gpa-imbalance": r"gpa|baseline|prior (performance|achievement|ability)|confound|not matched|unmatched|equivalen",
    "unblinded-grader": r"blind|grader|grading|instructor|assessor|rater",
    "no-effect-size/CI": r"effect size|confidence interval|\bCIs?\b|cohen",
}


def _review(_task, _ws, result):
    t = result or ""
    hit = {k: bool(re.search(v, t, re.I)) for k, v in FLAWS.items()}
    n = len(re.findall(r"^\s*\d+[.)]", t, re.M))
    return {"score": round(sum(hit.values()) / len(hit), 3), "pass": sum(hit.values()) >= 6,
            "detail": {"found": [k for k, v in hit.items() if v], "missed": [k for k, v in hit.items() if not v], "items": n}}


def _focus(task, ws, result):
    """_code + scope: the goal allows editing mini/cli.py only; other changes halve the score."""
    r = _code(task, ws, result)
    orig = os.path.join(TASKS, task, "ws")
    touched = []
    for root, dirs, files in os.walk(orig):
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), orig)
            p = os.path.join(ws, rel)
            if rel != os.path.join("mini", "cli.py") and (
                not os.path.exists(p) or open(p, "rb").read() != open(os.path.join(root, f), "rb").read()
            ):
                touched.append(rel)
    r["detail"]["touched_other"] = touched
    if touched:
        r["score"], r["pass"] = round(r["score"] / 2, 3), False
    return r


def _steps(t):
    return len(re.findall(r"^\s*\d+[.)]", t, re.M))


def _plan(_task, _ws, result):
    t = result or ""
    c = {
        "6-10 numbered steps": 6 <= _steps(t) <= 10,
        "names client.py": "client.py" in t,
        "names config.py": "config.py" in t,
        "names get/post": bool(re.search(r"\bget\b", t)) and bool(re.search(r"\bpost\b", t)),
        "backoff+jitter": bool(re.search(r"exponential", t, re.I)) and bool(re.search(r"jitter", t, re.I)),
        "retry settings": bool(re.search(r"max[_ -]?(retries|attempts)|retry[_ -]?(limit|count)", t, re.I)) and bool(re.search(r"base[_ -]?(delay|backoff)|backoff[_ -]?(base|factor)", t, re.I)),
        "429 and 5xx": "429" in t and bool(re.search(r"5xx|50\d", t)),
        "not retried (4xx)": bool(re.search(r"4xx|not retr|never retr|do not retry|don't retry|non-retry", t, re.I)),
        "Retry-After": bool(re.search(r"retry-after", t, re.I)),
        "tests without network": bool(re.search(r"mock|fake|stub|patch|monkeypatch|inject", t, re.I)) and bool(re.search(r"test", t, re.I)),
        "idempotency of post": bool(re.search(r"idempot|post.{0,60}(retry|retri)|(retry|retri).{0,60}post", t, re.I)),
    }
    return {"score": round(sum(c.values()) / len(c), 3), "pass": sum(c.values()) >= 9, "detail": {"missed": [k for k, v in c.items() if not v]}}


BUGS = {
    "page off-by-one": r"page.{0,200}(off.by.one|number\s*-\s*1|\(number - 1\)|1-based|zero|skips? the first)|(off.by.one|1-based).{0,200}page",
    "mutable default": r"mutable default|tags=\[\]|default (argument|arg|list)|shared (between|across)",
    "float money": r"float.{0,120}(money|price|currenc|rounding|precision|decimal)|decimal",
    "float equality": r"(==|equal).{0,100}(float|0\.0)|is_free|float.{0,60}(compar|equal)|isclose",
    "sql injection": r"sql.?inject|parameteri[sz]|placeholder|string concat|bind (var|param)",
    "file not closed": r"(not|never) clos|resource leak|context manager|with open|leak",
    "keyerror/missing": r"keyerror|missing (key|item|name)|\.get\(|unknown name|not in (the )?(stock|dict)",
    "split malformed": r"split.{0,100}(more than|exactly|two|malformed|blank|empty|valueerror)|blank line|malformed|empty line|valueerror",
}


def _codereview(_task, _ws, result):
    t = result or ""
    hit = {k: bool(re.search(v, t, re.I | re.S)) for k, v in BUGS.items()}
    must = ["page off-by-one", "mutable default", "sql injection", "file not closed", "keyerror/missing"]
    return {"score": round(sum(hit.values()) / len(hit), 3), "pass": all(hit[k] for k in must), "detail": {"missed": [k for k, v in hit.items() if not v], "items": _steps(t)}}


# Fast set (12): easy passes, partials and hard failures from the 0.2.6 baseline; tether's weak spots.
POLY_FAST = ("affine-cipher bottle-song list-ops paasio dot-dsl food-chain forth go-counting poker pov react "
             "rest-api").split()

# ~15 min: 4 flaky exercises that can flip + 3 fast guards that must not regress (baseline in canary_baseline.json)
POLY_CANARY = "phone-number tree-building grep pig-latin proverb robot-name list-ops".split()
POLY_PAIRED = "grep go-counting pov dominoes beer-song hangman wordy forth paasio poker".split()  # A/B set, see README
GUARDS = ("proverb", "robot-name", "list-ops")


def poly_dir(ex=""):
    """Aider polyglot-benchmark Python exercises (cloned once, never vendored)."""
    root = os.environ.get("POLYGLOT_DIR") or os.path.expanduser("~/.cache/tether-bench/polyglot-benchmark")
    if not os.path.isdir(root):
        subprocess.run(["git", "clone", "--depth", "1", "https://github.com/Aider-AI/polyglot-benchmark", root], check=True)
    return os.path.join(root, "python", "exercises", "practice", ex)


def poly_goal(ex):
    d = poly_dir(ex)
    docs = "\n\n".join(open(os.path.join(d, ".docs", f)).read() for f in ("instructions.md", "instructions.append.md")
                        if os.path.exists(os.path.join(d, ".docs", f)))
    sol = ex.replace("-", "_") + ".py"
    return (f"Implement `{sol}` in the current directory so that `python3 -m unittest discover -p '*_test.py'` passes. "
            f"Do not edit the test file.\n\n{docs}")


def _poly(task, ws, _result):
    ex = task.removeprefix("poly-")
    tmp = tempfile.mkdtemp(prefix="g_")
    try:
        shutil.copytree(ws, tmp, dirs_exist_ok=True)
        test = ex.replace("-", "_") + "_test.py"
        shutil.copy(os.path.join(poly_dir(ex), test), os.path.join(tmp, test))  # restore: editing tests cannot pass
        try:
            p = subprocess.run([sys.executable, "-m", "unittest", "-v", test[:-3]], cwd=tmp, capture_output=True, text=True, timeout=90)
        except subprocess.TimeoutExpired:
            return {"score": 0.0, "pass": False, "detail": {"error": "tests timed out"}}
        out = p.stderr + p.stdout
        ok = len(re.findall(r"\.\.\. ok$", out, re.M))
        bad = len(re.findall(r"\.\.\. (FAIL|ERROR)$", out, re.M))
        total = ok + bad
        return {"score": round(ok / total, 3) if total else 0.0, "pass": p.returncode == 0 and total > 0, "detail": {"ok": ok, "total": total}}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def grade(task, ws, result):
    orig = task
    if task.startswith("poly-"):
        task = "poly"
    fn = {"poly": _poly, "qa": _qa, "content": _content, "review": _review, "focus": _focus, "plan": _plan, "codereview": _codereview}.get(task, _code)
    try:
        return fn(orig, ws, result)
    except Exception as e:  # grader bug must never look like a model result
        return {"score": 0.0, "pass": False, "detail": {"grader_error": repr(e)}}


if __name__ == "__main__":
    task, ws, rf = sys.argv[1:4]
    print(json.dumps(grade(task, ws, open(rf).read() if os.path.exists(rf) else "")))
