"""Shopping cart."""
from shop.pricing import bulk_price


class Cart:
    def __init__(self, inventory=None, lines=None):
        self.inventory = inventory
        self.lines = {} if lines is None else lines

    def add(self, sku, qty=1):
        self.inventory.get(sku)
        self.lines[sku] = self.lines.get(sku, 0) + qty

    def total(self):
        return round(
            sum(bulk_price(self.inventory.get(s)["price"], q) for s, q in self.lines.items()), 2
        )