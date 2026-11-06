"""Draft prices for the 2026-11-06 test project (Claude working tool).

Usage: python -I tools/claude/price_boards_2etazh.py <out.json>
Uses the governed sources of this branch (catalogue cabinet bridge, CHINT
January table, canonical price formula). NOT the governed Case chain: no
Human Approval or Case artifact. Result for 463-1: 209553 / 111362 / 103668x3.
"""

import json
import sys
from decimal import Decimal as D
from pathlib import Path

sys.path.insert(0, r"C:\Users\IgorN\projects\my_project_claude\scripts")
import future_case_hardening as f
from calc_quote_price_draft import canonical_material_work_price
from openpyxl import load_workbook
from price_baseline_contract import resolve_active_price_baseline, sha256_file

src = f.BRAND_PRICE_SOURCES["CHINT"]
assert sha256_file(Path(src["path"])) == src["sha256"]
jan = load_workbook(src["path"], read_only=True, data_only=False)
base = resolve_active_price_baseline(
    Path(
        r"C:\Users\IgorN\Documents\invoice_quote_filler_data\prices\active-price-baseline.json"
    )
)
main = load_workbook(base.path, read_only=True, data_only=False)


def row(cat):
    sheet, r, label = f.CATEGORIES[cat]
    ws = jan[sheet]
    assert " ".join(str(ws.cell(r, 1).value).split()) == label, cat
    return D(str(ws.cell(r, 2).value)), D(str(ws.cell(r, 3).value)), f"{sheet}!{r}"


boards = [
    (
        "ЩО6",
        1,
        {
            "family": "METAL",
            "row": 37,
            "label": "800х600х250 ",
            "code": "CATALOGUE-METAL-ROW-37",
        },
        [("MCCB SHR 3P 16-63A", 1), ("RCBO 1P+N 30mA <=63A", 20)],
    ),
    (
        "НЩР",
        1,
        {
            "family": "KRN",
            "row": 64,
            "label": "Корпус КРН-36 540х330х100 ",
            "code": "CATALOGUE-KRN-ROW-64",
        },
        [("SWITCH 3P 16-100A", 1), ("RCBO 1P+N 30mA <=63A", 12)],
    ),
    (
        "АВР",
        3,
        {
            "family": "KRN",
            "row": 64,
            "label": "Корпус КРН-36 540х330х100 ",
            "code": "CATALOGUE-KRN-ROW-64",
        },
        [("SWITCH 3P 16-100A", 1), ("RCBO 1P+N 30mA <=63A", 11)],
    ),
]
K = f.K_BY_FAMILY["ЩР"]
out = []
for name, qty, cab, bom in boards:
    item = {"cabinet": {"cabinet_code": cab["code"], "cabinet_label": cab["label"]}}
    c = f.catalogue_enclosure_cost(
        main, base, {"enclosure_mm": None}, item, cab["family"], cab["row"]
    )
    cost = D(str(c["cost_kzt"]))
    mat = sum(row(cat)[0] * n for cat, n in bom)
    work = sum(row(cat)[1] * n for cat, n in bom)
    unit = canonical_material_work_price(cost, mat, work, K)
    out.append(
        {
            "name": name,
            "qty": qty,
            "cabinet_cost": str(cost),
            "material": str(mat),
            "work": str(work),
            "K": str(K),
            "unit": unit,
            "sum": unit * qty,
            "rows": [
                [cat, n, str(row(cat)[0]), str(row(cat)[1]), row(cat)[2]]
                for cat, n in bom
            ],
            "cabinet_locator": c.get("source_locator"),
        }
    )
assert sha256_file(Path(src["path"])) == src["sha256"]
json.dump(out, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for o in out:
    print(
        o["name"],
        o["qty"],
        o["cabinet_cost"],
        o["material"],
        o["work"],
        o["unit"],
        o["sum"],
    )
print("TOTAL", sum(o["sum"] for o in out))
