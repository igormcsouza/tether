# Plan: Cart.checkout() Implementation

## Modules That Change
- `cart.py` - Adds the `checkout()` method to create orders
- `inventory.py` - Reduces stock via `remove_stock()` when an order is placed
- `storage.py` - Saves the order to a JSON file via `save_orders()`

## Order Data Structure
Each order saved will be a dictionary with these fields:
- `id`: Unique order identifier (e.g., "order_001")
- `date`: Date in "YYYY-MM-DD" format
- `region`: Region where the order was placed
- `total`: Total price rounded to 2 decimal places

## Order of Operations
1. **Validate cart contents**: Ensure all SKUs in the cart exist in inventory
2. **Calculate total price**: Sum up prices for all items using `bulk_price()` from pricing module
3. **Check stock availability**: For each SKU, verify sufficient stock exists via `inventory.remove_stock()`
4. **Reduce stock**: If stock is sufficient, call `inventory.remove_stock(sku, qty)` for each item
5. **Create order object**: Build an order dictionary with id, date, region, and total
6. **Save order**: Call `storage.save_orders(path, orders)` to persist the order
7. **Return success**: Return the created order or raise an exception on failure

## What Happens If Stock Is Short
- The `inventory.remove_stock()` call will raise a `ValueError` with message "insufficient stock"
- This exception propagates up and prevents the order from being saved
- No partial orders are created; the entire checkout fails if any item lacks sufficient stock
- Cart contents remain unchanged (no items were removed from inventory)
