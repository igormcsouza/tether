# Multi-Currency Support Plan

## 1. Define Currency Model
- Create a `Currency` class or module to represent currency codes (USD, EUR, GBP, etc.)
- Define exchange rates mechanism (static rates, API-based, or database-backed)
- Decide on a base currency (e.g., USD) for internal calculations

## 2. Update Inventory to Support Multiple Currencies
- Modify `Inventory.add()` to accept an optional `currency` parameter
- Store currency information with each item (either as a separate field or in a nested structure)
- Decide: store price in item's local currency or base currency?

## 3. Update Pricing Module for Currency Conversion
- Modify `line_total()` and `bulk_price()` to accept a `currency` parameter
- Add currency conversion logic to convert prices to/from base currency
- Decide: should pricing functions return prices in base currency or local currency?

## 4. Update Cart Module for Multi-Currency
- Modify `Cart` class to handle items with different currencies
- Decide: should cart total be in base currency or allow multiple currency totals?
- Add currency conversion for cart total calculation

## 5. Update Order Model for Currency Tracking
- Modify order data structure to include currency information
- Store original order currency and converted total (if applicable)
- Update `storage.py` to handle currency fields in JSON

## 6. Update Report Module for Currency-Aware Reporting
- Modify `summary()` and `monthly()` to handle multiple currencies
- Decide: should reports show totals in base currency or per-currency breakdown?
- Add option to convert all totals to a single currency for reporting

## 7. Update CLI for Currency Options
- Add currency flag/option to CLI commands
- Allow users to specify which currency to display totals in
- Update help text to document currency options

## 8. Update Tests for Multi-Currency Scenarios
- Add tests for currency conversion accuracy
- Add tests for mixed-currency carts
- Add tests for currency-specific reports
- Add tests for edge cases (zero rates, missing rates)

## 9. Decide on Currency Rate Management
- **Decision needed**: How to manage exchange rates?
  - Option A: Hard-coded static rates (simplest, needs updates)
  - Option B: Configuration file (flexible, needs maintenance)
  - Option C: External API (most accurate, adds complexity)
  - Option D: Database-backed rates (most flexible, requires backend)

## 10. Decide on Price Storage Strategy
- **Decision needed**: How to store item prices?
  - Option A: Store in base currency only (simpler, requires conversion on display)
  - Option B: Store in local currency with conversion on add (more complex)
  - Option C: Store both (most flexible, uses more storage)

## 11. Decide on Cart Behavior
- **Decision needed**: How should mixed-currency carts work?
  - Option A: Convert all to base currency, show total in base currency
  - Option B: Group by currency, show multiple totals
  - Option C: Force single currency per cart

## 12. Decide on Report Behavior
- **Decision needed**: How should reports handle multiple currencies?
  - Option A: Show per-currency breakdown
  - Option B: Convert all to base currency
  - Option C: Both (breakdown + converted total)

## 13. Implementation Order
1. Define currency model and rate management (Step 1)
2. Update inventory to store currency info (Step 2)
3. Update pricing module with conversion logic (Step 3)
4. Update cart module (Step 4)
5. Update order storage format (Step 5)
6. Update report module (Step 6)
7. Update CLI (Step 7)
8. Update tests (Step 8)
9. Document decisions and update documentation

## Open Decisions to Make
1. **Exchange rate management**: Which approach (A/B/C/D)?
2. **Price storage**: Base currency only vs. local currency (Option A/B/C)?
3. **Cart behavior**: Single currency vs. multi-currency totals (Option A/B/C)?
4. **Report behavior**: Per-currency vs. converted totals (Option A/B/C)?
5. **Base currency**: Which currency to use as base (USD, EUR, etc.)?