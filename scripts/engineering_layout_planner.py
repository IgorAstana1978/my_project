"""Source-bound, read-only exploratory joint layouts; always physical HOLD."""

from __future__ import annotations

import argparse
import copy
import hashlib
import html
import io
import json
import re
import stat
import sys
from collections.abc import Sequence
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any

import cabinet_preliminary_recommendations as advisory
import cabinet_sizing as strict
import cabinet_sizing_evidence as evidence
import cabinet_sizing_pragmatic as planning
import engineering_layout_geometry as geometry
from governed_case_intake import _pairs

SCHEMA = "engineering_layout.assessment.v0.1"
REQUEST_SCHEMA = "engineering_layout.scenarios.v0.1"
POLICY = "joint-shelves-v0.1/source-envelope-v0.2/independent-reserve25"
REAL_GAPS = [
    "USEFUL_INTERIOR_NOT_PROVEN",
    "MOUNTING_ANCHORS_AND_COMPATIBILITY_UNKNOWN",
    "IP_INSTALLATION_FACTORY_LAYOUT_UNKNOWN",
    "DEVICE_PORT_ORIGINS_UNKNOWN",
    "TERMINATION_AND_SECTION_COMPATIBILITY_UNKNOWN",
    "ENTRY_GEOMETRY_UNKNOWN",
    "BEND_RADIUS_UNKNOWN",
    "ROUTING_MEDIUM_DIAMETERS_FILL_UNKNOWN",
    "OPERATIONAL_RESERVE_REFERENCE_NOT_SOURCE_PROVEN",
]
PARAMETERS = {
    "insets_mm",
    "mount_offset_mm",
    "duct_width_mm",
    "duct_depth_mm",
    "connection_height_mm",
    "connection_depth_mm",
    "service_height_mm",
    "access_width_mm",
    "assigned_width_mm",
    "auxiliary_width_mm",
    "future_din_hwd_mm",
    "future_panel_hwd_mm",
}
ZERO_PARAMETERS = {"mount_offset_mm", "access_width_mm", "assigned_width_mm"}


def normalize_scenarios(request: Any) -> dict[str, Any]:
    if request is None:
        return {"schema_version": REQUEST_SCHEMA, "profiles": []}
    strict.require(
        isinstance(request, dict)
        and set(request) == {"schema_version", "profiles"}
        and request["schema_version"] == REQUEST_SCHEMA
        and isinstance(request["profiles"], list)
        and 0 < len(request["profiles"]) <= 16,
        "HOLD_SCENARIO_REQUEST_SCHEMA",
    )
    result = []
    for profile in request["profiles"]:
        strict.require(
            isinstance(profile, dict)
            and set(profile)
            == {"id", "author", "version", "rationale", "unit", "parameters"}
            and all(
                isinstance(profile[k], str)
                and bool(profile[k].strip())
                and len(profile[k]) <= 1000
                for k in ("id", "author", "version", "rationale")
            )
            and profile["unit"] == "mm"
            and isinstance(profile["parameters"], dict)
            and set(profile["parameters"]) in (PARAMETERS, PARAMETERS | {"routing"}),
            "HOLD_SCENARIO_PROFILE_SCHEMA",
        )
        normalized = copy.deepcopy(profile)
        parameters = normalized["parameters"]
        try:
            for key in PARAMETERS:
                value = parameters[key]
                if key == "insets_mm":
                    parameters[key] = geometry.vector(value, 6, zero=True)
                elif key.startswith("future_"):
                    parameters[key] = (
                        None if value is None else geometry.vector(value, 3)
                    )
                else:
                    parameters[key] = geometry.number(
                        value, zero=key in ZERO_PARAMETERS
                    )
            if "routing" in parameters:
                route = parameters["routing"]
                strict.require(
                    isinstance(route, dict)
                    and set(route)
                    == {
                        "medium",
                        "diameter_mm",
                        "count",
                        "fill_fraction",
                        "usable_width_mm",
                        "usable_depth_mm",
                        "bend_radius_mm",
                        "termination_max_section_mm2",
                    }
                    and route["medium"] in {"WHOLE_CABLE", "INSULATED_CORES"}
                    and type(route["count"]) is int
                    and 0 < route["count"] <= 4096,
                    "HOLD_SCENARIO_ROUTING_SCHEMA",
                )
                for key in set(route) - {"medium", "count"}:
                    route[key] = geometry.number(route[key])
                strict.require(
                    route["fill_fraction"] <= 1
                    and route["usable_width_mm"] <= parameters["duct_width_mm"]
                    and route["usable_depth_mm"] <= parameters["duct_depth_mm"],
                    "HOLD_SCENARIO_ROUTING_BOUNDS",
                )
        except (ValueError, TypeError, KeyError) as exc:
            raise strict.SizingHold("HOLD_SCENARIO_NUMERIC_SCHEMA") from exc
        result.append(geometry.serial(normalized))
    strict.require(
        len({p["id"] for p in result}) == len(result), "HOLD_SCENARIO_DUPLICATE_ID"
    )
    return {
        "schema_version": REQUEST_SCHEMA,
        "profiles": sorted(result, key=lambda p: p["id"]),
    }


