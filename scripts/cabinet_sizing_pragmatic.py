"""Versioned preliminary METAL planning, without inferred cabinet interiors.

Rectangular mounting zones and row datums below are a planning construction,
not cabinet mounting planes, usable dimensions or physical rail anchors.
Unsupported constructions and exhausted searches fail closed before ranking.
"""

from __future__ import annotations

import copy
from decimal import ROUND_CEILING, Decimal
from typing import Any

import cabinet_sizing_evidence as evidence
from cabinet_sizing import apparatus_hash, cabinet_identity, digest, require
from cabinet_sizing_selector import Budget, serial
from wu8_governed_sources import METAL_SIZES

REQUEST_SCHEMA = "cabinet_sizing.pragmatic_metal_request.v0.1"
SCHEMA = "cabinet_sizing.pragmatic_metal.v0.1"
POLICY = "DINVA-pragmatic-METAL-v0.1/envelope-v0.2/reserve-v0.1"
WHITELIST_SHA = "c1b412ce3b5aaa1b1882bcb4d8d952c96c89c76b1628a3d0fb2159a0473cb803"
ZERO = Decimal(0)
PITCH = Decimal(140)


def upward(value: Decimal) -> Decimal:
    """Six-place conservative numerical ceiling, never round required mm down."""
    return value.quantize(Decimal("0.000001"), rounding=ROUND_CEILING)


def whitelist() -> list[dict[str, Any]]:
    projection = [[*size, value[0]] for size, value in METAL_SIZES.items()]
    require(digest(projection) == WHITELIST_SHA, "HOLD_METAL_WHITELIST_DRIFT")
    return [
        {
            "cabinet_code": f"METAL-{h}X{w}X{d}-D{row}",
            "cabinet_label": f"METAL-{h}X{w}X{d}-D{row}",
            "cabinet_type": "METAL",
            "dimensions_mm": [h, w, d],
        }
        for h, w, d, row in projection
    ]


def request_for(case_id: str, items: Any) -> dict[str, Any]:
    return {
        "schema_version": REQUEST_SCHEMA,
        "case_id": case_id,
        "devices": evidence.default_binding(),
        "source_facts": {
            item["item_id"]: evidence.pragmatic_default_binding() for item in items
        },
    }


def source_fact(case_id: str, item: Any, binding: Any) -> dict[str, Any]:
    require(
        binding is not None, "HOLD_SOURCE_DIMENSIONS_INSTALL_HISTORY_EVIDENCE_REQUIRED"
    )
    fact = evidence.pragmatic_source_fact(case_id, item, binding)
    require(
        set(fact)
        == {
            "case_id",
            "item_id",
            "apparatus_sha256",
            "dimensions_status",
            "dimensions_mm",
            "installation",
            "prior_approval",
            "raw_sources",
        },
        "HOLD_SOURCE_FACT_SCHEMA",
    )
    require(
        fact["case_id"] == case_id
        and fact["item_id"] == item["item_id"]
        and fact["apparatus_sha256"] == apparatus_hash(item),
        "HOLD_SOURCE_FACT_COMPOSITION_BINDING",
    )
    require(
        fact["dimensions_status"] in {"ABSENT", "EXPLICIT"},
        "HOLD_SOURCE_DIMENSIONS_AMBIGUOUS",
    )
    if fact["dimensions_status"] == "EXPLICIT":
        evidence.dimensions(fact["dimensions_mm"])
    else:
        require(fact["dimensions_mm"] is None, "HOLD_SOURCE_DIMENSIONS_AMBIGUOUS")
    require(
        fact["installation"] is None
        or isinstance(fact["installation"], str)
        and bool(fact["installation"]),
        "HOLD_SOURCE_INSTALLATION_AMBIGUOUS",
    )
    prior = fact["prior_approval"]
    require(isinstance(prior, dict), "HOLD_PRIOR_APPROVAL_UNKNOWN")
    if prior.get("status") == "NONE":
        require(set(prior) == {"status"}, "HOLD_PRIOR_APPROVAL_UNKNOWN")
    else:
        require(
            set(prior) == {"status", "cabinet_code", "dimensions_mm"}
            and prior["status"] == "APPROVED",
            "HOLD_PRIOR_APPROVAL_UNKNOWN",
        )
        _, _, size = cabinet_identity(prior["cabinet_code"])
        require(size == prior["dimensions_mm"], "HOLD_PRIOR_CABINET_IDENTITY")
    return fact


