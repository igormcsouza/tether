class Cart:
    """A shopping cart with coupon code support."""
    
    def __init__(self):
        self.items = []  # List of (name, price) tuples
        self.coupon = None  # Applied coupon code
    
    def add_item(self, name, price):
        """Add an item to the cart."""
        self.items.append((name, price))
    
    def apply_coupon(self, code):
        """Apply a coupon code to the cart.
        
        Args:
            code: Coupon code string
            
        Raises:
            ValueError: If the coupon code is unknown
        """
        if code == "SAVE10":
            self.coupon = "SAVE10"
        elif code == "FIVEOFF":
            self.coupon = "FIVEOFF"
        else:
            raise ValueError(f"Unknown coupon code: {code}")
    
    def total(self):
        """Calculate the cart total including any applied coupon.
        
        Returns:
            float: The total price after coupon discount (never below 0)
        """
        subtotal = sum(price for name, price in self.items)
        
        if self.coupon == "SAVE10":
            discount = subtotal * 0.10
        elif self.coupon == "FIVEOFF":
            discount = 5.0
        else:
            discount = 0.0
        
        return max(0, subtotal - discount)
    
    def remove_item(self, name):
        """Remove an item from the cart by name."""
        self.items = [(n, p) for n, p in self.items if n != name]
    
    def clear(self):
        """Clear all items from the cart."""
        self.items = []
        self.coupon = None
    
    def __len__(self):
        """Return the number of items in the cart."""
        return len(self.items)
    
    def __str__(self):
        """String representation of the cart."""
        items_str = ", ".join(f"{name}: ${price:.2f}" for name, price in self.items)
        return f"Cart({items_str})"
