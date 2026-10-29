# Cart.checkout() Implementation Plan

## Overview
Implement `Cart.checkout()` method that creates an order, saves it to storage, and reduces inventory stock.

## Modules That Will Change

1. **shop/cart.py** - Add `checkout()` method to the `Cart` class
2. **shop/storage.py** - Add `save_order()` function to save individual orders
3. **shop/report.py** - Update `summary()` to handle new order format (optional enhancement)

## Order Data Structure

Each order will be a dictionary with the following fields:
```python
{
    "id": <unique identifier, e.g., UUID or timestamp>,
    "date": "YYYY-MM-DD",
    "region": <region identifier>,
    "lines": [
        {"sku": <sku>, "qty": <quantity>},
        ...
    ],
    "total": <calculated total price>
}
```

## Order of Operations

1. **Validate stock availability** - Check if each item in the cart has sufficient stock
2. **Calculate order total** - Use existing `bulk_price()` from pricing module
3. **Create order object** - Build order dictionary with required fields
4. **Reduce inventory stock** - Call `inventory.remove_stock()` for each item
5. **Save order to storage** - Append order to orders list and save via `storage.save_orders()`

## Stock Shortage Handling

If stock is insufficient for any item in the cart:
- Raise `ValueError("insufficient stock")` before any order is created
- No order is saved to storage
- No inventory is reduced
- The error should be raised during the stock validation step

## Implementation Steps

1. Add `checkout()` method to `Cart` class in `shop/cart.py`:
   - Accept parameters: `inventory`, `storage_path`, `order_id`, `date`, `region`
   - Validate stock for all items in cart
   - Calculate total using existing pricing logic
   - Create order dictionary
   - Reduce stock via inventory module
   - Save order via storage module

2. Add `save_order()` function to `shop/storage.py`:
   - Load existing orders from file
   - Append new order to list
   - Save updated list back to file

3. Update `shop/report.py` if needed:
   - Ensure `summary()` handles the new order format

## Dependencies

- Uses existing `bulk_price()` from `shop/pricing.py`
- Uses existing `inventory.remove_stock()` from `shop/inventory.py`
- Uses existing `storage.save_orders()` and `storage.load_orders()` from `shop/storage.py`