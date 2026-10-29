# Cart.checkout() Implementation Plan

## Modules That Change
1. **cart.py** - Add `checkout()` method to Cart class
2. **storage.py** - Use `save_orders()` to persist order data
3. **inventory.py** - Use `remove_stock()` to reduce stock levels

## Order Data Structure
The order should contain:
- `order_id`: Unique identifier for the order
- `items`: List of items with SKU and quantity
- `total`: Total price of the order
- `timestamp`: When the order was created

## Order of Operations
1. Validate that cart has items (lines is not empty)
2. Calculate order total using current cart lines and inventory prices
3. Create order object with order_id, items, total, and timestamp
4. Save order to storage using `storage.save_orders()`
5. Reduce stock for each item in the cart using `inventory.remove_stock()`
6. Clear cart lines after successful checkout

## Stock Shortage Handling
If stock is insufficient for any item:
1. Catch `ValueError` raised by `inventory.remove_stock()`
2. Rollback: Do not save the order to storage
3. Raise an error to the user indicating which item(s) have insufficient stock
4. Do not modify cart state (keep items in cart for retry)

## Detailed Steps
1. Check if cart.lines is empty; if so, raise error
2. Generate unique order_id (e.g., timestamp or UUID)
3. Build order dict with items list (sku, qty) and calculated total
4. Call `storage.save_orders()` to persist order
5. For each item in cart.lines:
   - Call `inventory.remove_stock(sku, qty)`
   - If ValueError raised, handle stock shortage (see above)
6. Clear cart.lines after successful checkout
7. Return order object to caller
