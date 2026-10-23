import csv
from datetime import date
from decimal import Decimal


def parse_rows(lines):
    """Parse CSV lines 'date,account,amount,memo' (header row optional) into dicts."""
    rows = []
    for rec in csv.reader(lines):
        if not rec or rec[0] == "date":
            continue
        d, account, amount, memo = rec[0], rec[1], rec[2], rec[3] if len(rec) > 3 else ""
        rows.append({"date": date.fromisoformat(d), "account": account, "amount": Decimal(amount), "memo": memo})
    return rows
