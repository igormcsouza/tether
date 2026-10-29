"""Scheduling."""
from shop.export import export
from shop.retry import retry


def nightly(orders, partner):
    retry(lambda: export(orders, "/tmp/out.csv", partner))
    return len(orders)
