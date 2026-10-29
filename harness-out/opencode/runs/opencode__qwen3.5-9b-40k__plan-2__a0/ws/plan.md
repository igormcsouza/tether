# Low-Stock Alert Feature Plan

## Overview
Add a method to report inventory items whose stock falls below a configurable threshold.

## Default Threshold
**Default threshold: 5 units** - This is a reasonable default for retail stock management, balancing between avoiding stockouts and not generating excessive alerts.

## File and Method Changes

### 1. `shop/inventory.py`
**Change**: Add new method `low_stock_alerts(threshold: int | None = None) -> list[dict]`

**Location**: After `list_items()` method

**Implementation details**:
- If `threshold` is `None`, use class/singleton default of `5`
- If `threshold` is provided, use that value
- Return a sorted list of item dictionaries containing `sku`, `name`, `price`, `stock`, and `shortage` (difference between threshold and current stock)
- Only include items where `stock < threshold`
- Sort by SKU for consistency

**Example signature**:
```python
def low_stock_alerts(self, threshold: int | None = None) -> list[dict]:
    """Return items with stock below threshold.
    
    Args:
        threshold: Stock threshold (default: 5). Use None for default.
    
    Returns:
        List of dicts with sku, name, price, stock, and shortage field.
        Sorted by SKU. Empty list if no items below threshold.
    """
    thresh = threshold if threshold is not None else 5
    alerts = []
    for item in self._items.values():
        if item["stock"] < thresh:
            alerts.append({
                "sku": item["sku"],
                "name": item["name"],
                "price": item["price"],
                "stock": item["stock"],
                "shortage": thresh - item["stock"],
            })
    return sorted(alerts, key=lambda i: i["sku"])
```

### 2. `tests/test_inventory.py`
**Add tests** for the new `low_stock_alerts` method

**Test scenarios to cover**:
1. **No alerts** - All items above threshold → empty list returned
2. **Some alerts** - Mix of items above and below threshold → only below items returned, sorted by SKU
3. **All alerts** - All items below threshold → all items returned
4. **Threshold boundary** - Item exactly at threshold (not below) → not included
5. **Default threshold** - Call with `None` → uses default of 5
6. **Zero stock** - Items with zero stock are included with correct shortage calculated

**Example test structure**:
```python
class LowStockAlertTest(unittest.TestCase):
    def test_no_alerts_above_threshold(self):
        inv = Inventory()
        inv.add("A", "a", 10, stock=10)
        inv.add("B", "b", 20, stock=8)
        self.assertEqual(inv.low_stock_alerts(), [])  # default=5, both > 5
    
    def test_some_alerts_below_threshold(self):
        inv = Inventory()
        inv.add("A", "a", 10, stock=3)
        inv.add("B", "b", 20, stock=8)
        inv.add("C", "c", 15, stock=1)
        alerts = inv.low_stock_alerts()
        self.assertEqual(len(alerts), 2)
        self.assertEqual(alerts[0]["sku"], "A")  # shortage=2
        self.assertEqual(alerts[1]["sku"], "C")  # shortage=4
        self.assertEqual(alerts[1]["shortage"], 4)
    
    def test_at_threshold_not_below(self):
        inv = Inventory()
        inv.add("A", "a", 10, stock=5)  # exactly at threshold
        self.assertEqual(inv.low_stock_alerts(), [])
    
    def test_custom_threshold(self):
        inv = Inventory()
        inv.add("A", "a", 10, stock=3)
        self.assertEqual(inv.low_stock_alerts(threshold=10), [{"sku": "A", ...}])
    
    def test_zero_stock_included(self):
        inv = Inventory()
        inv.add("A", "a", 10, stock=0)
        alerts = inv.low_stock_alerts()
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["sku"], "A")
        self.assertEqual(alerts[0]["shortage"], 5)
```

## Tests to Run
1. `TETHER_E2E=1 uv run pytest tests/test_inventory.py -v`
2. Add new tests, verify with: `uv run pytest tests/test_inventory.py -v`
3. Lint check: `uv run ruff check tests/test_inventory.py`
4. Format check: `uv run ruff format --check tests/test_inventory.py`

## Impact Assessment
- **Backward compatibility**: `None` - no changes to existing methods
- **Token usage**: Minimal - new method is straightforward imperative logic
- **Risk**: Low - isolated feature, easy to test

## Acceptance Criteria
- ✅ Returns empty list when no items below threshold
- ✅ Items sorted alphabetically by SKU
- ✅ Includes shortage calculation in each alert
- ✅ Supports custom threshold parameter
- ✅ Includes zero-stock items
- ✅ All unit tests pass
- ✅ No lint/format errors
- ✅ Docs updated (if applicable)
