# Cart.checkout() Implementation Plan

## Modules That Will Change

1. **cart.py** - Add `checkout()` method to Cart class
2. **order.py** - Create new Order class (new file)
3. **storage.py** - Add `save_order()` function (new function)
4. **inventory.py** - Use `remove_stock()` method (no changes needed)

## Order Data Structure

Each order will contain:
- `id`: Unique identifier (UUID or timestamp-based)
- `date`: Date string in "YYYY-MM-DD" format
- `region`: Region identifier (e.g., "US", "EU")
- `total`: Total amount rounded to 2 decimal places

## Order of Operations

1. **Validate cart items** - Ensure cart is not empty
2. **Calculate order total** - Sum of all line totals (using pricing.py bulk_price)
3. **Check stock availability** - For each item, verify sufficient stock exists
4. **Create order object** - Generate order with id, date, region, and total
5. **Reduce inventory** - Call inventory.remove_stock() for each item
6. **Save order** - Call storage.save_order() to persist the order

## What Happens If Stock Is Short

If any item in the cart has insufficient stock:
- Raise a `ValueError` with message "insufficient stock"
- The transaction is aborted (no order created, no stock reduced)
- This follows the existing pattern in inventory.py.remove_stock()

## Detailed Steps

1. **Import required modules** in cart.py:
   - `from shop import inventory, storage`
   - `from datetime import date`
   - `from shop.pricing import bulk_price`

2. **Add checkout() method to Cart class** in cart.py:
   - Validate cart has items
   - Calculate total using bulk_price for each line item
   - Check stock for each item before checkout
   - Create order dictionary with required fields
   - Reduce stock via inventory.remove_stock()
   - Save order via storage.save_order()

3. **Create order.py** (new file):
   - Define Order class or data structure
   - Include id, date, region, total fields
   - Optionally add methods for order validation

4. **Add save_order() to storage.py**:
   - Load existing orders from file
   - Append new order to list
   - Save updated list back to file
   - Handle file creation if it doesn't exist

5. **Update cart.py imports** to include new modules

6. **Test the flow**:
   - Test with sufficient stock
   - Test with insufficient stock (should raise ValueError)
   - Verify order is saved correctly
   - Verify stock is reduced correctly