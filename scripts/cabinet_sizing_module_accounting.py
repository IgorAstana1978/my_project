"""Source-bound resource ledger, independent of cabinet selection and authority."""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping, Sequence
from decimal import Context, Decimal, localcontext
from pathlib import Path
from typing import Any, cast

import cabinet_reserve_policy as reserve_rules
import cabinet_sizing as sizing
import cabinet_sizing_evidence as evidence

EVIDENCE_SCHEMA = "module_accounting.evidence.v0.1"
SCHEMA = "module_accounting.ledger.v0.1"
REPORT_SCHEMA = "cabinet_sizing.module.v0.1"
ROLE = "module_accounting"
SCOPE = "ALL_INSTALLED_EQUIPMENT_AND_DIN_ACCESSORIES"
KINDS = {"DIN", "PANEL", "OTHER"}
HASH = re.compile(r"[0-9a-f]{64}\Z")


def obj(value: Any, fields: str) -> dict[str, Any]:
    return sizing.object_with(value, set(fields.split()), "module_accounting")


def string(value: Any) -> str:
    sizing.require(isinstance(value, str) and bool(value.strip()), "HOLD_MODULE_STRING")
    assert isinstance(value, str)
    return value


def number(value: Any, *, zero: bool = False) -> Decimal:
    return evidence.number(value, zero=zero)


def percent(value: Any) -> Decimal:
    result = number(value, zero=True)
    sizing.require(result < 100, "HOLD_MODULE_RESERVE_PERCENT")
    return result


def integer(value: Any) -> int:
    sizing.require(type(value) is int and 0 < value <= 256, "HOLD_MODULE_QUANTITY")
    assert isinstance(value, int)
    return value


def collection(value: Any, *, empty: bool = False) -> list[Any]:
    sizing.require(
        isinstance(value, list) and len(value) <= 256 and (empty or bool(value)),
        "HOLD_MODULE_COLLECTION",
    )
    assert isinstance(value, list)
    return value


def unique(records: Any, fields: str, key: str) -> dict[str, dict[str, Any]]:
    result = {}
    for raw in collection(records):
        record = obj(raw, fields)
        identity = string(record[key])
        sizing.require(identity not in result, "HOLD_MODULE_DUPLICATE_ID")
        result[identity] = record
    return result


def serial(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, dict):
        return {key: serial(child) for key, child in value.items()}
    if isinstance(value, list):
        return [serial(child) for child in value]
    return value


def composition_hash(items: Sequence[Mapping[str, Any]]) -> str:
    return sizing.digest(
        [
            {
                "apparatus": sizing.apparatus_hash(item),
                "cabinet": item["cabinet"],
            }
            for item in items
        ]
    )


def binding(path: Path | None, sha256: str | None) -> dict[str, str] | None:
    sizing.require(
        (path is None) == (sha256 is None), "HOLD_MODULE_PATH_AND_SHA_REQUIRED"
    )
    if path is None:
        return None
    sizing.require(
        isinstance(sha256, str) and HASH.fullmatch(sha256) is not None,
        "HOLD_MODULE_SOURCE_HASH",
    )
    assert isinstance(sha256, str)
    return {"path": str(path), "sha256": sha256}


def footprint(record: Any, kind: str) -> dict[str, Any]:
    if kind == "DIN":
        sizing.require(record["area_mm2"] is None, "HOLD_MODULE_DIN_AREA")
        sizing.require(
            record["nominal_modules"] is not None,
            "HOLD_MODULE_NOMINAL_MODULES_REQUIRED",
        )
        sizing.require(record["width_mm"] is not None, "HOLD_MODULE_WIDTH_REQUIRED")
        return {
            "nominal_modules": number(record["nominal_modules"]),
            "width_mm": number(record["width_mm"]),
            "area_mm2": None,
        }
    sizing.require(
        record["nominal_modules"] is None and record["width_mm"] is None,
        "HOLD_MODULE_NON_DIN_MODULES",
    )
    return {
        "nominal_modules": None,
        "width_mm": None,
        "area_mm2": number(record["area_mm2"]),
    }


