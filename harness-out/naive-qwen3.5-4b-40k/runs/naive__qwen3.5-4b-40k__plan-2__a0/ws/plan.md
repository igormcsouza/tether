1. Add a new method `list_low_stock(threshold)` to the `Inventory` class in `shop/inventory.py`. This method should accept an optional threshold parameter and return a list of items whose stock is below that threshold.

2. Set the default threshold value to 0 (items with stock less than 0 would be reported). Alternatively, you could use a positive integer like 5 for more practical low-stock alerts.

3. Add tests in `tests/test_inventory.py` to verify:
   - The method returns an empty list when all items are above the threshold
   - The method correctly identifies items below the threshold
   - The default threshold works as expected
   - Edge cases (e.g., items exactly at the threshold)
