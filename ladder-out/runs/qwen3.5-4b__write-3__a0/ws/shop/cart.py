"""Shopping cart."""
from shop.pricing import bulk_price


class Cart:
    def __init__(self, inventory):
        self.inventory = inventory
        self.lines = {}
        self._coupon_code = None

    def add(self, sku, qty=1):
        self.inventory.get(sku)
        self.lines[sku] = self.lines.get(sku, 0) + qty

    def apply_coupon(self, code):
        if code == "SAVE10":
            self._coupon_code = "SAVE10"
        elif code == "FIVEOFF":
            self._coupon_code = "FIVEOFF"
        else:
            raise ValueError("Unknown coupon code")

    def total(self):
        base_total = round(
            sum(bulk_price(self.inventory.get(s)["price"], q) for s, q in self.lines.items()), 2
        )
        
        if self._coupon_code == "SAVE10":
            discount = base_total * 0.10
        elif self._coupon_code == "FIVEOFF":
            discount = min(5.0, base_total)
        else:
            discount = 0
        
        return round(max(0, base_total - discount), 2)