def source_units(item: Any, binding: Any) -> list[dict[str, Any]]:
    classes = evidence.envelopes(binding)
    return list(
        geometry.serial(
            [
                {
                    "id": f"{u['component_id']}:{u['unit']}",
                    "mounting": u["envelope"]["mounting"],
                    "dimensions_mm": u["envelope"]["dimensions_mm"],
                    "clearance_mm": u["envelope"]["clearance_mm"],
                    "pair_gap_mm": u["envelope"]["pair_gap_mm"],
                    "extra_gap_mm": u["envelope"]["extra_gap_mm"],
                    "body_reference": u["envelope"]["body_reference"],
                    "class_id": u["envelope"]["class_id"],
                    "source_envelope": u["envelope"],
                    "source_designation": _designation(item, u["component_id"]),
                }
                for u in planning.prepare(item, binding, classes)
            ]
        )
    )


def _designation(item: Any, component_id: str) -> str | None:
    component = next(c for c in item["components"] if c["component_id"] == component_id)
    match = re.match(
        r"(QF\d+)\s",
        component.get("component_label", component.get("component_label_guess", "")),
    )
    return match.group(1) if match else None


def project_cables(case_id: str, item: Any) -> dict[str, Any]:
    """Only admitted WU15 p1 QF0..20. Other pages deliberately remain unknown.

    Explicit reviewed row tuples corroborate extraction; a parser match alone
    cannot admit new facts. Draft/apphash and PDF bytes are rechecked each call.
    """
    if case_id != evidence.WU15_CASE:
        return {
            "status": "UNKNOWN",
            "first_missing": "PROJECT_CABLE_MAPPING_NOT_ADMITTED",
            "outgoing": [],
            "feeder": None,
        }
    fact = evidence.pragmatic_source_fact(
        case_id, item, evidence.pragmatic_default_binding()
    )
    if item["item_id"] != "ITEM-001":
        return {
            "status": "UNKNOWN",
            "first_missing": "PROJECT_CABLE_MAPPING_NOT_ADMITTED",
            "outgoing": [],
            "feeder": None,
            "source_fact": fact,
        }
    from pypdf import PdfReader

    binding = fact["raw_sources"][0]
    raw = evidence.safe_bytes(Path(binding["path"]), binding["sha256"])
    text = PdfReader(io.BytesIO(raw)).pages[0].extract_text()
    strict.require(
        isinstance(text, str) and "QF0ВА88-323P 63А" in text and "ЩО6" in text,
        "HOLD_PROJECT_CABLE_SOURCE_LOCATOR",
    )
    expected = [
        (1, 16, 1, "4", 50, 1),
        (2, 16, 2, "2.5", 45, 2),
        (3, 16, 3, "2.5", 35, 4),
        (4, 16, 1, "2.5", 50, 5),
        (5, 16, 2, "2.5", 35, 13),
        (6, 16, 3, "2.5", 40, 10),
        (7, 20, 1, "6", 70, 9),
        (8, 20, 3, "6", 65, 8),
        (9, 20, 3, "6", 70, 7),
        (10, 20, 1, "6", 90, 6),
        (11, 20, 2, "6", 70, 11),
        (12, 16, 3, "2.5", 30, 12),
        (13, 16, 1, "4", 60, 3),
        (14, 16, 2, "4", 53, 14),
        (15, 16, 3, "2.5", 45, 15),
        (16, 16, 1, "2.5", 60, 16),
        (17, 16, 2, "2.5", 40, 17),
        (18, 16, 3, "2.5", 35, 18),
        (19, 16, 1, "4", 60, 19),
        (20, 16, 2, "4", 70, 20),
    ]
    matches = list(re.finditer(r"QF(\d+)", text))
    strict.require(
        [int(m.group(1)) for m in matches] == list(range(21)),
        "HOLD_PROJECT_CABLE_QF_COVERAGE",
    )
    outgoing: list[dict[str, Any]] = []
    for index, current, phase, section, length, group in expected:
        start = matches[index].start()
        end = matches[index + 1].start() if index < 20 else text.index("Инв.", start)
        row = text[start:end].strip()
        pattern = (
            rf"QF{index}АВДТ32\s*2PC{current}/30мАL{phase}"
            rf"[\d,]+-0,8-[\d,]+-{length}[\d,]+-ВВГнг\(А\)-LS\s*3х"
            + re.escape(section.replace(".", ","))
            + rf"Гр\.Р{group}[\d,]+"
        )
        strict.require(
            re.match(pattern, row) is not None,
            f"HOLD_PROJECT_CABLE_ROW_MAPPING:QF{index}",
        )
        outgoing.append(
            {
                "qf": f"QF{index}",
                "group": f"Р{group}",
                "current_a": current,
                "phase": f"L{phase}",
                "mark": "ВВГнг(А)-LS",
                "cores": 3,
                "section_mm2": section,
                "length_m": length,
                "raw": row,
                "locator": {"page": 1, "qf": f"QF{index}", "source": binding},
                "endpoints": [
                    f"QF{index}:L",
                    f"QF{index}:N_individual_RCBO",
                    f"QF{index}:PE",
                ],
            }
        )
    strict.require(
        len({r["group"] for r in outgoing}) == 20
        and sum(r["length_m"] for r in outgoing) == 1073,
        "HOLD_PROJECT_CABLE_TOTAL",
    )
    strict.require(
        evidence.safe_bytes(Path(binding["path"]), binding["sha256"]) == raw,
        "HOLD_PROJECT_CABLE_SOURCE_DRIFT",
    )
    return {
        "status": "SOURCE_BOUND_PARTIAL",
        "first_missing": "FEEDER_MARK_CORES_SECTION_UNKNOWN",
        "source_fact": fact,
        "source": binding,
        "page": 1,
        "outgoing": outgoing,
        "feeder": {
            "qf": "QF0",
            "apparatus": "ВА88-32 3P63A",
            "mark": None,
            "cores": None,
            "section_mm2": None,
        },
        "summary": {
            "outgoing_count": 20,
            "logical_core_endpoints": 60,
            "length_m": 1073,
            "section_counts": {"2.5": 10, "4": 5, "6": 5},
            "phase_counts": {"L1": 7, "L2": 6, "L3": 7},
        },
        "limitations": [
            "Logical endpoints are not glands or terminal BOM.",
            "Individual RCBO load neutrals remain separate; PE is a distinct role.",
            "Voltage-drop prefix is not count; PVC pipe is not cable diameter.",
        ],
    }


