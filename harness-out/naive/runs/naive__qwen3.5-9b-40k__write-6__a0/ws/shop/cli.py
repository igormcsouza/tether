"""Command line: `python -m shop.cli summary orders.json`."""
import sys
import csv

from shop import report, storage


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    
    if len(argv) < 2:
        print("usage: shop.cli export ORDERS.json OUT.csv [--region R]", file=sys.stderr)
        return 2
    
    # Check for export command
    if argv[0] != "export":
        print("usage: shop.cli export ORDERS.json OUT.csv [--region R]", file=sys.stderr)
        return 2
    
    orders_file = argv[1]
    output_file = argv[2]
    region_filter = None
    i = 3
    
    # Parse optional --region argument
    while i < len(argv):
        if argv[i] == "--region" and i + 1 < len(argv):
            region_filter = argv[i + 1]
            i += 2
        elif argv[i] == "-R" and i + 1 < len(argv):
            region_filter = argv[i + 1]
            i += 2
        else:
            i += 1
    
    try:
        orders = storage.load_orders(orders_file)
    except FileNotFoundError:
        print(f"no such file: {orders_file}", file=sys.stderr)
        return 1
    
    # Filter by region if specified
    if region_filter:
        orders = [o for o in orders if o.get("region") == region_filter]
    
    # Write CSV
    with open(output_file, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["id", "date", "region", "total"])
        for order in orders:
            writer.writerow([order["id"], order["date"], order["region"], order["total"]])
    
    print(f"Exported {len(orders)} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
