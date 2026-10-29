# Multi-Currency Support Plan

## Overview
Add support for multiple currencies in the shop system, allowing different regions to use their local currency while maintaining consistent pricing logic.

## Steps

1. **Define Currency Constants**
   - Add a `CURRENCIES` dictionary mapping currency codes (e.g., "USD", "EUR", "GBP") to symbols and exchange rates against a base currency (USD)
   - Store default currency setting in configuration

2. **Update Inventory Model**
   - Modify `Inventory.add()` to accept an optional `currency` parameter for each item
   - Update `Inventory.get()` to return items with currency information
   - Add method to get the current currency of an item

3. **Update Pricing Module**
   - Modify `pricing.py` to work with currency-aware prices
   - Add function to convert prices between currencies using exchange rates
   - Update `bulk_price()` and `line_total()` to handle currency conversion if needed

4. **Update Cart Model**
   - Modify `Cart` to track the currency of each line item
   - Update `total()` to sum up totals in a consistent currency (convert all to base currency, then convert back)
   - Add method to get total in a specific currency

5. **Update CLI and Reports**
   - Modify `report.py` to handle multi-currency orders
   - Update `cli.py` to display prices with appropriate currency symbols
   - Add option to specify output currency for reports

6. **Add Currency Conversion Logic**
   - Implement exchange rate management (static rates or dynamic API)
   - Add caching mechanism for exchange rates to avoid repeated lookups

7. **Update Tests**
   - Add test cases for multi-currency scenarios
   - Verify price calculations work correctly across different currencies
   - Test currency conversion accuracy

8. **Documentation**
   - Document the currency system in code comments
   - Create a README section explaining how to use multi-currency features