def _capacity(profile: Any, cables: Any) -> dict[str, Any]:
    route = profile["parameters"].get("routing")
    if route is None:
        return {
            "status": "UNKNOWN",
            "missing": [
                "ROUTING_MEDIUM_DIAMETERS_FILL_UNKNOWN",
                "BEND_RADIUS_UNKNOWN",
                "TERMINATION_SECTION_COMPATIBILITY_UNKNOWN",
            ],
        }
    required_count = cables.get("summary", {}).get(
        "logical_core_endpoints"
        if route["medium"] == "INSULATED_CORES"
        else "outgoing_count"
    )
    max_section = max(
        (Decimal(c["section_mm2"]) for c in cables["outgoing"]), default=None
    )
    # Upper bound for pi makes this one common-trunk area comparison conservative.
    occupied = (
        Decimal("3.141592653589794")
        * Decimal(route["diameter_mm"]) ** 2
        * route["count"]
        / 4
    )
    permitted = (
        Decimal(route["usable_width_mm"])
        * Decimal(route["usable_depth_mm"])
        * Decimal(route["fill_fraction"])
    )
    failures = []
    if required_count is not None and route["count"] < required_count:
        failures.append("SOURCE_ENDPOINT_COUNT_EXCEEDS_SCENARIO")
    if (
        max_section is not None
        and Decimal(route["termination_max_section_mm2"]) < max_section
    ):
        failures.append("SOURCE_SECTION_EXCEEDS_SCENARIO_TERMINATION")
    if occupied > permitted:
        failures.append("SCENARIO_DUCT_CROSS_SECTION_EXCEEDED")
    return dict(
        geometry.serial(
            {
                "status": (
                    "CONDITIONAL_AREA_OK"
                    if not failures
                    else "SCENARIO_CAPACITY_CONFLICT"
                ),
                "routing_inputs": route,
                "occupied_mm2_upper_bound": occupied,
                "permitted_mm2": permitted,
                "failed_constraints": failures,
                "scope": (
                    "One common-trunk uniform diameter hypothesis; absent feeder "
                    "excluded and remains UNKNOWN. No bend/path/aperture/port proof."
                ),
                "bend_status": "UNKNOWN_ACTUAL_PATH",
                "port_status": "UNKNOWN",
            }
        )
    )


