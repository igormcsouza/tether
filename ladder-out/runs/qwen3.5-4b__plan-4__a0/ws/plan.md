# Multi-Currency Support Plan

1. Define a Currency class or type to represent currency codes (e.g., USD, EUR, GBP) and handle currency operations
2. Add an exchange rate mechanism to convert between currencies (store base rates relative to a reference currency like USD)
3. Modify Inventory.add() to accept a currency parameter for each item's price
4. Modify Inventory.get() to return items with their associated currency information
5. Modify Cart.__init__() to accept and store a default currency
6. Add a method to set/change the cart's currency (Cart.set_currency())
7. Update Cart.total() to convert all prices to the cart's currency before calculating the total
8. Optionally add a method to get item price in a specific currency (Cart.get_item_price(sku, currency))
9. Write tests for currency conversion and multi-currency cart operations