"""Automatic catalogue comparison with explicit three-valued candidate proofs."""

from __future__ import annotations

import copy
from decimal import Decimal
from typing import Any

import cabinet_catalogue as catalogue
import cabinet_sizing_evidence as evidence
import cabinet_sizing_pragmatic as planning
import cabinet_sizing_selector as exact
from cabinet_sizing import SizingHold, apparatus_hash, require
from governed_metal_cost import resolve_metal_source

REQUEST_SCHEMA = "cabinet_sizing.catalogue_request.v0.1"
SCHEMA = "cabinet_sizing.catalogue.v0.1"
VERSIONED_REQUEST_SCHEMA = "cabinet_sizing.catalogue_request.v0.2"
VERSIONED_SCHEMA = "cabinet_sizing.catalogue.v0.2"
TECHNICAL_REQUEST_SCHEMA = "cabinet_sizing.catalogue_request.v0.3"
TECHNICAL_SCHEMA = "cabinet_sizing.catalogue.v0.3"
CURRENT_REQUEST_SCHEMA = "cabinet_sizing.catalogue_request.v0.4"
CURRENT_SCHEMA = "cabinet_sizing.catalogue.v0.4"
REQUEST_SCHEMAS = {
    REQUEST_SCHEMA,
    VERSIONED_REQUEST_SCHEMA,
    TECHNICAL_REQUEST_SCHEMA,
    CURRENT_REQUEST_SCHEMA,
}


def request_for(case_id: str, items: Any) -> dict[str, Any]:
    return dict(
        planning.request_for(case_id, items),
        schema_version=CURRENT_REQUEST_SCHEMA,
        metal_source=resolve_metal_source(),
    )


def validate_request(case_id: str, request: Any) -> dict[str, Any]:
    require(
        isinstance(request, dict) and request.get("schema_version") in REQUEST_SCHEMAS,
        "HOLD_CATALOGUE_REQUEST_SCHEMA",
    )
    base = dict(request, schema_version=planning.REQUEST_SCHEMA)
    if request["schema_version"] != REQUEST_SCHEMA:
        binding = base.pop("metal_source", None)
        require(
            isinstance(binding, dict)
            and set(binding) == {"version", "path", "sha256", "predecessor_version"}
            and isinstance(binding["version"], str)
            and binding["version"] != "CURRENT",
            "HOLD_METAL_SOURCE_BINDING",
        )
        try:
            admitted = resolve_metal_source(binding["version"])
        except (ValueError, OSError, TypeError, KeyError) as exc:
            raise SizingHold("HOLD_METAL_SOURCE_DRIFT_OR_UNKNOWN_VERSION") from exc
        require(binding == admitted, "HOLD_METAL_SOURCE_BINDING")
    planning.validate_request(case_id, base)
    return dict(request)


def hold(reason: str, details: Any) -> None:
    raise SizingHold(reason, exact.serial(dict(details, first_missing=reason)))


