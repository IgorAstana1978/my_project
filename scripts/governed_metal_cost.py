"""Read-only D52 adapter for the existing manifest/selector contracts.

No materialization or activation entrypoint. Historical D82 resolver is untouched.
"""

from __future__ import annotations

from decimal import ROUND_UP, Decimal
from pathlib import Path
from typing import Any

from future_case_hardening import number, require
from openpyxl import load_workbook
from price_baseline_contract import (
    canonical_json_bytes,
    mapping_identity_fingerprint,
    resolve_active_price_baseline,
    sha256_bytes,
    sha256_file,
    validate_mapping_snapshot,
)

GENESIS_SHA = "b51d7087e0bd8f92e48985294062ead6826c6b50ce3cfacd0f9d0dc22c05f7f2"
GENESIS_PATH = Path(
    r"C:\Users\IgorN\Documents\invoice_quote_filler_data\prices\current"
) / ("прайс_металл_лотки_крышки с 2026.06.18.xlsx")
LABEL = "1700х800х500 ВРУ "
FORMULAS = {
    "D52": "=ROUNDUP((M52+N52)*R52+O52+P52+S52+Q52,0)",
    "H52": "=E52/1000",
    "I52": "=F52/1000",
    "J52": "=G52/1000",
    "K52": "=H52*I52*3+H52*J52*2+I52*J52*2",
    "L52": "=K52*$B$1*8.42",
    "M52": "=L52*$B$2",
    "N52": "=K52*2*0.25*$B$3*1.33",
    "Q52": "=1250",
}
IDENTITY_VALUES = {
    "B1": 1,
    "E52": 1700,
    "F52": 800,
    "G52": 500,
    "O52": 6750,
    "P52": 3500,
    "R52": 1.05,
    "S52": 2000,
}
IDENTITY = {
    "mapping_id": "METAL-VRU-D52-COST",
    "source_role": "ENCLOSURE_COST",
    "sheet": "Лист1",
    "row": 52,
    "label": LABEL,
    "formulas": FORMULAS,
    "identity_values": IDENTITY_VALUES,
    "price_inputs": ["B2", "B3"],
    "excluded_sales_outputs": ["B52", "C52"],
}


def inspect_cost(workbook: Path, expected_sha256: str) -> dict[str, Any]:
    raw_sha = sha256_file(workbook)
    require(raw_sha == expected_sha256, "metal workbook SHA drift")
    book = load_workbook(workbook, read_only=True, data_only=False, keep_links=False)
    try:
        require(book.sheetnames == ["Лист1"], "metal sheet identity drift")
        s = book["Лист1"]
        require(s["A52"].value == LABEL, "metal label identity drift")
        for cell, formula in FORMULAS.items():
            require(s[cell].value == formula, f"metal formula drift: {cell}")
        for cell, value in IDENTITY_VALUES.items():
            require(
                number(s[cell].value) == Decimal(str(value)),
                f"metal identity drift: {cell}",
            )
        metal, paint = number(s["B2"].value), number(s["B3"].value)
        h, w, d = (Decimal(x) / 1000 for x in (1700, 800, 500))
        area = h * w * 3 + h * d * 2 + w * d * 2
        mass = area * Decimal("8.42")
        base = (
            (mass * metal + area * 2 * Decimal("0.25") * paint * Decimal("1.33"))
            * Decimal("1.05")
            + 6750
            + 3500
            + 2000
            + 1250
        ).quantize(Decimal(1), rounding=ROUND_UP)
    finally:
        book.close()
    require(sha256_file(workbook) == raw_sha, "metal changed during resolution")
    entry = {
        "mapping_id": IDENTITY["mapping_id"],
        "mapping_kind": "cabinet_dynamic",
        "identity": IDENTITY,
        "identity_fingerprint": mapping_identity_fingerprint(IDENTITY),
        "source": {
            "sheet": "Лист1",
            "row": 52,
            "label_cell": "Лист1!A52",
            "price_cells": ["Лист1!D52"],
        },
        "prices": {"price_kzt": int(base)},
    }
    validate_mapping_snapshot([entry])
    return {
        "workbook_path": str(workbook.resolve()),
        "workbook_sha256": raw_sha,
        "structural_fingerprint": mapping_identity_fingerprint(IDENTITY),
        "mapping_snapshot": [entry],
        "cost_kzt": int(base),
        "source_role": "ENCLOSURE_COST",
        "source_locator": "Лист1!D52",
        "price_inputs": {"B2": str(metal), "B3": str(paint)},
    }


