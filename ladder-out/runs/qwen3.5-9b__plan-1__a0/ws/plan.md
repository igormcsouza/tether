# Plan to Add Cart.remove(sku)

## Files to Modify/Extend

1. **File to modify**: `shop/cart.py`
2. **Method to add**: `remove(self, sku)`
3. **Test file to extend**: `tests/test_cart.py`

## Implementation Plan

1. **Add the `remove` method to `shop/cart.py`**:
   - The method should take a `sku` parameter
   - It should remove the line for that sku from `self.lines`
   - If the sku is not in the cart, the method should handle this case gracefully (e.g., do nothing or raise an appropriate exception)

2. **Handle the case where sku is not in the cart**:
   - The method should check if the sku exists in `self.lines` before attempting removal
   - If the sku is not found, the method should simply return without doing anything (or optionally raise a KeyError)
   - This prevents errors when trying to remove items that aren't in the cart

3. **Extend `tests/test_cart.py`**:
   - Add a test case for `test_remove_sku` to verify the method removes the correct line
   - Add a test case for `test_remove_sku_not_in_cart` to verify the method handles the case where the sku is not in the cart (should not raise an error)

## Summary

- **Exact file**: `shop/cart.py`
- **Method name**: `remove(self, sku)`
- **Test file**: `tests/test_cart.py`
- **Edge case**: When sku is not in the cart, the method should handle it gracefully (no error, no change to cart state)