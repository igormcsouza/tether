# Low-Stock Alert Implementation Plan

## Overview
This plan outlines how to add a low-stock alert feature to the Inventory class that reports items whose stock is below a configurable threshold.

## File and Method Changes

### 1. `./shop/inventory.py` - Add `get_low_stock_items()` method
   - **Purpose**: Returns a list of items with stock below the threshold
   - **Implementation**: 
     ```python
     def get_low_stock_items(self, threshold=0):
         return [item for item in self._items.values() if item["stock"] < threshold]
     ```

### 2. Default Threshold
   - **Value**: `0` (items with stock below zero are considered low-stock)
   - **Rationale**: This is the default because negative stock indicates overselling, which is always a critical condition requiring alerts. The threshold can be customized when calling the method.

## Tests to Add

### 3. Test File: `./tests/test_inventory.py`

Add these test methods:

```python
def test_get_low_stock_items_default_threshold(self):
    inv = Inventory()
    inv.add("A", "a", 1, stock=5)
    inv.add("B", "b", 2, stock=0)
    inv.add("C", "c", 3, stock=-1)
    result = inv.get_low_stock_items()
    self.assertEqual([i["sku"] for i in result], ["B", "C"])

def test_get_low_stock_items_custom_threshold(self):
    inv = Inventory()
    inv.add("A", "a", 1, stock=3)
    inv.add("B", "b", 2, stock=5)
    inv.add("C", "c", 3, stock=4)
    result = inv.get_low_stock_items(threshold=4)
    self.assertEqual([i["sku"] for i in result], ["A"])

def test_get_low_stock_items_empty(self):
    inv = Inventory()
    inv.add("A", "a", 1, stock=5)
    result = inv.get_low_stock_items(threshold=10)
    self.assertEqual([], result)
```

## Summary of Changes

| Component | Change |
|-----------|--------|
| File | `./shop/inventory.py` |
| Method | Add `get_low_stock_items(self, threshold=0)` |
| Default Threshold | `0` (stock < 0 triggers alert) |
| Test File | `./tests/test_inventory.py` |
| Tests to Add | 3 new test methods for default threshold, custom threshold, and empty results |
