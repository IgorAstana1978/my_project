"""Opt-in panel dimensions only; never usable geometry, sizing or physical FIT."""

from __future__ import annotations

import copy
from typing import Any

import cabinet_catalogue as catalogue
import cabinet_sizing as strict
import cabinet_sizing_evidence as evidence

SCHEMA = "dinva_metal.mounting_panel.v0.1"
CONSTRUCTION_SCHEMA = "dinva_metal.standard_construction.v0.1"
CONSTRUCTION_ROLE = "metal_standard_construction"
EXECUTION = "STANDARD_OUTER_DOOR_WITH_MOUNTING_PANEL"
RULE = "DINVA-METAL-Mounting-Panel-v0.1"
IDENTITY_FIELDS = (
    "cabinet_code",
    "cabinet_label",
    "family",
    "row",
    "dimensions_mm",
    "label_dimensions_mm",
    "qualifier",
    "interpretation_status",
    "source_issues",
    "source",
)


def panel_hw_mm(outer_hwd_mm: Any) -> list[int]:
    """Conditional arithmetic only; this function does not admit a construction."""
    h, w, _ = strict.vector(outer_hwd_mm)
    strict.require(h > 100 and w > 80, "HOLD_NONPOSITIVE_MOUNTING_PANEL")
    return [h - 100, w - 80]


def assess_panel(
    cabinet_code: str,
    *,
    construction_binding: Any = None,
    source_version: str = "2026.10.21",
) -> dict[str, Any]:
    """Read the governed catalogue and separately admitted construction evidence."""
    try:
        return _assess_panel(cabinet_code, construction_binding, source_version)
    except strict.SizingHold:
        raise
    except (KeyError, TypeError, ValueError, OSError, RecursionError) as ex:
        raise strict.SizingHold("HOLD_PANEL_INVALID_OR_UNAVAILABLE_EVIDENCE") from ex


def _assess_panel(
    cabinet_code: str, construction_binding: Any, source_version: str
) -> dict[str, Any]:
    strict.require(
        isinstance(source_version, str) and source_version != "CURRENT",
        "HOLD_PANEL_CONCRETE_SOURCE_VERSION_REQUIRED",
    )
    before = catalogue.inventory(source_version=source_version)
    matches = [r for r in before["records"] if r["cabinet_code"] == cabinet_code]
    strict.require(len(matches) == 1, "HOLD_PANEL_CATALOGUE_IDENTITY")
    record = matches[0]
    identity = {k: copy.deepcopy(record[k]) for k in IDENTITY_FIELDS}
    report: dict[str, Any] = {
        "schema_version": SCHEMA,
        "rule": RULE,
        "rule_provenance": {
            "authority": "IGOR_DIRECT_HUMAN_DECISION",
            "decision_id": "IGOR-DINVA-METAL-MOUNTING-PANEL-20261030",
            "date": "2026-10-30",
            "scope": EXECUTION,
            "formula": "H_panel = H_outer - 100; W_panel = W_outer - 80",
            "unit": "mm",
        },
        "catalogue_identity": identity,
        "construction_binding": copy.deepcopy(construction_binding),
        "status": "HOLD",
        "first_missing": "HOLD_STANDARD_CONSTRUCTION_EVIDENCE_REQUIRED",
        "panel_hw_mm": None,
        "usable_geometry_status": "UNKNOWN",
        "usable_depth_status": "UNKNOWN",
        "physical_status": "HOLD",
        "stop_before": "HUMAN_APPROVAL_1",
    }
    if record["family"] != "METAL":
        report["first_missing"] = "HOLD_PANEL_RULE_FAMILY_OUT_OF_SCOPE"
    elif (
        record["qualifier"] != ""
        or record["source_issues"]
        or record["interpretation_status"] != "LITERAL_HWD"
        or record["dimensions_mm"] != record["label_dimensions_mm"]
    ):
        report["first_missing"] = "HOLD_PANEL_SPECIAL_OR_UNCONFIRMED_CONSTRUCTION"
    elif construction_binding is not None:
        data = evidence.read(construction_binding, CONSTRUCTION_ROLE)
        strict.require(
            set(data)
            == {"schema_version", "catalogue_identity", "execution", "raw_sources"}
            and data["schema_version"] == CONSTRUCTION_SCHEMA
            and data["catalogue_identity"] == identity
            and data["execution"] == EXECUTION
            and isinstance(data["raw_sources"], list)
            and bool(data["raw_sources"]),
            "HOLD_PANEL_CONSTRUCTION_BINDING",
        )
        report["panel_hw_mm"] = panel_hw_mm(record["dimensions_mm"])
        report["status"] = "PANEL_DIMENSIONS_BY_APPROVED_RULE"
        report["first_missing"] = None
        strict.require(
            data == evidence.read(construction_binding, CONSTRUCTION_ROLE),
            "HOLD_PANEL_CONSTRUCTION_SOURCE_DRIFT",
        )
    strict.require(
        before == catalogue.inventory(source_version=source_version),
        "HOLD_PANEL_CATALOGUE_SOURCE_DRIFT",
    )
    return report


def verify_assessment(report: Any) -> None:
    """Recompute from pinned sources; matching JSON claims confer no authority."""
    try:
        strict.require(
            report
            == assess_panel(
                report["catalogue_identity"]["cabinet_code"],
                source_version=report["catalogue_identity"]["source"]["version"],
                construction_binding=report["construction_binding"],
            ),
            "HOLD_PANEL_REPORT_DRIFT",
        )
    except (KeyError, TypeError) as ex:
        raise strict.SizingHold("HOLD_PANEL_REPORT_SCHEMA") from ex
