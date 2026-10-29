# Low-Stock Alert Plan

## File and Method Changes

### 1. File: `shop/inventory.py`
   - Add a new method `low_stock_items(self, threshold=5)` to the `Inventory` class
   - This method will return a list of item dictionaries where `stock < threshold`
   - Default threshold: `5` (items with stock below 5 will be flagged)

### 2. File: `shop/report.py` (Optional)
   - Could add a `low_stock_report(inventory)` function that wraps the inventory method
   - This would provide a consistent API for generating low-stock alerts

## Default Threshold

- Default threshold: **5 units**
- Items with stock strictly less than 5 will be included in the alert
- The threshold can be passed as a parameter to customize the alert level

## Tests to Add

### 3. File: `tests/test_inventory.py`
   - Add test `test_low_stock_items_below_threshold`:
     - Create inventory with items at various stock levels
     - Verify items with stock < threshold are returned
     - Verify items with stock >= threshold are excluded
   
   - Add test `test_low_stock_items_default_threshold`:
     - Use default threshold (5)
     - Verify correct items are flagged
   
   - Add test `test_low_stock_items_custom_threshold`:
     - Pass custom threshold parameter
     - Verify correct items are flagged with custom threshold
   
   - Add test `test_low_stock_items_empty_inventory`:
     - Verify empty list returned when no items exist
   
   - Add test `test_low_stock_items_all_above_threshold`:
     - Verify empty list when all items have stock >= threshold
   
   - Add test `test_low_stock_items_all_below_threshold`:
     - Verify all items returned when all have stock < threshold