def prepare(item: Any, binding: Any, classes: Any) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    seen = set()
    for component in item["components"]:
        cid = component["component_id"]
        require(isinstance(cid, str) and cid not in seen, "HOLD_DUPLICATE_COMPONENT")
        seen.add(cid)
        class_id = evidence.class_for(component, binding)
        require(class_id in classes, "HOLD_MISSING_CLASS_EVIDENCE")
        quantity = component.get("quantity", component.get("quantity_guess"))
        require(type(quantity) is int and 0 < quantity <= 256, "HOLD_DEVICE_QUANTITY")
        units.extend(
            {"component_id": cid, "unit": n, "envelope": classes[class_id]}
            for n in range(1, quantity + 1)
        )
    require(bool(units) and len(units) <= 256, "HOLD_EMPTY_OR_UNBOUNDED_COMPOSITION")
    return units


def partition(
    units: Any, rows: int, last_height: Decimal, budget: Budget
) -> tuple[Decimal, list[list[Any]]] | None:
    """Complete minimum-maximum-width partition with symmetry and lower bounds."""
    ordered = sorted(
        units,
        key=lambda u: (
            -u["envelope"]["dimensions_mm"][1],
            u["component_id"],
            u["unit"],
        ),
    )
    total = sum((u["envelope"]["dimensions_mm"][1] for u in ordered), ZERO)
    lower = max(
        upward(total * 4 / (3 * rows)),
        max(u["envelope"]["dimensions_mm"][1] for u in ordered),
    )
    greedy: list[list[Any]] = [[] for _ in range(rows)]
    loads = [ZERO] * rows
    for unit in ordered:
        allowed = [
            i
            for i in range(rows)
            if i < rows - 1 or unit["envelope"]["dimensions_mm"][0] <= last_height
        ]
        if not allowed:
            return None
        index = min(allowed, key=lambda i: (loads[i], i))
        greedy[index].append(unit)
        loads[index] += unit["envelope"]["dimensions_mm"][1]
    best = max(lower, max(loads))
    answer = copy.deepcopy(greedy)
    if best == lower:
        return best, answer
    current: list[list[Any]] = [[] for _ in range(rows)]
    loads = [ZERO] * rows
    visited = set()

    def search(index: int) -> None:
        nonlocal best, answer
        state = (index, tuple(sorted(loads[:-1])), loads[-1])
        if state in visited:
            return
        visited.add(state)
        budget.step()
        if index == len(ordered):
            result = max(lower, max(loads))
            if result < best:
                best, answer = result, copy.deepcopy(current)
            return
        unit = ordered[index]
        width = unit["envelope"]["dimensions_mm"][1]
        seen_loads = set()
        for ri in range(rows):
            signature = (loads[ri], last_height if ri == rows - 1 else PITCH)
            if (
                signature in seen_loads
                or loads[ri] + width >= best
                or ri == rows - 1
                and unit["envelope"]["dimensions_mm"][0] > last_height
            ):
                continue
            seen_loads.add(signature)
            loads[ri] += width
            current[ri].append(unit)
            search(index + 1)
            current[ri].pop()
            loads[ri] -= width
            if best == lower:
                return

    search(0)
    return best, answer


