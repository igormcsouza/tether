"""Order reports. An order is {"id", "date": "YYYY-MM-DD", "region", "total"}."""


def summary(orders):
    tax = 0.0
    for o in orders:
        region_tax = rate(o["region"])
        tax += round(o["total"] * region_tax, 2)
    return {"count": len(orders), "revenue": round(sum(o["total"] for o in orders), 2), "tax": round(tax, 2)}


def monthly(orders):
    """Revenue per month, keyed "YYYY-MM"."""
    out = {}
    for o in orders:
        key = o["date"][:7]
        out[key] = round(out.get(key, 0) + o["total"], 2)
    return out