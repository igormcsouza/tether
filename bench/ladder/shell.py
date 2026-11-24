"""Everyday Ubuntu-terminal work: the opt-in `shell` kind (`--kinds shell`), six tiers, imported by tasks.py.

A person asks for a file, a rename, a CSV summary, a search, a broken script fixed, a log report. Each task
starts from a small folder of its own (no `shop` project, no web) and is graded deterministically:
`checks` read the deliverable text (as in general.py), `ws_checks` look at the workspace after the run
(renamed files, an archive made by running the script in a fresh copy). Only coreutils, grep, sed, awk,
find, python3 and tar are needed. `ref` is the set of files a correct solution leaves (None deletes a
file), so `validate.py` can prove the grader.
"""
import csv
import io
import random
import re
import shutil
import subprocess
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
