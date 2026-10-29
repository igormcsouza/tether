# Low-Stock Alert Plan

## 1. File and Method Change

**File**: `shop/inventory.py`

**Method to add**: `low_stock_alerts(threshold=None)`

This method should return a list of items whose stock is below the specified threshold. If no threshold is provided, it should use a default threshold.

## 2. Default Threshold

**Default threshold**: 5 units

The default threshold of 5 units is chosen because:
- It's low enough to trigger alerts before stock runs out completely
- It's high enough to avoid excessive false positives for items with normal turnover
- It provides a reasonable buffer for restocking

## 3. Tests to Add

Add tests to `tests/test_inventory.py`:

1. **test_low_stock_alerts_default_threshold**:
   - Create an inventory with items at various stock levels
   - Call `low_stock_alerts()` without arguments
   - Verify it returns items with stock < 5

2. **test_low_stock_alerts_custom_threshold**:
   - Create an inventory with items at various stock levels
   - Call `low_stock_alerts(threshold=10)`
   - Verify it returns items with stock < 10

3. **test_low_stock_alerts_no_low_stock**:
   - Create an inventory where all items have stock >= threshold
   - Verify the method returns an empty list

4. **test_low_stock_alerts_empty_inventory**:
   - Create an empty inventory
   - Verify the method returns an empty list

5. **test_low_stock_alerts_exact_threshold**:
   - Create an item with stock exactly equal to threshold
   - Verify it is NOT included in the results (strictly less than)