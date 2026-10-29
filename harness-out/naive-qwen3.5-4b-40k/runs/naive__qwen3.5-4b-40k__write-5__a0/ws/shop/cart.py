"""Shopping cart."""
from shop.pricing import bulk_price
from shop.tax import rate


class Cart:
    def __init__(self, inventory):
        self.inventory = inventory
        self.lines = {}

    def add(self, sku, qty=1):
        self.inventory.get(sku)
        self.lines[sku] = self.lines.get(sku, 0) + qty

    def total(self):
        return round(
            sum(bulk_price(self.inventory.get(s)["price"], q) for s, q in self.lines.items()), 2
        )

    def total_with_tax(self, region):
        """Return the total with tax applied at the given region's rate."""
        tax_rate = rate(region)
        return round(
            sum(bulk_price(self.inventory.get(s)["price"], q) for s, q in self.lines.items()) * (1 + tax_rate), 2
        )