def _build(
    case_id: str,
    items: Sequence[Mapping[str, Any]],
    sizing_report: Mapping[str, Any],
    source: Any,
) -> dict[str, Any]:
    sizing.require(source is not None, "HOLD_MODULE_EVIDENCE_REQUIRED_BEFORE_HA1")
    data = evidence.read(source, ROLE)
    obj(
        data,
        "schema_version case_id composition_sha256 sizing_sha256 inventory_scope "
        "products profiles boards raw_sources",
    )
    sizing.require(
        data["schema_version"] == EVIDENCE_SCHEMA and data["inventory_scope"] == SCOPE,
        "HOLD_MODULE_EVIDENCE_SCHEMA",
    )
    sizing.require(
        string(case_id) == data["case_id"] == sizing_report["case_id"]
        and data["composition_sha256"] == composition_hash(items)
        and data["sizing_sha256"] == sizing.digest(sizing_report),
        "HOLD_MODULE_COMPOSITION_BINDING",
    )
    base_devices = reserve_rules.request(sizing_report).get("devices")
    base_classes = (
        evidence.envelopes(base_devices) if base_devices is not None else None
    )
    raw_sources = set()
    for ref in collection(data["raw_sources"]):
        obj(ref, "path sha256")
        sizing.require(
            HASH.fullmatch(string(ref["sha256"])) is not None,
            "HOLD_MODULE_SOURCE_HASH",
        )
        evidence.safe_bytes(Path(string(ref["path"])), ref["sha256"])
        pair = (ref["path"], ref["sha256"])
        sizing.require(pair not in raw_sources, "HOLD_MODULE_DUPLICATE_SOURCE")
        raw_sources.add(pair)

    def provenance(ref: Any) -> None:
        obj(ref, "path sha256 locator")
        string(ref["locator"])
        sizing.require(
            (ref["path"], ref["sha256"]) in raw_sources,
            "HOLD_MODULE_UNBOUND_RAW_SOURCE",
        )

    products = unique(
        data["products"],
        "id manufacturer sku revision mounting nominal_modules "
        "width_mm area_mm2 source",
        "id",
    )
    product_identities = set()
    for product in products.values():
        for field in ("manufacturer", "sku", "revision"):
            value = string(product[field])
            sizing.require(
                value.strip().casefold() not in {"unknown", "none", "n/a", "tbd", "?"},
                "HOLD_MODULE_EXACT_SKU_OR_REVISION_REQUIRED",
            )
        identity = tuple(
            product[field] for field in ("manufacturer", "sku", "revision")
        )
        sizing.require(
            identity not in product_identities, "HOLD_MODULE_AMBIGUOUS_SKU_REVISION"
        )
        product_identities.add(identity)
        sizing.require(product["mounting"] in KINDS, "HOLD_MODULE_MOUNTING")
        footprint(product, product["mounting"])
        provenance(product["source"])
    profiles = unique(
        data["profiles"],
        "id product_ids nominal_modules width_mm area_mm2 left_gap_mm right_gap_mm "
        "allowed_zones source",
        "id",
    )
    for profile in profiles.values():
        ids = collection(profile["product_ids"])
        sizing.require(
            all(isinstance(pid, str) and pid in products for pid in ids),
            "HOLD_MODULE_PROFILE_PRODUCTS",
        )
        kinds = {products[pid]["mounting"] for pid in ids}
        sizing.require(len(kinds) == 1, "HOLD_MODULE_MIXED_MOUNTING_FOOTPRINT")
        kind = next(iter(kinds))
        shape = footprint(profile, kind)
        if len(ids) == 1:
            sizing.require(
                shape == footprint(products[ids[0]], kind),
                "HOLD_MODULE_SINGLE_PRODUCT_FOOTPRINT",
            )
        left = number(profile["left_gap_mm"], zero=True)
        right = number(profile["right_gap_mm"], zero=True)
        sizing.require(kind == "DIN" or left + right == 0, "HOLD_MODULE_NON_DIN_GAP")
        allowed = collection(profile["allowed_zones"])
        sizing.require(
            all(isinstance(z, str) and z.strip() for z in allowed)
            and len(set(allowed)) == len(allowed),
            "HOLD_MODULE_PLACEMENT_CONSTRAINT",
        )
        provenance(profile["source"])
    boards = unique(
        data["boards"],
        "item_id cabinet_sha256 quantity project_min_din_free_percent "
        "project_min_panel_free_percent zones instances groups source",
        "item_id",
    )
    sizing.require(
        len(items) == len(boards)
        and len({i["item_id"] for i in items}) == len(items)
        and set(boards) == {i["item_id"] for i in items},
        "HOLD_MODULE_BOARD_COVERAGE",
    )
    result = []
    for item in items:
        board = boards[item["item_id"]]
        provenance(board["source"])
        sizing.require(
            board["cabinet_sha256"] == sizing.digest(item["cabinet"])
            and integer(board["quantity"]) == integer(item["quantity"]),
            "HOLD_MODULE_CABINET_OR_QUANTITY_BINDING",
        )
        reserve_identity = reserve_rules.identity(item["cabinet"], sizing_report)
        policy = reserve_rules.make(
            case_id,
            {
                item["item_id"]: {
                    "DIN": board["project_min_din_free_percent"],
                    "PANEL": board["project_min_panel_free_percent"],
                }
            },
        )
        din_min, panel_min = reserve_rules.thresholds(
            policy, item["item_id"], reserve_identity["family"]
        )
        zones = unique(
            board["zones"],
            "id kind capacity_modules capacity_mm capacity_area_mm2 source",
            "id",
        )
        totals: dict[str, dict[str, Any]] = {}
        for zid, zone in zones.items():
            provenance(zone["source"])
            sizing.require(zone["kind"] in KINDS, "HOLD_MODULE_ZONE_KIND")
            cm: Decimal | None
            cw: Decimal | None
            ca: Decimal | None
            if zone["kind"] == "DIN":
                sizing.require(
                    zone["capacity_area_mm2"] is None, "HOLD_MODULE_DIN_AREA"
                )
                cm = number(zone["capacity_modules"])
                cw = number(zone["capacity_mm"])
                ca = None
            else:
                sizing.require(
                    zone["capacity_modules"] is None and zone["capacity_mm"] is None,
                    "HOLD_MODULE_NON_DIN_CAPACITY",
                )
                cm = cw = None
                ca = number(zone["capacity_area_mm2"])
            totals[zid] = {
                "zone_id": zid,
                "kind": zone["kind"],
                "capacity_modules": cm,
                "capacity_mm": cw,
                "capacity_area_mm2": ca,
                "occupied_modules": Decimal(0),
                "occupied_mm": Decimal(0),
                "occupied_area_mm2": Decimal(0),
                "footprints": [],
            }
        instances = unique(board["instances"], "id component_id unit product_id", "id")
        expected = {
            (string(c["component_id"]), unit)
            for c in item["components"]
            for unit in range(1, integer(c["quantity"]) + 1)
        }
        components_by_id = {c["component_id"]: c for c in item["components"]}
        sizing.require(
            len({c["component_id"] for c in item["components"]})
            == len(item["components"]),
            "HOLD_MODULE_DUPLICATE_COMPONENT",
        )
        covered = set()
        for instance in instances.values():
            integer(instance["unit"])
            sizing.require(
                instance["product_id"] in products, "HOLD_MODULE_UNKNOWN_SKU"
            )
            if instance["component_id"] is None:
                sizing.require(instance["unit"] == 1, "HOLD_MODULE_ACCESSORY_INSTANCE")
            else:
                pair = (string(instance["component_id"]), instance["unit"])
                sizing.require(
                    pair in expected and pair not in covered,
                    "HOLD_MODULE_INSTANCE_COVERAGE",
                )
                covered.add(pair)
                if base_classes is not None:
                    component = components_by_id[instance["component_id"]]
                    original = base_classes[evidence.class_for(component, base_devices)]
                    product = products[instance["product_id"]]
                    sizing.require(
                        product["mounting"] == original["mounting"],
                        "HOLD_MODULE_BASE_MOUNTING_CONFLICT",
                    )
                    dims = evidence.dimensions(original["dimensions_mm"])
                    exact = footprint(product, product["mounting"])
                    sizing.require(
                        (
                            exact["width_mm"] <= dims[1]
                            if product["mounting"] == "DIN"
                            else exact["area_mm2"] <= dims[0] * dims[1]
                        ),
                        "HOLD_MODULE_BASE_FOOTPRINT_UNDERBOUND",
                    )
        sizing.require(covered == expected, "HOLD_MODULE_INSTANCE_COVERAGE")
        groups = unique(board["groups"], "id profile_id instance_ids zone_id", "id")
        assigned: set[str] = set()
        for group in groups.values():
            sizing.require(
                group["profile_id"] in profiles, "HOLD_MODULE_UNKNOWN_PROFILE"
            )
            profile = profiles[group["profile_id"]]
            ids = collection(group["instance_ids"])
            sizing.require(
                all(isinstance(i, str) and i in instances for i in ids)
                and len(set(ids)) == len(ids)
                and not assigned.intersection(ids),
                "HOLD_MODULE_DUPLICATE_OR_UNKNOWN_FOOTPRINT",
            )
            sizing.require(
                [instances[i]["product_id"] for i in ids] == profile["product_ids"],
                "HOLD_MODULE_FOOTPRINT_MEMBERS",
            )
            zid = group["zone_id"]
            kind = products[profile["product_ids"][0]]["mounting"]
            sizing.require(
                zid in zones
                and zid in profile["allowed_zones"]
                and zones[zid]["kind"] == kind,
                "HOLD_MODULE_PLACEMENT_CONSTRAINT",
            )
            shape = footprint(profile, kind)
            target = totals[zid]
            if kind == "DIN":
                width = (
                    shape["width_mm"]
                    + number(profile["left_gap_mm"], zero=True)
                    + number(profile["right_gap_mm"], zero=True)
                )
                target["occupied_modules"] += shape["nominal_modules"]
                target["occupied_mm"] += width
            else:
                target["occupied_area_mm2"] += shape["area_mm2"]
            target["footprints"].append(dict(group, footprint=shape))
            assigned.update(ids)
        sizing.require(assigned == set(instances), "HOLD_MODULE_UNASSIGNED_INSTANCE")
        for zone in totals.values():
            if zone["kind"] == "DIN":
                sizing.require(
                    zone["occupied_modules"] <= zone["capacity_modules"]
                    and zone["occupied_mm"] <= zone["capacity_mm"],
                    "HOLD_MODULE_ROW_OVERFLOW",
                )
                zone["free_modules"] = (
                    zone["capacity_modules"] - zone["occupied_modules"]
                )
                zone["free_mm"] = zone["capacity_mm"] - zone["occupied_mm"]
            else:
                sizing.require(
                    zone["occupied_area_mm2"] <= zone["capacity_area_mm2"],
                    "HOLD_MODULE_ZONE_OVERFLOW",
                )
                zone["free_area_mm2"] = (
                    zone["capacity_area_mm2"] - zone["occupied_area_mm2"]
                )
                if zone["kind"] == "PANEL":
                    sizing.require(
                        zone["free_area_mm2"] * 100
                        >= zone["capacity_area_mm2"] * panel_min,
                        "HOLD_MODULE_RESERVE:PANEL:zone",
                    )
        reserve: dict[str, Any] = {}
        for kind, threshold in (
            ("DIN", din_min),
            ("PANEL", panel_min),
            ("OTHER", Decimal(0)),
        ):
            selected = [z for z in totals.values() if z["kind"] == kind]
            measures = ("modules", "mm") if kind == "DIN" else ("area_mm2",)
            reserve[kind] = {"minimum_free_percent": threshold, "measures": {}}
            for measure in measures:
                capacity = sum((z[f"capacity_{measure}"] for z in selected), Decimal(0))
                occupied = sum((z[f"occupied_{measure}"] for z in selected), Decimal(0))
                free = capacity - occupied
                sizing.require(
                    free * 100 >= capacity * threshold,
                    f"HOLD_MODULE_RESERVE:{kind}:{measure}",
                )
                reserve[kind]["measures"][measure] = {
                    "capacity": capacity,
                    "occupied": occupied,
                    "free": free,
                    "free_percent": free * 100 / capacity if capacity else None,
                }
        result.append(
            {
                "item_id": item["item_id"],
                "quantity": board["quantity"],
                "reserve_identity": reserve_identity,
                "reserve_policy": reserve_rules.VERSION,
                "instances": list(instances.values()),
                "zones": list(totals.values()),
                "reserve": reserve,
                "physical_fit": "NOT_ESTABLISHED_BY_MODULE_ACCOUNTING",
            }
        )
    sizing.require(evidence.read(source, ROLE) == data, "HOLD_MODULE_SOURCE_DRIFT")
    return cast(
        dict[str, Any],
        serial(
            {
                "schema_version": SCHEMA,
                "case_id": case_id,
                "composition_sha256": data["composition_sha256"],
                "sizing_sha256": data["sizing_sha256"],
                "evidence_binding": dict(source),
                "items": result,
            }
        ),
    )


