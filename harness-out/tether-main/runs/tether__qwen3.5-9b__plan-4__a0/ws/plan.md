# Multi-Currency Support Plan

## 1. Define Currency Configuration
- Create a `currency.py` module to handle currency definitions
- Define supported currencies (USD, EUR, GBP, etc.) with their symbols and decimal places
- Establish a default base currency for the shop (e.g., USD)

## 2. Implement Exchange Rate Management
- Create a mechanism to store exchange rates relative to the base currency
- Decide on rate source: manual configuration file, API integration, or both
- Implement rate update functionality (daily updates, manual override)

## 3. Modify Inventory to Support Multiple Currencies
- Add currency field to inventory items
- Decide: store prices in base currency only, or store in multiple currencies
- Update `inventory.py` to handle currency-aware pricing

## 4. Update Pricing Module
- Modify `pricing.py` to accept currency parameter
- Implement currency conversion in price calculations
- Ensure bulk discount logic works correctly across currencies

## 5. Update Cart Module
- Add currency selection to Cart class
- Convert cart total to user's preferred currency
- Ensure line items display in correct currency

## 6. Add User Currency Preference
- Create user profile or session storage for currency preference
- Decide storage mechanism: JSON file, database, or session-based
- Implement currency preference retrieval in cart operations

## 7. Update Order Storage and Reporting
- Modify order structure to include currency field
- Update `storage.py` to handle currency-aware order data
- Modify `report.py` to handle multi-currency revenue calculations
- Decide: report in base currency or allow currency selection

## 8. Update CLI Interface
- Add currency selection option to CLI commands
- Update `cli.py` to pass currency context through the system
- Ensure summary reports show currency information

## 9. Update Tests
- Add currency conversion test cases
- Test bulk pricing across different currencies
- Verify rounding behavior for different currency decimal places
- Test exchange rate edge cases

## 10. Documentation
- Document supported currencies and their properties
- Document exchange rate update procedures
- Document user-facing currency selection process
- Document API changes for external integrations

## Open Decisions to Make:
1. **Price Storage Strategy**: Store prices in base currency only vs. store in multiple currencies
   - Recommendation: Store in base currency only for consistency, convert on display
   
2. **Exchange Rate Source**: Manual file vs. API vs. hybrid
   - Recommendation: Start with manual file, add API later if needed
   
3. **User Preference Storage**: Session-based vs. persistent
   - Recommendation: Session-based for simplicity, persistent for logged-in users
   
4. **Order Currency**: Store in user's currency or base currency
   - Recommendation: Store in base currency for accounting, display in user's currency
   
5. **Rounding Rules**: Different currencies have different decimal places
   - Recommendation: Use standard 2 decimal places for all, or implement currency-specific rounding
   
6. **Rate Update Frequency**: Real-time vs. daily batch
   - Recommendation: Daily batch updates with manual override capability