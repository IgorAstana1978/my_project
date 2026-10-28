"""Pinned technical inventory; accesses only label/dimension workbook cells."""

from __future__ import annotations

import io
import json
import re
from pathlib import Path
from typing import Any

import cabinet_sizing_evidence as evidence
import wu8_governed_sources as wu8
from cabinet_sizing import SizingHold, require
from governed_case_intake import _pairs
from governed_metal_cost import GENESIS_PATH, GENESIS_SHA, resolve_metal_source
from openpyxl import load_workbook  # type: ignore[import-untyped]
from price_baseline_contract import (
    DEFAULT_ACTIVE_SELECTOR,
    resolve_active_price_baseline,
)

POLICY = "DINVA-METAL-KRN-KRV-catalogue-v0.1"
ACTIVE_SHA = "02ca5be9b2eb6775289ee1053c389a659c85e2bd27a2b9867b7d523d6d6e4096"
MANIFEST_SHA = "fc8a4da76aeaf9a7114063e888d3dc0e4e70237dee16e4c0d8fc23ec30ce931c"
SELECTOR_SHA = "56a06d4b1c66960ae10f32c124674935dd5bb00bf7492b823ee181b162f0de8b"
HEADERS = {
    "A7": "Размер шкафа ВхШхГ",
    "E7": "Высота, мм",
    "F7": "Ширина, мм",
    "G7": "Глубина, мм",
}
RANGES = (("METAL", 8, 56), ("KRN", 60, 72), ("KRV", 73, 80))
# Empty until independently authorized reusable mounting sources exist.
MOUNTING_SOURCES: dict[str, dict[str, str]] = {}
KRN36_METAL_SHA = "be4a3497cf86ee4e5a13ac55bfeeeb980e6948cd30847ae027f36d6ca599cc71"
WU8_PATH = Path(wu8.__file__).resolve()
WU8_SHA = "b001650308f9bf5eff4bef620240c74413ee7b68d2d29b4ecd6eff412999f173"


def krn36_binding(record: Any, entry: Any, metal_source: Any) -> dict[str, Any]:
    """Technical authority only; the immutable price signature retains its axes."""
    require(
        isinstance(metal_source, dict)
        and metal_source["version"] == "2026.10.21"
        and metal_source["sha256"] == KRN36_METAL_SHA,
        "HOLD_KRN36_TECHNICAL_SOURCE_BINDING",
    )
    require(
        record["cabinet_code"] == "CATALOGUE-KRN-ROW-64"
        and record["family"] == "KRN"
        and record["row"] == 64
        and record["cabinet_label"] == "Корпус КРН-36 540х330х100 "
        and record["dimensions_mm"] == record["label_dimensions_mm"] == [540, 330, 100]
        and record["source_issues"] == ["HOLD_ACTIVE_MAPPING_AXIS_CONFLICT"],
        "HOLD_KRN36_TECHNICAL_IDENTITY",
    )
    identity = {
        "authority": "TECHNICAL_MAPPING_IDENTITY",
        "cabinet_code": "КРН-36",
        "depth_mm": 100,
        "expected_label": "Корпус КРН-36 540х330х100",
        "height_mm": 330,
        "mapping_id": "CABINET-PRICE-KRN-36",
        "material": "metal",
        "row": 9,
        "sheet": "КРН",
        "strict_label": False,
        "width_mm": 540,
    }
    locator = {
        "label_cell": "КРН!L9",
        "price_cells": ["КРН!M9"],
        "row": 9,
        "sheet": "КРН",
    }
    fingerprint = "4eda337c68656d43d1ae64b378dffd20949aa06b5f940a6dba32f8fa1ce859d1"
    require(
        entry["identity"] == identity
        and entry["identity_fingerprint"] == fingerprint
        and entry["source"] == locator,
        "HOLD_KRN36_LEGACY_PRICE_IDENTITY",
    )
    evidence.safe_bytes(WU8_PATH, WU8_SHA)
    require(
        wu8.CABINETS.get("CAB-KRN-36") == ("КРН-36", 9, (540, 330, 100), 64, 1500, 350),
        "HOLD_KRN36_WU8_IDENTITY",
    )
    return {
        "binding_version": "KRN36-technical.v0.1",
        "dimensions_order": "HWD",
        "dimensions_mm": [540, 330, 100],
        "rail_count": 3,
        "rail_count_semantics": "CONSTRUCTION_ONLY_NOT_USABLE_CAPACITY",
        "human_decision": {
            "authority": "IGOR_DIRECT_HUMAN_DECISION",
            "decision_id": "IGOR-KRN36-HWD-3DIN-20261021",
            "provenance": "Direct Igor approved T06: H540 W330 D100 mm; 3 DIN rails",
        },
        "metal_source": record["source"],
        "wu8_source": {
            "path": str(WU8_PATH),
            "sha256": WU8_SHA,
            "key": "CAB-KRN-36",
            "dimensions_order": "HWD",
            "dimensions_mm": [540, 330, 100],
            "main_row": 9,
            "metal_row": 64,
        },
        "legacy_price_identity": {
            "identity": entry["identity"],
            "identity_fingerprint": fingerprint,
            "source": entry["source"],
            "physical_authority": False,
        },
    }


