"""Read-only advice over source-verified strict diagnostics; never an A1 artifact."""

from __future__ import annotations

import argparse
import copy
import io
import json
import stat
import sys
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import cabinet_catalogue as catalogue
import cabinet_sizing as strict
import cabinet_sizing_catalogue as selector
from governed_case_intake import _pairs

SCHEMA = "cabinet_sizing.preliminary_recommendations.v0.1"
BOUNDARY = (
    "Предварительный локальный shortlist по имеющимся доказательствам; "
    "не выбор корпуса, не подтверждение монтажа и не артефакт HUMAN_APPROVAL_1."
)
PLANNING_LIMITS = [
    "Внешние В×Ш×Г не доказывают внутреннее полезное пространство.",
    "Резерв METAL относится к планировочным прямоугольникам/DIN длине, "
    "а не к подтверждённой свободной площади корпуса.",
    "Геометрия кабелей, клемм и обслуживания, положение плоскости/смещения DIN, "
    "IP, монтажные анкеры и заводская компоновка требуют отдельных доказательств.",
    "Новые повороты аппаратов не исследованы; 90° mapping не утверждён.",
]


def _numbers(value: Any) -> list[Decimal]:
    strict.require(
        isinstance(value, list) and len(value) == 3, "HOLD_ADVISORY_DIMENSIONS"
    )
    try:
        strict.require(
            all(type(v) in (int, str) for v in value), "HOLD_ADVISORY_DIMENSIONS"
        )
        result = [Decimal(str(v)) for v in value]
        strict.require(
            all(v.is_finite() and v > 0 for v in result), "HOLD_ADVISORY_DIMENSIONS"
        )
        return result
    except InvalidOperation as exc:
        raise strict.SizingHold("HOLD_ADVISORY_DIMENSIONS") from exc


def _frontier(candidates: list[dict[str, Any]]) -> list[str]:
    """Necessary outer-axis partial order only; equality preserves identities."""
    return [
        c["cabinet_code"]
        for c in candidates
        if c["dimensions_mm"] is None
        or not any(
            o["dimensions_mm"] is not None
            and all(
                a <= b
                for a, b in zip(
                    _numbers(o["dimensions_mm"]),
                    _numbers(c["dimensions_mm"]),
                    strict=True,
                )
            )
            and _numbers(o["dimensions_mm"]) != _numbers(c["dimensions_mm"])
            for o in candidates
        )
    ]


def _layout_signature(layout: dict[str, Any]) -> dict[str, Any]:
    """Describe the existing proof; do not enumerate or rank new layouts."""
    return {
        "orientation": layout.get("orientation"),
        "zones": [
            {
                "kind": zone.get("kind"),
                "origin_mm": zone.get("origin_mm"),
                "din_row_count": (
                    len(zone.get("row_datums_mm", []))
                    if zone.get("kind") == "DIN"
                    else None
                ),
            }
            for zone in layout.get("zones", [])
        ],
        "placement_kinds": sorted(
            {p["zone"] for p in layout.get("placements", []) if "zone" in p}
        ),
    }


