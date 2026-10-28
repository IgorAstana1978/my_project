"""Exact, read-only cabinet sizing. Data and hashes never grant Human authority."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from governed_case_intake import _pairs
from wu8_governed_sources import CABINETS, METAL_SIZES

# The CLI and lazy selector/evidence imports must share the same HOLD class.
if __name__ == "__main__":
    sys.modules["cabinet_sizing"] = sys.modules[__name__]

SCHEMA = "cabinet_sizing.v0.1"
# Only direct Igor approval of exact role/path/SHA may extend this registry.
# Existing cabinet identities do not authorize device/layout/interior facts.
APPROVED_SOURCES: frozenset[tuple[str, str, str]] = frozenset()


class SizingHold(ValueError):
    """First missing or inconsistent engineering evidence; never guess/retry."""

    def __init__(self, reason: str, details: Any = None):
        super().__init__(reason)
        self.details = details


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise SizingHold(reason)


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def object_with(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    require(isinstance(value, dict) and set(value) == fields, f"HOLD_SCHEMA:{label}")
    return dict(value)


def vector(value: Any, *, zero: bool = False) -> tuple[int, int, int]:
    require(
        isinstance(value, list)
        and len(value) == 3
        and all(type(n) is int and n >= (0 if zero else 1) for n in value),
        "HOLD_INVALID_MM_VECTOR",
    )
    return value[0], value[1], value[2]


def load_request(path: Path, expected_sha256: str | None) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        require(len(raw) <= 1024 * 1024, "HOLD_SIZING_REQUEST_TOO_LARGE")
        require(
            hashlib.sha256(raw).hexdigest() == expected_sha256,
            "HOLD_SIZING_REQUEST_SHA_MISMATCH",
        )
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
        require(isinstance(value, dict), "HOLD_SIZING_REQUEST_SCHEMA")
        return dict(value)
    except SizingHold:
        raise
    except (ValueError, OSError, UnicodeError, RecursionError) as exc:
        raise SizingHold("HOLD_MALFORMED_OR_UNAVAILABLE_SIZING_REQUEST") from exc


def source(binding: Any, role: str) -> dict[str, Any]:
    ref = object_with(binding, {"path", "sha256", "pointer"}, role)
    require(all(isinstance(v, str) and v for v in ref.values()), "HOLD_SOURCE_BINDING")
    path = Path(ref["path"])
    require(path.is_absolute(), "HOLD_SOURCE_ABSOLUTE_PATH_REQUIRED")
    for p in (path, *path.parents):
        if p.exists():
            require(
                not p.is_symlink()
                and not getattr(p.lstat(), "st_file_attributes", 0)
                & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0),
                "HOLD_SOURCE_REPARSE_POINT",
            )
    require(
        (role, str(path.resolve()), ref["sha256"]) in APPROVED_SOURCES,
        f"HOLD_UNAPPROVED_SOURCE:{role}",
    )
    raw = path.read_bytes()
    require(len(raw) <= 1024 * 1024, "HOLD_SOURCE_TOO_LARGE")
    require(hashlib.sha256(raw).hexdigest() == ref["sha256"], "HOLD_SOURCE_SHA_DRIFT")
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
    pointer = ref["pointer"]
    require(pointer.startswith("/"), "HOLD_SOURCE_POINTER")
    for part in pointer[1:].split("/"):
        key = part.replace("~1", "/").replace("~0", "~")
        require(isinstance(value, dict) and key in value, "HOLD_SOURCE_POINTER")
        value = value[key]
    require(isinstance(value, dict), "HOLD_SOURCE_OBJECT_REQUIRED")
    return dict(value)


def apparatus_hash(item: Mapping[str, Any]) -> str:
    return digest(
        {
            "item_id": item["item_id"],
            "product_name": item.get("product_name", item.get("product_name_guess")),
            "quantity": item.get("quantity", item.get("quantity_guess")),
            "components": item["components"],
        }
    )


def cabinet_identity(code: str) -> tuple[str, str, list[int]]:
    if code in CABINETS:
        name, _, size, *_ = CABINETS[code]
        return name, "KRN" if code.startswith("CAB-KRN-") else "KRV", list(size)
    for size, (row, *_) in METAL_SIZES.items():
        exact = f"METAL-{size[0]}X{size[1]}X{size[2]}"
        if code in {exact, f"{exact}-D{row}"}:
            return code, "METAL", list(size)
    raise SizingHold("HOLD_CABINET_IDENTITY_OUTSIDE_APPROVED_CATALOG")


def size_item(case_id: str, item: Mapping[str, Any], request: Any) -> dict[str, Any]:
    req = object_with(request, {"item_id", "devices", "cabinet", "layout"}, "item")
    require(req["item_id"] == item["item_id"], "HOLD_ITEM_BINDING")
    components = item["components"]
    require(isinstance(components, list) and bool(components), "HOLD_EMPTY_COMPOSITION")
    require(isinstance(req["devices"], dict), "HOLD_DEVICE_BINDINGS")
    ids = [c["component_id"] for c in components]
    require(len(set(ids)) == len(ids), "HOLD_DUPLICATE_COMPONENT")
    require(set(req["devices"]) == set(ids), "HOLD_DEVICE_COVERAGE")
    footprints = {}
    expected: set[tuple[str, int]] = set()
    for component in components:
        cid = component["component_id"]
        data = object_with(
            source(req["devices"][cid], "device"),
            {"component_sha256", "dimensions_mm"},
            "device",
        )
        require(data["component_sha256"] == digest(component), "HOLD_DEVICE_SIGNATURE")
        footprints[cid] = vector(data["dimensions_mm"])
        qty = component.get("quantity", component.get("quantity_guess"))
        require(type(qty) is int and 0 < qty <= 10000, "HOLD_DEVICE_QUANTITY")
        expected.update((cid, n) for n in range(1, qty + 1))
    cab = object_with(
        source(req["cabinet"], "cabinet"),
        {"cabinet_code", "cabinet_label", "cabinet_type", "dimensions_mm", "usable_mm"},
        "cabinet",
    )
    _, kind, outer = cabinet_identity(cab["cabinet_code"])
    require(
        isinstance(cab["cabinet_label"], str) and bool(cab["cabinet_label"].strip()),
        "HOLD_CABINET_LABEL",
    )
    require(cab["cabinet_type"] == kind, "HOLD_CABINET_TYPE")
    require(cab["dimensions_mm"] == outer, "HOLD_CABINET_DIMENSION_IDENTITY")
    usable = vector(cab["usable_mm"])
    require(all(a <= b for a, b in zip(usable, outer, strict=True)), "HOLD_USABLE_SIZE")
    layout = object_with(
        source(req["layout"], "layout"),
        {
            "case_id",
            "item_id",
            "apparatus_sha256",
            "cabinet_code",
            "edge_mm",
            "gap_mm",
            "reserve",
            "placements",
        },
        "layout",
    )
    require(
        layout["case_id"] == case_id
        and layout["item_id"] == item["item_id"]
        and layout["apparatus_sha256"] == apparatus_hash(item)
        and layout["cabinet_code"] == cab["cabinet_code"],
        "HOLD_LAYOUT_COMPOSITION_BINDING",
    )
    edge = vector(layout["edge_mm"], zero=True)
    gap = vector(layout["gap_mm"], zero=True)
    reserve = object_with(layout["reserve"], {"origin_mm", "dimensions_mm"}, "reserve")
    reserve_size = vector(reserve["dimensions_mm"], zero=True)
    require(all(reserve_size) or not any(reserve_size), "HOLD_RESERVE_SHAPE")
    boxes = [(vector(reserve["origin_mm"], zero=True), reserve_size)]
    require(isinstance(layout["placements"], list), "HOLD_PLACEMENTS")
    seen = set()
    for value in layout["placements"]:
        place = object_with(value, {"component_id", "unit", "origin_mm"}, "placement")
        key = (place["component_id"], place["unit"])
        require(
            type(place["unit"]) is int and key in expected and key not in seen,
            "HOLD_LAYOUT_DEVICE_COVERAGE",
        )
        seen.add(key)
        boxes.append((vector(place["origin_mm"], zero=True), footprints[key[0]]))
    require(seen == expected, "HOLD_LAYOUT_DEVICE_COVERAGE")
    occupied: list[tuple[tuple[int, int, int], tuple[int, int, int]]] = []
    for origin, size in boxes:
        require(
            all(
                edge[i] <= origin[i] and origin[i] + size[i] <= usable[i] - edge[i]
                for i in range(3)
            ),
            "HOLD_LAYOUT_OUTSIDE_USABLE_SPACE",
        )
        if not any(size):
            continue
        for other, other_size in occupied:
            require(
                any(
                    origin[i] + size[i] + gap[i] <= other[i]
                    or other[i] + other_size[i] + gap[i] <= origin[i]
                    for i in range(3)
                ),
                "HOLD_LAYOUT_COLLISION_OR_CLEARANCE",
            )
        occupied.append((origin, size))
    return {
        "item_id": item["item_id"],
        "apparatus_sha256": apparatus_hash(item),
        "cabinet": {
            "cabinet_code": cab["cabinet_code"],
            "cabinet_label": cab["cabinet_label"],
            "cabinet_type": kind,
            "dimensions_mm": outer,
        },
    }


def legacy_size_composition(
    case_id: str,
    items: Sequence[Mapping[str, Any]],
    request: Any = None,
) -> dict[str, Any]:
    """Verify a supplied exact approved layout; never search/optimize/select by size."""
    try:
        require(
            isinstance(items, (list, tuple)) and bool(items), "HOLD_EMPTY_COMPOSITION"
        )
        require(
            all(
                isinstance(i, dict)
                and isinstance(i.get("item_id"), str)
                and isinstance(i.get("components"), list)
                and bool(i["components"])
                and all(
                    isinstance(c, dict) and isinstance(c.get("component_id"), str)
                    for c in i["components"]
                )
                for i in items
            ),
            "HOLD_MALFORMED_COMPOSITION",
        )
        if request is None:
            first = items[0]
            cid = first["components"][0]["component_id"]
            raise SizingHold(f"HOLD_MISSING_DEVICE_DIMENSIONS:{first['item_id']}:{cid}")
        req = object_with(request, {"case_id", "items"}, "request")
        require(req["case_id"] == case_id, "HOLD_CASE_BINDING")
        require(isinstance(req["items"], list), "HOLD_ITEM_COVERAGE")
        require(
            [i["item_id"] for i in req["items"]] == [i["item_id"] for i in items],
            "HOLD_ITEM_COVERAGE",
        )
        require(len({i["item_id"] for i in items}) == len(items), "HOLD_DUPLICATE_ITEM")
        selections = [
            size_item(case_id, item, bound)
            for item, bound in zip(items, req["items"], strict=True)
        ]
        return {
            "schema_version": SCHEMA,
            "case_id": case_id,
            "items": selections,
            "sources": req,
        }
    except SizingHold:
        raise
    except (
        ValueError,
        KeyError,
        TypeError,
        OSError,
        UnicodeError,
        RecursionError,
    ) as exc:
        raise SizingHold("HOLD_MALFORMED_OR_UNAVAILABLE_SIZING_EVIDENCE") from exc


def size_composition(
    case_id: str,
    items: Sequence[Mapping[str, Any]],
    request: Any = None,
) -> dict[str, Any]:
    """Automatic sizing by default; exact v0.1 requests remain historical replay."""
    if (
        request is not None
        and isinstance(request, dict)
        and "schema_version" not in request
    ):
        return legacy_size_composition(case_id, items, request)
    from cabinet_sizing_selector import select

    try:
        import cabinet_sizing_catalogue as catalogue
        import cabinet_sizing_pragmatic as pragmatic

        if request is None or (
            isinstance(request, dict)
            and request.get("schema_version") in catalogue.REQUEST_SCHEMAS
        ):
            return catalogue.select(case_id, items, request)

        if (
            isinstance(request, dict)
            and request.get("schema_version") == pragmatic.REQUEST_SCHEMA
        ):
            return pragmatic.select(case_id, items, request)
        return select(case_id, items, request)
    except SizingHold:
        raise
    except (
        ValueError,
        KeyError,
        TypeError,
        OSError,
        UnicodeError,
        RecursionError,
    ) as exc:
        raise SizingHold("HOLD_MALFORMED_OR_UNAVAILABLE_SIZING_EVIDENCE") from exc


def verify_report(
    report: Any,
    items: Sequence[Mapping[str, Any]],
    *,
    expected_case_id: str | None,
    before_human_approval_1: bool = False,
) -> None:
    require(isinstance(report, dict), "HOLD_SIZING_REQUIRED_BEFORE_HUMAN_APPROVAL_1")
    require(
        not before_human_approval_1
        or report.get("schema_version")
        in {
            "cabinet_sizing.auto.v0.2",
            "cabinet_sizing.pragmatic_metal.v0.1",
            "cabinet_sizing.catalogue.v0.1",
            "cabinet_sizing.catalogue.v0.2",
            "cabinet_sizing.catalogue.v0.3",
            "cabinet_sizing.catalogue.v0.4",
        },
        "HOLD_AUTOMATIC_SELECTOR_REQUIRED_BEFORE_HUMAN_APPROVAL_1",
    )
    require(
        report.get("schema_version")
        in {
            SCHEMA,
            "cabinet_sizing.auto.v0.2",
            "cabinet_sizing.pragmatic_metal.v0.1",
            "cabinet_sizing.catalogue.v0.1",
            "cabinet_sizing.catalogue.v0.2",
            "cabinet_sizing.catalogue.v0.3",
            "cabinet_sizing.catalogue.v0.4",
        },
        "HOLD_SIZING_REPORT_SCHEMA",
    )
    require(
        set(report) == {"schema_version", "case_id", "items", "sources"},
        "HOLD_SIZING_REPORT_SCHEMA",
    )
    require(
        isinstance(expected_case_id, str)
        and bool(expected_case_id)
        and report["case_id"] == expected_case_id,
        "HOLD_SIZING_CASE_BINDING",
    )
    require(
        report == size_composition(report["case_id"], items, report["sources"]),
        "HOLD_SIZING_REPORT_DRIFT",
    )
    for item, selection in zip(items, report["items"], strict=True):
        require(item["cabinet"] == selection["cabinet"], "HOLD_CONFIRMED_CABINET_DRIFT")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only cabinet sizing before Approval 1"
    )
    parser.add_argument("--composition-json", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--request-json", type=Path)
    parser.add_argument("--request-sha256")
    args = parser.parse_args(argv)
    try:
        raw = args.composition_json.read_bytes()
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
        require(
            isinstance(data, dict)
            and isinstance(data.get("items"), list)
            and bool(data["items"]),
            "HOLD_MALFORMED_COMPOSITION",
        )
        ids = [i["item_id"] for i in data["items"]]
        require(
            all(isinstance(i, str) and bool(i) for i in ids),
            "HOLD_MALFORMED_COMPOSITION",
        )
        require(len(set(ids)) == len(ids), "HOLD_DUPLICATE_ITEM")
        require(
            (args.request_json is None) == (args.request_sha256 is None),
            "HOLD_SIZING_REQUEST_PATH_AND_SHA_REQUIRED",
        )
        request = (
            load_request(args.request_json, args.request_sha256)
            if args.request_json
            else None
        )
        automatic = request is None or "schema_version" in request
        if request is not None and request.get("schema_version") in {
            "cabinet_sizing.pragmatic_metal_request.v0.1",
            "cabinet_sizing.catalogue_request.v0.1",
            "cabinet_sizing.catalogue_request.v0.2",
            "cabinet_sizing.catalogue_request.v0.3",
            "cabinet_sizing.catalogue_request.v0.4",
        }:
            require(
                isinstance(request.get("source_facts"), dict)
                and set(request["source_facts"]) == set(ids),
                "HOLD_SOURCE_FACT_COVERAGE",
            )
        if request is not None and not automatic:
            object_with(request, {"case_id", "items"}, "request")
            require(
                request["case_id"] == args.case_id
                and isinstance(request["items"], list)
                and [i["item_id"] for i in request["items"]]
                == [i["item_id"] for i in data["items"]],
                "HOLD_ITEM_COVERAGE",
            )
        results = []
        for index, item in enumerate(data["items"]):
            if automatic:
                bound = request
                if request is not None:
                    bound = dict(request)
                    if isinstance(request.get("source_facts"), dict):
                        bound["source_facts"] = {
                            k: v
                            for k, v in request["source_facts"].items()
                            if k == item["item_id"]
                        }
            else:
                assert request is not None
                bound = {"case_id": args.case_id, "items": [request["items"][index]]}
            try:
                report = size_composition(args.case_id, [item], bound)
                result = {
                    "item_id": item["item_id"],
                    "status": "PROPOSED",
                    "report": report,
                }
            except SizingHold as exc:
                result = {
                    "item_id": item["item_id"],
                    "status": "HOLD",
                    "first_missing": str(exc),
                }
                if exc.details is not None:
                    result["details"] = exc.details
            results.append(result)
        require(
            raw == args.composition_json.read_bytes(), "HOLD_COMPOSITION_SOURCE_DRIFT"
        )
        if args.request_json:
            require(
                load_request(args.request_json, args.request_sha256) == request,
                "HOLD_SIZING_REQUEST_DRIFT",
            )
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA,
                    "case_id": args.case_id,
                    "composition_sha256": hashlib.sha256(raw).hexdigest(),
                    "results": results,
                    "stop_before": "HUMAN_APPROVAL_1",
                },
                sort_keys=True,
            )
        )
        return 2 if any(r["status"] == "HOLD" for r in results) else 0
    except SizingHold as exc:
        reason = str(exc)
    except ValueError, KeyError, TypeError, OSError, UnicodeError, RecursionError:
        reason = "HOLD_MALFORMED_OR_UNAVAILABLE_COMPOSITION"
    print(json.dumps({"status": "HOLD", "first_missing": reason}, sort_keys=True))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