def build_ledger(
    case_id: str,
    items: Sequence[Mapping[str, Any]],
    sizing_report: Mapping[str, Any],
    source: Any,
) -> dict[str, Any]:
    """No writes, source admissions, SKU inference, packing or cabinet choices."""
    try:
        # Resource arithmetic must not inherit a caller's rounding or traps.
        # Source precision/range/count limits keep every acceptance comparison
        # exact within this context; recurring division is diagnostic only.
        with localcontext(Context(prec=50)):
            return _build(case_id, items, sizing_report, source)
    except sizing.SizingHold:
        raise
    except (
        ValueError,
        KeyError,
        TypeError,
        OSError,
        AttributeError,
        RecursionError,
    ) as exc:
        raise sizing.SizingHold(
            "HOLD_MODULE_MALFORMED_OR_UNAVAILABLE_EVIDENCE"
        ) from exc


def verify_ledger(
    ledger: Any,
    case_id: str,
    items: Sequence[Mapping[str, Any]],
    sizing_report: Mapping[str, Any],
) -> None:
    sizing.require(isinstance(ledger, dict), "HOLD_MODULE_LEDGER_REQUIRED_BEFORE_HA1")
    sizing.require(
        ledger
        == build_ledger(case_id, items, sizing_report, ledger.get("evidence_binding")),
        "HOLD_MODULE_LEDGER_DRIFT",
    )


