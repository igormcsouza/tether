# Low-Stock Alert Plan

## File and Method Changes

### 1. File: `shop/inventory.py`
   - **Method to add**: `low_stock(threshold: int = 5) -> list[dict]`
   - **Purpose**: Returns a list of items whose stock is below the given threshold
   - **Default threshold**: 5 units
   - **Return format**: List of item dictionaries (same format as `list_items()`)
   - **Behavior**: 
     - If threshold is not provided, uses default of 5
     - Returns items where `item["stock"] < threshold`
     - Returns empty list if no items are below threshold

### 2. File: `tests/test_inventory.py`
   - **Tests to add**:
     1. `test_low_stock_default_threshold`: Verify default threshold of 5 works
     2. `test_low_stock_custom_threshold`: Verify custom threshold parameter works
     3. `test_low_stock_no_items_below`: Verify empty list returned when no items below threshold
     4. `test_low_stock_exact_threshold`: Verify items at exact threshold are NOT included (strict less than)
     5. `test_low_stock_empty_inventory`: Verify empty list returned for empty inventory

## Implementation Details

The `low_stock` method will:
- Accept an optional `threshold` parameter (default: 5)
- Iterate through all items in `self._items`
- Filter items where `item["stock"] < threshold`
- Return the filtered list of item dictionaries

## Example Usage

```python
inv = Inventory()
inv.add("A", "Apple", 1.5, 3)
inv.add("B", "Banana", 0.75, 10)
inv.add("C", "Cherry", 2.0, 4)

# Using default threshold (5)
low = inv.low_stock()  # Returns items with stock < 5

# Using custom threshold
low = inv.low_stock(threshold=3)  # Returns items with stock < 3
```

## Tests to Add

1. **test_low_stock_default_threshold**: 
   - Add items with various stock levels
   - Verify only items below 5 are returned

2. **test_low_stock_custom_threshold**: 
   - Add items with various stock levels
   - Verify items below custom threshold are returned

3. **test_low_stock_no_items_below**: 
   - Add items all above threshold
   - Verify empty list is returned

4. **test_low_stock_exact_threshold**: 
   - Add item with stock exactly at threshold
   - Verify item is NOT included (strict less than comparison)

5. **test_low_stock_empty_inventory**: 
   - Create empty inventory
   - Verify empty list is returned