def _coverage(advice: Any, case_id: str, items: Any) -> None:
    strict.require(
        advice.get("schema_version") == advisory.SCHEMA
        and advice.get("case_id") == case_id
        and isinstance(advice.get("strict_request"), dict),
        "HOLD_ENGINEERING_BASELINE_SCHEMA",
    )
    expected = {i["item_id"] for i in items}
    strict.require(
        len(advice["items"]) == len(items)
        and {i["item_id"] for i in advice["items"]} == expected,
        "HOLD_ENGINEERING_ITEM_COVERAGE",
    )
    for board in advice["items"]:
        candidates = board["candidates"]
        strict.require(
            len(candidates) == 70
            and len({c["cabinet_code"] for c in candidates}) == 70,
            "HOLD_ENGINEERING_CATALOGUE_COVERAGE",
        )
        item = next(i for i in items if i["item_id"] == board["item_id"])
        strict.require(
            board["apparatus_sha256"] == strict.apparatus_hash(item),
            "HOLD_ENGINEERING_APPARATUS_BINDING",
        )


def _assessment(
    candidate: Any, units: Any, fact: Any, cables: Any, profile: Any
) -> dict[str, Any]:
    real_missing = sorted(
        set(
            REAL_GAPS
            + ([cables["first_missing"]] if cables.get("first_missing") else [])
            + list(candidate.get("missing_evidence", []))
            + (candidate["reasons"] if candidate["status"] == "UNKNOWN" else [])
        )
    )
    base: dict[str, Any] = {
        "scenario_id": profile["id"] if profile else None,
        "real_status": "HOLD",
        "physical_status": "HOLD",
        "real_missing_evidence": real_missing,
        "routing_capacity": (
            _capacity(profile, cables) if profile else {"status": "UNKNOWN"}
        ),
        "model_missing_evidence": [
            "DEVICE_PORT_ORIGINS_UNKNOWN",
            "BEND_RADIUS_UNKNOWN",
            "ENTRY_APERTURE_UNKNOWN",
            "PHYSICAL_ROUTE_UNPROVEN",
        ],
        "source_lower_bounds": {
            "apparatus_hwd_mm": {u["id"]: u["dimensions_mm"] for u in units},
            "reserve": "DIN/PANEL independently >=25%; DIN pitch exactly140mm",
        },
    }
    if profile is None:
        return dict(
            base,
            status="UNKNOWN",
            first_missing="EXPLICIT_USEFUL_GEOMETRY_OR_SCENARIO_REQUIRED",
            witness=None,
            failed_constraints=[],
            search={"examined": 0, "global_optimum_proven": False},
        )
    failed = []
    dims = candidate["dimensions_mm"]
    if dims is None:
        failed.append("SOURCE_CANDIDATE_DIMENSIONS_UNKNOWN")
    if fact["dimensions_status"] == "EXPLICIT" and dims != fact["dimensions_mm"]:
        failed.append("SOURCE_EXACT_DIMENSIONS_ONLY")
    prior = fact["prior_approval"]
    if prior["status"] == "APPROVED" and (
        candidate["cabinet_code"] != prior["cabinet_code"]
        or dims != prior["dimensions_mm"]
    ):
        failed.append("CABINET_CHANGE_REQUIRES_HUMAN_APPROVAL")
    # Proven necessary constraints remain binding even under an explicit profile.
    necessary = {
        "SOURCE_EXACT_DIMENSIONS_ONLY",
        "DEVICE_EXCEEDS_PROVEN_OUTER_BOUND",
        "DIN_TOTAL_RESERVE_INSUFFICIENT",
        "DIN_ROW_CAPACITY_INSUFFICIENT",
        "PROVEN_MOUNTING_CLASS_INCOMPATIBLE",
        "PROVEN_INSTALLATION_INCOMPATIBLE",
        "PROVEN_ROW_CAPACITY_OR_GEOMETRY_INSUFFICIENT",
    }
    failed.extend(r for r in candidate["reasons"] if r in necessary)
    if failed:
        return dict(
            base,
            status="SOURCE_CONSTRAINT_HOLD",
            witness=None,
            failed_constraints=sorted(set(failed)),
            search={"examined": 0, "global_optimum_proven": False},
        )
    rail_limit = None
    capacity = candidate.get("din_capacity_binding")
    # Existing admitted catalogue provenance owns the exact KRN36 identity and
    # 3x216 constraints; never infer capacity from suffixes or outer dimensions.
    if candidate["cabinet_code"] == "CATALOGUE-KRN-ROW-64":
        strict.require(
            isinstance(capacity, dict)
            and candidate["dimensions_mm"] == [540, 330, 100]
            and candidate["technical_binding"]["rail_count"]
            == capacity["rail_count"]
            == 3
            and capacity["rail_capacity_mm"] == 216
            and capacity["total_capacity_mm"] == 648,
            "HOLD_ENGINEERING_KRN36_SOURCE_BINDING",
        )
        rail_limit = {
            "count": capacity["rail_count"],
            "length_mm": capacity["rail_capacity_mm"],
        }
    result = geometry.search_joint(dims, units, profile["parameters"], rail_limit)
    if result.get("witness") is not None:
        _bind_endpoints(result["witness"], units, cables)
        if result["witness"]["routing_topology"] == "DIN_SHARED_COLUMN_RISERS":
            base["model_missing_evidence"].append(
                "SHARED_DUCT_BRANCH_COMPATIBILITY_UNKNOWN"
            )
    if base["routing_capacity"].get("failed_constraints"):
        result["failed_constraints"].extend(
            base["routing_capacity"]["failed_constraints"]
        )
        result["status"] = "SCENARIO_CAPACITY_CONFLICT"
        result["witness"] = None
    if any(
        v["operational_status"] == "UNKNOWN"
        for v in (result.get("witness") or {}).get("reserve", {}).values()
    ):
        base["model_missing_evidence"].append("OPERATIONAL_RESERVE_REFERENCE_UNKNOWN")
    return dict(base, **result)


