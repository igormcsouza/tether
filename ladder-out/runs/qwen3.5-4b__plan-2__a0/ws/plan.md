# Low-Stock Alert Implementation Plan

## 1. File and Method Change
- **File**: `shop/inventory.py`
- **Method**: Add a new method `get_low_stock_items(threshold)` to the `Inventory` class that returns items whose stock is below the specified threshold.

## 2. Default Threshold
- The default threshold should be set to **0** (items with stock less than 0, which would indicate negative stock).
- Alternatively, a more practical default could be **1** (items with zero or negative stock).

## 3. Tests to Add
- `test_get_low_stock_items`: Verify that items below the threshold are returned correctly.
- `test_get_low_stock_items_default_threshold`: Verify behavior when no threshold is provided (using default of 0).
- `test_get_low_stock_items_empty`: Verify empty list when all items are above threshold.