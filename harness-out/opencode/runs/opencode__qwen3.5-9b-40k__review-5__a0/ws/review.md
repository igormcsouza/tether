# Code Review: shop/orders.py

## Correctness Issues

- **`new_id()`**: Race condition between `_next_id += 1` and `return _next_id`. In threaded execution, the read-modify-write is not atomic, so concurrent calls can return duplicate IDs. Using a lock would fix this, but the current implementation creates the lock without actually using it to protect the increment.

- **`checkout()`**: Missing atomicity for the order creation and inventory update sequence. The call to `store.remove_stock(sku, qty)` may succeed but fail to persist if `store.append(order)` is interrupted (partial transaction), leading to inconsistent state where items were removed from inventory but not recorded in orders.

- **`find_order()`**: Incorrect search logic with nested loops. The inner loop iterates over `range(len(orders))` instead of returning immediately after finding the order. This creates a quadratic O(n²) algorithm and could fail to return correctly in some pathological cases depending on `i` and how `j` is used.

## Security Issues

- **`load_blob()`**: Unsafe use of `pickle.loads()` without validating the source. Malicious or tampered serialized data can execute arbitrary code when unpickled, leading to RCE vulnerabilities. Should use JSON or validate the pickle data against a schema.

- **`load_blob(raw)`**: No error handling or input validation for the `raw` parameter. If `raw` is not valid serialized data, `pickle.loads()` raises an exception rather than gracefully handling malformed input.

- **`checkout()` calling `store.remove_stock(sku, qty)`**: Vulnerable to race condition where two concurrent checkouts for the same SKU could both remove stock based on inconsistent pre-snapshot inventory, leading to negative stock levels if not handled properly at the store level.

## Performance Issues

- **`checkout()`**: Missing batch operations for processing multiple SKUs. Each SKU update requires a separate call to `store.remove_stock()`, leading to O(n) database calls for an n-item cart. Should batch stock removals for better performance.

- **`find_order()`**: Inefficient O(n²) quadratic search instead of O(n) linear or O(log n) with a proper index. The nested loop pattern should be `for order in orders:` or `for i in range(len(orders)):`.