def _bind_endpoints(witness: Any, units: Any, cables: Any) -> None:
    """Logical functions follow actual reservation paths, never electrical proof."""
    graph = witness["graph"]
    neighbours: dict[str, set[str]] = {n: set() for n in graph["nodes"]}
    for a, b in graph["edges"]:
        neighbours[a].add(b)
        neighbours[b].add(a)

    def path(start: str, target: str) -> list[str]:
        queue = [[start]]
        visited = {start}
        for chain in queue:
            if chain[-1] == target:
                return chain
            for node in sorted(neighbours.get(chain[-1], set()) - visited):
                if node != target and node not in duct_ids:
                    continue
                visited.add(node)
                queue.append([*chain, node])
        return []

    duct_ids = {obj["id"] for obj in witness["objects"] if obj["kind"] == "DUCT"}
    graph["device_connections"] = [
        {
            "device_id": u["id"],
            "source_designation": u.get("source_designation"),
            "reservation_id": u["id"] + ":connection",
            "reservation_path_to_entry": path(u["id"] + ":connection", "entry"),
            "attachment_basis": "SCENARIO connection band; actual port origin UNKNOWN",
        }
        for u in units
    ]
    endpoints = []
    for cable in cables["outgoing"]:
        matching = [u for u in units if u.get("source_designation") == cable["qf"]]
        strict.require(len(matching) == 1, "HOLD_PROJECT_CABLE_APPARATUS_MAPPING")
        reservation = matching[0]["id"] + ":connection"
        for identity in cable["endpoints"]:
            target = "PE" if identity.endswith(":PE") else "entry"
            route = path(reservation, target)
            strict.require(bool(route), "HOLD_ENGINEERING_ENDPOINT_UNREACHABLE")
            endpoints.append(
                {
                    "id": identity,
                    "source_qf": cable["qf"],
                    "source_device_id": matching[0]["id"],
                    "section_mm2": cable["section_mm2"],
                    "path": [identity, *route],
                    "port_status": "UNKNOWN",
                    "basis": (
                        "SOURCE logical role + SCENARIO reservation attachment; "
                        "not electrical circuit or physical route proof"
                    ),
                }
            )
    graph["logical_endpoints"] = endpoints
    graph["neutral_strategy"] = (
        "Individual RCBO load N endpoints never merged with other load N or "
        "common N reservation. N is hypothetical upstream function only."
    )
    graph["physical_route_status"] = "UNKNOWN"


