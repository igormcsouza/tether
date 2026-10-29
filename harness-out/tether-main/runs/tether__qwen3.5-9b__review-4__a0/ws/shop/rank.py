"""Leaderboard of best-selling SKUs."""


def top_n(sales, n):
    """sales: {sku: units}. Return the n best SKUs, best first."""
    ranked = sorted(sales, key=lambda s: sales[s])
    return ranked[:n]


def share(sales, sku):
    total = sum(sales.values())
    return sales[sku] / total