def planning_shapes(units: Any, maximum_height: Decimal) -> tuple[list[Any], Any]:
    din = [u for u in units if u["envelope"]["mounting"] == "DIN"]
    panel = [u for u in units if u["envelope"]["mounting"] == "PANEL"]
    # No incomplete panel search may justify a larger choice. The admitted real
    # source has one panel device. Multiple bodies need assembly pair anchors.
    require(len(panel) <= 1, "HOLD_PRAGMATIC_PANEL_GEOMETRY_UNSUPPORTED")
    panel_shape: dict[str, Any] | None = None
    if panel:
        env = panel[0]["envelope"]
        h, w, d = env["dimensions_mm"]
        top, bottom, left, right = env["clearance_mm"]
        body = env["body_reference"]
        if body is not None:
            bh, bw, bd = evidence.dimensions(body["dimensions_mm"])
            edge = [evidence.number(x, zero=True) for x in body["edge_mm"]]
            require(
                w == bw and d == bd and h >= bh,
                "HOLD_BODY_ASSEMBLY_REFERENCE_INCOMPLETE",
            )
            # Without a body/assembly offset, either end may carry the entire
            # protrusion. Both edge distances cover it; do not add it twice.
            protrusion = h - bh
            require(
                edge[0] >= protrusion and edge[1] >= protrusion,
                "HOLD_BODY_ASSEMBLY_REFERENCE_INCOMPLETE",
            )
            ph = bh + max(edge[0], top) + max(edge[1], bottom)
            pw = bw + max(edge[2], left) + max(edge[3], right)
        else:
            ph, pw = h + top + bottom, w + left + right
        panel_shape = {
            "minimum_mm": [ph, pw, d],
            "occupied_mm2": h * w,
            "unit": panel[0],
            "body_reference": body,
        }
    if not din:
        return [None], panel_shape
    for unit in din:
        env = unit["envelope"]
        require(
            not any(env["clearance_mm"] + env["pair_gap_mm"] + [env["extra_gap_mm"]]),
            "HOLD_PRAGMATIC_DIN_CLEARANCE_GEOMETRY_UNSUPPORTED",
        )
    height = max(u["envelope"]["dimensions_mm"][0] for u in din)
    require(height <= PITCH, "HOLD_PRAGMATIC_DIN_PITCH_GEOMETRY_UNSUPPORTED")
    depth = max(u["envelope"]["dimensions_mm"][2] for u in din)
    occupied = sum((u["envelope"]["dimensions_mm"][1] for u in din), ZERO)
    shapes = []
    budget = Budget()
    rows = 1
    last_heights = sorted({u["envelope"]["dimensions_mm"][0] for u in din})
    while (rows - 1) * PITCH <= maximum_height:
        for last_height in last_heights:
            if (rows - 1) * PITCH + last_height > maximum_height:
                continue
            packed = partition(din, rows, last_height, budget)
            if packed is None:
                continue
            width, contents = packed
            row_heights = [
                max(
                    (u["envelope"]["dimensions_mm"][0] for u in row),
                    default=last_height,
                )
                for row in contents
            ]
            reference = next(
                u["envelope"]["dimensions_mm"]
                for u in din
                if u["envelope"]["dimensions_mm"][0] == last_height
            )
            actual_height = max(
                ri * PITCH + row_height for ri, row_height in enumerate(row_heights)
            )
            shapes.append(
                {
                    "dimensions_mm": [actual_height, width, depth],
                    "rows": contents,
                    "occupied_mm": occupied,
                    "row_heights": row_heights,
                    "spare_references": [
                        None if row else reference for row in contents
                    ],
                }
            )
        rows += 1
    require(bool(shapes), "HOLD_NO_FITTING_APPROVED_METAL")
    return shapes, panel_shape


