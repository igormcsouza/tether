# Multi-Currency Support Plan

## 1. Define Currency Model
- Add `currency` field to Inventory items (default: "USD")
- Add `currency` field to Orders (default: "USD")
- Currency codes will be ISO 4217 format (e.g., "USD", "EUR", "GBP")

## 2. Add Exchange Rate Management
- Create `exchange_rates.py` module
- Store exchange rates as a dictionary: `{base_currency: {target_currency: rate}}`
- Add `load_exchange_rates(path)` and `save_exchange_rates(path, rates)` functions
- Exchange rates represent 1 unit of base currency = X units of target currency
- Add reference date to exchange rate data for historical accuracy

## 3. Update Inventory to Support Currency
- Modify `Inventory.add()` to accept `currency` parameter (default "USD")
- Store currency with each item in `_items`
- Items keep their base currency; conversion happens at cart/checkout

## 4. Update Pricing Module for Currency
- Modify `pricing.py` to accept optional `currency` parameter
- Add `convert_price(price, from_currency, to_currency, rates)` function
- `bulk_price()` should convert to target currency before applying discount
- Add `line_total()` with currency conversion support

## 5. Update Cart Module for Currency
- Add `currency` parameter to `Cart.__init__()` (default "USD")
- Add `set_currency(currency)` method to change cart currency
- `total()` should convert all item prices to cart currency before summing
- Add `get_currency()` method to get current cart currency

## 6. Update Storage for Currency
- Modify `storage.py` to handle currency in orders
- Orders should include `currency` field when saved/loaded
- Add `save_orders_with_currency()` and `load_orders_with_currency()` functions

## 7. Update Report Module for Currency
- Add `currency` parameter to `summary()` and `monthly()` functions
- Reports should convert all totals to specified currency
- Add `convert_report_totals(orders, target_currency, rates)` helper

## 8. Update Utils for Currency Formatting
- Modify `money()` function to accept `currency` parameter
- Add currency symbol mapping: `{"USD": "$", "EUR": "€", "GBP": "£", ...}`
- Add locale-aware formatting for different currencies
- Support different decimal places per currency (e.g., JPY uses 0 decimals)

## 9. Add Currency Conversion Utilities
- Create `convert_amount(amount, from_currency, to_currency, rates)` function
- Handle missing exchange rates gracefully (raise error or use fallback)
- Add caching for frequently used conversions

## 10. Add Currency Configuration
- Create `currency_config.py` module
- Define default currency: "USD"
- Define supported currencies list
- Define currency symbols and decimal places per currency
- Add `get_currency_symbol(currency)` and `get_currency_decimals(currency)` functions

## 11. Update CLI for Currency Selection
- Add `--currency` flag to `shop.cli summary` command
- Allow users to specify currency for report output
- Default to "USD" if not specified

## 12. Add Exchange Rate File Format
- Define JSON format for exchange rates file:
  ```json
  {
    "base": "USD",
    "rates": {
      "EUR": 0.92,
      "GBP": 0.79,
      "JPY": 150.0
    },
    "updated": "2024-01-01"
  }
  ```

## 13. Handle Edge Cases
- Missing exchange rates: raise clear error message
- Invalid currency codes: validate against supported list
- Zero or negative exchange rates: validate and reject
- Rounding: round to appropriate decimal places per currency

## 14. Testing Considerations
- Add tests for currency conversion accuracy
- Test with multiple currencies in same cart
- Test exchange rate loading/saving
- Test report generation with currency conversion
- Test edge cases (missing rates, invalid currencies)

## 15. Future Considerations (Not in Scope)
- Real-time exchange rate API integration
- Multi-currency inventory (items with prices in multiple currencies)
- Currency-specific tax rules
- Multi-currency user accounts with preferences
- Historical exchange rate lookups for past orders