def proven_mounting(record: Any) -> Any:
    """A deliberately narrow, proven DIN mounting record; no nominal modules."""
    binding = catalogue.MOUNTING_SOURCES.get(record["cabinet_code"])
    if binding is None:
        return None
    data = evidence.read(binding, "catalogue_mounting")
    require(
        set(data)
        == {
            "cabinet_code",
            "dimensions_mm",
            "mounting_kinds",
            "installation",
            "ip",
            "shock_class",
            "zones",
        },
        "HOLD_CATALOGUE_MOUNTING_SCHEMA",
    )
    require(
        data["cabinet_code"] == record["cabinet_code"]
        and data["dimensions_mm"] == record["dimensions_mm"],
        "HOLD_CATALOGUE_MOUNTING_IDENTITY",
    )
    require(data["mounting_kinds"] == ["DIN"], "HOLD_CATALOGUE_MOUNTING_UNSUPPORTED")
    require(
        isinstance(data["installation"], str) and bool(data["installation"]),
        "HOLD_CATALOGUE_INSTALLATION_EVIDENCE",
    )
    require(
        isinstance(data["ip"], list)
        and len(data["ip"]) == 2
        and all(type(x) is int and 0 <= x <= 9 for x in data["ip"]),
        "HOLD_CATALOGUE_IP_EVIDENCE",
    )
    require(data["shock_class"] in {"I", "II", None}, "HOLD_CATALOGUE_SHOCK_EVIDENCE")
    require(
        isinstance(data["zones"], list) and len(data["zones"]) == 1,
        "HOLD_CATALOGUE_MOUNTING_UNSUPPORTED",
    )
    zone = data["zones"][0]
    require(
        set(zone)
        == {
            "zone_id",
            "kind",
            "origin_mm",
            "usable_mm",
            "rails_mm",
            "mounting_plane_mm",
            "panel_material",
            "panel_thickness_mm",
            "barriers_compatible",
        }
        and zone["kind"] == "DIN",
        "HOLD_CATALOGUE_ZONE_SCHEMA",
    )
    require(
        isinstance(zone["zone_id"], str) and bool(zone["zone_id"]),
        "HOLD_CATALOGUE_ZONE_SCHEMA",
    )
    pos = evidence.dimensions(zone["origin_mm"], zero=True)
    size = evidence.dimensions(zone["usable_mm"])
    outer = evidence.dimensions(record["dimensions_mm"])
    require(
        all(pos[i] + size[i] <= outer[i] for i in range(3)),
        "HOLD_USABLE_OUTSIDE_CABINET",
    )
    require(
        evidence.number(zone["mounting_plane_mm"], zero=True) <= size[2],
        "HOLD_MOUNTING_PLANE_OUTSIDE_USABLE",
    )
    require(
        isinstance(zone["rails_mm"], list) and bool(zone["rails_mm"]),
        "HOLD_DIN_RAIL_EVIDENCE",
    )
    rails = [evidence.number(x, zero=True) for x in zone["rails_mm"]]
    if "technical_binding" in record:
        require(
            len(rails) == record["technical_binding"]["rail_count"],
            "HOLD_CONSTRUCTION_MOUNTING_RAIL_COUNT_CONFLICT",
        )
    require(
        rails == sorted(set(rails))
        and all(y <= size[0] for y in rails)
        and all(
            rails[i + 1] - rails[i] == planning.PITCH for i in range(len(rails) - 1)
        ),
        "HOLD_DIN_PITCH_EVIDENCE",
    )
    require(
        zone["panel_material"] in {None, "metal", "insulating"}
        and type(zone["barriers_compatible"]) is bool,
        "HOLD_CATALOGUE_ZONE_SCHEMA",
    )
    if zone["panel_thickness_mm"] is not None:
        evidence.number(zone["panel_thickness_mm"])
    return data