def construct(
    din: Any, panel: Any, bound: Any, orientation: str
) -> dict[str, Any] | None:
    dh, dw, dd = din["dimensions_mm"] if din else [ZERO] * 3
    ph, pw, pd = panel["minimum_mm"] if panel else [ZERO] * 3
    if max(dd, pd) > bound[2]:
        return None
    max_ph = bound[0] - (dh if orientation == "VERTICAL" else ZERO)
    max_pw = bound[1] - (dw if orientation == "HORIZONTAL" else ZERO)
    if panel:
        if max_ph < ph or max_pw < pw:
            return None
        area = panel["occupied_mm2"]
        # Independent panel denominator; ceiling avoids underestimating 1/3mm.
        ph = max(ph, upward(area * 4 / (3 * max_pw)))
        if ph > max_ph:
            return None
        pw = max(pw, upward(area * 4 / (3 * ph)))
        if pw > max_pw:
            return None
    if orientation == "VERTICAL":
        required = [dh + ph, max(dw, pw), max(dd, pd)]
        panel_origin, din_origin = [ZERO, ZERO], [ph, ZERO]
    else:
        required = [max(dh, ph), dw + pw, max(dd, pd)]
        panel_origin, din_origin = [ZERO, ZERO], [ZERO, pw]
    if any(required[i] > bound[i] for i in range(3)):
        return None
    reserve: dict[str, Any] = {}
    zones = []
    placements = []
    if din:
        capacity = dw * len(din["rows"])
        reserve["DIN"] = {
            "occupied_mm": din["occupied_mm"],
            "capacity_mm": capacity,
            "free_mm": capacity - din["occupied_mm"],
            "minimum_free_fraction": "0.25",
        }
        zones.append(
            {
                "kind": "DIN",
                "origin_mm": din_origin,
                "planning_extent_mm": [dh, dw, dd],
                "row_datums_mm": [ri * PITCH for ri in range(len(din["rows"]))],
                "row_pitch_mm": PITCH,
                "row_planning_heights_mm": din["row_heights"],
                "spare_row_reference_dimensions_mm": din["spare_references"],
                "physical_rail_anchors": None,
            }
        )
        for ri, row in enumerate(din["rows"]):
            x = ZERO
            for unit in row:
                env = unit["envelope"]
                placements.append(
                    {
                        "component_id": unit["component_id"],
                        "unit": unit["unit"],
                        "zone": "DIN",
                        "planning_envelope_origin_mm": [
                            din_origin[0] + ri * PITCH,
                            din_origin[1] + x,
                        ],
                        "dimensions_mm": env["dimensions_mm"],
                    }
                )
                x += env["dimensions_mm"][1]
    if panel:
        reserve["PANEL"] = {
            "occupied_mm2": panel["occupied_mm2"],
            "capacity_mm2": ph * pw,
            "free_mm2": ph * pw - panel["occupied_mm2"],
            "minimum_free_fraction": "0.25",
        }
        zones.append(
            {
                "kind": "PANEL",
                "origin_mm": panel_origin,
                "planning_extent_mm": [ph, pw, pd],
            }
        )
        unit = panel["unit"]
        placements.append(
            {
                "component_id": unit["component_id"],
                "unit": unit["unit"],
                "zone": "PANEL",
                "dimensions_mm": unit["envelope"]["dimensions_mm"],
                "body_reference": panel["body_reference"],
                "assembly_anchor_mm": None,
                "planning_containment": (
                    "body-edge clearances cover either unknown assembly protrusion"
                ),
            }
        )
    return {
        "required_dimensions_mm": required,
        "orientation": orientation,
        "zones": zones,
        "placements": placements,
        "reserve": reserve,
    }


def validate_request(case_id: str, request: Any) -> dict[str, Any]:
    require(
        isinstance(request, dict)
        and set(request) == {"schema_version", "case_id", "devices", "source_facts"}
        and request["schema_version"] == REQUEST_SCHEMA
        and isinstance(request["source_facts"], dict),
        "HOLD_PRAGMATIC_REQUEST_SCHEMA",
    )
    require(request["case_id"] == case_id, "HOLD_CASE_BINDING")
    return dict(request)