def _sensitivity(boards: Any, profiles: Any) -> list[dict[str, Any]]:
    if len(profiles) < 2:
        return []
    first = profiles[0]
    result = []
    for other in profiles[1:]:
        differences = {
            key: {
                first["id"]: first["parameters"].get(key),
                other["id"]: other["parameters"].get(key),
            }
            for key in sorted(set(first["parameters"]) | set(other["parameters"]))
            if first["parameters"].get(key) != other["parameters"].get(key)
        }
        changes = []
        for board in boards:
            candidates = []
            for c in board["candidates"]:
                a = next(v for v in c["assessments"] if v["scenario_id"] == first["id"])
                b = next(v for v in c["assessments"] if v["scenario_id"] == other["id"])
                candidates.append(
                    {
                        "cabinet_code": c["cabinet_code"],
                        "statuses": [a["status"], b["status"]],
                        "geometry_changed": a["witness"] != b["witness"],
                        "constraints_changed": a["failed_constraints"]
                        != b["failed_constraints"],
                    }
                )
            changes.append(
                {
                    "item_id": board["item_id"],
                    "changed_status_count": sum(
                        c["statuses"][0] != c["statuses"][1] for c in candidates
                    ),
                    "changed_geometry_count": sum(
                        c["geometry_changed"] for c in candidates
                    ),
                    "candidates": candidates,
                }
            )
        result.append(
            {
                "scenarios": [first["id"], other["id"]],
                "parameter_differences": differences,
                "items": changes,
            }
        )
    return result


def assess_composition(
    case_id: str, items: Any, scenarios: Any = None, strict_request: Any = None
) -> dict[str, Any]:
    """Assess all source-bound candidates; no caller cabinet or exact placements."""
    with localcontext():
        return _assess_composition(case_id, items, scenarios, strict_request)


def _assess_composition(
    case_id: str, items: Any, scenarios: Any, strict_request: Any
) -> dict[str, Any]:
    try:
        input_digest = strict.digest([case_id, items, scenarios, strict_request])
        normalized = normalize_scenarios(scenarios)
        before = advisory.recommend_composition(case_id, items, strict_request)
        _coverage(before, case_id, items)
        req = before["strict_request"]
        boards = []
        snapshots = []
        for item in sorted(items, key=lambda i: i["item_id"]):
            original = next(
                b for b in before["items"] if b["item_id"] == item["item_id"]
            )
            units = source_units(item, req["devices"])
            cables = project_cables(case_id, item)
            fact = planning.source_fact(
                case_id, item, req.get("source_facts", {}).get(item["item_id"])
            )
            snapshots.append([units, cables, fact])
            profiles = normalized["profiles"] or [None]
            candidates = [
                {
                    "cabinet_code": c["cabinet_code"],
                    "strict_baseline": copy.deepcopy(c),
                    "catalogue_identity": {
                        key: copy.deepcopy(c[key])
                        for key in (
                            "cabinet_code",
                            "cabinet_label",
                            "family",
                            "qualifier",
                            "dimensions_mm",
                            "row",
                            "source",
                            "source_issues",
                            "technical_binding",
                            "din_capacity_binding",
                        )
                        if key in c
                    },
                    "construction_compatibility": {
                        "status": "UNKNOWN",
                        "basis": (
                            "Source catalogue identity and partial bindings only; "
                            "a rectangular scenario witness does not prove "
                            "construction or mounting compatibility."
                        ),
                        "source_reasons": copy.deepcopy(c["reasons"]),
                        "missing_evidence": copy.deepcopy(
                            c.get("missing_evidence", [])
                        ),
                    },
                    "assessments": [
                        _assessment(c, units, fact, cables, p) for p in profiles
                    ],
                }
                for c in original["candidates"]
            ]
            boards.append(
                {
                    "item_id": item["item_id"],
                    "apparatus_sha256": strict.apparatus_hash(item),
                    "units": units,
                    "source_fact": fact,
                    "project_cables": cables,
                    "strict_status": original["strict_status"],
                    "real_status": "HOLD",
                    "physical_status": "HOLD",
                    "candidates": candidates,
                }
            )
        # Independent public source re-snapshot is outside the scenario loop.
        strict.require(
            before == advisory.recommend_composition(case_id, items, req),
            "HOLD_ENGINEERING_STRICT_SOURCE_DRIFT",
        )
        after = [
            [
                source_units(item, req["devices"]),
                project_cables(case_id, item),
                planning.source_fact(
                    case_id, item, req.get("source_facts", {}).get(item["item_id"])
                ),
            ]
            for item in sorted(items, key=lambda i: i["item_id"])
        ]
        strict.require(snapshots == after, "HOLD_ENGINEERING_SOURCE_DRIFT")
        strict.require(
            input_digest == strict.digest([case_id, items, scenarios, strict_request]),
            "HOLD_ENGINEERING_INPUT_DRIFT",
        )
        return {
            "schema_version": SCHEMA,
            "case_id": case_id,
            "policy": POLICY,
            "real_status": "HOLD",
            "physical_status": "HOLD",
            "stop_before": "HUMAN_APPROVAL_1",
            "boundary": (
                "SCENARIO / PHYSICAL HOLD; finite-family witness is not "
                "cabinet assignment, physical fit or approval."
            ),
            "strict_request": copy.deepcopy(req),
            "strict_baseline": before,
            "strict_baseline_sha256": strict.digest(before),
            "scenario_request": normalized,
            "scenario_request_sha256": strict.digest(normalized),
            "scenario_provenance": [
                {
                    "id": p["id"],
                    "origin": "SCENARIO",
                    "author": p["author"],
                    "version": p["version"],
                    "rationale": p["rationale"],
                    "unit": p["unit"],
                    "profile_sha256": strict.digest(p),
                    "human_approval": False,
                }
                for p in normalized["profiles"]
            ],
            "items": boards,
            "sensitivity": _sensitivity(boards, normalized["profiles"]),
        }
    except strict.SizingHold:
        raise
    except (KeyError, TypeError, ValueError, OSError, RecursionError) as exc:
        raise strict.SizingHold(
            "HOLD_ENGINEERING_MALFORMED_OR_UNAVAILABLE_SOURCE"
        ) from exc