def candidate(
    record: Any,
    units: Any,
    shapes: Any,
    panel: Any,
    fact: Any,
    planning_error: str | None = None,
) -> dict[str, Any]:
    result = dict(
        record,
        status="UNKNOWN",
        reasons=[],
        layout=None,
        physical_installation_status="HOLD",
    )
    capacity = None
    if "din_capacity_binding" in record:
        try:
            capacity = din_capacity(record, units)
        except SizingHold as exc:
            result["reasons"] = [str(exc)]
            return result
        result["din_capacity_assessment"] = capacity
    size = record["dimensions_mm"]
    raw_axes = record["source"]["raw_dimension_values"]
    explicit_size = (
        evidence.dimensions(fact["dimensions_mm"])
        if fact["dimensions_status"] == "EXPLICIT"
        else None
    )
    if explicit_size is not None and any(
        type(value) is int and value != explicit_size[axis]
        for axis, value in enumerate(raw_axes)
    ):
        result.update(status="NO_FIT", reasons=["SOURCE_EXACT_DIMENSIONS_ONLY"])
        return result
    if any(
        any(
            type(value) is int and unit["envelope"]["dimensions_mm"][axis] > value
            for axis, value in enumerate(raw_axes)
        )
        for unit in units
    ):
        result.update(status="NO_FIT", reasons=["DEVICE_EXCEEDS_PROVEN_OUTER_BOUND"])
        return result
    # A conflict stays visible even when independent necessary bounds refute fit.
    issues = [
        issue
        for issue in record["source_issues"]
        if issue != "HOLD_SPECIAL_FORM_FACTOR_MOUNTING_EVIDENCE_REQUIRED"
        or record["cabinet_code"] not in catalogue.MOUNTING_SOURCES
    ]
    if issues:
        result["reasons"] = issues
        return result
    if explicit_size is not None and size != explicit_size:
        result.update(status="NO_FIT", reasons=["SOURCE_EXACT_DIMENSIONS_ONLY"])
        return result
    # Proven outer bounds can refute fit even if mounting evidence is absent.
    if any(
        any(unit["envelope"]["dimensions_mm"][i] > size[i] for i in range(3))
        for unit in units
    ):
        result.update(status="NO_FIT", reasons=["DEVICE_EXCEEDS_PROVEN_OUTER_BOUND"])
        return result
    try:
        if capacity is not None and capacity["status"] != "PASS":
            result.update(status=capacity["status"], reasons=[capacity["reason"]])
            return result
        mount = proven_mounting(record)
        if mount is not None:
            if any(
                unit["envelope"]["mounting"] not in mount["mounting_kinds"]
                for unit in units
            ):
                result.update(
                    status="NO_FIT", reasons=["PROVEN_MOUNTING_CLASS_INCOMPATIBLE"]
                )
                return result
            if (
                fact["installation"] is not None
                and fact["installation"] != mount["installation"]
            ):
                result.update(
                    status="NO_FIT", reasons=["PROVEN_INSTALLATION_INCOMPATIBLE"]
                )
                return result
            if capacity is not None:
                # Independent mounting may narrow the approved capacity, never
                # silently enlarge it. Preserve the admitted source verbatim.
                mount = copy.deepcopy(mount)
                zone = mount["zones"][0]
                zone["usable_mm"][1] = min(
                    evidence.number(zone["usable_mm"][1]), Decimal(216)
                )
            packed = exact.din_layout(units, mount, exact.Budget())
            if packed is None:
                result.update(
                    status="NO_FIT",
                    reasons=["PROVEN_ROW_CAPACITY_OR_GEOMETRY_INSUFFICIENT"],
                )
            else:
                result.update(
                    status="FIT",
                    reasons=["PROVEN_DIN_MOUNTING_AND_INDEPENDENT_RESERVE"],
                    layout={"placements": packed[0], "reserve": {"DIN": packed[1]}},
                )
                if fact["installation"] == mount["installation"]:
                    result["physical_installation_status"] = (
                        "VERIFIED_MOUNTING_RECORD_ONLY"
                    )
            result["mounting_evidence"] = catalogue.MOUNTING_SOURCES[
                record["cabinet_code"]
            ]
            return result
        if record["family"] != "METAL":
            result["reasons"] = (
                ["HOLD_PHYSICAL_MOUNTING_DEPTH_INSTALLATION_IP_EVIDENCE_REQUIRED"]
                if capacity is not None
                else ["HOLD_ROW_MOUNTING_CAPACITY_INSTALLATION_EVIDENCE_REQUIRED"]
            )
            if capacity is not None and capacity["panel_assessment"]["unit_count"]:
                result["reasons"].append(
                    "HOLD_PANEL_GEOMETRY_AND_INDEPENDENT_RESERVE_EVIDENCE_REQUIRED"
                )
            return result
        if planning_error is not None:
            result["reasons"] = [planning_error]
            return result
        layouts = [
            layout
            for shape in shapes
            for orientation in ("VERTICAL", "HORIZONTAL")
            if (
                layout := planning.construct(
                    shape, panel, evidence.dimensions(size), orientation
                )
            )
            is not None
        ]
        if not layouts:
            result.update(
                status="NO_FIT", reasons=["PRELIMINARY_PLANNING_BOUNDS_INSUFFICIENT"]
            )
        else:
            result.update(
                status="FIT",
                reasons=["METAL_PRELIMINARY_OUTER_PLANNING_ONLY"],
                layout=min(
                    layouts,
                    key=lambda x: (*x["required_dimensions_mm"], x["orientation"]),
                ),
            )
    except SizingHold as exc:
        result["reasons"] = [str(exc)]
    return result


