1. File to modify: shop/cart.py
2. Method to add: remove(sku)
3. Test file to extend: tests/test_cart.py
4. Case where sku is not in the cart: The method should handle this gracefully (e.g., do nothing or raise an error) without throwing an exception, since the sku doesn't exist in self.lines.