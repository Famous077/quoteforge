"""Rectangular part nesting on a standard sheet. Standard library only (runs in the TrueForge sandbox).

Run: python3 nesting.py 200 100 50   ->  JSON for a 200 x 100 mm part, qty 50
"""

import json
import math
import sys

SHEET_W_MM = 1250
SHEET_L_MM = 2500


def nest(length_mm: float, width_mm: float, qty: int, sheet_w_mm: float = SHEET_W_MM, sheet_l_mm: float = SHEET_L_MM) -> dict:
    """Grid-nest one part size, trying both orientations, and report sheets needed and real scrap."""
    as_given = math.floor(sheet_w_mm / length_mm) * math.floor(sheet_l_mm / width_mm)
    rotated = math.floor(sheet_w_mm / width_mm) * math.floor(sheet_l_mm / length_mm)
    parts_per_sheet = max(as_given, rotated)
    if parts_per_sheet == 0:
        raise ValueError(f"Part {length_mm} x {width_mm} mm does not fit a {sheet_w_mm} x {sheet_l_mm} mm sheet")

    sheets_needed = math.ceil(qty / parts_per_sheet)
    used_area = qty * length_mm * width_mm
    sheet_area = sheets_needed * sheet_w_mm * sheet_l_mm
    return {
        "sheet_mm": [sheet_w_mm, sheet_l_mm],
        "parts_per_sheet": parts_per_sheet,
        "orientation": "as_given" if as_given >= rotated else "rotated",
        "sheets_needed": sheets_needed,
        "scrap_pct": round((1 - used_area / sheet_area) * 100, 2),
    }


if __name__ == "__main__":
    length, width, qty = float(sys.argv[1]), float(sys.argv[2]), int(sys.argv[3])
    print(json.dumps(nest(length, width, qty), indent=2))
