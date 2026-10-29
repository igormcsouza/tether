1. Cart.checkout() is called
2. Cart contents are validated for stock availability
3. If stock is sufficient, an order is created
4. Order data is saved using the storage module
5. Stock is reduced by the quantity of items in the order
6. If stock is insufficient, an error is returned and the order is not created