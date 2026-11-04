"""Versioned family reserve thresholds; no catalogue admission or ranking."""

from __future__ import annotations

import copy
import hashlib
from decimal import Decimal
from typing import Any

import cabinet_sizing as sizing
import cabinet_sizing_evidence as evidence

VERSION = "cabinet_reserve.by_family.v0.1"
BASE_SCHEMA = "cabinet_sizing.reserve_base.v0.1"
FAMILIES = {"KRN", "KRV", "KURN", "METAL"}


def make(case_id: str, projects: Any) -> dict[str, Any]:
    sizing.require(
        isinstance(case_id, str)
        and bool(case_id)
        and isinstance(projects, dict)
        and 0 < len(projects) <= 256,
        "HOLD_RESERVE_PROJECT_BINDING",
    )
    result = {}
    for iid, raw in projects.items():
        sizing.require(
            isinstance(iid, str) and bool(iid), "HOLD_RESERVE_PROJECT_BINDING"
        )
        record = sizing.object_with(raw, {"DIN", "PANEL"}, "reserve_project")
        result[iid] = {
            key: format(percent(record[key]), "f") for key in ("DIN", "PANEL")
        }
    return {"schema_version": VERSION, "case_id": case_id, "projects": result}


def percent(value: Any) -> Decimal:
    result = evidence.number(value, zero=True)
    sizing.require(result < 100, "HOLD_RESERVE_PROJECT_PERCENT")
    return result


def thresholds(policy: Any, item_id: str, family: str) -> tuple[Decimal, Decimal]:
    if policy is None:
        return Decimal(25), Decimal(25)
    sizing.object_with(
        policy, {"schema_version", "case_id", "projects"}, "reserve_policy"
    )
    sizing.require(policy["schema_version"] == VERSION, "HOLD_RESERVE_POLICY_VERSION")
    sizing.require(family in FAMILIES, "HOLD_RESERVE_CABINET_FAMILY_UNKNOWN")
    project = sizing.object_with(
        policy["projects"][item_id], {"DIN", "PANEL"}, "reserve_project"
    )
    din = Decimal(10) if family == "METAL" else Decimal(0)
    return max(din, percent(project["DIN"])), max(
        Decimal(25), percent(project["PANEL"])
    )


def fits(occupied: Decimal, capacity: Decimal, free_percent: Decimal) -> bool:
    value = percent(free_percent)
    if value == 25:
        return occupied * 4 <= capacity * 3
    return occupied * 100 <= capacity * (100 - value)


def minimum_extent(
    occupied: Decimal, extent: Decimal, free_percent: Decimal
) -> Decimal:
    percent(free_percent)
    # Retain the historical operation order and bit-for-bit Decimal replay.
    if free_percent == 25:
        return occupied * 4 / (3 * extent)
    return occupied * 100 / ((100 - free_percent) * extent)


def fraction(free_percent: Decimal) -> str:
    return format(percent(free_percent) / 100, "f")


def request(report: Any) -> Any:
    if report.get("schema_version") != BASE_SCHEMA:
        return report["sources"]
    sources = sizing.object_with(
        report["sources"],
        {"request", "reserve_policy", "algorithm_schema"},
        "reserve_base_sources",
    )
    return sources["request"]


def identity(cabinet: Any, report: Any) -> dict[str, Any]:
    """Resolve an exact governed identity, never a label/prefix guess."""
    import cabinet_catalogue as catalogue

    code = cabinet["cabinet_code"]
    try:
        _, family, dimensions = sizing.cabinet_identity(code)
    except sizing.SizingHold:
        req = request(report)
        sizing.require(isinstance(req, dict), "HOLD_RESERVE_IDENTITY_SOURCE_REQUIRED")
        schema = req.get("schema_version")
        versioned = schema in {
            "cabinet_sizing.catalogue_request.v0.2",
            "cabinet_sizing.catalogue_request.v0.3",
            "cabinet_sizing.catalogue_request.v0.4",
            "cabinet_sizing.catalogue_request.v0.5",
        }
        technical = schema in {
            "cabinet_sizing.catalogue_request.v0.3",
            "cabinet_sizing.catalogue_request.v0.4",
            "cabinet_sizing.catalogue_request.v0.5",
        }
        sizing.require(
            schema
            in {
                "cabinet_sizing.catalogue_request.v0.1",
                "cabinet_sizing.catalogue_request.v0.2",
                "cabinet_sizing.catalogue_request.v0.3",
                "cabinet_sizing.catalogue_request.v0.4",
                "cabinet_sizing.catalogue_request.v0.5",
            },
            "HOLD_RESERVE_IDENTITY_SOURCE_REQUIRED",
        )
        kwargs: dict[str, Any] = {}
        if versioned:
            kwargs["source_version"] = req["metal_source"]["version"]
        if technical:
            kwargs["technical_binding"] = True
        if schema in {
            "cabinet_sizing.catalogue_request.v0.4",
            "cabinet_sizing.catalogue_request.v0.5",
        }:
            kwargs["capacity_binding"] = True
        inventory = catalogue.inventory(**kwargs)
        matches = [r for r in inventory["records"] if r["cabinet_code"] == code]
        sizing.require(len(matches) == 1, "HOLD_RESERVE_IDENTITY_SOURCE_REQUIRED")
        record = matches[0]
        sizing.require(
            all(
                issue == "HOLD_SPECIAL_FORM_FACTOR_MOUNTING_EVIDENCE_REQUIRED"
                for issue in record["source_issues"]
            ),
            "HOLD_RESERVE_IDENTITY_SOURCE_CONFLICT",
        )
        family, dimensions = record["family"], record["dimensions_mm"]
        source = record["source"]
    else:
        # CABINETS / METAL_SIZES are code-controlled exact identity registries.
        code_sha = hashlib.sha256(catalogue.WU8_PATH.read_bytes()).hexdigest()
        evidence.safe_bytes(catalogue.WU8_PATH, code_sha)
        source = {
            "path": str(catalogue.WU8_PATH),
            "sha256": code_sha,
            "record_id": code,
        }
    sizing.require(
        family in FAMILIES
        and cabinet.get("cabinet_type") == family
        and cabinet.get("dimensions_mm") == dimensions,
        "HOLD_RESERVE_CABINET_IDENTITY_CONFLICT",
    )
    return {"family": family, "cabinet_code": code, "source": source}


def wrap(report: Any, policy: Any) -> dict[str, Any]:
    sizing.require(policy["case_id"] == report["case_id"], "HOLD_RESERVE_CASE_BINDING")
    result: dict[str, Any] = copy.deepcopy(report)
    result["schema_version"] = BASE_SCHEMA
    result["sources"] = {
        "request": copy.deepcopy(report["sources"]),
        "reserve_policy": copy.deepcopy(policy),
        "algorithm_schema": report["schema_version"],
    }
    for selection in result["items"]:
        proof = identity(selection["cabinet"], result)
        din, panel = thresholds(policy, selection["item_id"], proof["family"])
        selection["provenance"]["reserve_policy"] = {
            "schema_version": VERSION,
            "identity": proof,
            "DIN_minimum_free_percent": format(din, "f"),
            "PANEL_minimum_free_percent": format(panel, "f"),
        }
    return result