def build_sizing_report(
    case_id: str,
    items: Sequence[Mapping[str, Any]],
    base_report: Mapping[str, Any],
    source: Any,
) -> dict[str, Any]:
    """Add a versioned gate without changing the base selector or its policies."""
    sizing.require(
        base_report.get("schema_version") != REPORT_SCHEMA,
        "HOLD_MODULE_NESTED_REPORT",
    )
    ledger = build_ledger(case_id, items, base_report, source)
    return {
        "schema_version": REPORT_SCHEMA,
        "case_id": case_id,
        "items": copy.deepcopy(base_report["items"]),
        "sources": {
            "base_sizing_sources": copy.deepcopy(base_report["sources"]),
            "module_evidence": dict(source),
        },
        "base_report": copy.deepcopy(dict(base_report)),
        "module_ledger": ledger,
    }


def verify_sizing_report(
    report: Any,
    items: Sequence[Mapping[str, Any]],
    expected_case_id: str | None,
) -> None:
    obj(report, "schema_version case_id items sources base_report module_ledger")
    sizing.require(
        report["schema_version"] == REPORT_SCHEMA
        and isinstance(expected_case_id, str)
        and report["case_id"] == expected_case_id,
        "HOLD_MODULE_CASE_BINDING",
    )
    assert isinstance(expected_case_id, str)
    sources = obj(report["sources"], "base_sizing_sources module_evidence")
    base = report["base_report"]
    sizing.require(
        isinstance(base, dict) and base.get("schema_version") != REPORT_SCHEMA,
        "HOLD_MODULE_NESTED_REPORT",
    )
    if base.get("schema_version") == reserve_rules.BASE_SCHEMA:
        policy = project_policy(expected_case_id, sources["module_evidence"])
        base_sources = obj(base["sources"], "request reserve_policy algorithm_schema")
        sizing.require(
            base_sources["reserve_policy"] == policy, "HOLD_MODULE_RESERVE_POLICY_DRIFT"
        )
        sizing.require(
            base
            == sizing.size_composition(
                expected_case_id, items, base_sources["request"], reserve_policy=policy
            ),
            "HOLD_SIZING_REPORT_DRIFT",
        )
        sizing.require(
            [i["cabinet"] for i in items] == [s["cabinet"] for s in base["items"]],
            "HOLD_CONFIRMED_CABINET_DRIFT",
        )
    else:
        sizing.verify_report(
            base, items, expected_case_id=expected_case_id, before_human_approval_1=True
        )
    sizing.require(
        sources["base_sizing_sources"] == base["sources"],
        "HOLD_MODULE_BASE_SOURCES_DRIFT",
    )
    verify_ledger(report["module_ledger"], expected_case_id, items, base)
    sizing.require(
        report
        == build_sizing_report(
            expected_case_id, items, base, sources["module_evidence"]
        ),
        "HOLD_MODULE_REPORT_DRIFT",
    )


