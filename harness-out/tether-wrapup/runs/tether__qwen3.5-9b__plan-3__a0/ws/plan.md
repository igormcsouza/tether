# Cart.checkout() Implementation Plan

## Overview
Implement `Cart.checkout()` method that creates an order, saves it to storage, and reduces inventory stock.

## Modules That Will Change

1. **shop/cart.py** - Add `checkout()` method to the Cart class
2. **shop/storage.py** - Add `save_order()` function to save individual orders
3. **shop/order.py** - Create new module to define Order data structure and validation

## Order Data Structure

Each order will contain:
```python
{
    "id": str,           # Unique order identifier (e.g., UUID or timestamp)
    "date": str,         # Date in "YYYY-MM-DD" format
    "region": str,       # Region identifier
    "items": [           # List of line items
        {
            "sku": str,
            "quantity": int,
            "unit_price": float,
            "line_total": float
        }
    ],
    "total": float,      # Total order amount (with bulk pricing applied)
    "status": str        # Order status (e.g., "completed")
}
```

## Order of Operations

1. **Validate Cart Contents**
   - Check that cart has at least one item
   - Calculate total quantity for each SKU

2. **Validate Stock Availability**
   - For each SKU in cart, check if inventory has sufficient stock
   - If any SKU has insufficient stock, raise `ValueError("insufficient stock")`

3. **Reduce Inventory Stock**
   - Call `inventory.remove_stock(sku, qty)` for each item in cart
   - This updates the inventory in place

4. **Calculate Order Details**
   - Calculate line totals using `bulk_price()` for each item
   - Sum all line totals to get order total
   - Generate order ID (e.g., timestamp-based or UUID)
   - Set date to current date in "YYYY-MM-DD" format
   - Set region (could be passed as parameter or derived from inventory)

5. **Create Order Object**
   - Build the order dictionary with all required fields

6. **Save Order to Storage**
   - Load existing orders from storage file
   - Append new order to the list
   - Save updated orders list back to storage file

7. **Return Order Object**
   - Return the created order for confirmation

## Error Handling

### Insufficient Stock
- If any item in the cart has more quantity than available in inventory:
  - Raise `ValueError("insufficient stock")`
  - Do NOT modify inventory or create order
  - Do NOT save to storage

### Empty Cart
- If cart has no items:
  - Raise `ValueError("cart is empty")`
  - Do NOT modify inventory or create order

### Storage Errors
- If storage file cannot be read/written:
  - Raise appropriate exception (e.g., `FileNotFoundError`, `IOError`)

## Implementation Details

### shop/cart.py
Add `checkout()` method:
```python
def checkout(self, inventory, storage_path, region="default"):
    # 1. Validate cart not empty
    # 2. Validate stock for all items
    # 3. Reduce stock via inventory.remove_stock()
    # 4. Calculate order totals
    # 5. Create order dict
    # 6. Save via storage.save_order()
    # 7. Return order
```

### shop/storage.py
Add `save_order()` function:
```python
def save_order(path, order):
    # Load existing orders
    # Append new order
    # Save back to file
```

### shop/order.py (new file)
Define constants and helper functions:
```python
# Order ID generation
# Date formatting
# Order validation helpers
```

## Summary of Changes

| Module | Action | Purpose |
|--------|--------|---------|
| shop/cart.py | Add method | Implement checkout logic |
| shop/storage.py | Add function | Save individual orders |
| shop/order.py | Create file | Define order structure and helpers |

## Key Points

- Stock reduction happens BEFORE order creation (atomic operation)
- If stock validation fails, no changes are made to inventory or storage
- Order ID should be unique (use timestamp or UUID)
- Date format must be "YYYY-MM-DD" for consistency with report.py
- Bulk pricing is already handled by pricing.py.bulk_price()