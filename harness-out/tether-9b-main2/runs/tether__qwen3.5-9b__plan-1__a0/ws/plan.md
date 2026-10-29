1. File to modify: `shop/cart.py`
   - Add a `remove(self, sku)` method to the `Cart` class
   - The method should remove the line (entry) for the given sku from `self.lines`
   - If the sku is not in the cart, the method should do nothing (no error)

2. Method signature:
   ```python
   def remove(self, sku):
       if sku in self.lines:
           del self.lines[sku]
   ```

3. Test file to extend: `tests/test_cart.py`
   - Add a test case for `test_remove_sku` to verify that removing an existing sku works
   - Add a test case for `test_remove_sku_not_in_cart` to verify that removing a sku not in the cart does nothing (no error)

4. Case where sku is not in the cart:
   - When `remove(sku)` is called with a sku that doesn't exist in `self.lines`, the method should simply do nothing (no exception, no change to cart state)
   - This is handled by checking `if sku in self.lines` before attempting deletion