# Plan: Cart.checkout() Order History

## Modules That Change
- **cart.py**: Main checkout logic, creates order and orchestrates operations
- **storage.py**: Saves the order to orders.json file
- **inventory.py**: Reduces stock when an item is purchased

## Order Data Structure
An order object contains:
- `id`: Unique identifier for the order
- `date`: Date in "YYYY-MM-DD" format
- `region`: Geographic region of the purchase
- `total`: Total amount (sum of line totals)
- `items`: List of purchased items with SKU, quantity, and unit price

## Order of Operations
1. **Validate stock**: Check if inventory has sufficient stock for all items in the cart
2. **Create order object**: Build order data with id, date, region, total, and items
3. **Save to storage**: Write the order to orders.json using `storage.save_orders()`
4. **Reduce stock**: For each item, call `inventory.remove_stock(sku, quantity)`

## What Happens If Stock Is Short
- The `remove_stock()` method in inventory.py checks if requested quantity exceeds available stock
- If insufficient stock is detected, it raises a `ValueError` with message "insufficient stock"
- This exception propagates up through cart.checkout(), preventing the order from being created
- No order is saved to storage if stock validation fails