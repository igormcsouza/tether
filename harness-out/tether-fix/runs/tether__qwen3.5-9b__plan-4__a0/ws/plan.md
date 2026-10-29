# Multi-Currency Support Plan

## 1. Define Currency Model
- Create a `Currency` class or data structure to represent currency codes (e.g., "USD", "EUR", "GBP")
- Define exchange rates mechanism (static rates, API-based, or file-based)
- Decide on base currency for internal calculations

## 2. Update Inventory to Support Multiple Currencies
- Modify `Inventory.add()` to accept currency parameter or store prices per currency
- Decide: single price with currency field, or multiple prices per SKU
- Update `Inventory.get()` to return currency information with price

## 3. Extend Pricing Module
- Add currency parameter to `line_total()` and `bulk_price()` functions
- Consider: should bulk discount apply per currency or globally?
- Add currency conversion logic if needed

## 4. Update Cart to Handle Currencies
- Add currency field to Cart class
- Decide: cart uses single currency or supports multiple currencies
- Update `Cart.add()` to track currency of added items
- Modify `Cart.total()` to return price in specified currency with conversion

## 5. Add Currency Conversion Logic
- Implement exchange rate lookup (file-based for simplicity)
- Add conversion function: `convert(amount, from_currency, to_currency)`
- Decide: convert at cart level or at checkout level?

## 6. Update Order Model
- Add currency field to order data structure
- Store original currency and converted amount if applicable
- Update `storage.py` to handle currency in JSON

## 7. Update Report Module
- Modify `summary()` to handle multiple currencies
- Add currency breakdown to reports
- Consider: separate reports per currency or combined with conversion

## 8. Update CLI Interface
- Add currency selection option to CLI
- Allow specifying output currency for reports
- Update usage message to reflect new options

## 9. Decide: Currency Scope
- **Decision point**: Will each customer have their own currency, or is currency per order?
- **Decision point**: Should prices be stored per currency or converted at display?
- **Decision point**: How to handle exchange rate updates?

## 10. Implementation Order
1. Define Currency model and exchange rate storage
2. Update Inventory to store currency
3. Update pricing functions to accept currency
4. Update Cart to track and convert currencies
5. Update storage to include currency in orders
6. Update reports to handle multiple currencies
7. Update CLI to allow currency selection
8. Add tests for currency conversion edge cases
9. Document API changes

## Open Questions to Decide:
1. **Exchange rate source**: File-based static rates vs. API vs. manual entry
2. **Price storage**: Single price with currency vs. multiple prices per SKU
3. **Conversion timing**: At cart creation, at checkout, or at display
4. **Bulk discount**: Apply before or after currency conversion
5. **Order currency**: Store original currency or always in base currency
6. **Report granularity**: Per-currency reports or consolidated with conversion