def _validate_details(details: Any, item: Any, inventory: Any) -> None:
    strict.require(
        isinstance(details, dict), "HOLD_ADVISORY_COMPLETE_DIAGNOSTICS_REQUIRED"
    )
    strict.require(
        details.get("item_id") == item["item_id"]
        and details.get("apparatus_sha256") == strict.apparatus_hash(item)
        and details.get("catalogue") == inventory
        and isinstance(details.get("physical_installation_status"), str),
        "HOLD_ADVISORY_STRICT_BINDING",
    )
    outcomes = details.get("candidate_outcomes")
    strict.require(
        isinstance(outcomes, list) and len(outcomes) == 70,
        "HOLD_ADVISORY_CATALOGUE_COVERAGE",
    )
    expected = {r["cabinet_code"]: r for r in inventory["records"]}
    codes = [c["cabinet_code"] for c in outcomes]
    strict.require(
        len(set(codes)) == 70 and set(codes) == set(expected),
        "HOLD_ADVISORY_CATALOGUE_COVERAGE",
    )
    strict.require(
        isinstance(details.get("frontier"), list)
        and len(set(details["frontier"])) == len(details["frontier"])
        and set(details["frontier"]) <= set(codes),
        "HOLD_ADVISORY_STRICT_FRONTIER",
    )
    for candidate in outcomes:
        record = expected[candidate["cabinet_code"]]
        strict.require(
            all(candidate.get(k) == v for k, v in record.items()),
            "HOLD_ADVISORY_CANDIDATE_SOURCE_BINDING",
        )
        strict.require(
            candidate.get("status") in {"FIT", "NO_FIT", "UNKNOWN"}
            and isinstance(candidate.get("reasons"), list)
            and bool(candidate["reasons"])
            and all(isinstance(r, str) and r for r in candidate["reasons"])
            and isinstance(candidate.get("physical_installation_status"), str)
            and (
                candidate.get("layout") is None or isinstance(candidate["layout"], dict)
            ),
            "HOLD_ADVISORY_CANDIDATE_SCHEMA",
        )
        if candidate["dimensions_mm"] is not None:
            _numbers(candidate["dimensions_mm"])
        if "din_capacity_assessment" in candidate:
            partial = candidate["din_capacity_assessment"]
            strict.require(
                isinstance(partial, dict)
                and partial.get("status") in {"PASS", "NO_FIT", "UNKNOWN"},
                "HOLD_ADVISORY_PARTIAL_PROOF_SCHEMA",
            )
        layout = candidate.get("layout")
        if layout is not None:
            strict.require(
                isinstance(layout.get("zones", []), list)
                and all(
                    isinstance(zone, dict)
                    and isinstance(zone.get("kind"), str)
                    and isinstance(zone.get("row_datums_mm", []), list)
                    for zone in layout.get("zones", [])
                )
                and isinstance(layout.get("placements", []), list)
                and all(
                    isinstance(placement, dict)
                    for placement in layout.get("placements", [])
                ),
                "HOLD_ADVISORY_LAYOUT_SCHEMA",
            )
        if candidate["status"] == "FIT":
            strict.require(
                candidate["dimensions_mm"] is not None
                and isinstance(candidate["layout"], dict)
                and isinstance(candidate["layout"].get("reserve"), dict)
                and bool(candidate["layout"]["reserve"])
                and all(
                    isinstance(proof, dict) and bool(proof)
                    for proof in candidate["layout"]["reserve"].values()
                )
                and bool(
                    candidate["layout"].get("zones")
                    or candidate["layout"].get("placements")
                ),
                "HOLD_ADVISORY_FIT_PROOF_REQUIRED",
            )
            required = candidate["layout"].get("required_dimensions_mm")
            if required is not None:
                _numbers(required)


def _snapshot(case_id: str, items: Any, request: Any) -> list[dict[str, Any]]:
    selector.validate_request(case_id, request)
    inventory = catalogue.inventory(
        source_version=request["metal_source"]["version"],
        technical_binding=True,
        capacity_binding=True,
    )
    records = inventory["records"]
    expected_rows = {
        (family, row)
        for family, start, end in catalogue.RANGES
        for row in range(start, end + 1)
    }
    strict.require(
        isinstance(records, list)
        and len(records) == 70
        and len({r["cabinet_code"] for r in records}) == 70
        and {(r["family"], r["row"]) for r in records} == expected_rows,
        "HOLD_ADVISORY_CATALOGUE_COVERAGE",
    )
    results = []
    for item in items:
        # The strict CLI narrows source_facts only. Devices remain shared.
        bound = copy.deepcopy(request)
        bound["source_facts"] = {
            item["item_id"]: bound["source_facts"][item["item_id"]]
        }
        missing: str | None
        try:
            report = strict.size_composition(case_id, [copy.deepcopy(item)], bound)
        except strict.SizingHold as exc:
            details = exc.details
            status, missing = "HOLD", str(exc)
            strict.require(
                isinstance(details, dict) and details.get("first_missing") == missing,
                "HOLD_ADVISORY_COMPLETE_DIAGNOSTICS_REQUIRED",
            )
        else:
            strict.require(
                report.get("schema_version") == selector.CURRENT_SCHEMA
                and report.get("case_id") == case_id
                and len(report["items"]) == 1,
                "HOLD_ADVISORY_STRICT_REPORT_SCHEMA",
            )
            details = report["items"][0]["provenance"]
            status, missing = "PROPOSED", None
        _validate_details(details, item, inventory)
        results.append(
            {
                "strict_status": status,
                "first_missing": missing,
                "item_name": item.get("product_name", item.get("product_name_guess")),
                "details": copy.deepcopy(details),
            }
        )
    return results


