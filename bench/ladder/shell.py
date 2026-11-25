"""Everyday Ubuntu-terminal work: the opt-in `shell` kind (`--kinds shell`), nine tiers, imported by tasks.py.

A person asks for a file, a rename, a CSV summary, a search, a broken script fixed, a log report. Each task
starts from a small folder of its own (no `shop` project, no web) and is graded deterministically:
`checks` read the deliverable text (as in general.py), `ws_checks` look at the workspace after the run
(renamed files, an archive made by running the script in a fresh copy). Only coreutils, grep, sed, awk,
find, python3 and tar are needed. `ref` is the set of files a correct solution leaves (None deletes a
file), so `validate.py` can prove the grader.
"""
import csv
import io
import json
import random
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from tasks import Task, add


def _text(ws, rel):
    p = Path(ws) / rel
    return p.read_text() if p.is_file() else None


def _rows(text):
    return [r for r in csv.reader(io.StringIO(text)) if r]


# ---------------------------------------------------------------- 1: count unique IPs
def _access_log():
    rng = random.Random(7)
    pool = [f"203.0.113.{n}" for n in (5, 9, 14, 22, 31, 47, 58, 61, 77, 90, 104, 150, 171)]
    paths = ["/", "/index.html", "/api/items", "/api/cart", "/login", "/static/app.js"]
    out = []
    for _ in range(60):
        ip = rng.choice(pool)
        stamp = f"{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d}"
        method = rng.choice(["GET", "GET", "POST"])
        status = rng.choice([200, 200, 200, 404, 500])
        out.append(f'{ip} - - [24/Nov/2026:{stamp} +0000] "{method} {rng.choice(paths)} HTTP/1.1" {status} {rng.randint(120, 9000)}')
    return "\n".join(out) + "\n"


ACCESS_LOG = _access_log()
UNIQUE_IPS = len({line.split()[0] for line in ACCESS_LOG.splitlines()})

add(Task(
    "shell-1", "shell", 1,
    "access.log is a web server log in this folder. Count the unique client IP addresses in it and write only "
    "that number to answer.txt.",
    files={"access.log": ACCESS_LOG},
    deliverable="answer.txt",
    checks=[("the unique IP count", lambda t: t.strip() == str(UNIQUE_IPS)),
            ("one line, nothing else", lambda t: len(t.strip().splitlines()) == 1)],
    ref={"answer.txt": f"{UNIQUE_IPS}\n"},
))

# ---------------------------------------------------------------- 2: rename photos
PHOTO_FILES = {
    "photos/IMG_0001.JPG": "sunrise\n",
    "photos/IMG_0002.JPG": "lake\n",
    "photos/img_0003.jpg": "forest\n",
    "photos/IMG_0004 beach.JPG": "beach\n",
    "photos/IMG_0005.JPG": "city\n",
    "photos/notes.txt": "Trip photos, summer\n",
}
PHOTO_RENAMES = {  # old -> new, relative to photos/
    "IMG_0001.JPG": "img_0001.jpg",
    "IMG_0002.JPG": "img_0002.jpg",
    "IMG_0004 beach.JPG": "img_0004 beach.jpg",
    "IMG_0005.JPG": "img_0005.jpg",
}
PHOTO_EXPECT = {
    "photos/img_0001.jpg": "sunrise\n",
    "photos/img_0002.jpg": "lake\n",
    "photos/img_0003.jpg": "forest\n",
    "photos/img_0004 beach.jpg": "beach\n",
    "photos/img_0005.jpg": "city\n",
    "photos/notes.txt": "Trip photos, summer\n",
}


def _photos_tree(ws):
    d = Path(ws) / "photos"
    return {f"photos/{p.name}": p.read_text() for p in d.iterdir() if p.is_file()} if d.is_dir() else {}


