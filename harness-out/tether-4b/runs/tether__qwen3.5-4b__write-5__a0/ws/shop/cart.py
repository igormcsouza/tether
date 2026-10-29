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
        """Return the cart total including sales tax for the given region."""
        pre_tax = self.total()
        tax_rate = rate(region)
        tax = round(pre_tax * tax_rate, 2)
        return round(pre_tax + tax, 2)