def select(case_id: str, items: Any, request: Any = None) -> dict[str, Any]:
    req = validate_request(
        case_id, request_for(case_id, items) if request is None else request
    )
    require(isinstance(items, (list, tuple)) and bool(items), "HOLD_EMPTY_COMPOSITION")
    ids = [item["item_id"] for item in items]
    require(len(set(ids)) == len(ids), "HOLD_DUPLICATE_ITEM")
    require(set(req["source_facts"]) == set(ids), "HOLD_SOURCE_FACT_COVERAGE")
    cabs = whitelist()
    classes = evidence.envelopes(req["devices"])
    selections = []
    for item in items:
        fact = source_fact(case_id, item, req["source_facts"][item["item_id"]])
        units = prepare(item, req["devices"], classes)
        # Complete the supported search across the whole whitelist, even when
        # an explicit source size restricts selection to one identity.
        shapes, panel = planning_shapes(
            units, max(Decimal(c["dimensions_mm"][0]) for c in cabs)
        )
        candidates = cabs
        if fact["dimensions_status"] == "EXPLICIT":
            exact = evidence.dimensions(fact["dimensions_mm"])
            candidates = [
                c for c in cabs if evidence.dimensions(c["dimensions_mm"]) == exact
            ]
            require(bool(candidates), "HOLD_SOURCE_DIMENSIONS_OUTSIDE_METAL_WHITELIST")
        feasible = []
        outcomes = []
        for cab in candidates:
            layouts = [
                layout
                for shape in shapes
                for orientation in ("VERTICAL", "HORIZONTAL")
                if (
                    layout := construct(
                        shape,
                        panel,
                        evidence.dimensions(cab["dimensions_mm"]),
                        orientation,
                    )
                )
                is not None
            ]
            outcomes.append(
                {"cabinet_code": cab["cabinet_code"], "fits": bool(layouts)}
            )
            if layouts:
                layout = min(
                    layouts,
                    key=lambda x: (*x["required_dimensions_mm"], x["orientation"]),
                )
                feasible.append((cab, layout))
        require(
            bool(feasible),
            (
                "HOLD_SOURCE_DIMENSIONS_INCOMPATIBLE"
                if fact["dimensions_status"] == "EXPLICIT"
                else "HOLD_NO_FITTING_APPROVED_METAL"
            ),
        )
        minima = [
            (cab, layout)
            for cab, layout in feasible
            if all(
                all(
                    a <= b
                    for a, b in zip(
                        cab["dimensions_mm"], other["dimensions_mm"], strict=True
                    )
                )
                for other, _ in feasible
            )
        ]
        require(len(minima) == 1, "HOLD_SMALLEST_CABINET_AMBIGUOUS")
        cab, layout = minima[0]
        prior = fact["prior_approval"]
        if prior["status"] == "APPROVED":
            require(
                cab["cabinet_code"] == prior["cabinet_code"]
                and cab["dimensions_mm"] == prior["dimensions_mm"],
                "HOLD_CABINET_CHANGE_REQUIRES_NEW_HUMAN_APPROVAL",
            )
        selections.append(
            {
                "item_id": item["item_id"],
                "apparatus_sha256": apparatus_hash(item),
                "cabinet": cab,
                "required_dimensions_mm": layout["required_dimensions_mm"],
                "layout": layout,
                "envelopes": {
                    cid: classes[cid]
                    for cid in sorted({u["envelope"]["class_id"] for u in units})
                },
                "preliminary_only": True,
                "unverified": {
                    "cabinet_ip": None,
                    "installation_compatibility": None,
                    "physical_rail_anchors": None,
                    "factory_layout": None,
                },
                "provenance": {
                    "policy": POLICY,
                    "whitelist_sha256": WHITELIST_SHA,
                    "source_fact": fact,
                    "candidate_outcomes": outcomes,
                    "planning_model": (
                        "independent rectangular zones; all DIN row counts; "
                        "both zone orientations; exact width partitions; "
                        "complete admitted-envelope spare rows; "
                        "six-place upward arithmetic"
                    ),
                },
            }
        )
    return dict(
        serial(
            {
                "schema_version": SCHEMA,
                "case_id": case_id,
                "items": selections,
                "sources": req,
            }
        )
    )
