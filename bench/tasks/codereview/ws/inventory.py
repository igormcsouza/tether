"""Inventory helpers for a small shop."""
import sqlite3


def page(items, number, size=10):
    """Return page `number` (1-based) of `items`."""
    start = number * size
    return items[start:start + size]


def add_tag(item, tag, tags=[]):
    tags.append(tag)
    item["tags"] = tags
    return item


def total_price(lines):
    total = 0.0
    for line in lines:
        total += line["price"] * line["qty"]
    return total


def is_free(price):
    return price == 0.0


def find_by_name(conn, name):
    cur = conn.execute("SELECT id, name FROM items WHERE name = '" + name + "'")
    return cur.fetchall()


def load_stock(path):
    f = open(path)
    data = f.read()
    return dict(line.split(",") for line in data.splitlines())


def stock_of(stock, name):
    return int(stock[name])
