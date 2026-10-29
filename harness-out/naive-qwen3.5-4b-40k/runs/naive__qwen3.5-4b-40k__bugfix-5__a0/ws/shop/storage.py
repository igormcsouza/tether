"""Order files (JSON)."""
import json


def save_orders(path, orders):
    with open(path, "w") as fh:
        json.dump(orders, fh)


def load_orders(path):
    with open(path) as fh:
        orders = json.load(fh)
    # for o in orders:
    #     o["total"] = int(o["total"])
    return orders
