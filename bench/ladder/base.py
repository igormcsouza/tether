"""The small `shop` project every ladder task starts from (all tests pass on this base)."""

SRC = {
    "shop/__init__.py": "",
    "shop/utils.py": '''"""Small helpers."""


def clamp(value, low, high):
    return max(low, min(high, value))


def money(amount):
    return f"${amount:,.2f}"
''',
    "shop/pricing.py": '''"""Price calculations."""

BULK_THRESHOLD = 10


def line_total(unit_price, quantity):
    return round(unit_price * quantity, 2)


def bulk_price(unit_price, quantity):
    """10% off every unit once the quantity reaches the bulk threshold."""
    if quantity >= BULK_THRESHOLD:
        return round(unit_price * quantity * 0.9, 2)
    return line_total(unit_price, quantity)
''',
    "shop/inventory.py": '''"""Stock keeping."""


class Inventory:
    def __init__(self):
        self._items = {}

    def add(self, sku, name, price, stock=0):
        if sku in self._items:
            raise KeyError(f"duplicate sku {sku}")
        self._items[sku] = {"sku": sku, "name": name, "price": price, "stock": stock}

    def get(self, sku):
        return self._items[sku]

    def remove_stock(self, sku, qty):
        item = self._items[sku]
        if qty > item["stock"]:
            raise ValueError("insufficient stock")
        item["stock"] -= qty

    def list_items(self):
        return sorted(self._items.values(), key=lambda i: i["sku"])
''',
    "shop/cart.py": '''"""Shopping cart."""
from shop.pricing import bulk_price


class Cart:
    def __init__(self, inventory):
        self.inventory = inventory
        self.lines = {}

    def add(self, sku, qty=1):
        self.inventory.get(sku)
        self.lines[sku] = self.lines.get(sku, 0) + qty

    def total(self):
        return round(
            sum(bulk_price(self.inventory.get(s)["price"], q) for s, q in self.lines.items()), 2
        )
''',
    "shop/storage.py": '''"""Order files (JSON)."""
import json


def save_orders(path, orders):
    with open(path, "w") as fh:
        json.dump(orders, fh)


def load_orders(path):
    with open(path) as fh:
        return json.load(fh)
''',
    "shop/report.py": '''"""Order reports. An order is {"id", "date": "YYYY-MM-DD", "region", "total"}."""


def summary(orders):
    return {"count": len(orders), "revenue": round(sum(o["total"] for o in orders), 2)}


def monthly(orders):
    """Revenue per month, keyed "YYYY-MM"."""
    out = {}
    for o in orders:
        key = o["date"][:7]
        out[key] = round(out.get(key, 0) + o["total"], 2)
    return out
''',
    "shop/cli.py": '''"""Command line: `python -m shop.cli summary orders.json`."""
import sys

from shop import report, storage


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
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
''',
}

TESTS = {
    "tests/__init__.py": "",
    "tests/test_pricing.py": '''import unittest

from shop.pricing import bulk_price, line_total


class PricingTest(unittest.TestCase):
    def test_line_total(self):
        self.assertEqual(line_total(2.5, 4), 10.0)

    def test_bulk_starts_at_ten(self):
        self.assertEqual(bulk_price(10, 10), 90.0)
        self.assertEqual(bulk_price(10, 9), 90.0)
        self.assertEqual(bulk_price(10, 2), 20.0)
''',
    "tests/test_cart.py": '''import unittest

from shop.cart import Cart
from shop.inventory import Inventory


class CartTest(unittest.TestCase):
    def setUp(self):
        self.inv = Inventory()
        self.inv.add("A1", "pen", 2.0, 100)
        self.inv.add("B2", "book", 12.5, 5)

    def test_total(self):
        cart = Cart(self.inv)
        cart.add("A1", 3)
        cart.add("B2")
        self.assertEqual(cart.total(), 18.5)

    def test_same_sku_adds_up(self):
        cart = Cart(self.inv)
        cart.add("A1", 2)
        cart.add("A1", 3)
        self.assertEqual(cart.lines["A1"], 5)
''',
    "tests/test_inventory.py": '''import unittest

from shop.inventory import Inventory


class InventoryTest(unittest.TestCase):
    def test_list_sorted(self):
        inv = Inventory()
        inv.add("B", "b", 1)
        inv.add("A", "a", 1)
        self.assertEqual([i["sku"] for i in inv.list_items()], ["A", "B"])

    def test_remove_stock(self):
        inv = Inventory()
        inv.add("A", "a", 1, 3)
        inv.remove_stock("A", 3)
        self.assertEqual(inv.get("A")["stock"], 0)
        with self.assertRaises(ValueError):
            inv.remove_stock("A", 1)
''',
    "tests/test_report.py": '''import unittest

from shop.report import monthly, summary

ORDERS = [
    {"id": 1, "date": "2025-01-05", "region": "US-CA", "total": 10.5},
    {"id": 2, "date": "2025-01-20", "region": "EU", "total": 4.25},
    {"id": 3, "date": "2025-02-02", "region": "US-NY", "total": 7.0},
]


class ReportTest(unittest.TestCase):
    def test_summary(self):
        self.assertEqual(summary(ORDERS), {"count": 3, "revenue": 21.75})

    def test_monthly(self):
        self.assertEqual(monthly(ORDERS), {"2025-01": 14.75, "2025-02": 7.0})
''',
}


def project():
    """Source plus the visible tests, as {path: text}."""
    return {**SRC, **TESTS}
