"""Order reports. An order is {"id", "date": "YYYY-MM-DD", "region", "total"}."""


def summary(orders):
    paid = [o for o in orders if o["total"] > 0]
    return {"count": len(paid), "revenue": round(sum(o["total"] for o in paid), 2)}


def monthly(orders):
    """Revenue per month, keyed "YYYY-MM"."""
    out = {}
    for o in orders:
        key = o["date"][:7]
        out[key] = round(out.get(key, 0) + o["total"], 2)
    return out