def resolve_metal_cost(selector: Path) -> dict[str, Any]:
    baseline = resolve_active_price_baseline(selector)
    result = inspect_cost(baseline.path, baseline.sha256)
    require(
        list(baseline.mapping_snapshot) == result["mapping_snapshot"],
        "metal mapping/price drift",
    )
    require(resolve_active_price_baseline(selector) == baseline, "metal selector drift")
    return {
        **result,
        "manifest_sha256": baseline.manifest_sha256,
        "status": "APPROVED_BASELINE_COST_DRAFT",
    }


def workbook_cells(path: Path) -> dict[str, Any]:
    book = load_workbook(path, read_only=False, data_only=False, keep_links=False)
    try:
        return {
            s.title: {
                "cells": {
                    c.coordinate: [c.value, c.data_type]
                    for row in s
                    for c in row
                    if c.value is not None
                },
                "merges": sorted(str(r) for r in s.merged_cells.ranges),
            }
            for s in book
        }
    finally:
        book.close()


def audit_metal_candidate(
    candidate: Path,
    expected_sha256: str,
    *,
    selector: Path | None = None,
    predecessor_source: Path | None = None,
    expected_predecessor_sha256: str | None = None,
) -> dict[str, Any]:
    """Price-only candidate audit, never permission to write or activate."""
    predecessor = resolve_active_price_baseline(selector) if selector else None
    if predecessor is None:
        predecessor_path = predecessor_source or GENESIS_PATH
        predecessor_sha = expected_predecessor_sha256 or GENESIS_SHA
        require(
            predecessor_sha == GENESIS_SHA,
            "predecessor needs exact existing genesis metal authority",
        )
    else:
        require(
            predecessor_source is None and expected_predecessor_sha256 is None,
            "selector and genesis predecessor authority cannot mix",
        )
        resolve_metal_cost(selector)
        predecessor_path, predecessor_sha = predecessor.path, predecessor.sha256
    previous = inspect_cost(predecessor_path, predecessor_sha)
    result = inspect_cost(candidate, expected_sha256)
    before, after = workbook_cells(predecessor_path), workbook_cells(candidate)
    require(set(before) == set(after), "candidate worksheet identity drift")
    changed_inputs = []
    for sheet in before:
        require(
            before[sheet]["merges"] == after[sheet]["merges"],
            "candidate merge identity drift",
        )
        cells_before, cells_after = before[sheet]["cells"], after[sheet]["cells"]
        for cell in cells_before.keys() | cells_after.keys():
            if cells_before.get(cell) == cells_after.get(cell):
                continue
            require(
                sheet == "Лист1" and cell in {"B2", "B3"},
                f"candidate outside price-only footprint: {sheet}!{cell}",
            )
            changed_inputs.append(
                {
                    "cell": cell,
                    "old": cells_before.get(cell),
                    "new": cells_after.get(cell),
                }
            )
    require(
        sha256_file(predecessor_path) == predecessor_sha
        and sha256_file(candidate) == expected_sha256,
        "metal predecessor/candidate changed during audit",
    )
    changes = (
        []
        if previous["cost_kzt"] == result["cost_kzt"]
        else [{"old_kzt": previous["cost_kzt"], "new_kzt": result["cost_kzt"]}]
    )
    payload = {
        "schema_version": "metal_cost_candidate_audit.v0.1",
        "status": "HOLD_EXACT_HUMAN_BASELINE_APPROVAL_REQUIRED",
        "predecessor": (
            {
                "workbook_path": previous["workbook_path"],
                "workbook_sha256": predecessor_sha,
                "manifest_id": predecessor.manifest_id if predecessor else None,
                "manifest_sha256": predecessor.manifest_sha256 if predecessor else None,
            }
        ),
        **result,
        "cost_changes": changes,
        "price_input_changes": sorted(
            changed_inputs, key=lambda change: change["cell"]
        ),
        "future_cases_only": True,
        "historical_repricing_authorized": False,
    }
    if predecessor:
        require(
            resolve_active_price_baseline(selector) == predecessor,
            "audit predecessor drift",
        )
    return {
        **payload,
        "approval_fingerprint": sha256_bytes(canonical_json_bytes(payload)),
    }
