# Cart.checkout() Implementation Plan

## Modules That Change

1. **cart.py** - Add `checkout()` method to Cart class
2. **storage.py** - Use existing `save_orders()` function to persist order
3. **inventory.py** - Use existing `remove_stock()` method (no changes needed)

## Order Data Structure

Each order is a dictionary with the following keys:
- `id`: Unique order identifier (string)
- `date`: Order date in "YYYY-MM-DD" format (string)
- `region`: Region identifier (string)
- `total`: Total order amount (float, rounded to 2 decimal places)

## Order of Operations

1. **Calculate order total**
   - Iterate through cart items
   - Use `pricing.bulk_price()` for each item (handles bulk discount at 10+ units)
   - Sum all line totals to get order total

2. **Validate stock availability**
   - For each item in cart, check if inventory has sufficient stock
   - Call `inventory.remove_stock(sku, quantity)` for each item
   - This will raise `ValueError("insufficient stock")` if any item lacks stock

3. **Create order record**
   - Generate unique order ID
   - Get current date in "YYYY-MM-DD" format
   - Use cart's region
   - Store calculated total

4. **Save order to storage**
   - Load existing orders from storage
   - Append new order to list
   - Call `storage.save_orders()` to persist

5. **Clear cart**
   - Remove all items from cart after successful checkout

## What Happens If Stock Is Short

- When `inventory.remove_stock(sku, qty)` is called, it checks if `qty > item["stock"]`
- If true, it raises `ValueError("insufficient stock")`
- This exception propagates to `checkout()` and should be caught by the caller
- No order is created or saved if stock is insufficient
- Cart remains unchanged (no partial checkout)

## Implementation Notes

- Use `uuid.uuid4()` or similar for order ID generation
- Use `datetime.date.today().strftime("%Y-%m-%d")` for date
- Order IDs should be unique and persistent
- Stock reduction happens before order is saved (atomic operation)
- If any step fails after stock reduction, consider rolling back (not implemented in current design)