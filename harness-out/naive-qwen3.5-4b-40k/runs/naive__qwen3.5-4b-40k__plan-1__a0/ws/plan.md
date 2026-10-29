1. Add a `remove(sku)` method to the `Cart` class in `shop/cart.py`.
2. The method should check if the SKU exists in `self.lines`.
3. If the SKU is found, delete it from `self.lines`.
4. If the SKU is not in the cart (not found in `self.lines`), raise an error or handle appropriately.
5. Extend the test file `tests/test_cart.py` with a new test case for `remove(sku)`.
6. Add a test case where the SKU is not in the cart to verify the error handling.
