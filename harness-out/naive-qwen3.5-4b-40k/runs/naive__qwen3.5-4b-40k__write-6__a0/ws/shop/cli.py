"""Command line: `python -m shop.cli summary orders.json`."""
import sys
import argparse

from shop import report, storage


def main(argv=None):
    parser = argparse.ArgumentParser(description="Shop CLI")
    
    # summary command
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    summary_parser = subparsers.add_parser("summary", help="Show order summary")
    summary_parser.add_argument("orders_file", help="Path to orders JSON file")
    
    export_parser = subparsers.add_parser("export", help="Export orders to CSV")
    export_parser.add_argument("--region", "-r", dest="region", metavar="R", help="Filter by region")
    export_parser.add_argument("output_file", help="Path to output CSV file")
    
    args = parser.parse_args(argv)
    
    if args.command == "summary":
        return _run_summary(args)
    elif args.command == "export":
        return _run_export(args)
    else:
        print("usage: shop.cli <command> [args]", file=sys.stderr)
        return 2


def _run_summary(args):
    try:
        orders = storage.load_orders(args.orders_file)
    except FileNotFoundError:
        print(f"no such file: {args.orders_file}", file=sys.stderr)
        return 1
    s = report.summary(orders)
    print(f"{s['count']} orders, revenue {s['revenue']:.2f}")
    return 0


def _run_export(args):
    try:
        orders = storage.load_orders(args.orders_file)
    except FileNotFoundError:
        print(f"no such file: {args.orders_file}", file=sys.stderr)
        return 1
    
    count = report.export(orders, args.output_file, args.region)
    print(f"Wrote {count} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
