"""24 ladder tasks: 6 tiers x {write, bugfix, plan, review}, all on the `shop` project (base.py).

Tier 1 hands over file, place and code. Each tier gives less: T2 names the behaviour, T3 makes the
model find the file, T4 leaves cases unsaid that hidden tests check, T5 spans modules, T6 is an
open goal. Graders are deterministic: hidden unittest files for code, regex rubrics for text.
Every task has a `ref` (files that make it score 1.0) so `validate.py` can prove the grader.
"""
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from base import project

KINDS = ("write", "bugfix", "plan", "review")


@dataclass
class Task:
    id: str
    kind: str
    tier: int
    goal: str
    files: dict = field(default_factory=dict)  # workspace overlay on top of base.project()
    hidden: str = ""  # hidden unittest source (code kinds)
    rubric: list = field(default_factory=list)  # text kinds: (label, [regex, ...]) all must match in one chunk
    herrings: list = field(default_factory=list)  # review: regexes that flag clean code
    ref: dict = field(default_factory=dict)  # files that solve it (validate.py)
    deliverable: str = ""  # text kinds: file the model must write
    allowed_files: tuple = ()  # plan: file names that exist or may be created


def workspace(task):
    return {**project(), **task.files}


# ---------------------------------------------------------------- code grading
def run_hidden(ws, source):
    """Run the hidden tests in a copy-free way: write the file, run unittest, parse the counts."""
    ws = Path(ws)
    (ws / "_hidden_test.py").write_text(source)
    try:
        p = subprocess.run([sys.executable, "-m", "unittest", "_hidden_test", "-v"], cwd=ws,
                           capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return 0, 1, "hidden tests timed out"
    finally:
        (ws / "_hidden_test.py").unlink(missing_ok=True)
    out = p.stderr + p.stdout
    m = re.search(r"Ran (\d+) tests?", out)
    total = int(m.group(1)) if m else 1
    f = re.search(r"FAILED \((.*?)\)", out)
    bad = sum(int(n) for n in re.findall(r"=(\d+)", f.group(1))) if f else 0
    if not m:
        bad = total
    return total - bad, total, out[-600:]


def grade_code(task, ws):
    ok, total, tail = run_hidden(ws, task.hidden)
    return ok / total, f"{ok}/{total} hidden tests"


# ---------------------------------------------------------------- text grading
def chunks(text):
    """Findings: bullets / numbered items / headings, with their continuation lines."""
    out, cur = [], []
    for line in text.splitlines():
        if re.match(r"\s*([-*+]|\d+[.)]|#{1,4})\s", line):
            if cur:
                out.append("\n".join(cur))
            cur = [line]
        elif line.strip():
            cur.append(line)
        elif cur:
            out.append("\n".join(cur))
            cur = []
    if cur:
        out.append("\n".join(cur))
    return out


def hit(chunk_list, patterns):
    return any(all(re.search(p, c, re.I | re.S) for p in patterns) for c in chunk_list)


def grade_text(task, ws):
    path = Path(ws) / task.deliverable
    if not path.exists() or not path.read_text().strip():
        return 0.0, f"{task.deliverable} missing or empty"
    text = path.read_text()
    cs = chunks(text)
    found = [label for label, pats in task.rubric if hit(cs, pats) or hit([text], pats[:1]) and len(pats) == 1]
    score = len(found) / len(task.rubric)
    notes = [f"{len(found)}/{len(task.rubric)} items"]
    if task.kind == "review":
        fp = sum(1 for c in cs if any(re.search(h, c, re.I) for h in task.herrings))
        if fp:
            score = max(0.0, score - 0.15 * fp)
            notes.append(f"{fp} false alarm(s)")
        if len(cs) > 2 * len(task.rubric) + 2:
            score *= 0.7
            notes.append("noisy review")
    if task.kind == "plan":
        known = set(task.allowed_files) | set(workspace(task))
        known_names = {k.split("/")[-1] for k in known}
        ghosts = {m for m in re.findall(r"\b([a-z_]+\.py)\b", text) if m not in known_names}
        if ghosts:
            score = max(0.0, score - 0.1 * len(ghosts))
            notes.append(f"invented files {sorted(ghosts)}")
    return score, ", ".join(notes)


def grade(task, ws):
    return grade_text(task, ws) if task.kind in ("plan", "review") else grade_code(task, ws)


def grade_copy(task, ws):
    """Grade a snapshot so a running model never sees the hidden tests."""
    import shutil
    tmp = tempfile.mkdtemp(prefix="gc_")
    try:
        shutil.copytree(ws, tmp, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".tether", "__pycache__"))
        return grade(task, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def pass_threshold(task):
    return 0.99 if task.kind in ("write", "bugfix") else 0.7


def numbered(src):
    return "\n".join(f"{i:3}| {l}" for i, l in enumerate(src.splitlines(), 1))


TASKS = {}


def add(t):
    TASKS[t.id] = t


# ================================================================= WRITE
add(Task(
    "write-1", "write", 1,
    "In shop/pricing.py add these lines at the very end of the file (after bulk_price), exactly:\n\n"
    "def apply_discount(price, pct):\n    return round(price * (1 - pct / 100), 2)\n",
    hidden='''import unittest
from shop.pricing import apply_discount
class T(unittest.TestCase):
    def test_ten(self): self.assertEqual(apply_discount(100, 10), 90.0)
    def test_zero(self): self.assertEqual(apply_discount(19.99, 0), 19.99)
    def test_all(self): self.assertEqual(apply_discount(50, 100), 0.0)
''',
    ref={"shop/pricing.py": project()["shop/pricing.py"] + "\n\ndef apply_discount(price, pct):\n    return round(price * (1 - pct / 100), 2)\n"},
))

add(Task(
    "write-2", "write", 2,
    "Add a function slugify(text) to shop/utils.py: lowercase the text, replace every run of "
    "non-alphanumeric characters with a single '-', and strip leading and trailing '-'.",
    hidden='''import unittest
from shop.utils import slugify
class T(unittest.TestCase):
    def test_basic(self): self.assertEqual(slugify("Hello, World!"), "hello-world")
    def test_spaces(self): self.assertEqual(slugify("  A  b "), "a-b")
    def test_empty(self): self.assertEqual(slugify(""), "")
    def test_symbols(self): self.assertEqual(slugify("C++ rocks"), "c-rocks")
''',
    ref={"shop/utils.py": project()["shop/utils.py"] + '''

def slugify(text):
    import re
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
'''},
))

COUPON_CART = project()["shop/cart.py"] + '''
    def apply_coupon(self, code):
        if code not in COUPONS:
            raise ValueError(f"unknown coupon {code}")
        self.coupon = code

'''
add(Task(
    "write-3", "write", 3,
    "Customers can use coupon codes at checkout. Support it on the cart: Cart.apply_coupon(code). "
    "SAVE10 takes 10% off the cart total, FIVEOFF takes $5 off (the total never goes below 0). "
    "An unknown code raises ValueError. Cart.total() must include the coupon.",
    hidden='''import unittest
from shop.cart import Cart
from shop.inventory import Inventory
def cart():
    inv = Inventory(); inv.add("A", "a", 10.0, 50); c = Cart(inv); c.add("A", 2); return c
class T(unittest.TestCase):
    def test_none(self): self.assertEqual(cart().total(), 20.0)
    def test_save10(self):
        c = cart(); c.apply_coupon("SAVE10"); self.assertEqual(c.total(), 18.0)
    def test_fiveoff(self):
        c = cart(); c.apply_coupon("FIVEOFF"); self.assertEqual(c.total(), 15.0)
    def test_floor(self):
        inv = Inventory(); inv.add("A", "a", 2.0, 5); c = Cart(inv); c.add("A"); c.apply_coupon("FIVEOFF")
        self.assertEqual(c.total(), 0)
    def test_unknown(self):
        with self.assertRaises(ValueError): cart().apply_coupon("NOPE")
''',
    ref={"shop/cart.py": '''"""Shopping cart."""
from shop.pricing import bulk_price

COUPONS = {"SAVE10": ("pct", 10), "FIVEOFF": ("off", 5)}


class Cart:
    def __init__(self, inventory):
        self.inventory = inventory
        self.lines = {}
        self.coupon = None

    def add(self, sku, qty=1):
        self.inventory.get(sku)
        self.lines[sku] = self.lines.get(sku, 0) + qty

    def apply_coupon(self, code):
        if code not in COUPONS:
            raise ValueError(f"unknown coupon {code}")
        self.coupon = code

    def total(self):
        t = sum(bulk_price(self.inventory.get(s)["price"], q) for s, q in self.lines.items())
        if self.coupon:
            kind, v = COUPONS[self.coupon]
            t = t * (1 - v / 100) if kind == "pct" else max(0, t - v)
        return round(t, 2)
'''},
))

add(Task(
    "write-4", "write", 4,
    "The inventory list is getting long. Add pagination to Inventory.list_items so the CLI can show "
    "it page by page (keyword arguments page and page_size). Existing callers must keep working.",
    hidden='''import unittest
from shop.inventory import Inventory
def inv(n=5):
    i = Inventory()
    for k in range(n): i.add(f"S{k}", "x", 1)
    return i
class T(unittest.TestCase):
    def test_default_all(self): self.assertEqual(len(inv().list_items()), 5)
    def test_first_page(self): self.assertEqual([x["sku"] for x in inv().list_items(page=1, page_size=2)], ["S0", "S1"])
    def test_last_partial(self): self.assertEqual([x["sku"] for x in inv().list_items(page=3, page_size=2)], ["S4"])
    def test_past_end(self): self.assertEqual(inv().list_items(page=9, page_size=2), [])
    def test_bad_page(self):
        with self.assertRaises(ValueError): inv().list_items(page=0, page_size=2)
    def test_bad_size(self):
        with self.assertRaises(ValueError): inv().list_items(page=1, page_size=0)
''',
    ref={"shop/inventory.py": project()["shop/inventory.py"].replace(
        '''    def list_items(self):
        return sorted(self._items.values(), key=lambda i: i["sku"])''',
        '''    def list_items(self, page=None, page_size=10):
        items = sorted(self._items.values(), key=lambda i: i["sku"])
        if page is None:
            return items
        if page < 1 or page_size < 1:
            raise ValueError("page and page_size must be >= 1")
        start = (page - 1) * page_size
        return items[start:start + page_size]''')},
))

TAX_PY = '''"""Sales tax by region."""
RATES = {"US-CA": 0.0725, "US-NY": 0.04, "EU": 0.2}


def rate(region):
    return RATES.get(region, 0.0)
'''
add(Task(
    "write-5", "write", 5,
    "Add sales tax. Rates: US-CA 7.25%, US-NY 4%, EU 20%, any other region 0%. Put the rates in a new "
    "module shop/tax.py with rate(region). Cart.total() must keep returning the pre-tax total (existing "
    "tests rely on it); add Cart.total_with_tax(region) rounded to cents. report.summary must also "
    "return a 'tax' key: the tax over all orders, each order taxed at its own region's rate on its 'total'.",
    hidden='''import unittest
from shop import tax
from shop.cart import Cart
from shop.inventory import Inventory
from shop.report import summary
class T(unittest.TestCase):
    def test_rates(self):
        self.assertEqual(tax.rate("EU"), 0.2); self.assertEqual(tax.rate("MARS"), 0.0)
    def test_cart(self):
        inv = Inventory(); inv.add("A", "a", 10.0, 9); c = Cart(inv); c.add("A", 4)
        self.assertEqual(c.total(), 40.0); self.assertEqual(c.total_with_tax("US-CA"), 42.9)
        self.assertEqual(c.total_with_tax("MARS"), 40.0)
    def test_summary(self):
        s = summary([{"id": 1, "date": "2025-01-01", "region": "EU", "total": 10.0},
                     {"id": 2, "date": "2025-01-02", "region": "US-NY", "total": 25.0}])
        self.assertEqual(s["tax"], 3.0); self.assertEqual(s["count"], 2); self.assertEqual(s["revenue"], 35.0)
    def test_summary_unknown_region(self):
        self.assertEqual(summary([{"id": 1, "date": "2025-01-01", "region": "X", "total": 9.0}])["tax"], 0.0)
''',
    ref={
        "shop/tax.py": TAX_PY,
        "shop/cart.py": project()["shop/cart.py"].replace("from shop.pricing import bulk_price", "from shop import tax\nfrom shop.pricing import bulk_price") + '''
    def total_with_tax(self, region):
        t = self.total()
        return round(t + t * tax.rate(region), 2)
''',
        "shop/report.py": project()["shop/report.py"].replace(
            '"""Order reports.', 'from shop import tax\n\n"""Order reports.', 1).replace(
            'return {"count": len(orders), "revenue": round(sum(o["total"] for o in orders), 2)}',
            'return {\n        "count": len(orders),\n        "revenue": round(sum(o["total"] for o in orders), 2),\n        "tax": round(sum(o["total"] * tax.rate(o["region"]) for o in orders), 2),\n    }'),
    },
))

add(Task(
    "write-6", "write", 6,
    "Add an `export` command to the shop CLI: `python -m shop.cli export ORDERS.json OUT.csv` writes a CSV "
    "of the orders and prints how many rows it wrote. Support an optional `--region R` filter.",
    hidden='''import csv, json, os, tempfile, unittest
from contextlib import redirect_stdout
from io import StringIO
from shop.cli import main
ORD = [{"id": 2, "date": "2025-02-01", "region": "EU", "total": 5.5},
       {"id": 1, "date": "2025-01-01", "region": "US-CA", "total": 10.0},
       {"id": 3, "date": "2025-03-01", "region": "EU", "total": 7.25}]
def run(*args):
    d = tempfile.mkdtemp(); src = os.path.join(d, "o.json"); out = os.path.join(d, "o.csv")
    json.dump(ORD, open(src, "w")); buf = StringIO()
    with redirect_stdout(buf): rc = main(["export", src, out, *args])
    return rc, buf.getvalue(), out
class T(unittest.TestCase):
    def test_rows(self):
        rc, said, out = run(); rows = list(csv.reader(open(out)))
        self.assertEqual(rc, 0); self.assertEqual(len(rows), 4); self.assertIn("3", said)
    def test_header(self):
        rc, said, out = run(); self.assertEqual(next(csv.reader(open(out)))[:1], ["id"])
        self.assertEqual(set(next(csv.reader(open(out)))), {"id", "date", "region", "total"})
    def test_sorted_by_date(self):
        rc, said, out = run(); self.assertEqual([r[0] for r in list(csv.reader(open(out)))[1:]], ["1", "2", "3"])
    def test_region(self):
        rc, said, out = run("--region", "EU"); self.assertEqual(len(list(csv.reader(open(out)))), 3)
    def test_missing_file(self):
        with redirect_stdout(StringIO()): self.assertNotEqual(main(["export", "/nope.json", "/tmp/x.csv"]), 0)
    def test_summary_still_works(self):
        d = tempfile.mkdtemp(); p = os.path.join(d, "o.json"); json.dump(ORD, open(p, "w"))
        buf = StringIO()
        with redirect_stdout(buf): rc = main(["summary", p])
        self.assertEqual(rc, 0); self.assertIn("3 orders", buf.getvalue())
''',
    ref={"shop/cli.py": '''"""Command line: `python -m shop.cli summary orders.json`."""
import csv
import sys

from shop import report, storage


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "export" and len(argv) in (3, 5):
        region = argv[4] if len(argv) == 5 and argv[3] == "--region" else None
        try:
            orders = storage.load_orders(argv[1])
        except FileNotFoundError:
            print(f"no such file: {argv[1]}", file=sys.stderr)
            return 1
        rows = sorted((o for o in orders if region in (None, o["region"])), key=lambda o: o["date"])
        with open(argv[2], "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["id", "date", "region", "total"])
            for o in rows:
                w.writerow([o["id"], o["date"], o["region"], o["total"]])
        print(f"{len(rows)} rows written")
        return 0
    if len(argv) != 2 or argv[0] != "summary":
        print("usage: shop.cli summary ORDERS.json", file=sys.stderr)
        return 2
    try:
        orders = storage.load_orders(argv[1])
    except FileNotFoundError:
        print(f"no such file: {argv[1]}", file=sys.stderr)
        return 1
    s = report.summary(orders)
    print(f"{s['count']} orders, revenue {s['revenue']:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''},
))


# ================================================================= BUGFIX
def broken(path, old, new):
    src = project()[path]
    assert old in src, (path, old)
    return {path: src.replace(old, new, 1)}


b1 = broken("shop/pricing.py", "if quantity >= BULK_THRESHOLD", "if quantity > BULK_THRESHOLD")
b1_line = next(i for i, l in enumerate(b1["shop/pricing.py"].splitlines(), 1) if "> BULK" in l)
add(Task(
    "bugfix-1", "bugfix", 1,
    f"shop/pricing.py line {b1_line} compares with `>` but must use `>=` (the bulk discount starts AT 10). "
    "Change that one comparison.",
    files=b1,
    hidden='''import unittest
from shop.pricing import bulk_price
class T(unittest.TestCase):
    def test_at_ten(self): self.assertEqual(bulk_price(10, 10), 90.0)
    def test_below(self): self.assertEqual(bulk_price(10, 9), 90.0)
    def test_above(self): self.assertEqual(bulk_price(10, 20), 180.0)
''',
    ref={"shop/pricing.py": project()["shop/pricing.py"]},
))

add(Task(
    "bugfix-2", "bugfix", 2,
    "Cart.add overwrites the quantity when the same sku is added twice (add 2 then add 3 gives 3, not 5). "
    "The failing test is tests/test_cart.py::CartTest::test_same_sku_adds_up. Fix it in shop/cart.py.",
    files=broken("shop/cart.py", "self.lines[sku] = self.lines.get(sku, 0) + qty", "self.lines[sku] = qty"),
    hidden='''import unittest
from shop.cart import Cart
from shop.inventory import Inventory
class T(unittest.TestCase):
    def test_adds_up(self):
        inv = Inventory(); inv.add("A", "a", 2.0, 9); c = Cart(inv); c.add("A", 2); c.add("A", 3)
        self.assertEqual(c.lines["A"], 5); self.assertEqual(c.total(), 10.0)
    def test_default_qty(self):
        inv = Inventory(); inv.add("A", "a", 2.0, 9); c = Cart(inv); c.add("A"); c.add("A")
        self.assertEqual(c.lines["A"], 2)
''',
    ref={"shop/cart.py": project()["shop/cart.py"]},
))

add(Task(
    "bugfix-3", "bugfix", 3,
    "Support reports that after a sale is refused with 'insufficient stock', the product shows a NEGATIVE "
    "stock number. Find and fix the cause.",
    files=broken("shop/inventory.py",
                 '''        if qty > item["stock"]:
            raise ValueError("insufficient stock")
        item["stock"] -= qty''',
                 '''        item["stock"] -= qty
        if item["stock"] < 0:
            raise ValueError("insufficient stock")'''),
    hidden='''import unittest
from shop.inventory import Inventory
class T(unittest.TestCase):
    def test_refused_keeps_stock(self):
        i = Inventory(); i.add("A", "a", 1, 3)
        with self.assertRaises(ValueError): i.remove_stock("A", 5)
        self.assertEqual(i.get("A")["stock"], 3)
    def test_exact(self):
        i = Inventory(); i.add("A", "a", 1, 3); i.remove_stock("A", 3); self.assertEqual(i.get("A")["stock"], 0)
    def test_normal(self):
        i = Inventory(); i.add("A", "a", 1, 3); i.remove_stock("A", 1); self.assertEqual(i.get("A")["stock"], 2)
''',
    ref={"shop/inventory.py": project()["shop/inventory.py"]},
))

b4 = broken("shop/report.py", 'key = o["date"][:7]', 'key = o["date"][5:7]')
b4["shop/report.py"] = b4["shop/report.py"].replace(
    'return {"count": len(orders), "revenue": round(sum(o["total"] for o in orders), 2)}',
    'paid = [o for o in orders if o["total"] > 0]\n    return {"count": len(paid), "revenue": round(sum(o["total"] for o in paid), 2)}')
add(Task(
    "bugfix-4", "bugfix", 4,
    "Finance says the monthly report is wrong: January 2025 and January 2026 are added into one 'January' "
    "bucket. Fix the report module. Check the rest of it while you are there.",
    files=b4,
    hidden='''import unittest
from shop.report import monthly, summary
O = [{"id": 1, "date": "2025-01-05", "region": "EU", "total": 10.0},
     {"id": 2, "date": "2026-01-09", "region": "EU", "total": 4.0},
     {"id": 3, "date": "2026-01-10", "region": "EU", "total": 0.0}]
class T(unittest.TestCase):
    def test_years_apart(self): self.assertEqual(monthly(O), {"2025-01": 10.0, "2026-01": 4.0})
    def test_count_includes_free(self): self.assertEqual(summary(O)["count"], 3)
    def test_revenue(self): self.assertEqual(summary(O)["revenue"], 14.0)
''',
    ref={"shop/report.py": project()["shop/report.py"]},
))

b5 = broken("shop/storage.py", "return json.load(fh)",
            "orders = json.load(fh)\n    for o in orders:\n        o[\"total\"] = int(o[\"total\"])\n    return orders")
add(Task(
    "bugfix-5", "bugfix", 5,
    "`python -m shop.cli summary orders.json` prints a revenue that is a few cents lower than the sum of "
    "the totals in the file (for example 10.50 + 4.25 shows 14.00 instead of 14.75). Find the cause and fix it "
    "without changing the file format.",
    files=b5,
    hidden='''import json, os, tempfile, unittest
from contextlib import redirect_stdout
from io import StringIO
from shop import storage
from shop.cli import main
O = [{"id": 1, "date": "2025-01-05", "region": "EU", "total": 10.5},
     {"id": 2, "date": "2025-01-06", "region": "EU", "total": 4.25}]
def path():
    p = os.path.join(tempfile.mkdtemp(), "o.json"); json.dump(O, open(p, "w")); return p
class T(unittest.TestCase):
    def test_load_exact(self): self.assertEqual(storage.load_orders(path()), O)
    def test_cli(self):
        buf = StringIO()
        with redirect_stdout(buf): rc = main(["summary", path()])
        self.assertEqual(rc, 0); self.assertIn("14.75", buf.getvalue())
    def test_roundtrip(self):
        p = os.path.join(tempfile.mkdtemp(), "r.json"); storage.save_orders(p, O)
        self.assertEqual(storage.load_orders(p), O)
''',
    ref={"shop/storage.py": project()["shop/storage.py"]},
))

b6 = broken("shop/inventory.py", "    def __init__(self):\n        self._items = {}",
            "    def __init__(self, _items={}):\n        self._items = _items")
b6["shop/cart.py"] = project()["shop/cart.py"].replace(
    "    def __init__(self, inventory):\n        self.inventory = inventory\n        self.lines = {}",
    "    def __init__(self, inventory, lines={}):\n        self.inventory = inventory\n        self.lines = lines")
add(Task(
    "bugfix-6", "bugfix", 6,
    "Odd behaviour: each test file passes when run alone, but running the whole suite, or creating two "
    "carts or two inventories in one program, makes them see each other's data (a new cart already has "
    "items, a new inventory already has SKUs). Find every cause and fix it.",
    files=b6,
    hidden='''import unittest
from shop.cart import Cart
from shop.inventory import Inventory
class T(unittest.TestCase):
    def test_inventories_independent(self):
        a = Inventory(); a.add("A", "a", 1, 1); b = Inventory()
        self.assertEqual(b.list_items(), [])
        b.add("A", "a", 1, 1)
    def test_carts_independent(self):
        inv = Inventory(); inv.add("A", "a", 1, 9)
        c1, c2 = Cart(inv), Cart(inv); c1.add("A", 2)
        self.assertEqual(c2.lines, {}); self.assertEqual(c2.total(), 0)
    def test_still_works(self):
        inv = Inventory(); inv.add("A", "a", 2.0, 9); c = Cart(inv); c.add("A", 3); self.assertEqual(c.total(), 6.0)
''',
    ref={"shop/inventory.py": project()["shop/inventory.py"], "shop/cart.py": project()["shop/cart.py"]},
))

# ================================================================= PLAN
PLAN_BOILER = " Write the plan to plan.md (a numbered list of steps). Do not change any code."
add(Task(
    "plan-1", "plan", 1,
    "Plan how to add Cart.remove(sku) to shop/cart.py: it removes the line for that sku. Name the exact file, "
    "the method and the test file to extend, and the case where the sku is not in the cart." + PLAN_BOILER,
    deliverable="plan.md",
    rubric=[("cart.py", [r"cart\.py"]), ("remove method", [r"remove"]),
            ("tests", [r"test_cart\.py"]), ("unknown sku", [r"(not in|missing|unknown|absent|KeyError|raise)"]),
            ("numbered", [r"^\s*1[.)]"])],
))
add(Task(
    "plan-2", "plan", 2,
    "Plan a low-stock alert: Inventory should report items whose stock is below a threshold. Say which "
    "file and method change, what the default threshold is, and which tests to add." + PLAN_BOILER,
    deliverable="plan.md",
    rubric=[("inventory.py", [r"inventory\.py"]), ("method", [r"(low_stock|low.stock)"]),
            ("threshold default", [r"(default|threshold).{0,40}\d"]), ("tests", [r"test_inventory\.py"]),
            ("boundary", [r"(strictly|equal|boundary|below|<)"])],
))
add(Task(
    "plan-3", "plan", 3,
    "Plan order history: Cart.checkout() should create an order and save it with the storage module, and "
    "reduce the stock. Cover which modules change, the order data, the order of operations and what happens "
    "if stock is short." + PLAN_BOILER,
    deliverable="plan.md", allowed_files=("orders.json",),
    rubric=[("cart.py", [r"cart\.py"]), ("storage.py", [r"storage\.py"]), ("checkout", [r"checkout"]),
            ("remove_stock", [r"remove_stock|stock"]), ("order fields", [r"(id|date|total|region)"]),
            ("failure/atomic", [r"(insufficient|short|fail|rollback|atomic|before)"]),
            ("tests", [r"test"])],
))
add(Task(
    "plan-4", "plan", 4,
    "Plan multi-currency support for the shop. Think about what the task leaves open and decide it." + PLAN_BOILER,
    deliverable="plan.md", allowed_files=("currency.py",),
    rubric=[("pricing.py", [r"pricing\.py"]), ("utils money", [r"(utils\.py|money)"]),
            ("currency field", [r"currenc(y|ies).{0,60}(field|code|attribute|column|key)"]),
            ("rates source", [r"(exchange|rate).{0,60}(source|table|file|api|config|static|fixed)"]),
            ("rounding", [r"(round|cent|decimal|precision)"]),
            ("report/orders", [r"(report|order|storage)"]),
            ("backward compat", [r"(backward|existing|migrat|default currency|legacy|old orders)"]),
            ("tests", [r"test"])],
))
add(Task(
    "plan-5", "plan", 5,
    "Plan customer accounts with per-customer discounts that apply in the cart, are saved with each order and "
    "show up in the reports. Give an order of work that keeps the suite green at every step." + PLAN_BOILER,
    deliverable="plan.md", allowed_files=("customers.py", "customer.py", "accounts.py"),
    rubric=[("cart.py", [r"cart\.py"]), ("storage.py", [r"storage\.py"]), ("report.py", [r"report\.py"]),
            ("customer model", [r"customer.{0,60}(model|class|record|id|fields?)"]),
            ("discount rule", [r"discount.{0,80}(percent|pct|rate|tier|apply|after|before|stack)"]),
            ("order stores customer", [r"order.{0,80}customer|customer.{0,80}order"]),
            ("old data", [r"(migrat|existing orders|backward|missing customer|default|legacy)"]),
            ("step order", [r"(first|then|finally|step|before|after)"]),
            ("tests", [r"test"])],
))
add(Task(
    "plan-6", "plan", 6,
    "The CLI has one command and will need many. Plan turning shop/cli.py into subcommands (summary, export, "
    "and later others) with a registry so report formats can be added without editing the CLI. Existing "
    "`summary` invocations must keep working. Cover design, sequencing, risks and how you would verify it." + PLAN_BOILER,
    deliverable="plan.md", allowed_files=("registry.py", "commands.py", "formats.py"),
    rubric=[("cli.py", [r"cli\.py"]), ("report.py", [r"report\.py"]),
            ("registry", [r"registry|register"]),
            ("subcommand dispatch", [r"(subcommand|dispatch|argparse|command)"]),
            ("backward compat", [r"(backward|keep working|compat|existing invocation|unchanged)"]),
            ("exit codes", [r"(exit code|return code|status code|returns? [012])"]),
            ("sequencing", [r"(first|then|finally|step|phase|before|after)"]),
            ("risks", [r"(risk|pitfall|danger|regress|break)"]),
            ("verification", [r"(test|verify|characteri[sz]ation|snapshot)"])],
))

# ================================================================= REVIEW
REV_BOILER = " Write your findings to review.md as a list (one bullet per real problem, naming the function). Do not change any code."
TIERS_PY = '''"""Volume discounts: 5% over 100, 10% over 500, 15% over 1000."""


def tier_discount(total):
    if total > 1000:
        rate = 0.15
    elif total > 500:
        rate = 0.01
    elif total > 100:
        rate = 0.05
    else:
        rate = 0
    return round(total * rate, 2)
'''
add(Task(
    "review-1", "review", 1,
    "Review the function tier_discount in shop/tiers.py against its docstring." + REV_BOILER,
    files={"shop/tiers.py": TIERS_PY}, deliverable="review.md",
    rubric=[("500 tier uses 0.01", [r"(0\.01|1 ?%)"])],
    herrings=[r"round\(total \* rate"],
))
STOCK_PY = '''"""Stock movements."""


def restock(items, sku, qty):
    """Add qty units to the stock of sku."""
    items[sku]["stock"] = qty


def low_stock(items, threshold):
    """SKUs whose stock is strictly below threshold."""
    return sorted(s for s, i in items.items() if i["stock"] <= threshold)


def total_units(items):
    return sum(i["stock"] for i in items.values())
'''
add(Task(
    "review-2", "review", 2,
    "Review shop/stock.py against its docstrings." + REV_BOILER,
    files={"shop/stock.py": STOCK_PY}, deliverable="review.md",
    rubric=[("restock overwrites", [r"restock", r"(overwrit|replace|instead of add|\+=|not add|sets)"]),
            ("low_stock boundary", [r"low_stock", r"(<=|strict|boundary|equal)"])],
    herrings=[r"total_units", r"sorted"],
))
ACCT_PY = '''"""Account lookups."""
import sqlite3


def find_user(conn, name):
    cur = conn.execute("SELECT id, name FROM users WHERE name = '" + name + "'")
    return cur.fetchone()


def add_tags(user, tags=[]):
    tags.append(user["name"])
    return tags


def read_config(path):
    f = open(path)
    data = f.read()
    return data.splitlines()


def parse_age(text):
    return int(text.strip())
'''
add(Task(
    "review-3", "review", 3,
    "Review shop/accounts.py. It is used by the web handlers with user-supplied input." + REV_BOILER,
    files={"shop/accounts.py": ACCT_PY}, deliverable="review.md",
    rubric=[("sql injection", [r"find_user", r"(inject|concatenat|parameteri|placeholder|format)"]),
            ("mutable default", [r"add_tags", r"(mutable|default|shared)"]),
            ("unclosed file", [r"read_config", r"(close|context manager|with open|leak)"])],
    herrings=[r"parse_age.{0,80}(inject|sql)"],
))
RANK_PY = '''"""Leaderboard of best-selling SKUs."""


def top_n(sales, n):
    """sales: {sku: units}. Return the n best SKUs, best first."""
    ranked = sorted(sales, key=lambda s: sales[s])
    return ranked[:n]


def share(sales, sku):
    total = sum(sales.values())
    return sales[sku] / total
'''
RANK_CALL = '''"""Weekly job."""
from shop.rank import top_n, share


def weekly(sales):
    best = top_n(sales, 3)
    return [(s, round(share(sales, s) * 100)) for s in best]
'''
add(Task(
    "review-4", "review", 4,
    "Review shop/rank.py and its caller shop/weekly.py. Report only real problems." + REV_BOILER,
    files={"shop/rank.py": RANK_PY, "shop/weekly.py": RANK_CALL}, deliverable="review.md",
    rubric=[("top_n ascending", [r"top_n", r"(ascending|reverse|worst|lowest|wrong order|best first)"]),
            ("share div by zero", [r"share", r"(zero|empty|ZeroDivision|no sales)"]),
            ("weekly empty/missing", [r"weekly", r"(empty|zero|ZeroDivision|no sales|fewer)"])],
    herrings=[r"round\(share", r"list comprehension"],
))
DIFF = '''diff --git a/shop/orders.py b/shop/orders.py
--- a/shop/orders.py
+++ b/shop/orders.py
@@ -1,22 +1,38 @@
+import threading
+import pickle
+
+_lock = threading.Lock()
+_next_id = 0
+
+
+def new_id():
+    global _next_id
+    _next_id += 1
+    return _next_id
+
+
 def checkout(cart, store):
-    order = {"id": 1, "total": cart.total()}
+    order = {"id": new_id(), "total": cart.total()}
+    for sku, qty in cart.lines.items():
+        store.remove_stock(sku, qty)
     store.append(order)
     return order


+def load_blob(raw):
+    return pickle.loads(raw)
+
+
+def find_order(orders, order_id):
+    for i in range(len(orders)):
+        for j in range(len(orders)):
+            if orders[j]["id"] == order_id:
+                return orders[j]
+    return None
+
+
+def label(order):
+    return "order-%d" % order["id"]
'''
add(Task(
    "review-5", "review", 5,
    "Review the change in change.diff (a pull request to shop/orders.py). Look for correctness, concurrency, "
    "security and performance problems; do not nitpick style." + REV_BOILER,
    files={"change.diff": DIFF}, deliverable="review.md",
    rubric=[("id race", [r"(new_id|_next_id)", r"(race|thread|lock|atomic|concurren)"]),
            ("stock removal not atomic", [r"(checkout|remove_stock)", r"(partial|atomic|rollback|half|before|fails? (midway|part))"]),
            ("pickle", [r"(load_blob|pickle)", r"(unsafe|untrusted|arbitrary|execution|insecure|json)"]),
            ("quadratic search", [r"find_order", r"(O\(n|quadratic|nested|inner loop|redundant|dict|index)"])],
    herrings=[r"label.{0,60}(bug|wrong|%d)", r"import threading"],
))
EXPORT_PY = '''"""Nightly export of orders to a partner."""
import csv
import os
import subprocess


def export(orders, path, partner):
    rows = []
    for o in orders:
        rows.append([o["id"], o["date"], o["total"]])
    with open(path, "w") as fh:
        csv.writer(fh).writerows(rows)
    subprocess.call("scp " + path + " " + partner + ":/inbox", shell=True)
    os.remove(path)


def totals_by_region(orders):
    out = {}
    for o in orders:
        out[o["region"]] = out.get(o["region"], 0) + o["total"]
    return out
'''
RETRY_PY = '''"""Retry helper."""
import time


def retry(fn, attempts=3, delay=1):
    for i in range(attempts):
        try:
            return fn()
        except Exception:
            time.sleep(delay)
    return None
'''
CACHE_PY = '''"""Price cache."""
_cache = {}


def cached_price(sku, load):
    if sku not in _cache:
        _cache[sku] = load(sku)
    return _cache[sku]


def clear():
    _cache.clear()
'''
SCHED_PY = '''"""Scheduling."""
from shop.export import export
from shop.retry import retry


def nightly(orders, partner):
    retry(lambda: export(orders, "/tmp/out.csv", partner))
    return len(orders)
'''
add(Task(
    "review-6", "review", 6,
    "Review this branch: shop/export.py, shop/retry.py, shop/cache.py and shop/sched.py (all new). Report "
    "real problems only, most severe first." + REV_BOILER,
    files={"shop/export.py": EXPORT_PY, "shop/retry.py": RETRY_PY, "shop/cache.py": CACHE_PY, "shop/sched.py": SCHED_PY},
    deliverable="review.md",
    rubric=[("shell injection", [r"(export|subprocess|scp)", r"(inject|shell=True|shell injection|unsanitized|quote|argument list)"]),
            ("file removed even when copy fails", [r"(export|os\.remove|scp)", r"(return code|exit status|fails?|error check|check=True|unchecked)"]),
            ("retry swallows errors", [r"retry", r"(swallow|bare|returns? None|silent|re-?raise|last exception|hid)"]),
            ("retry no backoff / exception breadth", [r"retry", r"(backoff|exponential|except Exception|too broad|fixed delay)"]),
            ("cache stale / unbounded / thread", [r"(cache|cached_price)", r"(stale|unbounded|ttl|invalidat|thread|memory|grow)"]),
            ("fixed tmp path", [r"(/tmp/out\.csv|sched|nightly)", r"(collision|race|predictable|tempfile|concurrent|fixed path|overwrite)"])],
    herrings=[r"totals_by_region.{0,80}(bug|wrong|incorrect)", r"csv\.writer"],
))


def by_kind(kind):
    return [t for t in TASKS.values() if t.kind == kind]
