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
        """Return the total including sales tax for the given region.
        
        Args:
            region: The region code to apply tax rate for
            
        Returns:
            The total amount including tax, rounded to cents
        """
        pre_tax_total = self.total()
        tax_rate = rate(region)
        tax_amount = pre_tax_total * tax_rate
        return round(pre_tax_total + tax_amount, 2)