def _advice(snapshot: dict[str, Any]) -> dict[str, Any]:
    details = snapshot["details"]
    candidates = copy.deepcopy(details["candidate_outcomes"])
    supported = [c for c in candidates if c["status"] == "FIT"]
    unknown = [c for c in candidates if c["status"] == "UNKNOWN"]
    frontier = _frontier(supported)
    groups: dict[str, dict[str, Any]] = {}
    for candidate in supported:
        signature = _layout_signature(candidate["layout"])
        key = strict.digest(signature)
        group = groups.setdefault(key, {"signature": signature, "candidates": []})
        group["candidates"].append(candidate)
    alternatives = [
        {"signature": g["signature"], "candidate_ids": _frontier(g["candidates"])}
        for g in groups.values()
    ]
    members = set(frontier).union(*(set(g["candidate_ids"]) for g in alternatives))
    unknown_frontier = _frontier([c for c in candidates if c["status"] != "NO_FIT"])
    conditional = [
        c["cabinet_code"]
        for c in unknown
        if c.get("din_capacity_assessment", {}).get("status") == "PASS"
    ]
    for candidate in candidates:
        code, status = candidate["cabinet_code"], candidate["status"]
        candidate["advisory_status"] = (
            "PLANNING_SUPPORTED" if status == "FIT" else status
        )
        candidate["shortlist_membership"] = code in members
        candidate["advisory_reason"] = (
            "Минимальный по внешним осям среди поддержанных планировочных вариантов."
            if code in frontier
            else (
                "Минимальный вариант внутри описанной существующим proof компоновки."
                if code in members
                else (
                    "Поддержанная планировочная альтернатива вне минимальных "
                    "фронтов; это не NO_FIT."
                    if status == "FIT"
                    else (
                        "Исключён только по исходному strict-доказательству ниже; "
                        "это граница текущей модели."
                        if status == "NO_FIT"
                        else "UNKNOWN сохранён: недостающие доказательства ниже "
                        "не позволяют сделать вывод о fit."
                    )
                )
            )
        )
        candidate["missing_evidence"] = (
            list(candidate["reasons"]) if status == "UNKNOWN" else []
        )
        if candidate["physical_installation_status"] == "HOLD":
            candidate["missing_evidence"].append(
                "Физический монтаж не доказан; см. ограничения планировочной модели."
            )
        layout = candidate.get("layout")
        if layout and "required_dimensions_mm" in layout:
            candidate["outer_minus_required_mm"] = [
                str(a - b)
                for a, b in zip(
                    _numbers(candidate["dimensions_mm"]),
                    _numbers(layout["required_dimensions_mm"]),
                    strict=True,
                )
            ]
            candidate["headroom_scope"] = (
                "NON_USABLE_PLANNING_HEADROOM: внешнее минус требуемое моделью; "
                "не полезный зазор/монтажный запас."
            )
            candidate["reserve_scope"] = (
                "PLANNING_PROOF_ONLY: DIN и PANEL независимы; свободная "
                "планировочная площадь не доказывает полезный резерв корпуса."
            )
    return {
        "item_id": details["item_id"],
        "item_name": snapshot["item_name"],
        "apparatus_sha256": details["apparatus_sha256"],
        "strict_status": snapshot["strict_status"],
        "first_missing": snapshot["first_missing"],
        "physical_installation_status": details["physical_installation_status"],
        "strict_frontier": details["frontier"],
        "strict_evaluation_sha256": strict.digest(snapshot),
        "catalogue_provenance": {
            k: v for k, v in details["catalogue"].items() if k != "records"
        },
        "counts": {
            s: sum(c["status"] == s for c in candidates)
            for s in ("FIT", "NO_FIT", "UNKNOWN")
        },
        "supported_candidates": [c["cabinet_code"] for c in supported],
        "supported_frontier": frontier,
        "layout_alternatives": alternatives,
        "shortlist": [
            c["cabinet_code"] for c in candidates if c["cabinet_code"] in members
        ],
        "unknown_candidates": [c["cabinet_code"] for c in unknown],
        "unresolved_dimensional_frontier": [
            c["cabinet_code"] for c in unknown if c["cabinet_code"] in unknown_frontier
        ],
        "conditional_candidates": conditional,
        "excluded_no_fit": [
            c["cabinet_code"] for c in candidates if c["status"] == "NO_FIT"
        ],
        "shortlist_scope": BOUNDARY,
        "limitations": list(PLANNING_LIMITS),
        "candidates": candidates,
    }