add(Task(
    "shell-2", "shell", 2,
    "The photos/ folder has camera files named IMG_*.JPG. Rename each of them to lowercase img_*.jpg, keeping the "
    "number and any text after it (IMG_0004 beach.JPG becomes img_0004 beach.jpg). Leave img_0003.jpg and "
    "notes.txt alone, and do not change any file's contents.",
    files=PHOTO_FILES,
    ws_checks=[
        ("each photo renamed, content kept",
         lambda ws: all(_text(ws, p) == c for p, c in PHOTO_EXPECT.items() if p != "photos/notes.txt")),
        ("no IMG_ names left", lambda ws: not any(n.startswith("IMG_") for n in
                                                  (p.split("/")[-1] for p in _photos_tree(ws)))),
        ("nothing missing or extra in photos/", lambda ws: set(_photos_tree(ws)) == set(PHOTO_EXPECT)),
        ("notes.txt untouched", lambda ws: _text(ws, "photos/notes.txt") == PHOTO_EXPECT["photos/notes.txt"]),
    ],
    ref={**{f"photos/{old}": None for old in PHOTO_RENAMES},
         **{f"photos/{new}": PHOTO_FILES[f"photos/{old}"] for old, new in PHOTO_RENAMES.items()}},
))

# ---------------------------------------------------------------- 3: totals per region
SALES = """order_id,region,customer,amount
1001,North,"Smith, John",120.50
1002,South,Ana Lopes,75.00
1003,North,"Okafor, Grace",310.25
1004,East,Li Wei,42.10
1005,South,"Dupont, Marie",199.99
1006,West,Tom Reid,88.00
1007,East,"Kim, Jae",150.00
1008,North,Ben Hall,20.00
1009,West,"Rossi, Luca",64.75
1010,South,Sam Park,310.00
1011,East,"Patel, Ravi",99.90
1012,North,Eva Stone,45.25
1013,West,"Brown, Nia",205.00
1014,South,Hugo Diaz,12.35
"""


def _totals(csv_text):
    tot = {}
    for row in csv.DictReader(io.StringIO(csv_text)):
        tot[row["region"]] = tot.get(row["region"], 0) + float(row["amount"])
    return [(r, round(tot[r], 2)) for r in sorted(tot)]


SALES_TOTALS = _totals(SALES)

add(Task(
    "shell-3", "shell", 3,
    "sales.csv lists orders by region (some customer names contain a comma inside quotes). Write totals.csv with "
    "the total amount per region: a header line `region,total`, then one row per region sorted by region name, "
    "with two decimals.",
    files={"sales.csv": SALES},
    deliverable="totals.csv",
    checks=[("header is region,total", lambda t: _rows(t)[:1] == [["region", "total"]]),
            ("one row per region, sorted", lambda t: [r[0] for r in _rows(t)[1:]] == [r for r, _ in SALES_TOTALS]),
            ("totals are right", lambda t: [(r[0], round(float(r[1]), 2)) for r in _rows(t)[1:]] == SALES_TOTALS)],
    ref={"totals.csv": "region,total\n" + "".join(f"{r},{x:.2f}\n" for r, x in SALES_TOTALS)},
))

# ---------------------------------------------------------------- 4: find a leaked key
LEAK = re.compile(r"sk-[A-Za-z0-9]{20}")
SRC_FILES = {
    "src/README.md": "# Service\n\nInternal billing service. Run `make test`.\n",
    "src/app/__init__.py": "",
    "src/app/config.py": 'API_HOST = "https://api.example.test"\nTIMEOUT = 30\n',
    "src/app/db/__init__.py": "",
    "src/app/db/conn.py": 'def connect(url):\n    return {"url": url}\n',
    "src/app/db/models.py": "class Invoice:\n    id = None\n",
    "src/billing/__init__.py": "",
    "src/billing/invoice.py": "def total(lines):\n    return sum(l.price for l in lines)\n",
    "src/billing/stripe.py": 'STRIPE_KEY = "sk-k3Hs9Lq2Vb7Rt4Yx8Zn1"\n\ndef charge(amount):\n    return amount\n',
    "src/tests/test_billing.py": "def test_total():\n    assert True\n",
    "src/utils/strings.py": "def slug(text):\n    return text.lower().replace(' ', '-')\n",
    "src/utils/retry.py": "def retry(fn, times=3):\n    return fn()\n",
    "src/web/routes.py": 'ROUTES = ["/", "/invoices"]\n',
    "src/web/templates/index.html": '<script>const KEY = "sk-Qw8Rt3Ne6Lp1Zx5Vc2Bm9";</script>\n',
    "src/legacy/old_client.py": 'OLD = "sk-Abc12Def34Ghi56Jkl7"  # 19 characters, not a key\n',
    "src/docs/notes.md": "Keys are rotated; see risk-management-plan for the schedule.\n",
}
LEAKS = sorted(p for p, body in SRC_FILES.items() if LEAK.search(body))

