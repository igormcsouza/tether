"""Order reports. An order is {"id", "date": "YYYY-MM-DD", "region", "total"}."""


def summary(orders):
    return {"count": len(orders), "revenue": round(sum(o["total"] for o in orders), 2)}


def monthly(orders):
    """Revenue per month, keyed "YYYY-MM"."""
    out = {}
    for o in orders:
        key = o["date"][:7]
        out[key] = round(out.get(key, 0) + o["total"], 2)
    return out
