"""Shopping cart."""
from shop.pricing import bulk_price


class Cart:
    def __init__(self, inventory):
        self.inventory = inventory
        self.lines = {}
        self.coupon = None

    def add(self, sku, qty=1):
        self.inventory.get(sku)
        self.lines[sku] = self.lines.get(sku, 0) + qty

    def apply_coupon(self, code):
        """Apply a coupon code to the cart."""
        if code == "SAVE10":
            self.coupon = "SAVE10"
        elif code == "FIVEOFF":
            self.coupon = "FIVEOFF"
        else:
            raise ValueError(f"Unknown coupon code: {code}")

    def total(self):
        # Calculate subtotal
        subtotal = round(
            sum(bulk_price(self.inventory.get(s)["price"], q) for s, q in self.lines.items()), 2
        )
        
        # Apply coupon discount
        if self.coupon == "SAVE10":
            discount = subtotal * 0.10
        elif self.coupon == "FIVEOFF":
            discount = 5.00
        else:
            discount = 0
        
        # Total never goes below 0
        total = max(0, subtotal - discount)
        return round(total, 2)