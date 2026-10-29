# Plan: Customer Accounts with Per-Customer Discounts

## Overview
Implement customer accounts with per-customer discounts that apply in the cart, are saved with each order, and show up in reports.

## Steps

1. **Create Customer Model**
   - Add a `Customer` class to `shop/customer.py`
   - Include fields: `id`, `name`, `email`, `discount_percent` (default 0)
   - Add methods: `create()`, `get_by_id()`, `update()`

2. **Add Customer to Cart**
   - Modify `shop/cart.py` to accept a customer parameter
   - Store customer reference in cart instance
   - Apply per-customer discount in `Cart.total()` method
   - Discount formula: `unit_price * quantity * (1 - discount_percent/100)`

3. **Add Customer to Order**
   - Modify `shop/order.py` (create if needed) to include customer reference
   - Order structure: `{"id", "date", "region", "customer_id", "total"}`
   - Save customer_id with each order in `shop/storage.py`

4. **Update Reports to Include Customer Data**
   - Modify `shop/report.py` to include customer information
   - Add `customer_summary()` function showing revenue per customer
   - Add `customer_discounts()` function showing discount totals per customer
   - Update `summary()` to optionally include customer breakdown

5. **Add Tests for Customer Model**
   - Create `tests/test_customer.py`
   - Test customer creation, retrieval, and discount field

6. **Add Tests for Cart with Discounts**
   - Extend `tests/test_cart.py`
   - Test cart with customer discount applied
   - Test discount calculation accuracy

7. **Add Tests for Order with Customer**
   - Create `tests/test_order.py`
   - Test order includes customer_id
   - Test order total includes discount

8. **Add Tests for Reports with Customer Data**
   - Extend `tests/test_report.py`
   - Test customer summary report
   - Test customer discounts report

9. **Run Full Test Suite**
   - Execute `python -m pytest` or `python -m unittest discover`
   - Verify all tests pass (suite green)

10. **Update CLI for Customer Summary**
    - Modify `shop/cli.py` to support `shop.cli summary-customer ORDERS.json`
    - Display customer breakdown of revenue and discounts

## Implementation Order (to keep suite green)

1. Step 1 (Customer model) - isolated, no dependencies
2. Step 5 (Customer tests) - verify model works
3. Step 2 (Cart with discounts) - depends on customer model
4. Step 6 (Cart tests) - verify discount logic
5. Step 3 (Order with customer) - depends on customer model
6. Step 7 (Order tests) - verify order structure
7. Step 4 (Report updates) - depends on order structure
8. Step 8 (Report tests) - verify report output
9. Step 10 (CLI updates) - final integration
10. Step 9 (Full suite) - final verification