add(Task(
    "shell-4", "shell", 4,
    "The src/ folder has a few dozen files in nested folders. Find the files that contain a leaked API key (a "
    "string shaped like sk- followed by exactly 20 letters or digits). Write the path of each one, relative to "
    "this folder, one per line, to answer.txt.",
    files=SRC_FILES,
    deliverable="answer.txt",
    checks=[("exactly the files with a key",
             lambda t: sorted(l.strip() for l in t.splitlines() if l.strip()) == LEAKS),
            ("one path per line, nothing else", lambda t: all(l.strip().startswith("src/")
                                                             for l in t.splitlines() if l.strip()))],
    ref={"answer.txt": "".join(f"{p}\n" for p in LEAKS)},
))

# ---------------------------------------------------------------- 5: fix backup.sh
BROKEN_BACKUP = """#!/bin/bash
# Back up the data/ folder into out/backup.tar.gz
mkdir out
for f in $(ls data)
do
  tar -cf out/backup.tar.gz data/$f
done
echo "backup written"
"""
FIXED_BACKUP = """#!/bin/bash
# Back up the data/ folder into out/backup.tar.gz
set -euo pipefail
mkdir -p out
tar -czf out/backup.tar.gz data
echo "backup written"
"""
BACKUP_FILES = {
    "backup.sh": BROKEN_BACKUP,
    "data/todo list.txt": "buy milk\nfix the bike\n",
    "data/budget.csv": "item,cost\nrent,1200\n",
    "data/notes/week 1.md": "# Week 1\n",
}
BACKUP_NEED = ("data/todo list.txt", "data/budget.csv", "data/notes/week 1.md")


def _backup(ws, drop=None):
    """Run backup.sh in a fresh copy of the workspace (without any old out/); (exit code, archive members or None)."""
    with tempfile.TemporaryDirectory(prefix="bk_") as tmp:
        dst = Path(tmp) / "w"
        shutil.copytree(ws, dst, ignore=shutil.ignore_patterns(".tether", "out", "__pycache__"))
        if drop:
            shutil.rmtree(dst / drop, ignore_errors=True)
        try:
            code = subprocess.run(["bash", "backup.sh"], cwd=dst, capture_output=True, timeout=60).returncode
        except subprocess.TimeoutExpired:
            return 1, None
        arc, names = dst / "out" / "backup.tar.gz", None
        if arc.is_file():
            try:
                with tarfile.open(arc, "r:gz") as tf:
                    names = [m.name.removeprefix("./") for m in tf.getmembers()]
            except (tarfile.TarError, OSError):
                names = None
        return code, names


add(Task(
    "shell-5", "shell", 5,
    "backup.sh in this folder is meant to archive data/ into out/backup.tar.gz, but it is broken: running "
    "`bash backup.sh` does not give a usable backup. Fix the script so that it works and fails loudly when data/ "
    "is missing. Keep it a short bash script.",
    files=BACKUP_FILES,
    ws_checks=[
        ("bash backup.sh exits 0", lambda ws: _backup(ws)[0] == 0),
        ("archive is gzip and holds data/", lambda ws: set(BACKUP_NEED) <= set(_backup(ws)[1] or [])),
        ("file with a space in its name is archived", lambda ws: "data/todo list.txt" in (_backup(ws)[1] or [])),
        ("missing data/ is an error", lambda ws: _backup(ws, drop="data")[0] != 0),
    ],
    ref={"backup.sh": FIXED_BACKUP},
))

