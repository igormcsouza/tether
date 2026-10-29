# Cart.checkout() Implementation Plan

## Modules That Change
1. **shop/cart.py** - Add `checkout()` method to the Cart class
2. **shop/order.py** - Create new file to define Order class and order data structure
3. **shop/storage.py** - Add function to save individual orders (or modify existing save_orders)

## Order Data Structure
Each order will contain:
- `id`: Unique identifier (auto-generated, e.g., UUID or timestamp-based)
- `date`: Current date in "YYYY-MM-DD" format
- `region`: Region identifier (could be derived from cart or passed as parameter)
- `total`: Total order value (calculated from cart lines using bulk_price)
- `items`: List of line items with sku and quantity
- `inventory_snapshot`: Copy of inventory state at checkout time (optional, for audit)

## Order of Operations
1. **Validate cart** - Ensure cart has items before checkout
2. **Calculate order total** - Use existing `bulk_price()` function for each line item
3. **Validate stock** - Check that each item has sufficient stock (sum of quantities)
4. **Create order object** - Generate order with id, date, region, total, and items
5. **Reduce stock** - Call `inventory.remove_stock()` for each item in cart
6. **Save order** - Append new order to orders list and call `storage.save_orders()`

## Stock Shortage Handling
If stock is insufficient for any item:
1. **Raise ValueError** - Similar to `Inventory.remove_stock()` behavior
2. **Error message** - "insufficient stock for SKU: {sku}"
3. **Transaction rollback** - No stock is reduced if checkout fails (all operations before stock reduction are safe)
4. **User feedback** - Cart.checkout() should raise exception that caller can catch

## Detailed Steps

1. **Create shop/order.py**
   - Define Order class with __init__(id, date, region, total, items)
   - Implement __dict__ or __repr__ for debugging

2. **Modify shop/cart.py**
   - Add `checkout()` method that:
     - Validates cart is not empty
     - Creates order data structure
     - Validates stock for all items
     - Reduces inventory stock
     - Saves order to storage
     - Returns order object

3. **Modify shop/storage.py**
   - Add `save_order(path, order)` function
   - Load existing orders, append new one, save back
   - Or modify `save_orders()` to accept list of orders

4. **Update shop/__init__.py**
   - Export new Order class if needed
   - Ensure all modules are properly imported

## Error Handling Flow
```
Cart.checkout()
  ├─> Validate cart has items
  ├─> Calculate total (no stock change yet)
  ├─> Validate stock (no stock change yet)
  ├─> Create order object
  ├─> Reduce stock (side effect)
  ├─> Save order (side effect)
  └─> Return order
```

If any step fails after stock reduction, consider:
- Option A: Accept partial failure (stock reduced, order not saved)
- Option B: Rollback stock (requires tracking reduced amounts)
- Option C: Validate stock before any changes (recommended)