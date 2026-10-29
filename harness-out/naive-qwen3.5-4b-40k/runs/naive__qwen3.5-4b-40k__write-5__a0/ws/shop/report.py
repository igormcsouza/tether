"""Order reports. An order is {"id", "date": "YYYY-MM-DD", "region", "total"}."""
from shop.tax import rate


def summary(orders):
    """Return count, revenue, and total tax over all orders."""
    total_revenue = sum(o["total"] for o in orders)
    total_tax = 0.0
    for o in orders:
        tax_rate = rate(o["region"])
        order_tax = round(o["total"] * tax_rate, 2)
        total_tax += order_tax
    return {
        "count": len(orders),
        "revenue": round(total_revenue, 2),
        "tax": round(total_tax, 2)
    }


def monthly(orders):
    """Revenue per month, keyed "YYYY-MM"."""
    out = {}
    for o in orders:
        key = o["date"][:7]
        out[key] = round(out.get(key, 0) + o["total"], 2)
    return out
