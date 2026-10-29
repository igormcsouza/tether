"""Order reports. An order is {"id", "date": "YYYY-MM-DD", "region", "total"}."""
from shop.tax import rate


def summary(orders):
    """Return count, revenue, and total tax."""
    count = len(orders)
    revenue = round(sum(o["total"] for o in orders), 2)
    tax = 0.0
    for o in orders:
        tax_rate = rate(o["region"])
        tax += o["total"] * tax_rate
    tax = round(tax, 2)
    return {"count": count, "revenue": revenue, "tax": tax}


def monthly(orders):
    """Revenue per month, keyed "YYYY-MM"."""
    out = {}
    for o in orders:
        key = o["date"][:7]
        out[key] = round(out.get(key, 0) + o["total"], 2)
    return out