def recommend_composition(
    case_id: str, items: Any, request: Any = None
) -> dict[str, Any]:
    """Build advice only from complete current v4 public strict evaluations."""
    try:
        strict.require(
            isinstance(case_id, str)
            and bool(case_id)
            and isinstance(items, (list, tuple))
            and bool(items),
            "HOLD_ADVISORY_COMPOSITION",
        )
        before = strict.digest([items, request])
        supplied = copy.deepcopy(items)
        ids = [item["item_id"] for item in supplied]
        strict.require(
            all(isinstance(i, str) and i for i in ids) and len(set(ids)) == len(ids),
            "HOLD_ADVISORY_ITEM_COVERAGE",
        )
        req = copy.deepcopy(
            selector.request_for(case_id, supplied) if request is None else request
        )
        strict.require(
            isinstance(req, dict)
            and req.get("schema_version") == selector.CURRENT_REQUEST_SCHEMA,
            "HOLD_ADVISORY_REQUEST_SCHEMA",
        )
        strict.require(
            req.get("case_id") == case_id
            and isinstance(req.get("source_facts"), dict)
            and set(req["source_facts"]) == set(ids),
            "HOLD_SOURCE_FACT_COVERAGE",
        )
        first = _snapshot(case_id, supplied, req)
        result = {
            "schema_version": SCHEMA,
            "case_id": case_id,
            "strict_request": copy.deepcopy(req),
            "boundary": BOUNDARY,
            "stop_before": "HUMAN_APPROVAL_1",
            "items": [_advice(snapshot) for snapshot in first],
        }
        strict.require(
            first == _snapshot(case_id, supplied, req),
            "HOLD_ADVISORY_STRICT_SOURCE_DRIFT",
        )
        strict.require(
            before == strict.digest([items, request]), "HOLD_ADVISORY_INPUT_DRIFT"
        )
        return result
    except strict.SizingHold:
        raise
    except (KeyError, TypeError, ValueError, OSError, RecursionError) as exc:
        raise strict.SizingHold(
            "HOLD_ADVISORY_MALFORMED_OR_UNAVAILABLE_SOURCE"
        ) from exc


def verify_recommendations(report: Any, items: Any, *, expected_case_id: str) -> None:
    """Recompute sources and advice, comparing the entire report, not its claims."""
    strict.require(
        isinstance(report, dict)
        and report.get("schema_version") == SCHEMA
        and report.get("case_id") == expected_case_id
        and "strict_request" in report,
        "HOLD_RECOMMENDATION_REPORT_SCHEMA",
    )
    fresh = recommend_composition(expected_case_id, items, report["strict_request"])
    strict.require(report == fresh, "HOLD_RECOMMENDATION_REPORT_DRIFT")