# ---------------------------------------------------------------- 6: top errors from several logs
def _logs():
    rng = random.Random(11)
    msgs = (["payment gateway timeout"] * 14 + ["database connection refused"] * 11
            + ["unhandled exception in worker"] * 8 + ["cache miss storm on products"] * 5
            + ["healthcheck failed on db ping"] * 20)
    entries = [("ERROR", m) for m in msgs] + [("INFO", m) for m in ["order accepted", "user logged in", "cache warmed"] * 10]
    rng.shuffle(entries)
    days = ["2026-11-20", "2026-11-21", "2026-11-22"]
    per_day = {d: [] for d in days}
    for i, (level, msg) in enumerate(entries):
        day = days[i % 3]
        stamp = f"{day} {rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d}"
        per_day[day].append(f"{stamp} {level} {msg} [req={rng.getrandbits(24):06x}]")
    return {f"logs/app-{d}.log": "\n".join(sorted(lines)) + "\n" for d, lines in per_day.items()}


LOGS = _logs()


def _top_errors(files):
    counts = {}
    for text in files.values():
        for line in text.splitlines():
            m = re.match(r"\S+ \S+ ERROR (.*) \[req=\w+\]$", line)
            if m and "healthcheck" not in m.group(1):
                counts[m.group(1)] = counts.get(m.group(1), 0) + 1
    return sorted(counts.items(), key=lambda kv: -kv[1])[:3]


TOP_ERRORS = _top_errors(LOGS)

add(Task(
    "shell-6", "shell", 6,
    "logs/ holds three days of application logs (app-*.log). Write report.md: the top 3 ERROR messages across all "
    "three files, most frequent first, each with its count. Leave out healthcheck noise. The same message often "
    "carries a different [req=...] id, so count the message, not the id.",
    files=LOGS,
    deliverable="report.md",
    checks=[("the three messages are named",
             lambda t: all(m in t for m, _ in TOP_ERRORS)),
            ("ranked by count", lambda t: (lambda pos: all(p >= 0 for p in pos) and pos == sorted(pos))(
                [t.find(m) for m, _ in TOP_ERRORS])),
            ("each count next to its message",
             lambda t: all(re.search(re.escape(m) + r"\D{0,30}\b" + str(n) + r"\b", t) for m, n in TOP_ERRORS)),
            ("healthcheck left out", lambda t: "healthcheck" not in t.lower()),
            ("request ids stripped", lambda t: "req=" not in t),
            ("only the top three", lambda t: "cache miss" not in t.lower())],
    ref={"report.md": "# Top ERROR messages\n\n" + "".join(f"{i}. {m} - {n}\n" for i, (m, n) in enumerate(TOP_ERRORS, 1))},
))


def _lines(text):
    return [l.strip() for l in text.splitlines() if l.strip()] if text is not None else None


def _files_under(ws, top):
    base = Path(ws) / top
    return {p.relative_to(Path(ws)).as_posix() for p in base.rglob("*") if p.is_file()} if base.is_dir() else set()


