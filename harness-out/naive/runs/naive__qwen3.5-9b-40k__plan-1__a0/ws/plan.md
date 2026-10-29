1. File to modify: `shop/cart.py`
2. Method to add: `remove(self, sku)`
3. Test file to extend: `tests/test_cart.py`
4. Case where sku is not in the cart: The method should handle this gracefully (e.g., do nothing or raise a KeyError) - since the existing `add` method doesn't check for existence, `remove` should also not raise an error when the sku is not in the cart, simply doing nothing.
