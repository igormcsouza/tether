# Cart.checkout() Implementation Plan

## Overview
Implement `Cart.checkout()` to create an order, persist it via storage, and reduce inventory stock. The method must validate stock sufficiency before proceeding.

## Module Interactions

| Module | Purpose |
|--------|---------|
| `cart.py` | Cart class with `add()` and `total()`. Adds `checkout()` method. |
| `inventory.py` | Validates available stock via `remove_stock()`. Raises `ValueError` on shortage. |
| `storage.py` | Persists orders to JSON via `save_orders()`. Expects a list of orders. |

## Order of Operations

1. Build order from `cart.items`:
   - For each `(name, qty, price)` tuple:
     - Deduct `qty` from inventory via `Inventory.remove_stock(name, qty)`.
   - If any item fails stock validation, raise `ValueError("insufficient stock")`.
2. Construct order dict:
   ```python
   {
       "order_id": generate_order_id(),
       "items": [{'name': n, 'qty': q, 'price': p} for n, q, p in cart.items],
       "total": cart.total(),
       "timestamp": datetime.now().isoformat(),
   }
   ```
3. Persist order via `storage.save_orders([order])`.
4. Return `order_id`.

## Stock Short Error Handling Flow

- When `remove_stock(product, qty)` finds `qty > available`, it raises `ValueError("insufficient stock")`.
- This exception propagates through `checkout()`, stopping the transaction.
- No order is created or persisted.
- No partial inventory updates occur (ACID integrity).

## Files Changed

- `shop/cart.py` — Add `checkout()` method to `Cart` class.

## Dependencies

The implementation assumes:
- `Inventory.remove_stock(name, qty)` is available.
- `storage.save_orders(orders)` expects a list of order dicts.
- A UUID generator or incrementing ID strategy exists for `order_id`.
- `datetime` module is available for timestamps.
