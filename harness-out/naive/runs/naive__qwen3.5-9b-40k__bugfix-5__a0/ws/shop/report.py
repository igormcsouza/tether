"""Order reports. An order is {"id", "date": "YYYY-MM-DD", "region", "total"}."""
from decimal import Decimal, ROUND_HALF_UP


def summary(orders):
    total = sum(Decimal(str(o["total"])) for o in orders)
    return {"count": len(orders), "revenue": float(total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))}


def monthly(orders):
    """Revenue per month, keyed "YYYY-MM"."""
    out = {}
    for o in orders:
        key = o["date"][:7]
        total = Decimal(str(o["total"]))
        current = out.get(key)
        if current is None:
            current = Decimal("0")
        else:
            current = Decimal(str(current))
        out[key] = float((current + total).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    return out
