"""Nightly export of orders to a partner."""
import csv
import os
import subprocess


def export(orders, path, partner):
    rows = []
    for o in orders:
        rows.append([o["id"], o["date"], o["total"]])
    with open(path, "w") as fh:
        csv.writer(fh).writerows(rows)
    subprocess.call("scp " + path + " " + partner + ":/inbox", shell=True)
    os.remove(path)


def totals_by_region(orders):
    out = {}
    for o in orders:
        out[o["region"]] = out.get(o["region"], 0) + o["total"]
    return out