def format_recommendations(report: Any, items: Any, *, expected_case_id: str) -> str:
    """Verified human view, including every candidate's full source proof."""
    verify_recommendations(report, items, expected_case_id=expected_case_id)
    lines = [
        "# Предварительные рекомендации по корпусам",
        "",
        BOUNDARY,
        "",
        f"Case: {expected_case_id}",
        "",
    ]
    for board in report["items"]:
        lines.extend(
            [
                f"## {board['item_id']} — {board['item_name'] or 'название не задано'}",
                "",
                f"Strict: {board['strict_status']}; физический монтаж: "
                f"{board['physical_installation_status']}",
                f"Первый HOLD: {board['first_missing']}",
                f"Количество FIT / NO_FIT / UNKNOWN: {board['counts']}",
                "",
            ]
        )
        for label, key in (
            ("Поддержанный минимальный фронт", "supported_frontier"),
            ("Общий shortlist с компоновочными альтернативами", "shortlist"),
            (
                "Условный DIN capacity PASS (общий статус UNKNOWN)",
                "conditional_candidates",
            ),
            ("Все UNKNOWN", "unknown_candidates"),
            (
                "Неразрешённый размерный фронт (только необходимые внешние границы)",
                "unresolved_dimensional_frontier",
            ),
            ("Исключённые strict NO_FIT", "excluded_no_fit"),
            ("Все поддержанные планировочные альтернативы", "supported_candidates"),
        ):
            lines.extend([f"{label}: {', '.join(board[key]) or 'нет'}", ""])
        lines.extend(
            [
                "Описательные альтернативы существующих компоновок:",
                "",
                "```json",
                json.dumps(
                    board["layout_alternatives"],
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                ),
                "```",
                "",
            ]
        )
        lines.extend([f"- {limit}" for limit in board["limitations"]])
        lines.append("")
        for candidate in board["candidates"]:
            lines.extend(
                [
                    f"### {candidate['cabinet_code']} — {candidate['advisory_status']}",
                    "",
                    candidate["advisory_reason"],
                    "",
                    "Основания, источники, ограничения и недостающие доказательства:",
                    "",
                    "```json",
                    json.dumps(candidate, ensure_ascii=False, sort_keys=True, indent=2),
                    "```",
                    "",
                ]
            )
    lines.extend(
        [
            "## Конкретный strict request и источники",
            "",
            "```json",
            json.dumps(
                report["strict_request"], ensure_ascii=False, sort_keys=True, indent=2
            ),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _input_bytes(path: Path) -> bytes:
    strict.require(path.is_absolute(), "HOLD_ADVISORY_ABSOLUTE_INPUT_PATH_REQUIRED")
    for part in [path, *path.parents]:
        info = part.lstat()
        strict.require(
            not stat.S_ISLNK(info.st_mode)
            and not (getattr(info, "st_file_attributes", 0) & 0x400),
            "HOLD_ADVISORY_REPARSE_INPUT",
        )
    return path.read_bytes()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only preliminary cabinet advice; not Human Approval"
    )
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--composition-json", type=Path, required=True)
    parser.add_argument("--request-json", type=Path)
    parser.add_argument("--request-sha256")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args(argv)
    try:
        strict.require(
            (args.request_json is None) == (args.request_sha256 is None),
            "HOLD_SIZING_REQUEST_PATH_AND_SHA_REQUIRED",
        )
        raw = _input_bytes(args.composition_json)
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
        strict.require(
            isinstance(data, dict) and isinstance(data.get("items"), list),
            "HOLD_ADVISORY_COMPOSITION",
        )
        req_raw = _input_bytes(args.request_json) if args.request_json else None
        request = (
            strict.load_request(args.request_json, args.request_sha256)
            if args.request_json
            else None
        )
        report = recommend_composition(args.case_id, data["items"], request)
        verify_recommendations(report, data["items"], expected_case_id=args.case_id)
        rendered = (
            format_recommendations(report, data["items"], expected_case_id=args.case_id)
            if args.format == "markdown"
            else json.dumps(report, ensure_ascii=False, sort_keys=True)
        )
        strict.require(
            raw == _input_bytes(args.composition_json), "HOLD_COMPOSITION_SOURCE_DRIFT"
        )
        if args.request_json:
            strict.require(
                req_raw == _input_bytes(args.request_json)
                and strict.load_request(args.request_json, args.request_sha256)
                == request,
                "HOLD_SIZING_REQUEST_DRIFT",
            )
        print(rendered)
        return 2 if any(b["strict_status"] == "HOLD" for b in report["items"]) else 0
    except strict.SizingHold as exc:
        reason = str(exc)
    except ValueError, KeyError, TypeError, OSError, UnicodeError, RecursionError:
        reason = "HOLD_ADVISORY_MALFORMED_OR_UNAVAILABLE_SOURCE"
    print(json.dumps({"status": "HOLD", "first_missing": reason}, sort_keys=True))
    return 2


if __name__ == "__main__":
    # Only this CLI owns its stdout encoding; importing the module changes none.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