def verify_assessment(report: Any, items: Any, *, expected_case_id: str) -> None:
    strict.require(
        isinstance(report, dict)
        and report.get("schema_version") == SCHEMA
        and report.get("case_id") == expected_case_id
        and isinstance(report.get("scenario_request"), dict)
        and isinstance(report["scenario_request"].get("profiles"), list)
        and isinstance(report.get("strict_request"), dict),
        "HOLD_ENGINEERING_REPORT_SCHEMA",
    )
    request = (
        report["scenario_request"] if report["scenario_request"]["profiles"] else None
    )
    fresh = assess_composition(
        expected_case_id, items, request, report["strict_request"]
    )
    strict.require(report == fresh, "HOLD_ENGINEERING_REPORT_DRIFT")


def format_assessment(report: Any, items: Any, *, expected_case_id: str) -> str:
    verify_assessment(report, items, expected_case_id=expected_case_id)
    lines = [
        "# Engineering Layout — SCENARIO / PHYSICAL HOLD",
        "",
        report["boundary"],
        "",
        "Stop before HUMAN_APPROVAL_1.",
        "",
    ]
    for board in report["items"]:
        lines.extend(
            [
                f"## {board['item_id']} — HOLD",
                "",
                "| Candidate / source label / family / qualifier | "
                "Construction compatibility | Scenario | Geometry | "
                "Routing topology | First constraint / gap |",
                "|---|---|---|---|---|---|",
            ]
        )
        for c in board["candidates"]:
            identity = c["catalogue_identity"]
            label = (
                " / ".join(
                    str(identity.get(key, ""))
                    for key in ("cabinet_code", "cabinet_label", "family", "qualifier")
                )
                .replace("|", "&#124;")
                .replace("\n", " ")
            )
            for a in c["assessments"]:
                reason = (a["failed_constraints"] or a["real_missing_evidence"])[0]
                topology = (a["witness"] or {}).get("routing_topology", "none")
                lines.append(
                    f"| {label} | {c['construction_compatibility']['status']} "
                    f"| {a['scenario_id'] or 'none'} "
                    f"| {a['status']} | {topology} | {reason} |"
                )
        lines.append("")
    lines.extend(
        [
            "Full sources, raw geometry, independent reserve, graph and sensitivity:",
            "",
            "```json",
            json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2),
            "```",
        ]
    )
    return "\n".join(lines)


