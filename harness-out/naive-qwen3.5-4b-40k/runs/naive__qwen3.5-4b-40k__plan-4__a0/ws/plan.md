# Multi-Currency Support Plan for Shop

## Decisions Made
- **Base Currency**: All inventory prices will be stored in a base currency (default USD)
- **Conversion Rates**: Exchange rates will be fetched from an external API on each transaction
- **User Selection**: Users can select their preferred currency via CLI argument or store preference
- **Order Storage**: Orders will include both the original price and converted amount for the selected currency
- **Display Currency**: The `money()` utility will support multiple currency symbols

## Steps

1. **Add currency field to inventory items**
   - Modify `Inventory.add()` to accept an optional `currency` parameter (default: "USD")
   - Store currency alongside price in each item record

2. **Create currency conversion service**
   - Add a new module `shop/currency.py` with exchange rate functions
   - Implement `get_exchange_rate(from_currency, to_currency)` function
   - Cache rates for performance (TTL-based or file-based)

3. **Update pricing calculations**
   - Modify `bulk_price()` in `pricing.py` to accept an optional currency parameter
   - Add currency conversion step: convert base price to target currency before applying bulk discount
   - Store both original and converted prices in order records

4. **Add CLI argument for currency selection**
   - Update `cli.py` to accept a `--currency` flag (default: "USD")
   - Pass selected currency through the entire pipeline

5. **Modify Cart class**
   - Add `currency` parameter to `Cart.__init__()` with default "USD"
   - Store currency in each cart line item
   - Update `total()` to convert to selected currency before returning

6. **Update order structure**
   - Add `currency` field to orders (store original transaction currency)
   - Add `converted_total` field showing amount in user's preferred currency
   - Modify `report.py` functions to handle multi-currency data

7. **Enhance money formatting**
   - Update `utils.money()` to accept optional `currency` parameter
   - Support common currencies: USD, EUR, GBP, JPY, CAD, AUD

8. **Add currency selector UI (optional)**
   - Consider adding a simple prompt or menu for users who don't use CLI
   - Store user's preferred currency in their order history

9. **Test multi-currency scenarios**
   - Create test cases with different currencies and exchange rates
   - Verify bulk discount calculations work correctly across currencies
   - Test edge cases: zero exchange rate, unsupported currency, etc.

10. **Documentation**
    - Document supported currencies and their symbols
    - Add notes about how to add new currencies (requires updating `money()` function)
    - Explain the conversion rate caching mechanism