# ---------------------------------------------------------------- 7: bisect by hand over snapshots
CHECK_PY = '''"""Check total_due() in the module named by argv[1]: exit 0 if it is right, 1 if it is wrong.

Rule: SAVE10 takes 10% off an order of 100 or more (an order of exactly 100 included).
"""
import importlib.util
import sys

CASES = [([50, 50], "SAVE10", 90.0), ([30, 20], None, 50.0), ([200], "SAVE10", 180.0),
         ([99.5], "SAVE10", 99.5), ([60, 45], "SAVE10", 94.5), ([60, 40], "OTHER", 100.0)]


def main():
    spec = importlib.util.spec_from_file_location("candidate", sys.argv[1])
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    bad = [(p, c, want) for p, c, want in CASES if abs(mod.total_due(p, c) - want) > 1e-9]
    for p, c, want in bad:
        print(f"wrong: total_due({p}, {c!r}) should be {want}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
'''
_V_HEAD = '''def total_due(prices, coupon=None):
    """Amount to charge for a list of prices."""
    subtotal = sum(prices)
    if coupon == "SAVE10" and subtotal >= 100:
        return round(subtotal * 0.9, 2)
    return round(subtotal, 2)
'''
V_BODY = {
    1: _V_HEAD.replace('    """Amount to charge for a list of prices."""\n', ""),
    2: _V_HEAD,
    3: _V_HEAD,
    4: _V_HEAD.replace("subtotal >= 100", "subtotal > 100"),  # the bug: an order of exactly 100 gets no discount
    5: _V_HEAD.replace("subtotal >= 100", "subtotal > 100").replace(
        "    subtotal = sum(prices)\n", "    # prices are in dollars\n    subtotal = sum(prices)\n"),
    6: _V_HEAD.replace("subtotal >= 100", "subtotal > 100").replace("Amount to charge", "Amount to charge (dollars)"),
}
T7_CALC_FIXED = V_BODY[4].replace("subtotal > 100", "subtotal >= 100")
T7_FILES = {"check.py": CHECK_PY, **{f"versions/calc_v{n}.py": body for n, body in V_BODY.items()}}


def _fixed_passes(ws):
    """The model's calc_fixed.py through the grader's own copy of check.py, in a fresh folder."""
    src = _text(ws, "calc_fixed.py")
    if src is None:
        return False
    with tempfile.TemporaryDirectory(prefix="fix_") as tmp:
        (Path(tmp) / "check.py").write_text(CHECK_PY)
        (Path(tmp) / "calc_fixed.py").write_text(src)
        try:
            r = subprocess.run([sys.executable, "check.py", "calc_fixed.py"], cwd=tmp, capture_output=True, timeout=60)
        except subprocess.TimeoutExpired:
            return False
    return r.returncode == 0


add(Task(
    "shell-7", "shell", 7,
    "versions/ holds six snapshots of one function, calc_v1.py to calc_v6.py, made one after another. Somewhere "
    "along the way a bug crept into total_due(). check.py in this folder takes a module path as its argument and "
    "exits 1 when total_due() is wrong. Find the first version in versions/ where check.py fails and write its "
    "file name (for example calc_v2.py) to answer.txt. Then write a fixed copy of that version as calc_fixed.py "
    "in this folder, so that `python3 check.py calc_fixed.py` exits 0.",
    files=T7_FILES,
    deliverable="answer.txt",
    checks=[("the first failing version, by file name", lambda t: t.strip() == "calc_v4.py")],
    ws_checks=[("calc_fixed.py passes check.py in a fresh copy", _fixed_passes)],
    ref={"answer.txt": "calc_v4.py\n", "calc_fixed.py": T7_CALC_FIXED},
))

