"""Command line: `python -m shop.cli summary orders.json`."""
import sys

from shop import report, storage


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
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


if __name__ == "__main__":
    sys.exit(main())