def render_witness_svg(
    report: Any,
    items: Any,
    *,
    expected_case_id: str,
    item_id: str,
    cabinet_code: str,
    scenario_id: str,
) -> str:
    """Choose a view AFTER assessment; recompute, never select a cabinet."""
    verify_assessment(report, items, expected_case_id=expected_case_id)
    board = next((b for b in report["items"] if b["item_id"] == item_id), None)
    strict.require(board is not None, "HOLD_ENGINEERING_VIEW_ITEM")
    assert board is not None
    candidate = next(
        (c for c in board["candidates"] if c["cabinet_code"] == cabinet_code), None
    )
    strict.require(candidate is not None, "HOLD_ENGINEERING_VIEW_CANDIDATE")
    assert candidate is not None
    assessment = next(
        (a for a in candidate["assessments"] if a["scenario_id"] == scenario_id), None
    )
    strict.require(
        assessment is not None and assessment["witness"] is not None,
        "HOLD_ENGINEERING_VIEW_NO_WITNESS",
    )
    assert assessment is not None
    witness = assessment["witness"]
    origin = [Decimal(v) for v in witness["boundary"]["origin_xyz_mm"]]
    w, h, _ = [Decimal(v) for v in witness["boundary"]["size_xyz_mm"]]
    colors = {
        "KEEPOUT": "#d9976c",
        "DUCT": "#7cb4dc",
        "CONNECTION": "#cca3d9",
        "ACCESS": "#a6cd93",
        "ASSIGNED": "#bbb",
        "ENTRY": "#f1cf65",
        "AUXILIARY": "#c5b582",
    }
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w + 40} {h + 120}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<text x="10" y="20" font-size="14">'
        "SCENARIO / PHYSICAL HOLD — FOR VIEW ONLY</text>",
        '<text x="10" y="40" font-size="10">'
        f'{html.escape(item_id + " / " + cabinet_code + " / " + scenario_id)}</text>',
        '<text x="10" y="55" font-size="9">'
        "Scenario boundary from outer HWD; no factory/approval authority.</text>",
    ]
    for obj in witness["objects"]:
        x, y, _ = [Decimal(v) for v in obj["origin_xyz_mm"]]
        width, height, _ = obj["size_xyz_mm"]
        lines.append(
            f'<rect x="{x - origin[0] + 20}" y="{y - origin[1] + 80}" '
            f'width="{width}" height="{height}" '
            f'fill="{colors.get(obj["kind"], "#ddd")}" fill-opacity="0.6" '
            'stroke="#333" stroke-width="0.5"><title>'
            f'{html.escape(obj["id"] + " / " + obj["kind"])}</title></rect>'
        )
    lines.append("</svg>")
    return "\n".join(lines)


def _read_json(path: Path, sha: str | None = None) -> tuple[bytes, Any]:
    strict.require(path.is_absolute(), "HOLD_ENGINEERING_ABSOLUTE_INPUT_PATH")
    for ancestor in (path, *path.parents):
        info = ancestor.lstat()
        strict.require(
            not stat.S_ISLNK(info.st_mode)
            and not (getattr(info, "st_file_attributes", 0) & 0x400),
            "HOLD_ENGINEERING_REPARSE_INPUT",
        )
    raw = path.read_bytes()
    strict.require(len(raw) <= 16 * 1024 * 1024, "HOLD_ENGINEERING_INPUT_SIZE")
    if sha is not None:
        strict.require(
            hashlib.sha256(raw).hexdigest() == sha, "HOLD_ENGINEERING_INPUT_SHA"
        )
    return raw, json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only joint layout research; physical HOLD"
    )
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--composition-json", type=Path, required=True)
    parser.add_argument("--request-json", type=Path)
    parser.add_argument("--request-sha256")
    parser.add_argument("--scenarios-json", type=Path)
    parser.add_argument("--scenarios-sha256")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args(argv)
    try:
        for key in ("request", "scenarios"):
            strict.require(
                (getattr(args, key + "_json") is None)
                == (getattr(args, key + "_sha256") is None),
                "HOLD_ENGINEERING_PATH_AND_SHA_REQUIRED",
            )
        reads = []
        raw, data = _read_json(args.composition_json)
        reads.append((args.composition_json, None, raw))
        values = {}
        for key in ("request", "scenarios"):
            path, sha = getattr(args, key + "_json"), getattr(args, key + "_sha256")
            if path is not None:
                content, values[key] = _read_json(path, sha)
                reads.append((path, sha, content))
        report = assess_composition(
            args.case_id, data["items"], values.get("scenarios"), values.get("request")
        )
        verify_assessment(report, data["items"], expected_case_id=args.case_id)
        rendered = (
            format_assessment(report, data["items"], expected_case_id=args.case_id)
            if args.format == "markdown"
            else json.dumps(report, ensure_ascii=False, sort_keys=True)
        )
        for path, sha, content in reads:
            strict.require(
                _read_json(path, sha)[0] == content,
                "HOLD_ENGINEERING_INPUT_SOURCE_DRIFT",
            )
        print(rendered)
        return 2
    except strict.SizingHold as exc:
        reason = str(exc)
    except ValueError, KeyError, TypeError, OSError, UnicodeError, RecursionError:
        reason = "HOLD_ENGINEERING_MALFORMED_OR_UNAVAILABLE_SOURCE"
    print(json.dumps({"status": "HOLD", "first_missing": reason}, sort_keys=True))
    return 2


if __name__ == "__main__":
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
