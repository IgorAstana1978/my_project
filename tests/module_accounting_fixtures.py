"""Explicit synthetic module facts for portable tests; no real admissions."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import cabinet_sizing as sizing  # type: ignore[import-not-found]
import cabinet_sizing_evidence as evidence  # type: ignore[import-not-found]
import cabinet_sizing_module_accounting as modules  # type: ignore[import-not-found]
import pytest

NATIVE_BUILD = modules.build_sizing_report


def provision_modules(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case_id: str,
    items: Any,
    base: Any,
    mounting_by_item: Any = None,
) -> tuple[dict[str, str], dict[str, Any]]:
    """Declare TEST SKU 1 module / 1mm facts, never infer from electrical types."""
    raw = tmp_path / f"module-primary-{uuid4().hex}.txt"
    raw.write_text("SYNTHETIC manufacturer, rail and assembly source for tests only.")
    raw_binding = {
        "path": str(raw),
        "sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
    }
    ref = dict(raw_binding, locator="TEST explicit technical facts")
    data: dict[str, Any] = {
        "schema_version": modules.EVIDENCE_SCHEMA,
        "case_id": case_id,
        "composition_sha256": modules.composition_hash(items),
        "sizing_sha256": sizing.digest(base),
        "inventory_scope": modules.SCOPE,
        "products": [],
        "profiles": [],
        "boards": [],
        "raw_sources": [raw_binding],
    }
    for bi, item in enumerate(items):
        kind = (mounting_by_item or {}).get(item["item_id"], "DIN")
        board: dict[str, Any] = {
            "item_id": item["item_id"],
            "cabinet_sha256": sizing.digest(item["cabinet"]),
            "quantity": item["quantity"],
            "project_min_din_free_percent": 0,
            "project_min_panel_free_percent": 0,
            "zones": [],
            "instances": [],
            "groups": [],
            "source": dict(ref),
        }
        for zone_kind in ("DIN", "PANEL", "OTHER"):
            board["zones"].append(
                {
                    "id": zone_kind,
                    "kind": zone_kind,
                    "capacity_modules": 1000 if zone_kind == "DIN" else None,
                    "capacity_mm": 1000 if zone_kind == "DIN" else None,
                    "capacity_area_mm2": None if zone_kind == "DIN" else 1000,
                    "source": dict(ref),
                }
            )
        for ci, component in enumerate(item["components"]):
            pid = f"PRODUCT-{bi}-{ci}"
            shape = {
                "nominal_modules": 1 if kind == "DIN" else None,
                "width_mm": 1 if kind == "DIN" else None,
                "area_mm2": None if kind == "DIN" else 1,
            }
            data["products"].append(
                dict(
                    id=pid,
                    manufacturer="TEST",
                    sku=f"TEST-SKU-{bi}-{ci}",
                    revision="TEST-REV-1",
                    mounting=kind,
                    source=dict(ref),
                    **shape,
                )
            )
            data["profiles"].append(
                dict(
                    id=pid,
                    product_ids=[pid],
                    left_gap_mm=0,
                    right_gap_mm=0,
                    allowed_zones=[kind],
                    source=dict(ref),
                    **shape,
                )
            )
            for unit in range(1, component["quantity"] + 1):
                iid = f"INSTANCE-{bi}-{ci}-{unit}"
                board["instances"].append(
                    {
                        "id": iid,
                        "component_id": component["component_id"],
                        "unit": unit,
                        "product_id": pid,
                    }
                )
                board["groups"].append(
                    {
                        "id": iid,
                        "profile_id": pid,
                        "instance_ids": [iid],
                        "zone_id": kind,
                    }
                )
        data["boards"].append(board)
    path = tmp_path / f"module-evidence-{uuid4().hex}.json"
    return repin(monkeypatch, path, data), data


def repin(monkeypatch: pytest.MonkeyPatch, path: Path, data: Any) -> dict[str, str]:
    path.write_text(json.dumps(data), encoding="utf-8")
    binding = {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    monkeypatch.setattr(
        evidence,
        "AUTHORIZED",
        evidence.AUTHORIZED | {(modules.ROLE, str(path.resolve()), binding["sha256"])},
    )
    return binding


def install_synthetic_modules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, item_geometry: Any = None
) -> None:
    """Old workflow tests now provide real validated TEST ledgers, not a gate stub."""
    kinds = copy.deepcopy(getattr(modules.build_sizing_report, "_test_mounting", {}))
    for iid, geometry in (item_geometry or {}).items():
        kinds[iid] = geometry.get("mounting", "DIN")

    def build(case_id: str, items: Any, base: Any, source: Any) -> Any:
        if source is None:
            source, _ = provision_modules(
                tmp_path, monkeypatch, case_id, items, base, kinds
            )
        return NATIVE_BUILD(case_id, items, base, source)

    build._test_mounting = kinds  # type: ignore[attr-defined]
    monkeypatch.setattr(modules, "build_sizing_report", build)
