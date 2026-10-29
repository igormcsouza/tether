# Plan to add `Cart.remove(sku)` method

## 1. File and Method to Extend
- **File**: `./shop/cart.py`
- **Method**: Add a new method named `remove(self, sku)` that removes the line for the given SKU from the cart's lines dictionary.

## 2. Test File to Extend
- **File**: `./tests/test_cart.py`
- **Test Class**: `CartTest`
- **New Test Case**: Add a test case (e.g., `test_remove_skus`) that:
  - Creates a Cart with an Inventory containing items A1 and B2
  - Adds both SKUs to the cart
  - Verifies the initial total
  - Calls `cart.remove("A1")`
  - Verifies that "A1" is no longer in `cart.lines`
  - Verifies that the total reflects the removal

## 3. Case Where SKU is Not in Cart
- The `remove(sku)` method should handle the case where the SKU does not exist in the cart gracefully.
- **Behavior**: If the SKU is not found in `self.lines`, the method should simply do nothing (no error raised, no side effects).
- **Implementation approach**: Use a conditional check like `if sku in self.lines: del self.lines[sku]` to avoid KeyError exceptions.