"""Command line: `python -m shop.cli summary orders.json`."""
import sys

from shop import report, storage


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    
    print(f"DEBUG: argv={argv}")  # Debug output
    
    if argv[0] == "export":
        return export_command(argv)
    
    if len(argv) != 2 or argv[0] != "summary":
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


def export_command(argv):
    """Export orders to CSV with optional region filter."""
    print(f"DEBUG: export_command argv={argv}")  # Debug output
    
    if len(argv) < 3:
        print("usage: shop.cli export ORDERS.json OUT.csv [--region R]", file=sys.stderr)
        return 1
    
    try:
        orders = storage.load_orders(argv[1])
    except FileNotFoundError:
        print(f"no such file: {argv[1]}", file=sys.stderr)
        return 1
    
    # Find the region filter argument
    i = 2
    region_filter = None
    while i < len(argv):
        print(f"DEBUG: checking argv[{i}]={argv[i]}")
        if argv[i] == "--region":
            if i + 1 >= len(argv):
                print("usage: shop.cli export ORDERS.json OUT.csv [--region R]", file=sys.stderr)
                return 1
            region_filter = argv[i + 1]
            i += 2
        else:
            i += 1
    
    # Filter orders by region if specified
    filtered_orders = orders
    if region_filter is not None:
        filtered_orders = [o for o in orders if o.get("region") == region_filter]
    
    # Write CSV
    with open(argv[2], "w") as fh:
        # Write header
        fh.write("id,date,region,total\n")
        # Write data rows
        for o in filtered_orders:
            date = o["date"]
            region = o["region"]
            total = o["total"]
            # Format total to 2 decimal places if it's a float
            if isinstance(total, float):
                total = f"{total:.2f}"
            fh.write(f"{o['id']},{date},{region},{total}\n")
    
    print(f"Wrote {len(filtered_orders)} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())