def _project_policy(case_id: str, source: Any) -> dict[str, Any]:
    """Read admitted project requirements before reserve-scoped base sizing."""
    data = evidence.read(source, ROLE)
    obj(
        data,
        "schema_version case_id composition_sha256 sizing_sha256 inventory_scope "
        "products profiles boards raw_sources",
    )
    sizing.require(
        data["schema_version"] == EVIDENCE_SCHEMA
        and data["case_id"] == case_id
        and data["inventory_scope"] == SCOPE,
        "HOLD_MODULE_EVIDENCE_SCHEMA",
    )
    raw = set()
    for ref in collection(data["raw_sources"]):
        obj(ref, "path sha256")
        evidence.safe_bytes(Path(string(ref["path"])), string(ref["sha256"]))
        raw.add((ref["path"], ref["sha256"]))
    projects = {}
    for board in collection(data["boards"]):
        obj(
            board,
            "item_id cabinet_sha256 quantity project_min_din_free_percent "
            "project_min_panel_free_percent zones instances groups source",
        )
        ref = obj(board["source"], "path sha256 locator")
        string(ref["locator"])
        sizing.require(
            (ref["path"], ref["sha256"]) in raw, "HOLD_MODULE_UNBOUND_RAW_SOURCE"
        )
        iid = string(board["item_id"])
        sizing.require(iid not in projects, "HOLD_MODULE_DUPLICATE_ID")
        projects[iid] = {
            "DIN": board["project_min_din_free_percent"],
            "PANEL": board["project_min_panel_free_percent"],
        }
    return reserve_rules.make(case_id, projects)


