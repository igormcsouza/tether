1. Create a `Customer` class in `shop/customer.py` with fields for `id`, `name`, and `discount_percent` (default 0). The class should have methods to create, get, and update customer records.

2. Modify `shop/cart.py` to accept an optional `customer` parameter in the `__init__` method. Update the `total()` method to apply the customer's discount percentage to the cart total before returning it.

3. Create a new `shop/order.py` module with an `Order` class that stores order details including `id`, `date`, `region`, `customer_id`, and `discount_percent`. The order should also store the line items and calculate the final total with discount applied.

4. Update `shop/storage.py` to add functions for saving and loading orders that include customer information, ensuring the JSON structure supports the new fields.

5. Modify `shop/report.py` to update both `summary()` and `monthly()` functions to handle orders with customer discounts, displaying the discount percentage in the reports.

6. Add a `customer` parameter to the `Cart.__init__()` method that accepts a Customer object or None.

7. Update the `Cart.total()` method to apply the customer's discount: if a customer exists, multiply the total by (1 - discount_percent/100) before rounding and returning.

8. Create an `Order` class in `shop/order.py` with fields for `id`, `date`, `region`, `customer_id`, `discount_percent`, `lines`, and `total`. Include a method to create an order from cart data that applies the customer discount.

9. Update `storage.save_orders()` to serialize orders with all new fields including customer information and discount percentages.

10. Modify `report.summary()` to include customer discount information in its output, showing the total count of orders and revenue while optionally displaying discount details.

11. Update `report.monthly()` to handle orders with customer discounts, aggregating revenue correctly regardless of discount applied per order.

12. Ensure all existing tests continue to pass by verifying that default behavior (no customer/discount) remains unchanged when a Customer object is None.