def din_capacity(record: Any, units: Any) -> dict[str, Any]:
    """Partial linear proof; relative rows are not physical mounting geometry."""
    binding = record["din_capacity_binding"]
    require(
        record["cabinet_code"] == "CATALOGUE-KRN-ROW-64"
        and record["dimensions_mm"] == [540, 330, 100]
        and record["technical_binding"]["rail_count"] == binding["rail_count"] == 3
        and binding["rail_capacity_mm"] == 216
        and binding["total_capacity_mm"] == 648,
        "HOLD_KRN36_CAPACITY_BINDING_CONFLICT",
    )
    din = [u for u in units if u["envelope"]["mounting"] == "DIN"]
    panels = [u for u in units if u["envelope"]["mounting"] == "PANEL"]
    occupied = sum((u["envelope"]["dimensions_mm"][1] for u in din), Decimal(0))
    capacity = Decimal(648)
    proof: dict[str, Any] = {
        "status": "UNKNOWN",
        "reason": "HOLD_DIN_CAPACITY_GEOMETRY_UNSUPPORTED",
        "capacity_only": True,
        "rail_count": 3,
        "rail_capacity_mm": Decimal(216),
        "capacity_mm": capacity,
        "occupied_mm": occupied,
        "free_mm": capacity - occupied,
        "reserve_denominator_mm": capacity,
        "free_percent": (capacity - occupied) * 100 / capacity,
        "reserve_required_percent": Decimal(25),
        "rows": None,
        "units": [
            {
                "component_id": u["component_id"],
                "unit": u["unit"],
                "actual_width_mm": u["envelope"]["dimensions_mm"][1],
            }
            for u in din
        ],
        "panel_assessment": {
            "unit_count": len(panels),
            "status": "UNKNOWN" if panels else "NOT_APPLICABLE",
            "reason": (
                "HOLD_PANEL_GEOMETRY_AND_INDEPENDENT_RESERVE_EVIDENCE_REQUIRED"
                if panels
                else None
            ),
        },
        "planning_coordinates": "RELATIVE_ROW_ASSIGNMENT_ONLY_NOT_FACTORY_COORDINATES",
    }
    if any(
        any(
            u["envelope"]["clearance_mm"]
            + u["envelope"]["pair_gap_mm"]
            + [u["envelope"]["extra_gap_mm"]]
        )
        or u["envelope"]["dimensions_mm"][0] > planning.PITCH
        for u in din
    ):
        return proof
    if occupied * 4 > capacity * 3:
        proof.update(status="NO_FIT", reason="DIN_TOTAL_RESERVE_INSUFFICIENT")
        return proof
    if any(u["envelope"]["dimensions_mm"][1] > 216 for u in din):
        proof.update(status="NO_FIT", reason="DIN_ROW_CAPACITY_INSUFFICIENT")
        return proof
    try:
        packed = (
            planning.partition(din, 3, planning.PITCH, exact.Budget()) if din else None
        )
    except SizingHold as exc:
        proof["reason"] = str(exc)
        return proof
    assignments = packed[1] if packed else [[], [], []]
    rows: list[dict[str, Any]] = []
    for index, assigned in enumerate(assignments):
        load = Decimal(0)
        row_units = []
        for unit in assigned:
            width = unit["envelope"]["dimensions_mm"][1]
            row_units.append(
                {
                    "component_id": unit["component_id"],
                    "unit": unit["unit"],
                    "actual_width_mm": width,
                    "relative_x_mm": load,
                }
            )
            load += width
        rows.append(
            {
                "row": index + 1,
                "relative_rail_datum_mm": index * planning.PITCH,
                "capacity_mm": Decimal(216),
                "occupied_mm": load,
                "free_mm": Decimal(216) - load,
                "units": row_units,
            }
        )
    proof["rows"] = rows
    if any(row["occupied_mm"] > 216 for row in rows):
        proof.update(status="NO_FIT", reason="DIN_ROW_CAPACITY_INSUFFICIENT")
    else:
        proof.update(status="PASS", reason="DIN_CAPACITY_AND_TOTAL_RESERVE_PROVEN")
    return proof


