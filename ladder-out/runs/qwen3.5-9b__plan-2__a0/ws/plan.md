# Low-Stock Alert Plan

## 1. File and Method Change
- **File**: `shop/inventory.py`
- **Method**: Add a new method `low_stock_items(self, threshold=0)` to the `Inventory` class
- **Purpose**: Return a list of items whose stock is below the specified threshold

## 2. Default Threshold
- **Default value**: `0` (items with stock of 0 or less will be reported)
- **Note**: The threshold is a parameter that can be customized when calling the method

## 3. Implementation Details
- The method should iterate through all items in `self._items`
- Filter items where `item["stock"] < threshold`
- Return a list of item dictionaries (or item objects) matching the criteria
- Should maintain consistency with existing code style (return sorted items by SKU)

## 4. Tests to Add (in `tests/test_inventory.py`)
Add the following test cases to the `InventoryTest` class:

### Test 1: Basic low stock detection
```python
def test_low_stock_items_default_threshold(self):
    inv = Inventory()
    inv.add("A", "a", 10, 5)
    inv.add("B", "b", 20, 0)
    inv.add("C", "c", 15, 10)
    low = inv.low_stock_items()
    self.assertEqual(len(low), 1)
    self.assertEqual(low[0]["sku"], "B")
```

### Test 2: Low stock with custom threshold
```python
def test_low_stock_items_custom_threshold(self):
    inv = Inventory()
    inv.add("A", "a", 10, 5)
    inv.add("B", "b", 20, 3)
    inv.add("C", "c", 15, 10)
    low = inv.low_stock_items(threshold=5)
    self.assertEqual(len(low), 1)
    self.assertEqual(low[0]["sku"], "B")
```

### Test 3: No items below threshold
```python
def test_low_stock_items_no_matches(self):
    inv = Inventory()
    inv.add("A", "a", 10, 5)
    inv.add("B", "b", 20, 10)
    low = inv.low_stock_items(threshold=5)
    self.assertEqual(low, [])
```

### Test 4: All items below threshold
```python
def test_low_stock_items_all_match(self):
    inv = Inventory()
    inv.add("A", "a", 10, 2)
    inv.add("B", "b", 20, 1)
    low = inv.low_stock_items(threshold=5)
    self.assertEqual(len(low), 2)
    skus = [i["sku"] for i in low]
    self.assertEqual(sorted(skus), ["A", "B"])
```

### Test 5: Empty inventory
```python
def test_low_stock_items_empty_inventory(self):
    inv = Inventory()
    low = inv.low_stock_items()
    self.assertEqual(low, [])
```

### Test 6: Threshold of zero (default behavior)
```python
def test_low_stock_items_threshold_zero(self):
    inv = Inventory()
    inv.add("A", "a", 10, 0)
    inv.add("B", "b", 20, 5)
    low = inv.low_stock_items(threshold=0)
    self.assertEqual(len(low), 1)
    self.assertEqual(low[0]["sku"], "A")
```