# Multi-Currency Support Plan

## 1. Define Currency Model
- Add a `Currency` class to represent currency codes (e.g., USD, EUR, GBP)
- Implement currency validation against ISO 4217 standard
- Create a registry of supported currencies with their codes and symbols

## 2. Add Exchange Rate Management
- Create an `ExchangeRates` class to manage conversion rates between currencies
- Implement a base currency (e.g., USD) as the reference
- Add methods to get conversion rates and convert between any two currencies
- Consider caching rates for performance

## 3. Update Inventory to Support Multiple Currencies
- Add a `currency` field to inventory items (default to base currency)
- Optionally add `prices` as a dict mapping currency codes to prices
- Decide on approach: single currency per item vs. multi-currency pricing

## 4. Update Cart to Track Currency
- Add currency tracking to the `Cart` class
- Ensure cart total is calculated in the appropriate currency
- Handle currency conversion when displaying cart total

## 5. Add Currency Conversion to Pricing
- Modify `bulk_price` to accept a currency parameter
- Ensure bulk discount calculations work correctly across currencies
- Consider whether discounts should be applied before or after conversion

## 6. Update Order Storage for Currency
- Modify order structure to include currency information
- Update `storage.py` to handle currency fields in orders
- Ensure orders can be saved and loaded with currency data

## 7. Update Reports for Multi-Currency
- Modify `report.py` to handle multiple currencies in summaries
- Add currency conversion to revenue calculations
- Consider grouping reports by currency or showing totals in base currency

## 8. Add Currency Selection to CLI
- Update `cli.py` to accept a currency parameter
- Allow users to specify which currency to display prices in
- Add currency conversion to the summary output

## 9. Add Currency Conversion Utilities
- Create a `currency.py` module with conversion functions
- Implement functions for:
  - Converting prices between currencies
  - Formatting currency display
  - Validating currency codes

## 10. Decide on Currency Strategy
- **Decision Point**: Choose between:
  - Option A: Store items in base currency only, convert at display time
  - Option B: Store items in multiple currencies (more complex but more flexible)
  - Option C: Hybrid approach - base currency + optional alternative currencies
- **Decision**: Select Option A for simplicity - store all prices in base currency (USD), convert on display
- This minimizes data duplication and simplifies inventory management

## 11. Add Currency Configuration
- Create a configuration file or environment variables for:
  - Base currency setting
  - Supported currencies list
  - Exchange rate source (manual, API, file)
  - Default exchange rates

## 12. Update Documentation
- Document the currency model and how to use it
- Add examples of currency conversion
- Document the exchange rate management approach
- Update any API documentation if applicable

## 13. Testing Strategy
- Write tests for currency conversion accuracy
- Test edge cases (zero rates, invalid currencies)
- Verify bulk pricing works correctly across currencies
- Test cart total calculations with currency conversion

## 14. Implementation Order
1. Currency model (Step 1)
2. Exchange rates (Step 2)
3. Currency utilities (Step 9)
4. Inventory updates (Step 3)
5. Cart updates (Step 4)
6. Pricing updates (Step 5)
7. Storage updates (Step 6)
8. Report updates (Step 7)
9. CLI updates (Step 8)
10. Configuration (Step 11)
11. Documentation (Step 12)
12. Testing (Step 13)

## Open Questions to Decide
1. **Exchange Rate Source**: Should we use a live API, manual updates, or a fixed file?
   - *Decision*: Start with a manual JSON file for simplicity, can be extended to API later
2. **Base Currency**: Which currency should be the base?
   - *Decision*: USD (already implied by current implementation)
3. **Price Precision**: How many decimal places for currency amounts?
   - *Decision*: Keep current 2 decimal places for consistency
4. **Rounding Behavior**: How to handle rounding during conversion?
   - *Decision*: Round to 2 decimal places after each conversion
5. **Bulk Discount in Converted Currency**: Should bulk discount be calculated in base currency then converted, or converted then discounted?
   - *Decision*: Calculate in base currency, then convert final total (simpler)