# ---------------------------------------------------------------- 8: dedupe by content
DL_FILES = {
    "downloads/notes.txt": "Meeting notes: ship on Friday.\n",
    "downloads/old/notes (1).txt": "Meeting notes: ship on Friday.\n",
    "downloads/old/backup/notes.txt": "Meeting notes: ship on Friday.\n",
    "downloads/invoice.csv": "item,cost\nrent,1200\n",
    "downloads/archive/2025/invoice-copy.csv": "item,cost\nrent,1200\n",
    "downloads/invoice_v2.csv": "item,cost\nrent,1250\n",
    "downloads/a/config.ini": "[db]\nhost = localhost\nport = 5432\n",
    "downloads/b/config.ini": "[db]\nhost = localhost\nport = 5432\n",
    "downloads/readme.md": "# Readme\n\nSee docs.\n",
    "downloads/misc/readme (2).md": "# Readme\n\nSee docs.\n",
    "downloads/misc/deep/readme.md": "# Readme\n\nSee docs.\n",
    "downloads/todo.txt": "buy milk\n",
}
# every copy that goes: in each group the shortest path (ties alphabetically) is the one kept
DL_REMOVED = [
    "downloads/archive/2025/invoice-copy.csv",
    "downloads/b/config.ini",
    "downloads/misc/deep/readme.md",
    "downloads/misc/readme (2).md",
    "downloads/old/backup/notes.txt",
    "downloads/old/notes (1).txt",
]
DL_KEEP = {p: body for p, body in DL_FILES.items() if p not in DL_REMOVED}

add(Task(
    "shell-8", "shell", 8,
    "downloads/ holds twelve files from several folders. Some are byte-for-byte copies of others, under other "
    "names or in other folders. For each group of identical files, keep the one with the shortest path (fewest "
    "characters, counted from this folder); if two tie, keep the one whose path comes first alphabetically, and "
    "delete the other copies. Files that only look alike (invoice_v2.csv has one figure different) stay. Then "
    "write dupes.txt in this folder: the paths you deleted, one per line, sorted.",
    files=DL_FILES,
    ws_checks=[
        ("every file that stays is there, unchanged", lambda ws: all(_text(ws, p) == c for p, c in DL_KEEP.items())),
        ("no copy left behind in downloads/", lambda ws: _files_under(ws, "downloads") == set(DL_KEEP)),
        ("dupes.txt lists exactly the deleted paths, sorted", lambda ws: _lines(_text(ws, "dupes.txt")) == DL_REMOVED),
    ],
    ref={**{p: None for p in DL_REMOVED}, "dupes.txt": "".join(f"{p}\n" for p in DL_REMOVED)},
))

# ---------------------------------------------------------------- 9: a log report script, checked on unseen logs
JUNK_LOGS = [  # lines that are not valid records: skipped by the report
    '{"ts": "2026-11-20T10:59:00Z", "level": "WARN", "service": "auth"',
    "not json at all",
    '{"ts": "2026-11-20T10:58:00Z", "level": "INFO", "service": "billing", "ms": "250"}',
    '{"ts": "2026-11-20T10:57:00Z", "level": "ERROR", "service": "search"}',
]
HIDDEN_JUNK = [
    '{"level": "INFO", "service": "mail", "ms": 12.5}',
    '{"ts": "2026-11-20T11:00:00Z", "level": "INFO", "ms": 40}',
    "[1, 2, 3]",
]


def _log_files(seed, plan, junk, names):
    """Deterministic JSON-lines files: plan is (service, records) pairs, junk lines are mixed in."""
    rng = random.Random(seed)
    recs = []
    for service, n in plan:
        recs += [(service, rng.randint(20, 900)) for _ in range(n)]
    rng.shuffle(recs)
    lines = []
    for i, (svc, ms) in enumerate(recs):
        level = rng.choice(["INFO", "INFO", "WARN", "ERROR"])
        lines.append(f'{{"ts": "2026-11-20T10:{i % 60:02d}:{i * 7 % 60:02d}Z", "level": "{level}", '
                     f'"service": "{svc}", "ms": {ms}}}')
    lines += junk
    rng.shuffle(lines)
    out = {name: [] for name in names}
    for i, line in enumerate(lines):
        out[names[i % len(names)]].append(line)
    return {name: "\n".join(body) + "\n" for name, body in out.items()}


