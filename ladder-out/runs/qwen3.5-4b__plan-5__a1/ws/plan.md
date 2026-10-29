# Plan: Add Per-Customer Discounts

## Overview
Implement per-customer discounts that apply in the cart, are saved with each order, and show up in reports. This plan keeps the suite green at every step by introducing new files/structures where needed rather than modifying existing code.

## Step-by-Step Plan

1. **Create customer data structure** (`shop/customer.py`)
   - Define `Customer` class with fields: id, name, discount_rate (default 0)
   - Add methods to get/set/update customer discounts

2. **Update storage module** (`shop/storage.py`)
   - Add `load_customer()` function to load a customer from JSON
   - Add `save_customer()` function to persist customer data
   - Modify `load_orders()` to include customer ID in order records
   - Add `save_order()` to store customer reference with each order

3. **Update cart module** (`shop/cart.py`)
   - Accept optional `customer_id` parameter in constructor
   - Load customer discount rate if provided
   - Apply customer-specific discount when calculating totals
   - Update `total()` method to apply per-customer discount

4. **Update pricing module** (`shop/pricing.py`)
   - Add `apply_discount(unit_price, quantity, discount_rate)` function
   - Modify `bulk_price()` to accept optional discount rate parameter
   - Ensure backward compatibility (default 0% discount)

5. **Update report module** (`shop/report.py`)
   - Modify `summary()` to include total discounts given
   - Add `discount_summary()` function for per-customer breakdown
   - Update `monthly()` to show discounts by month

6. **Create test file** (`tests/test_customer.py`)
   - Test customer data structure operations
   - Test discount application in cart
   - Test order storage with customer info
   - Test report functions with discount data

7. **Run tests**
   - Execute `python -m pytest` to verify all tests pass
   - Fix any issues that arise (should be minimal due to backward-compatible design)

8. **Verify integration**
   - Test CLI command with customer orders
   - Confirm discounts appear in summary and monthly reports
   - Ensure existing functionality remains unchanged