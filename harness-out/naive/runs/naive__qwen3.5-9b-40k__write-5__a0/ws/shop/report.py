"""Order reports. An order is {"id", "date": "YYYY-MM-DD", "region", "total"}."""
from shop.tax import rate


def summary(orders):
    """Generate a summary of orders including tax.
    
    Args:
        orders: List of order dictionaries with "total" and "region" keys
        
    Returns:
        Dictionary with "count", "revenue", and "tax" keys
    """
    count = len(orders)
    revenue = round(sum(o["total"] for o in orders), 2)
    tax = round(sum(o["total"] * rate(o["region"]) for o in orders), 2)
    return {"count": count, "revenue": revenue, "tax": tax}


def monthly(orders):
    """Revenue per month, keyed "YYYY-MM"."""
    out = {}
    for o in orders:
        key = o["date"][:7]
        out[key] = round(out.get(key, 0) + o["total"], 2)
    return out
