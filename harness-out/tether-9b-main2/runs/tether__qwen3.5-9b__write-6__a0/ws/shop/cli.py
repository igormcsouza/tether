"""Command line: `python -m shop.cli summary orders.json`."""
import sys
import csv

from shop import report, storage


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    
    if len(argv) < 2:
        print("usage: shop.cli summary ORDERS.json", file=sys.stderr)
        print("       shop.cli export ORDERS.json OUT.csv [--region R]", file=sys.stderr)
        return 2
    
    command = argv[0]
    
    if command == "summary":
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
    
    elif command == "export":
        # Parse --region flag
        region = None
        i = 1
        while i < len(argv):
            if argv[i] == "--region" and i + 1 < len(argv):
                region = argv[i + 1]
                i += 2
            else:
                i += 1
        
        # Filter orders by region if specified
        if region:
            orders = [o for o in orders if o.get("region") == region]
        
        if len(argv) < 3:
            print("usage: shop.cli export ORDERS.json OUT.csv [--region R]", file=sys.stderr)
            return 2
        
        orders_file = argv[1]
        out_file = argv[2]
        
        try:
            orders = storage.load_orders(orders_file)
        except FileNotFoundError:
            print(f"no such file: {orders_file}", file=sys.stderr)
            return 1
        
        # Write CSV
        with open(out_file, "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=["id", "date", "region", "total"])
            writer.writeheader()
            for order in orders:
                writer.writerow(order)
        
        print(len(orders))
        return 0
    
    else:
        print(f"unknown command: {command}", file=sys.stderr)
        print("usage: shop.cli summary ORDERS.json", file=sys.stderr)
        print("       shop.cli export ORDERS.json OUT.csv [--region R]", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())