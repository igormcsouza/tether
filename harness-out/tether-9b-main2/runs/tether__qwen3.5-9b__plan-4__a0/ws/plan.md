# Multi-Currency Support Plan

## 1. Define Currency Model
- Decide on currency representation (e.g., string codes like "USD", "EUR", "GBP")
- Determine if we need a currency enum or simple string type
- Decide on default/base currency for the shop

## 2. Update Inventory to Support Multiple Currencies
- Modify `Inventory.add()` to accept a `currency` parameter
- Store currency alongside price in item data
- Decide: store prices in base currency only, or store per-currency prices?

## 3. Add Exchange Rate Management
- Create `exchange_rates.py` module to handle currency conversion
- Decide on storage: hardcoded rates, file-based, or external API
- Implement `convert(amount, from_currency, to_currency)` function
- Decide on rate update mechanism (manual, periodic, or dynamic)

## 4. Update Cart to Support Currency
- Modify `Cart` class to track currency
- Decide: cart uses base currency or customer-selected currency?
- Update `Cart.total()` to return amount with currency
- Consider: should cart convert to display currency?

## 5. Update Pricing Module
- Modify `bulk_price()` to work with currency-aware prices
- Decide: bulk discount applies before or after currency conversion?
- Ensure price calculations respect the currency context

## 6. Update Order/Report System
- Modify order data structure to include `currency` field
- Update `report.summary()` to include currency in output
- Update `report.monthly()` to handle currency-aware totals
- Decide: should reports show in base currency or per-currency breakdown?

## 7. Update Storage Layer
- Modify `storage.py` to handle currency-aware data
- Ensure JSON serialization/deserialization preserves currency info
- Decide: separate files per currency or unified with currency field?

## 8. Update CLI
- Modify `cli.py` to display currency in summary output
- Add option to specify currency for reports
- Consider: add currency conversion display option

## 9. Decide on User Interface for Currency Selection
- How do customers select their currency?
- Options: automatic based on IP, dropdown selector, account preference
- Decide on implementation approach (not code, just planning)

## 10. Decide on Price Strategy
- Option A: Store all prices in base currency, convert at display
- Option B: Store prices in each currency separately
- Option C: Hybrid approach
- **Decision needed**: Choose one strategy and document rationale

## 11. Decide on Exchange Rate Source
- Option A: Hardcoded rates (static)
- Option B: File-based rates (manual updates)
- Option C: External API (dynamic)
- **Decision needed**: Choose one and document update process

## 12. Decide on Rounding and Precision Rules
- How many decimal places for different currencies?
- How to handle rounding in conversions?
- **Decision needed**: Define rounding rules per currency

## 13. Decide on Error Handling
- What happens if a currency is not supported?
- What happens if exchange rates are unavailable?
- **Decision needed**: Define fallback behavior

## 14. Decide on Testing Strategy
- Unit tests for currency conversion
- Integration tests for multi-currency flows
- Test data with multiple currencies
- **Decision needed**: Test coverage requirements

## 15. Decide on Documentation
- API documentation for currency operations
- User guide for currency selection
- Admin guide for managing exchange rates
- **Decision needed**: Documentation format and scope

## Open Decisions to Make:
1. **Currency representation**: String codes vs enum
2. **Price storage strategy**: Base currency only vs per-currency storage
3. **Exchange rate source**: Hardcoded, file, or API
4. **Default currency**: What is the shop's base currency?
5. **Rounding rules**: Decimal places per currency
6. **User currency selection**: Automatic vs manual
7. **Error handling**: Fallback behavior for unsupported currencies
8. **Rate update process**: How often and by whom

## Implementation Order Recommendation:
1. Define currency model and default currency
2. Implement exchange rate module
3. Update inventory to store currency
4. Update cart to track currency
5. Update pricing to be currency-aware
6. Update reports to show currency
7. Update storage and CLI
8. Add user selection mechanism
9. Add testing
10. Add documentation