def project_policy(case_id: str, source: Any) -> dict[str, Any]:
    try:
        with localcontext(Context(prec=50)):
            return _project_policy(case_id, source)
    except sizing.SizingHold:
        raise
    except (
        ValueError,
        KeyError,
        TypeError,
        OSError,
        AttributeError,
        RecursionError,
    ) as exc:
        raise sizing.SizingHold(
            "HOLD_MODULE_MALFORMED_OR_UNAVAILABLE_EVIDENCE"
        ) from exc


def algorithm_schema(report: Any) -> str:
    if report["schema_version"] == reserve_rules.BASE_SCHEMA:
        return string(report["sources"]["algorithm_schema"])
    return string(report["schema_version"])


def size_base(
    case_id: str, items: Sequence[Mapping[str, Any]], request: Any, source: Any
) -> dict[str, Any]:
    # Missing module evidence cannot authorize new thresholds. The existing
    # base preflight may still run, but the mandatory ledger subsequently HOLDs.
    if source is None:
        return sizing.size_composition(case_id, items, request)
    try:
        with localcontext(Context(prec=50)):
            policy = project_policy(case_id, source)
            return sizing.size_composition(
                case_id, items, request, reserve_policy=policy
            )
    except sizing.SizingHold:
        raise
    except (
        ValueError,
        KeyError,
        TypeError,
        OSError,
        AttributeError,
        RecursionError,
    ) as exc:
        raise sizing.SizingHold(
            "HOLD_MODULE_MALFORMED_OR_UNAVAILABLE_EVIDENCE"
        ) from exc
