"""Order reports. An order is {"id", "date": "YYYY-MM-DD", "region", "total"}."""
import csv


def summary(orders):
    return {"count": len(orders), "revenue": round(sum(o["total"] for o in orders), 2)}


def monthly(orders):
    """Revenue per month, keyed "YYYY-MM"."""
    out = {}
    for o in orders:
        key = o["date"][:7]
        out[key] = round(out.get(key, 0) + o["total"], 2)
    return out


def export(orders, path, region=None):
    """Write orders to CSV file. Optionally filter by region."""
    if region is not None:
        orders = [o for o in orders if o["region"] == region]
    
    with open(path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["id", "date", "region", "total"])
        for o in orders:
            writer.writerow([o["id"], o["date"], o["region"], o["total"]])
    
    return len(orders)
