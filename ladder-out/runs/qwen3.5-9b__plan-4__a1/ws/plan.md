# Multi-Currency Support Plan

## 1. Define Currency Model
- Create a `Currency` class or data structure to represent currency codes (e.g., USD, EUR, GBP)
- Add a `CURRENCIES` dictionary mapping currency codes to their symbols and decimal places

## 2. Add Exchange Rate Management
- Create a `rates.py` module to store and manage exchange rates against a base currency (e.g., USD)
- Implement functions to:
  - Load exchange rates from a JSON file
  - Update exchange rates (with versioning for historical accuracy)
  - Calculate conversion rates between any two currencies

## 3. Modify Inventory to Support Multiple Currencies
- Update `Inventory.add()` to accept an optional `currency` parameter
- Store prices in a base currency internally for consistency
- Add a method to get/display prices in a specific currency

## 4. Update Cart for Multi-Currency
- Modify `Cart` to accept a `currency` parameter in `__init__`
- Update `total()` to convert line totals to the cart's currency
- Ensure bulk discount calculations work correctly with currency conversion

## 5. Update Pricing Module
- Modify `line_total()` and `bulk_price()` to accept an optional `currency` parameter
- Add currency conversion logic before/after calculations as needed

## 6. Update Money Formatting
- Modify `utils.money()` to accept a `currency` parameter
- Support different decimal place requirements per currency (e.g., JPY uses 0 decimals)

## 7. Update Order Storage
- Modify `storage.save_orders()` and `load_orders()` to include currency information
- Store the currency used for each order

## 8. Update CLI Interface
- Add currency selection option to the CLI
- Allow users to specify their preferred currency for display

## 9. Update Report Module
- Modify report generation to include currency information
- Support generating reports in different currencies

## 10. Add Validation and Error Handling
- Validate currency codes against known currencies
- Handle missing exchange rates gracefully
- Add clear error messages for unsupported currencies

## 11. Write Tests
- Add tests for currency conversion accuracy
- Test bulk discounts with currency conversion
- Test edge cases (rounding differences, missing rates)

## 12. Documentation
- Document the currency model and exchange rate management
- Document how to add new currencies
- Document the impact on existing functionality