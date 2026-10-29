"""Shopping cart."""
from shop.pricing import bulk_price


class Cart:
    def __init__(self, inventory):
        self.inventory = inventory
        self.lines = {}

    def add(self, sku, qty=1):
        self.inventory.get(sku)
        self.lines[sku] = qty

    def total(self):
        return round(
            sum(bulk_price(self.inventory.get(s)["price"], q) for s, q in self.lines.items()), 2
        )
