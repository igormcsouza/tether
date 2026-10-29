1. File to modify: shop/cart.py
2. Method to add: remove(sku)
3. Test file to extend: tests/test_cart.py
4. Case where sku is not in cart: The method should handle this gracefully (e.g., do nothing or raise a KeyError) without throwing an exception, since the sku does not exist in self.lines.