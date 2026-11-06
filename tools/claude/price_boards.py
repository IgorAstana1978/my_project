"""Draft board prices for any project (Claude working tool).

Usage: python -I tools/claude/price_boards.py <boards.json> <out.json>

`boards.json` is a list of boards:
    {"name": "ЩС-49", "qty": 1,
     "cabinet": {"family": "METAL", "row": 35, "label": "700х500х250 ",
                 "code": "CATALOGUE-METAL-ROW-35"},
     "bom": [["MCCB 3P 80-100A", 1], ["MCB 3P D 10-63A", 6]]}
Categories are the keys of `future_case_hardening.CATEGORIES` (CHINT January
table); cabinet rows/labels are the price catalogue rows (КРН 60-72, METAL
8-56). Same sources and canonical formula as price_boards_2etazh.py.
NOT the governed Case chain: no Human Approval or Case artifact.
"""

import json
import sys
from decimal import Decimal as D
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import future_case_hardening as f  # noqa: E402
from calc_quote_price_draft import canonical_material_work_price  # noqa: E402
from openpyxl import load_workbook  # noqa: E402
from price_baseline_contract import (  # noqa: E402
    resolve_active_price_baseline,
    sha256_file,
)

src = f.BRAND_PRICE_SOURCES["CHINT"]
assert sha256_file(Path(src["path"])) == src["sha256"]
jan = load_workbook(src["path"], read_only=True, data_only=False)
base = resolve_active_price_baseline(
    Path(
        r"C:\Users\IgorN\Documents\invoice_quote_filler_data\prices"
        r"\active-price-baseline.json"
    )
)
main = load_workbook(base.path, read_only=True, data_only=False)


def row(cat):
    sheet, r, label = f.CATEGORIES[cat]
    ws = jan[sheet]
    assert " ".join(str(ws.cell(r, 1).value).split()) == label, cat
    return D(str(ws.cell(r, 2).value)), D(str(ws.cell(r, 3).value)), f"{sheet}!{r}"


boards = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
K = f.K_BY_FAMILY["ЩР"]
out = []
for board in boards:
    cab = board["cabinet"]
    item = {"cabinet": {"cabinet_code": cab["code"], "cabinet_label": cab["label"]}}
    c = f.catalogue_enclosure_cost(
        main, base, {"enclosure_mm": None}, item, cab["family"], cab["row"]
    )
    cost = D(str(c["cost_kzt"]))
    bom = board["bom"]
    mat = sum(row(cat)[0] * n for cat, n in bom)
    work = sum(row(cat)[1] * n for cat, n in bom)
    unit = canonical_material_work_price(cost, mat, work, K)
    out.append(
        {
            "name": board["name"],
            "qty": board["qty"],
            "cabinet": cab["label"].strip(),
            "cabinet_cost": str(cost),
            "material": str(mat),
            "work": str(work),
            "K": str(K),
            "unit": unit,
            "sum": unit * board["qty"],
            "rows": [
                [cat, n, str(row(cat)[0]), str(row(cat)[1]), row(cat)[2]]
                for cat, n in bom
            ],
            "cabinet_locator": c.get("source_locator"),
        }
    )
assert sha256_file(Path(src["path"])) == src["sha256"]
Path(sys.argv[2]).write_text(
    json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8"
)
for o in out:
    print(o["name"], o["qty"], o["cabinet"], o["cabinet_cost"], o["unit"], o["sum"])
print("TOTAL", sum(o["sum"] for o in out))
