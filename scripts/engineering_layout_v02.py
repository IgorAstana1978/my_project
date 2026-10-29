"""Explicit research v0.2; never selected by production or v0.1 APIs."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

import cabinet_sizing as strict
import cabinet_sizing_evidence as evidence
import engineering_layout_planner as legacy
import engineering_layout_v02_geometry as geometry

SCHEMA = "engineering_layout.assessment.v0.2"
REQUEST_SCHEMA = "engineering_layout.scenarios.v0.2"
POLICY = "research-v0.2/DIN150/free10/PANELfree25"
# Code-controlled admission only; an input approval flag cannot populate this.
FUTURE_POLICY_SOURCES: frozenset[tuple[str, str]] = frozenset()
PARAMETERS = {"insets_mm", "route_hwd_mm", "connection_hd_mm", "service_height_mm"}


def normalize(request: Any) -> dict[str, Any]:
    strict.require(
        isinstance(request, dict)
        and set(request) == {"schema_version", "profiles"}
        and request["schema_version"] == REQUEST_SCHEMA
        and isinstance(request["profiles"], list)
        and 0 < len(request["profiles"]) <= 16,
        "HOLD_V02_SCENARIOS",
    )
    result = copy.deepcopy(request)
    ids = set()
    for p in result["profiles"]:
        strict.require(
            isinstance(p, dict)
            and set(p) == {"id", "author", "rationale", "parameters", "future"}
            and all(
                isinstance(p[k], str) and 0 < len(p[k].strip()) <= 1000
                for k in ("id", "author", "rationale")
            )
            and p["id"] not in ids,
            "HOLD_V02_PROFILE",
        )
        ids.add(p["id"])
        q = p["parameters"]
        strict.require(
            isinstance(q, dict) and set(q) == PARAMETERS, "HOLD_V02_PARAMETERS"
        )
        q["insets_mm"] = geometry.g.vector(q["insets_mm"], 6, zero=True)
        strict.require(
            isinstance(q["route_hwd_mm"], dict)
            and set(q["route_hwd_mm"]) == set(geometry.METHODS),
            "HOLD_V02_METHOD_ENVELOPES",
        )
        q["route_hwd_mm"] = {
            method: geometry.g.vector(value, 2)
            for method, value in q["route_hwd_mm"].items()
        }
        q["connection_hd_mm"] = geometry.g.vector(q["connection_hd_mm"], 2)
        q["service_height_mm"] = geometry.g.number(q["service_height_mm"], zero=True)
        f = p["future"]
        strict.require(
            isinstance(f, dict)
            and set(f) == {"status", "reference_hwd_mm", "policy_binding"}
            and f["status"]
            in {"REQUIRED", "NOT_REQUIRED_BY_AUTHORIZED_POLICY", "UNKNOWN"}
            and isinstance(f["reference_hwd_mm"], dict)
            and set(f["reference_hwd_mm"]) <= {"DIN", "PANEL"},
            "HOLD_V02_FUTURE",
        )
        for kind, ref in f["reference_hwd_mm"].items():
            f["reference_hwd_mm"][kind] = geometry.g.vector(ref, 3)
        if f["status"] == "NOT_REQUIRED_BY_AUTHORIZED_POLICY":
            b = f["policy_binding"]
            strict.require(
                isinstance(b, dict)
                and set(b) == {"path", "sha256"}
                and all(isinstance(b[k], str) for k in b)
                and (b["path"], b["sha256"]) in FUTURE_POLICY_SOURCES,
                "HOLD_V02_UNAUTHORIZED_FUTURE_POLICY",
            )
            data = json.loads(
                evidence.safe_bytes(Path(b["path"]), b["sha256"]),
                object_pairs_hook=legacy._pairs,
            )
            strict.require(
                data
                == {
                    "policy": POLICY,
                    "future_reference": "NOT_REQUIRED_BY_AUTHORIZED_POLICY",
                },
                "HOLD_V02_FUTURE_POLICY_CONTENT",
            )
            strict.require(not f["reference_hwd_mm"], "HOLD_V02_FUTURE")
        else:
            strict.require(f["policy_binding"] is None, "HOLD_V02_FUTURE")
            strict.require(
                f["status"] != "UNKNOWN" or not f["reference_hwd_mm"], "HOLD_V02_FUTURE"
            )
    return dict(geometry.g.serial(result))


def assess_composition(
    case_id: str, items: Any, scenarios: Any, strict_request: Any = None
) -> dict[str, Any]:
    try:
        before = strict.digest([items, scenarios, strict_request])
        request = normalize(scenarios)
        baseline = legacy.assess_composition(
            case_id, items, strict_request=strict_request
        )
        boards = []
        for b in baseline["items"]:
            results = []
            for c in b["candidates"]:
                source = c["strict_baseline"]
                capacity = source.get("din_capacity_binding")
                limit = (
                    {
                        "count": capacity["rail_count"],
                        "length_mm": capacity["rail_capacity_mm"],
                    }
                    if capacity
                    else None
                )
                for p in request["profiles"]:
                    if p["future"]["status"] == "REQUIRED":
                        strict.require(
                            {u["mounting"] for u in b["units"]}
                            <= set(p["future"]["reference_hwd_mm"]),
                            "HOLD_V02_MISSING_REQUIRED_REFERENCE",
                        )
                    for method in geometry.METHODS:
                        necessary = set(source["reasons"]) & {
                            "SOURCE_EXACT_DIMENSIONS_ONLY",
                            "DEVICE_EXCEEDS_PROVEN_OUTER_BOUND",
                            "DIN_TOTAL_RESERVE_INSUFFICIENT",
                            "DIN_ROW_CAPACITY_INSUFFICIENT",
                            "PROVEN_MOUNTING_CLASS_INCOMPATIBLE",
                            "PROVEN_INSTALLATION_INCOMPATIBLE",
                            "PROVEN_ROW_CAPACITY_OR_GEOMETRY_INSUFFICIENT",
                        }
                        # Recompute the reserve threshold; preserve necessary bounds.
                        if capacity and sum(
                            geometry.g.number(u["dimensions_mm"][1])
                            for u in b["units"]
                            if u["mounting"] == "DIN"
                        ) <= geometry.g.number(capacity["total_capacity_mm"]) * (
                            1 - geometry.DIN_FREE
                        ):
                            necessary.discard("DIN_TOTAL_RESERVE_INSUFFICIENT")
                        fact = b["source_fact"]
                        prior = fact["prior_approval"]
                        if prior["status"] == "APPROVED" and (
                            prior["cabinet_code"] != c["cabinet_code"]
                            or prior["dimensions_mm"] != source["dimensions_mm"]
                        ):
                            necessary.add("CABINET_CHANGE_REQUIRES_HUMAN_APPROVAL")
                        result = (
                            {
                                "status": "SOURCE_CONSTRAINT_HOLD",
                                "reasons": sorted(necessary),
                            }
                            if necessary
                            else geometry.evaluate(
                                source["dimensions_mm"],
                                b["units"],
                                dict(
                                    p["parameters"],
                                    route_hwd_mm=p["parameters"]["route_hwd_mm"][
                                        method
                                    ],
                                ),
                                p["future"],
                                limit,
                            )
                        )
                        results.append(
                            {
                                "cabinet_code": c["cabinet_code"],
                                "profile": p["id"],
                                "method": method,
                                "route_basis": "SCENARIO_ENVELOPE",
                                "method_envelope_mm": p["parameters"]["route_hwd_mm"][
                                    method
                                ],
                                "result": result,
                                "physical_status": "HOLD",
                                "missing_evidence": [
                                    "FACTORY_INTERIOR_AND_MOUNTING",
                                    "ACTUAL_PORTS_AND_TERMINATIONS",
                                    "ROUTE_FASTENING_AND_PROTECTION",
                                    "BEND_FILL_THERMAL_COMPATIBILITY",
                                    "IP_INSTALLATION",
                                    b["project_cables"].get("first_missing"),
                                ],
                                "electrical_functions": {
                                    "N": "SEPARATE_RCBO_LOAD_NEUTRALS",
                                    "PE": "SEPARATE_PROTECTIVE_FUNCTION",
                                    "distribution": "FUNCTION_NOT_ASSIGNED_PRODUCT",
                                },
                            }
                        )
            boards.append(
                {
                    "item_id": b["item_id"],
                    "apparatus_sha256": b["apparatus_sha256"],
                    "assessments": results,
                }
            )
        strict.require(request == normalize(scenarios), "HOLD_V02_POLICY_DRIFT")
        strict.require(
            baseline
            == legacy.assess_composition(
                case_id, items, strict_request=baseline["strict_request"]
            ),
            "HOLD_V02_SOURCE_DRIFT",
        )
        strict.require(
            before == strict.digest([items, scenarios, strict_request]),
            "HOLD_V02_INPUT_DRIFT",
        )
        return {
            "schema_version": SCHEMA,
            "case_id": case_id,
            "policy": POLICY,
            "request": request,
            "source_baseline": baseline,
            "source_baseline_sha256": strict.digest(baseline),
            "physical_status": "HOLD",
            "stop_before": "HUMAN_APPROVAL_1",
            "items": boards,
        }
    except strict.SizingHold:
        raise
    except (KeyError, TypeError, ValueError, OSError, RecursionError) as ex:
        raise strict.SizingHold("HOLD_V02_INVALID_OR_UNAVAILABLE_EVIDENCE") from ex


def verify_assessment(report: Any, items: Any, *, expected_case_id: str) -> None:
    strict.require(
        isinstance(report, dict)
        and report.get("schema_version") == SCHEMA
        and report.get("case_id") == expected_case_id
        and isinstance(report.get("source_baseline"), dict)
        and isinstance(report.get("request"), dict),
        "HOLD_V02_REPORT",
    )
    strict.require(
        report
        == assess_composition(
            expected_case_id,
            items,
            report.get("request"),
            report.get("source_baseline", {}).get("strict_request"),
        ),
        "HOLD_V02_REPORT_DRIFT",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--composition-json", type=Path, required=True)
    parser.add_argument("--scenarios-json", type=Path, required=True)
    parser.add_argument("--scenarios-sha256", required=True)
    args = parser.parse_args()
    try:
        raw, data = legacy._read_json(args.composition_json)
        sr, scenarios = legacy._read_json(args.scenarios_json, args.scenarios_sha256)
        report = assess_composition(args.case_id, data["items"], scenarios)
        strict.require(
            raw == args.composition_json.read_bytes()
            and sr == args.scenarios_json.read_bytes(),
            "HOLD_V02_INPUT_DRIFT",
        )
        print(json.dumps(report, ensure_ascii=False))
    except (strict.SizingHold, KeyError, TypeError, ValueError, OSError) as ex:
        print(json.dumps({"physical_status": "HOLD", "first_missing": str(ex)}))
    return 2


if __name__ == "__main__":
    configure = getattr(sys.stdout, "reconfigure", None)
    if configure is not None:
        configure(encoding="utf-8")
    raise SystemExit(main())