def inventory(
    *,
    source_version: str | None = None,
    technical_binding: bool = False,
    capacity_binding: bool = False,
) -> dict[str, Any]:
    require(
        not capacity_binding or technical_binding,
        "HOLD_KRN36_CAPACITY_TECHNICAL_BINDING_REQUIRED",
    )
    # None is the frozen v0.1 historical parser contract.
    metal_source = (
        resolve_metal_source(source_version) if source_version is not None else None
    )
    source_path = Path(metal_source["path"]) if metal_source else GENESIS_PATH
    source_sha = metal_source["sha256"] if metal_source else GENESIS_SHA
    pointer = evidence.safe_bytes(DEFAULT_ACTIVE_SELECTOR, SELECTOR_SHA)
    pointer_data = json.loads(pointer.decode("utf-8"), object_pairs_hook=_pairs)
    manifest = evidence.safe_bytes(Path(pointer_data["manifest_path"]), MANIFEST_SHA)
    manifest_data = json.loads(manifest.decode("utf-8"), object_pairs_hook=_pairs)
    evidence.safe_bytes(Path(manifest_data["workbook"]["path"]), ACTIVE_SHA)
    baseline = resolve_active_price_baseline()
    require(
        baseline.sha256 == ACTIVE_SHA and baseline.manifest_sha256 == MANIFEST_SHA,
        "HOLD_ACTIVE_CATALOGUE_BASELINE_DRIFT",
    )
    if baseline.manifest_path is None:
        raise SizingHold("HOLD_ACTIVE_CATALOGUE_MANIFEST")
    evidence.safe_bytes(baseline.path, ACTIVE_SHA)
    evidence.safe_bytes(baseline.manifest_path, MANIFEST_SHA)
    raw = evidence.safe_bytes(source_path, source_sha)
    book = load_workbook(io.BytesIO(raw), read_only=True, data_only=False)
    records = []
    try:
        sheet = book["Лист1"]
        require(
            all(sheet[cell].value == value for cell, value in HEADERS.items()),
            "HOLD_CATALOGUE_HEADERS",
        )
        for family, first, last in RANGES:
            for row in range(first, last + 1):
                label = sheet[f"A{row}"].value
                values = [sheet[f"{axis}{row}"].value for axis in "EFG"]
                match = re.search(
                    r"(\d+)\s*[хxХX×]\s*(\d+)\s*[хxХX×]\s*(\d+)", label or ""
                )
                label_size = [int(x) for x in match.groups()] if match else None
                literal = all(type(x) is int and x > 0 for x in values)
                reasons = []
                if not literal or values != label_size:
                    reasons.append("HOLD_LABEL_DIMENSION_SOURCE_CONFLICT")
                qualifier = label[match.end() :].strip() if match else None
                if family == "METAL" and qualifier:
                    reasons.append(
                        "HOLD_SPECIAL_FORM_FACTOR_MOUNTING_EVIDENCE_REQUIRED"
                    )
                identity = None
                if family == "KRN" and row == 64:
                    entries = [
                        entry
                        for entry in baseline.mapping_snapshot
                        if entry["mapping_id"] == "CABINET-PRICE-KRN-36"
                    ]
                    require(len(entries) == 1, "HOLD_ACTIVE_CATALOGUE_MAPPING_REQUIRED")
                    entry = entries[0]
                    ident = entry["identity"]
                    identity = {
                        "mapping_id": entry["mapping_id"],
                        "dimensions_mm": [
                            ident[f"{axis}_mm"] for axis in ("height", "width", "depth")
                        ],
                        "label_cell": entry["source"]["label_cell"],
                    }
                    if identity["dimensions_mm"] != values:
                        reasons.append("HOLD_ACTIVE_MAPPING_AXIS_CONFLICT")
                code = f"CATALOGUE-{family}-ROW-{row}"
                records.append(
                    {
                        "cabinet_code": code,
                        "cabinet_label": label,
                        "family": family,
                        "row": row,
                        "dimensions_mm": values if literal else None,
                        "label_dimensions_mm": label_size,
                        "qualifier": qualifier,
                        "interpretation_status": (
                            "UNKNOWN" if reasons else "LITERAL_HWD"
                        ),
                        "source_issues": reasons,
                        "source": {
                            "path": str(source_path),
                            "sha256": source_sha,
                            **(
                                {"version": metal_source["version"]}
                                if metal_source
                                else {}
                            ),
                            "sheet": "Лист1",
                            "label_cell": f"A{row}",
                            "dimension_cells": [f"{axis}{row}" for axis in "EFG"],
                            "raw_dimension_values": values,
                        },
                        "active_mapping": identity,
                        "pricing_mapping_status": "UNVERIFIED_NEW_TECHNICAL_IDENTITY",
                    }
                )
                if technical_binding and family == "KRN" and row == 64:
                    record = records[-1]
                    record["technical_binding"] = krn36_binding(
                        record, entry, metal_source
                    )
                    record["source_issues"] = []
                    record["interpretation_status"] = "SOURCE_BACKED_TECHNICAL_HWD"
                    if capacity_binding:
                        record["din_capacity_binding"] = {
                            "binding_version": "KRN36-DIN-capacity.v0.1",
                            "rail_count": 3,
                            "modules_per_rail": 12,
                            "module_pitch_mm": 18,
                            "rail_capacity_mm": 216,
                            "total_capacity_mm": 648,
                            "capacity_only": True,
                            "human_decision": {
                                "authority": "IGOR_DIRECT_HUMAN_DECISION",
                                "decision_id": "IGOR-KRN36-3X12X18-20261021",
                                "provenance": (
                                    "Direct Igor approved T07: 3 rails x 12 modules "
                                    "x 18 mm; linear DIN capacity only"
                                ),
                            },
                        }
    finally:
        book.close()
    require(
        raw == evidence.safe_bytes(source_path, source_sha)
        and pointer == evidence.safe_bytes(DEFAULT_ACTIVE_SELECTOR, SELECTOR_SHA),
        "HOLD_CATALOGUE_SOURCE_DRIFT",
    )
    if metal_source is not None:
        require(
            metal_source == resolve_metal_source(metal_source["version"]),
            "HOLD_CATALOGUE_SOURCE_DRIFT",
        )
    return {
        **({"metal_source": metal_source} if metal_source else {}),
        "policy": POLICY,
        "records": records,
        "out_of_scope": [
            {"rows": "57:59", "family": "KURN"},
            {"rows": "81+", "family": "OTHER_FAMILIES_AND_ACCESSORIES"},
        ],
        "active_baseline": {
            "path": str(baseline.path),
            "sha256": baseline.sha256,
            "manifest_path": str(baseline.manifest_path),
            "manifest_sha256": baseline.manifest_sha256,
            "selector_sha256": SELECTOR_SHA,
        },
    }
