"""Command line: `python -m shop.cli summary|export ORDERS.json`."""
import csv
import sys

from shop import report, storage


def summary_command(argv):
    """Export orders to CSV with optional region filter.
    
    usage: shop.cli export ORDERS.json OUT.csv [--region R]
    """
    if len(argv) < 2 or argv[0] != "export":
        print("usage: shop.cli export ORDERS.json OUT.csv [--region R]", file=sys.stderr)
        return 2
    
    output_path = argv[1]
    region = None
    idx = 2
    
    # Parse optional --region flag
    while idx < len(argv):
        if argv[idx] == "--region" and idx + 1 < len(argv):
            region = argv[idx + 1]
            idx += 2
        else:
            print(f"unknown flag: {argv[idx]}", file=sys.stderr)
            return 2
    
    # Validate input file
    if len(argv) < 3:
        print("usage: shop.cli export ORDERS.json OUT.csv [--region R]", file=sys.stderr)
        return 2
    
    try:
        orders = storage.load_orders(argv[1])
    except FileNotFoundError:
        print(f"no such file: {argv[1]}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"cannot read orders: {e}", file=sys.stderr)
        return 1
    
    # Filter by region if specified
    if region is not None:
        orders = [o for o in orders if o.get("region") == region]
    
    # Write to CSV
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=orders[0].keys() if orders else [])
        writer.writeheader()
        writer.writerows(orders)
    
    print(len(orders))
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) == 0:
        print("usage: shop.cli summary|export ORDERS.json", file=sys.stderr)
        return 2
    
    cmd = argv[0]
    if cmd == "summary":
        if len(argv) != 2:
            print("usage: shop.cli summary ORDERS.json", file=sys.stderr)
            return 2
        try:
            orders = storage.load_orders(argv[1])
        except FileNotFoundError:
            print(f"no such file: {argv[1]}", file=sys.stderr)
            return 1
        s = report.summary(orders)
        print(f"{s['count']} orders, revenue {s['revenue']:.2f}")
        return 0
    elif cmd == "export":
        return summary_command(argv)
    else:
        print(f"unknown command: {cmd}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
