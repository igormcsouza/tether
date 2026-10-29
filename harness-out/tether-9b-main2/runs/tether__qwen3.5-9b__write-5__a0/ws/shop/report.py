"""Order reports. An order is {"id", "date": "YYYY-MM-DD", "region", "total"}."""
from shop.tax import rate


def summary(orders):
    """Return summary of orders with total revenue and total tax.
    
    Args:
        orders: List of order dictionaries, each with "total" and "region" keys.
    
    Returns:
        Dictionary with "count", "revenue", and "tax" keys.
        - count: Number of orders
        - revenue: Sum of all order totals (pre-tax)
        - tax: Sum of tax over all orders, each taxed at its own region's rate
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