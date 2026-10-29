# Low-Stock Alert Plan

## File and Method Changes

### 1. File: `shop/inventory.py`
   - **Method to add**: `low_stock_alerts(threshold=0)`
   - **Purpose**: Returns a list of items whose stock is below the specified threshold
   - **Default threshold**: 0 (items with stock <= 0)
   - **Implementation**: 
     - Iterate through all items in `self._items`
     - Filter items where `item["stock"] <= threshold`
     - Return sorted list of matching items

### 2. File: `tests/test_inventory.py`
   - **Test to add**: `test_low_stock_alerts`
   - **Purpose**: Verify the low_stock_alerts method works correctly
   - **Test cases to include**:
     - Test with default threshold (0): should return items with stock <= 0
     - Test with custom threshold (e.g., 5): should return items with stock <= 5
     - Test with no low stock items: should return empty list
     - Test with all items below threshold: should return all items

## Summary

- **File to modify**: `shop/inventory.py` - add `low_stock_alerts(threshold=0)` method
- **Default threshold**: 0 (alerts for items with 0 or less stock)
- **Test file to modify**: `tests/test_inventory.py` - add `test_low_stock_alerts` method
- **No other files need to be changed**