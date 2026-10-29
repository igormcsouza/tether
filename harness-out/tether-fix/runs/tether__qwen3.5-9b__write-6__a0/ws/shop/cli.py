"""Command line: `python -m shop.cli summary orders.json`."""
import sys
import csv
import argparse

from shop import report, storage


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    
    if len(argv) == 0:
        print("usage: shop.cli summary ORDERS.json", file=sys.stderr)
        print("       shop.cli export ORDERS.json [OUT.csv] [--region R]", file=sys.stderr)
        return 2
    
    if argv[0] == "summary":
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
    
    elif argv[0] == "export":
        if len(argv) < 2:
            print("usage: shop.cli export ORDERS.json [OUT.csv] [--region R]", file=sys.stderr)
            return 2
        
        orders_path = argv[1]
        out_path = argv[2] if len(argv) > 2 else "orders.csv"
        
        # Parse optional --region flag
        region_filter = None
        i = 2
        while i < len(argv):
            if argv[i] == "--region" and i + 1 < len(argv):
                region_filter = argv[i + 1]
                i += 2
            else:
                i += 1
        
        try:
            orders = storage.load_orders(orders_path)
        except FileNotFoundError:
            print(f"no such file: {orders_path}", file=sys.stderr)
            return 1
        
        # Apply region filter if specified
        if region_filter:
            orders = [o for o in orders if o.get("region") == region_filter]
        
        # Write CSV
        with open(out_path, "w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["id", "date", "region", "total"])
            for o in orders:
                writer.writerow([o["id"], o["date"], o["region"], o["total"]])
        
        print(len(orders))
        return 0
    
    else:
        print(f"unknown command: {argv[0]}", file=sys.stderr)
        print("usage: shop.cli summary ORDERS.json", file=sys.stderr)
        print("       shop.cli export ORDERS.json [OUT.csv] [--region R]", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())