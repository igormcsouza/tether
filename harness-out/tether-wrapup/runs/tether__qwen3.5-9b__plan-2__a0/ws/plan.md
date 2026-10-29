# Low-Stock Alert Plan

## Overview
Add a low-stock alert feature that reports inventory items whose stock is below a configurable threshold.

## File and Method Changes

### 1. File: `shop/inventory.py`
   - **Method to add**: `low_stock_items(self, threshold=0)`
   - **Purpose**: Returns a list of items where stock is below the given threshold
   - **Default threshold**: 0 (items with stock <= 0)
   - **Return format**: List of item dictionaries (same format as `list_items()`)
   - **Implementation**: Filter `self._items.values()` where `item["stock"] <= threshold`

### 2. File: `shop/report.py`
   - **Method to add**: `low_stock(inventory, threshold=0)`
   - **Purpose**: Generate a low-stock report from an Inventory object
   - **Default threshold**: 0
   - **Return format**: Dictionary with "items" key containing list of low-stock items
   - **Implementation**: Call `inventory.low_stock_items(threshold)` and wrap in report structure

### 3. File: `shop/cli.py` (Optional - for CLI access)
   - **Command to add**: `low-stock` command
   - **Purpose**: CLI interface to run low-stock report
   - **Usage**: `python -m shop.cli low-stock [threshold]`
   - **Default threshold**: 0

## Tests to Add

### 1. File: `tests/test_inventory.py`
   - **Test**: `test_low_stock_items_default_threshold`
     - Verify items with stock <= 0 are returned
     - Verify items with stock > 0 are excluded
   
   - **Test**: `test_low_stock_items_custom_threshold`
     - Verify items with stock <= threshold are returned
     - Verify items with stock > threshold are excluded
   
   - **Test**: `test_low_stock_items_empty`
     - Verify empty list returned when no items below threshold

### 2. File: `tests/test_report.py`
   - **Test**: `test_low_stock_default_threshold`
     - Verify report structure with "items" key
     - Verify correct items included with threshold=0
   
   - **Test**: `test_low_stock_custom_threshold`
     - Verify correct items included with custom threshold
   
   - **Test**: `test_low_stock_no_items`
     - Verify empty items list when no low-stock items

## Implementation Steps

1. Add `low_stock_items(self, threshold=0)` method to `Inventory` class
2. Add `low_stock(inventory, threshold=0)` function to `report.py`
3. Add CLI command for low-stock (optional)
4. Write unit tests for both new methods
5. Run tests to verify implementation

## Default Threshold
The default threshold is **0**, meaning items with stock of 0 or less will be flagged as low-stock.