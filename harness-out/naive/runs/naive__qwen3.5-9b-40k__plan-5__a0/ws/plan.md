# Plan: Customer Accounts with Per-Customer Discounts

## Overview
Add customer account support with per-customer discounts that apply in the cart, are saved with each order, and show up in reports.

## Step 1: Create Customer Storage Module
- Create `shop/customer.py` with `Customer` class
- Store customer ID, name, and discount percentage
- Add `load_customers(path)` and `save_customers(path, customers)` functions
- Add `get_customer(customer_id)` and `create_customer(customer_id, name, discount)` functions

## Step 2: Modify Cart to Support Customer Discounts
- Modify `shop/cart.py` to accept an optional `customer_id` parameter in `__init__`
- Add `customer_discount` attribute to Cart class
- Modify `total()` method to apply customer discount percentage to the subtotal before bulk pricing
- Keep existing bulk pricing logic intact

## Step 3: Create Order Module
- Create `shop/order.py` with `Order` class
- Store order id, date, region, customer_id, and total
- Add `create_order(cart, customer_id, region)` function that returns an order dict

## Step 4: Update Storage to Include Customer Data
- Modify `shop/storage.py` to save customer data alongside orders
- Add `save_customer(customer_id, customer_data)` function
- Add `load_customer(customer_id)` function
- Update `save_orders()` to optionally save customer info with each order

## Step 5: Update Reports to Include Customer Data
- Modify `shop/report.py` to include customer info in order data
- Update `summary()` to optionally include customer breakdown
- Update `monthly()` to optionally include customer breakdown
- Add `customer_summary(orders)` function to show revenue per customer

## Step 6: Add CLI for Customer Management
- Modify `shop/cli.py` to add customer management commands
- Add `customer create <id> <name> <discount>` command
- Add `customer list` command
- Add `customer show <id>` command

## Step 7: Add Tests for Customer Module
- Create `tests/test_customer.py`
- Test `load_customers`, `save_customers`, `get_customer`, `create_customer`
- Test customer data persistence

## Step 8: Add Tests for Cart with Customer Discounts
- Modify `tests/test_cart.py` to test customer discount application
- Test that customer discount applies correctly to cart total
- Test that bulk pricing still works with customer discount

## Step 9: Add Tests for Order Module
- Create `tests/test_order.py`
- Test `create_order` returns correct order dict
- Test order includes customer_id

## Step 10: Add Tests for Reports with Customer Data
- Modify `tests/test_report.py` to test customer breakdown
- Test `customer_summary()` returns correct revenue per customer
- Test monthly reports with customer data

## Step 11: Add Tests for Storage with Customer Data
- Modify `tests/test_storage.py` (or create new file)
- Test customer data persistence
- Test loading customer data from orders

## Step 12: Run Full Test Suite
- Run `python3 -m pytest tests/ -v`
- Verify all tests pass
- If any fail, debug and fix

## Implementation Order (to keep suite green at each step)
1. Step 1: Customer storage (no other code depends on it)
2. Step 7: Tests for customer storage
3. Step 2: Cart with customer discount
4. Step 8: Tests for cart with customer discount
5. Step 3: Order module
6. Step 9: Tests for order module
7. Step 4: Storage updates for customer data
8. Step 11: Tests for storage with customer data
9. Step 5: Report updates
10. Step 10: Tests for reports with customer data
11. Step 6: CLI updates
12. Step 12: Final test suite verification