def _report_csv(files):
    """Reference rule: valid = JSON object, text service, whole-number ms; p95 = nearest rank ceil(0.95 n)."""
    per = {}
    for text in files.values():
        for line in text.splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not isinstance(rec, dict):
                continue
            svc, ms = rec.get("service"), rec.get("ms")
            if isinstance(svc, str) and svc and isinstance(ms, int) and not isinstance(ms, bool):
                per.setdefault(svc, []).append(ms)
    rows = ["service,count,p95_ms"]
    for svc in sorted(per):
        vals = sorted(per[svc])
        rank = (95 * len(vals) + 99) // 100
        rows.append(f"{svc},{len(vals)},{vals[rank - 1]}")
    return "\n".join(rows) + "\n"


LOG_FILES = _log_files(23, [("api", 24), ("auth", 9), ("billing", 6), ("search", 4)], JUNK_LOGS,
                       ["logs/app-1.log", "logs/app-2.log", "logs/app-3.log"])
REPORT_CSV = _report_csv(LOG_FILES)
HIDDEN_LOG_FILES = _log_files(99, [("cart", 17), ("api", 5), ("mail", 22)], HIDDEN_JUNK,
                              ["node-1.log", "node-2.log", "node-3.log"])
HIDDEN_CSV = _report_csv(HIDDEN_LOG_FILES)
REPORT_SH = """#!/bin/bash
# Usage: bash report.sh <log dir>. Prints service,count,p95_ms for the valid records of every file in the folder.
set -euo pipefail
python3 - "$1" <<'PY'
import json
import os
import sys

folder = sys.argv[1]
per = {}
for name in sorted(os.listdir(folder)):
    path = os.path.join(folder, name)
    if not os.path.isfile(path):
        continue
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not isinstance(rec, dict):
                continue
            svc, ms = rec.get("service"), rec.get("ms")
            if isinstance(svc, str) and svc and isinstance(ms, int) and not isinstance(ms, bool):
                per.setdefault(svc, []).append(ms)
print("service,count,p95_ms")
for svc in sorted(per):
    vals = sorted(per[svc])
    rank = (95 * len(vals) + 99) // 100
    print(f"{svc},{len(vals)},{vals[rank - 1]}")
PY
"""


def _hidden_report_ok(ws):
    """Run the model's report.sh in a fresh copy of the workspace, on logs it has never seen."""
    with tempfile.TemporaryDirectory(prefix="rep_") as tmp, tempfile.TemporaryDirectory(prefix="hid_") as hid:
        dst = Path(tmp) / "w"
        shutil.copytree(ws, dst, ignore=shutil.ignore_patterns(".tether", "__pycache__"))
        for name, text in HIDDEN_LOG_FILES.items():
            (Path(hid) / name).write_text(text)
        try:
            r = subprocess.run(["bash", "report.sh", hid], cwd=dst, capture_output=True, text=True, timeout=20)
        except subprocess.TimeoutExpired:
            return False
    return r.returncode == 0 and _lines(r.stdout) == _lines(HIDDEN_CSV)


add(Task(
    "shell-9", "shell", 9,
    "logs/ holds three files of JSON lines from a service mesh. A valid line is a complete JSON object with a "
    "text service and a whole-number ms (milliseconds); the rest are broken or incomplete and must be skipped. "
    "Write report.sh in this folder: an executable script that takes a log directory as its only argument, reads "
    "every file in it, and prints CSV to stdout: the header `service,count,p95_ms`, then one row per service "
    "sorted by name. count is the number of valid records for the service, any level. p95_ms is the nearest-rank "
    "95th percentile of its ms values: sort them ascending and take the value at position ceil(0.95 x count), "
    "counting from 1. Then run it on logs/ and save its output as report.csv in this folder.",
    files=LOG_FILES,
    ws_checks=[
        ("report.csv has the right rows", lambda ws: _lines(_text(ws, "report.csv")) == _lines(REPORT_CSV)),
        ("report.sh gives the right CSV on a log folder it has not seen", _hidden_report_ok),
        ("logs/ left as it was", lambda ws: all(_text(ws, p) == c for p, c in LOG_FILES.items())),
    ],
    ref={"report.sh": REPORT_SH, "report.csv": REPORT_CSV},
))
