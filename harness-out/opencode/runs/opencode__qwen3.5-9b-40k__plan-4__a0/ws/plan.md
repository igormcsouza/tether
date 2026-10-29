# Multi-Currency Support Plan for Shop

## Objective
Enable the shop to handle multiple currencies while preserving existing single-currency USD functionality.

---

## Step 1: Define Currency Data Model
- Add `currency: str` field (ISO 4217 code like "USD", "EUR", "GBP") to the `Item` data structure in `inventory.py`.
- Modify `price_map` in `cart.py` to map `(item_id, currency)` pairs instead of just `item_id`.
- Add optional `user_currency: str` to the `Cart` to track the customer's preferred currency.
- Create a `Currency` namedtuple or simple structure with `code`, `name`, and optional `symbol`.

### Leaves Open
- Initial default currency logic when user currency is not specified.
- Currency availability management (e.g., which currencies are supported).

## Step 2: Implement Exchange Rate Management
- Create `shop/currencies.py` with exchange rate management functions.
- Support static exchange rates (hardcoded in config) or dynamic rates (API-based).
- Implement `get_exchange_rate(from_currency: str, to_currency: str) -> float`.
- Add `refresh_rates()` function for periodic updates.
- Store rates in `.tether/tether.db` or a config file for persistence.

### Leaves Open
- Rate source decision: API (exchangeratesapi.io, fixer.io) vs static config file vs database.
- Auto-refresh scheduling (cron or in-app refresh).
- Handling rate failures or stale rates.

## Step 3: Update Inventory Pricing
- Modify `Inventory.create_item()` to accept either:
  - A single price (backward compatible, treated as the item's native currency)
  - A price dict: `{currency: amount}` for multiple currencies
- Update `bulk_price_by_item()` to accept currency parameter.
- Add validation that at least one currency price is provided for new items.

### Leaves Open
- Migration strategy for existing single-currency items.
- Display logic when multiple currency prices exist.

## Step 4: Update Cart and Checkout Logic
- Modify `Cart.add_item()` to accept optional `customer_currency` parameter.
- Implement `calculate_total()` to:
  - Convert item prices to `customer_currency` using exchange rates
  - Round to 2 decimal places
  - Calculate bulk discounts in the target currency
- Update `Checkout.process()` to store transaction currency and exchange rate snapshot.

### Leaves Open
- Pricing precision and rounding rules for different currencies.
- Bulk discount calculations across currency boundaries.
- Displaying item prices vs cart total in different currencies.

## Step 5: Update Money Formatting Utility
- Modify `money()` in `utils.py` to accept optional `currency` parameter.
- Default to USD if not specified (backward compatible).
- Update hardcoded `'$'` references to dynamic `currency` or localized symbols.
- Add support for locale-aware number formatting (thousands separators, decimal places).

### Leaves Open
- Locale configuration strategy (user preference vs system locale).
- Handling of regions where currency placement differs (e.g., 1,234.56€ vs 1.234,56 €).

## Step 6: Update Reports and Analytics
- Modify `report.generate_order_summary()` to include `order_currency` in summaries.
- Add `group_by_currency()` aggregation in `report.generate_all_orders_report()`.
- Update SQL JOINs in `report.generate_low_stock_items()` if currency filtering is needed.
- Export reports to support multi-currency totals (subtotals by currency, grand total).

### Leaves Open
- Historical data conversion: should old USD-only orders be retrofitted?
- Report currency preference UI.

## Step 7: Update CLI Interface
- Add `--currency <CODE>` flag to CLI commands where applicable:
  - `add-item --currency <CODE>` (optional if item has native currency)
  - `view-items --currency <CODE>` (filter or display in currency)
  - `add-to-cart --currency <CODE>` (optional for cart currency)
- Add `get-exchange-rates` command to test/inspect available rates.
- Add `set-rate <from> <to> <rate>` command for manual rate updates.

### Leaves Open
- CLI currency flag consistency vs programmatic API.
- Which commands should expose currency options.

## Step 8: Database Schema Updates
- Add `currency` column to `Inventory` table.
- Consider adding transactions table with `currency` and `exchange_rate_at_time` columns.
- Add `user_currency` column to Orders/Carts if needed.
- Index `currency` columns for efficient filtering.

### Leaves Open
- Backward compatibility for existing tables without `currency` column.
- Transaction history retention for audit purposes.

## Step 9: Error Handling and Edge Cases
- Handle missing exchange rates (graceful fallback to native currency).
- Handle currency code validation (only valid ISO 4217 codes).
- Handle rate precision and floating-point arithmetic.
- Add currency validation for user input.

### Leaves Open
- Rate threshold for accepting stale rates vs error.
- Maximum exchange rate spread tolerance.

## Step 10: Testing Strategy
- Add tests for exchange rate precision (12+ decimal places).
- Test currency conversion edge cases (very small amounts, large amounts).
- Test backward compatibility with single-currency items.
- Add e2e tests for multi-currency cart flow.
- Add tests for report generation with mixed currencies.

## Step 11: Documentation Updates
- Document new currency parameter signatures.
- Document exchange rate management procedures.
- Document multi-currency pricing policies.
- Update user-facing documentation if applicable.

---

## Summary of Open Assumptions

1. **Currency Selection Mechanism**
   - How does the system know which currency a user prefers?
   - Should this be persistent (account setting), temporary (session), or inferred?

2. **Exchange Rate Source**
   - Static configuration file vs dynamic API calls.
   - API choice and fallback behavior.

3. **Existing Data Migration**
   - How to convert existing USD-only pricing to the new model.
   - Should the migration be automatic on first item creation vs manual.

4. **Pricing Precision**
   - Rounding rules per currency (some use 2 decimals, some use 4).
   - Localization of number formatting.

5. **User Experience**
   - Displaying multiple currency options for the same item.
   - Pricing strategy (fixed exchange vs real-time).

6. **Performance**
   - Caching strategy for exchange rates.
   - Impact on cart checkout performance.
