"""Order reports. An order is {"id", "date": "YYYY-MM-DD", "region", "total"}.


def summary(orders):
    """Return summary of orders including total tax.
    
    Args:
        orders: List of order dictionaries with 'total' and 'region' keys
        
    Returns:
        Dictionary with 'count', 'revenue', and 'tax' keys
    """
    from shop.tax import rate
    
    count = len(orders)
    revenue = round(sum(o["total"] for o in orders), 2)
    
    # Calculate tax for each order based on its region
    total_tax = 0.0
    for order in orders:
        tax_rate = rate(order["region"])
        tax = order["total"] * tax_rate
        total_tax += tax
    
    tax = round(total_tax, 2)
    
    return {"count": count, "revenue": revenue, "tax": tax}


def monthly(orders):
    """Revenue per month, keyed "YYYY-MM"."""
    out = {}
    for o in orders:
        key = o["date"][:7]
        out[key] = round(out.get(key, 0) + o["total"], 2)
    return out