def select(case_id: str, items: Any, request: Any = None) -> dict[str, Any]:
    req = validate_request(
        case_id, request_for(case_id, items) if request is None else request
    )
    require(isinstance(items, (list, tuple)) and bool(items), "HOLD_EMPTY_COMPOSITION")
    ids = [item["item_id"] for item in items]
    require(len(ids) == len(set(ids)), "HOLD_DUPLICATE_ITEM")
    require(set(req["source_facts"]) == set(ids), "HOLD_SOURCE_FACT_COVERAGE")
    current = req["schema_version"] != REQUEST_SCHEMA
    capacity = req["schema_version"] == CURRENT_REQUEST_SCHEMA
    technical = capacity or req["schema_version"] == TECHNICAL_REQUEST_SCHEMA
    source_version = req["metal_source"]["version"] if current else None
    inventory = (
        catalogue.inventory(
            source_version=source_version,
            technical_binding=True,
            **({"capacity_binding": True} if capacity else {}),
        )
        if technical
        else (
            catalogue.inventory(source_version=source_version)
            if current
            else catalogue.inventory()
        )
    )
    records = inventory["records"]
    require(bool(records), "HOLD_EMPTY_CATALOGUE")
    classes = evidence.envelopes(req["devices"])
    selections = []
    for item in items:
        units = planning.prepare(item, req["devices"], classes)
        fact = planning.source_fact(case_id, item, req["source_facts"][item["item_id"]])
        planning_error = None
        try:
            shapes, panel = planning.planning_shapes(
                units,
                max(
                    Decimal(c["dimensions_mm"][0])
                    for c in records
                    if c["dimensions_mm"] is not None
                ),
            )
        except SizingHold as exc:
            shapes, panel, planning_error = [], None, str(exc)
        outcomes = [
            candidate(record, units, shapes, panel, fact, planning_error)
            for record in records
        ]
        require(
            fact
            == planning.source_fact(
                case_id, item, req["source_facts"][item["item_id"]]
            ),
            "HOLD_SOURCE_FACT_DRIFT",
        )
        require(
            classes == evidence.envelopes(req["devices"]), "HOLD_DEVICE_ENVELOPE_DRIFT"
        )
        reread = (
            catalogue.inventory(
                source_version=source_version,
                technical_binding=True,
                **({"capacity_binding": True} if capacity else {}),
            )
            if technical
            else (
                catalogue.inventory(source_version=source_version)
                if current
                else catalogue.inventory()
            )
        )
        require(inventory == reread, "HOLD_CATALOGUE_SOURCE_DRIFT")
        validate_request(case_id, req)
        for record in records:
            if record["cabinet_code"] in catalogue.MOUNTING_SOURCES:
                evidence.read(
                    catalogue.MOUNTING_SOURCES[record["cabinet_code"]],
                    "catalogue_mounting",
                )
        possible = [c for c in outcomes if c["status"] != "NO_FIT"]
        feasible = [c for c in outcomes if c["status"] == "FIT"]
        frontier = [
            c["cabinet_code"]
            for c in possible
            if c["dimensions_mm"] is None
            or not any(
                o["dimensions_mm"] is not None
                and all(
                    a <= b
                    for a, b in zip(o["dimensions_mm"], c["dimensions_mm"], strict=True)
                )
                and o["dimensions_mm"] != c["dimensions_mm"]
                for o in possible
            )
        ]
        details = {
            "item_id": item["item_id"],
            "apparatus_sha256": apparatus_hash(item),
            "candidate_outcomes": outcomes,
            "frontier": frontier,
            "catalogue": inventory,
            "physical_installation_status": "HOLD",
        }
        unknown = [c for c in outcomes if c["status"] == "UNKNOWN"]
        if unknown:
            hold(
                "HOLD_CATALOGUE_UNRESOLVED_CANDIDATES:" + unknown[0]["reasons"][0],
                details,
            )
        if not feasible:
            hold(
                (
                    "HOLD_SOURCE_DIMENSIONS_INCOMPATIBLE"
                    if fact["dimensions_status"] == "EXPLICIT"
                    else "HOLD_NO_FITTING_CATALOGUE_CABINET"
                ),
                details,
            )
        minima = [
            c
            for c in feasible
            if all(
                all(
                    a <= b
                    for a, b in zip(c["dimensions_mm"], o["dimensions_mm"], strict=True)
                )
                for o in feasible
            )
        ]
        if len(minima) != 1:
            hold("HOLD_SMALLEST_CABINET_AMBIGUOUS", details)
        selected = minima[0]
        prior = fact["prior_approval"]
        if prior["status"] == "APPROVED" and (
            prior["cabinet_code"] != selected["cabinet_code"]
            or prior["dimensions_mm"] != selected["dimensions_mm"]
        ):
            hold("HOLD_CABINET_CHANGE_REQUIRES_NEW_HUMAN_APPROVAL", details)
        cabinet = {
            "cabinet_code": selected["cabinet_code"],
            "cabinet_label": selected["cabinet_label"],
            "cabinet_type": selected["family"],
            "dimensions_mm": selected["dimensions_mm"],
        }
        selections.append(
            {
                "item_id": item["item_id"],
                "apparatus_sha256": apparatus_hash(item),
                "cabinet": cabinet,
                "layout": selected["layout"],
                "preliminary_only": True,
                "unverified": {
                    "cabinet_ip": None,
                    "installation_compatibility": None,
                    "factory_layout": None,
                    "physical_rail_anchors": None,
                },
                "provenance": dict(details, source_fact=fact),
            }
        )
    return dict(
        exact.serial(
            {
                "schema_version": (
                    CURRENT_SCHEMA
                    if capacity
                    else (
                        TECHNICAL_SCHEMA
                        if technical
                        else VERSIONED_SCHEMA if current else SCHEMA
                    )
                ),
                "case_id": case_id,
                "items": selections,
                "sources": req,
            }
        )
    )
