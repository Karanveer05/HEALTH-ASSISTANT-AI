"""Optional: build the offline medicine price list used when live pharmacy lookups fail.

Usage (from backend/):
    .venv\\Scripts\\python scripts\\import_prices.py path\\to\\medicines.csv [--as-of "Nov 2022"]

Accepts any CSV that has a medicine name column and a price column (for example the Kaggle
"A-Z Medicine Dataset of India": name, price(₹), pack_size_label, short_composition1).
Writes storage/medicine_prices.csv with columns: name, composition, pack, price, as_of.
"""
import argparse
import csv
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "storage" / "medicine_prices.csv"
NAME_COLS = ("name", "medicine_name", "product_name", "brand")
PRICE_COLS = ("price(₹)", "price", "mrp", "price (rs)")
PACK_COLS = ("pack_size_label", "pack", "pack_size", "packsize")
COMP_COLS = ("short_composition1", "composition", "salt", "short_composition")


def pick(header, options):
    low = {h.lower().strip(): h for h in header}
    return next((low[o] for o in options if o in low), None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--as-of", default="dataset")
    args = ap.parse_args()
    with open(args.csv, encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.DictReader(f)
        name_c, price_c = pick(reader.fieldnames, NAME_COLS), pick(reader.fieldnames, PRICE_COLS)
        pack_c, comp_c = pick(reader.fieldnames, PACK_COLS), pick(reader.fieldnames, COMP_COLS)
        if not name_c or not price_c:
            sys.exit(f"Need a name and a price column; found {reader.fieldnames}")
        n = 0
        with OUT.open("w", encoding="utf-8", newline="") as out:
            w = csv.writer(out)
            w.writerow(["name", "composition", "pack", "price", "as_of"])
            for row in reader:
                try:
                    price = float(str(row[price_c]).replace(",", "").replace("₹", "").strip())
                except ValueError:
                    continue
                w.writerow([row[name_c].strip(), (row.get(comp_c) or "").strip(), (row.get(pack_c) or "").strip(), price, args.as_of])
                n += 1
    print(f"Wrote {n} rows to {OUT}")


if __name__ == "__main__":
    main()
