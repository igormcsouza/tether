"""Stock movements."""


def restock(items, sku, qty):
    """Add qty units to the stock of sku."""
    items[sku]["stock"] = qty


def low_stock(items, threshold):
    """SKUs whose stock is strictly below threshold."""
    return sorted(s for s, i in items.items() if i["stock"] <= threshold)


def total_units(items):
    return sum(i["stock"] for i in items.values())
