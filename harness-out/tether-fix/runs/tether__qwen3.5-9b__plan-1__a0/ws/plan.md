# Plan to Add Cart.remove(sku)

1. **File to modify**: `shop/cart.py`
   - Add a new method `remove(self, sku)` to the `Cart` class
   - The method should remove the line for the given sku from `self.lines`
   - If the sku is not in `self.lines`, the method should do nothing (no error)

2. **Method signature**: `remove(self, sku)`
   - Takes a single parameter `sku` (string)
   - Removes the entry from `self.lines` if it exists
   - Should not raise an exception when sku is not in the cart

3. **Test file to extend**: `tests/test_cart.py`
   - Add a new test method to `CartTest` class
   - Test case: verify that calling `remove(sku)` when sku is not in the cart does not raise an exception and leaves the cart unchanged

4. **Case where sku is not in the cart**:
   - When `remove(sku)` is called with a sku that doesn't exist in `self.lines`, the method should silently do nothing (no error, no change to cart state)
   - This is consistent with the principle of ignoring non-existent items rather than raising exceptions