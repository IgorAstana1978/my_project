"""Automatic, evidence-bound, fixed-orientation cabinet constraint search.

Search uncertainty is HOLD, never evidence that a larger cabinet is necessary.
Neither selected cabinet nor per-Case device placements are accepted as input.
"""

from __future__ import annotations

import itertools
from decimal import Decimal
from typing import Any

import cabinet_sizing_evidence as evidence
from cabinet_sizing import apparatus_hash, cabinet_identity, digest, require

REQUEST_SCHEMA = "cabinet_sizing.auto_request.v0.2"
SCHEMA = "cabinet_sizing.auto.v0.2"
POLICY = "DINVA-reserve-v0.1/source-dimension-precedence-v0.1/envelope-v0.2"
SEARCH_LIMIT = 100000
ZERO = Decimal(0)


def serial(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, dict):
        return {k: serial(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serial(v) for v in value]
    return value


class Budget:
    def __init__(self) -> None:
        self.remaining = SEARCH_LIMIT

    def step(self) -> None:
        self.remaining -= 1
        require(self.remaining >= 0, "HOLD_LAYOUT_SEARCH_UNCERTAIN")


def request_for(case_id: str) -> dict[str, Any]:
    return {
        "schema_version": REQUEST_SCHEMA,
        "case_id": case_id,
        "devices": evidence.default_binding(),
        "catalogue": None,
        "source_facts": {},
    }


def validate_request(case_id: str, request: Any) -> dict[str, Any]:
    require(
        isinstance(request, dict)
        and set(request)
        == {"schema_version", "case_id", "devices", "catalogue", "source_facts"}
        and request["schema_version"] == REQUEST_SCHEMA
        and isinstance(request["source_facts"], dict),
        "HOLD_AUTOMATIC_REQUEST_SCHEMA",
    )
    require(request["case_id"] == case_id, "HOLD_CASE_BINDING")
    return dict(request)


def catalogue(binding: Any) -> list[dict[str, Any]]:
    require(
        binding is not None, "HOLD_MISSING_CABINET_USABLE_INTERIOR_INSTALL_EVIDENCE"
    )
    data = evidence.read(binding, "catalogue")
    require(
        set(data) <= {"cabinets", "raw_sources", "version"}
        and isinstance(data.get("cabinets"), list),
        "HOLD_CATALOGUE_SCHEMA",
    )
    require(
        bool(data["cabinets"]), "HOLD_MISSING_CABINET_USABLE_INTERIOR_INSTALL_EVIDENCE"
    )
    seen = set()
    for cab in data["cabinets"]:
        require(
            isinstance(cab, dict)
            and set(cab)
            == {
                "cabinet_code",
                "cabinet_label",
                "cabinet_type",
                "dimensions_mm",
                "installation",
                "ip",
                "shock_class",
                "zones",
            },
            "HOLD_CABINET_INTERIOR_SCHEMA",
        )
        code = cab["cabinet_code"]
        require(
            isinstance(code, str) and code not in seen,
            "HOLD_DUPLICATE_CABINET_IDENTITY",
        )
        seen.add(code)
        _, kind, outer = cabinet_identity(code)
        require(
            cab["dimensions_mm"] == outer and cab["cabinet_type"] == kind,
            "HOLD_CABINET_DIMENSION_IDENTITY",
        )
        require(
            isinstance(cab["cabinet_label"], str)
            and bool(cab["cabinet_label"].strip()),
            "HOLD_CABINET_LABEL",
        )
        require(
            isinstance(cab["installation"], str) and bool(cab["installation"]),
            "HOLD_CABINET_INSTALL_EVIDENCE",
        )
        require(
            isinstance(cab["ip"], list)
            and len(cab["ip"]) == 2
            and all(type(n) is int and 0 <= n <= 9 for n in cab["ip"]),
            "HOLD_CABINET_IP_EVIDENCE",
        )
        require(cab["shock_class"] in {"I", "II", None}, "HOLD_CABINET_SHOCK_EVIDENCE")
        require(
            isinstance(cab["zones"], list) and bool(cab["zones"]),
            "HOLD_CABINET_USABLE_ZONES",
        )
        zones: list[tuple[list[Decimal], list[Decimal]]] = []
        zone_ids = set()
        for zone in cab["zones"]:
            require(
                isinstance(zone, dict)
                and set(zone)
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
                },
                "HOLD_USABLE_ZONE_SCHEMA",
            )
            require(
                isinstance(zone["zone_id"], str) and zone["zone_id"] not in zone_ids,
                "HOLD_DUPLICATE_ZONE",
            )
            zone_ids.add(zone["zone_id"])
            require(zone["kind"] in {"DIN", "PANEL"}, "HOLD_ZONE_MOUNTING_CLASS")
            pos = evidence.dimensions(zone["origin_mm"], zero=True)
            size = evidence.dimensions(zone["usable_mm"])
            require(
                evidence.number(zone["mounting_plane_mm"], zero=True) <= size[2],
                "HOLD_MOUNTING_PLANE_OUTSIDE_USABLE",
            )
            require(
                all(pos[i] + size[i] <= outer[i] for i in range(3)),
                "HOLD_USABLE_OUTSIDE_CABINET",
            )
            for other_pos, other_size in zones:
                require(
                    any(
                        pos[i] + size[i] <= other_pos[i]
                        or other_pos[i] + other_size[i] <= pos[i]
                        for i in range(3)
                    ),
                    "HOLD_OVERLAPPING_USABLE_ZONES",
                )
            zones.append((pos, size))
            require(isinstance(zone["rails_mm"], list), "HOLD_DIN_RAIL_EVIDENCE")
            rails = [evidence.number(y, zero=True) for y in zone["rails_mm"]]
            if zone["kind"] == "DIN":
                require(
                    bool(rails) and rails == sorted(set(rails)),
                    "HOLD_DIN_RAIL_EVIDENCE",
                )
                require(
                    all(rails[i + 1] - rails[i] == 140 for i in range(len(rails) - 1)),
                    "HOLD_DIN_PITCH_EVIDENCE",
                )
                require(
                    all(y <= size[0] for y in rails), "HOLD_DIN_RAIL_OUTSIDE_USABLE"
                )
            else:
                require(not rails, "HOLD_PANEL_RAIL_SCHEMA")
            require(
                zone["panel_material"] in {None, "metal", "insulating"},
                "HOLD_PANEL_MATERIAL_EVIDENCE",
            )
            if zone["panel_thickness_mm"] is not None:
                evidence.number(zone["panel_thickness_mm"])
            require(
                type(zone["barriers_compatible"]) is bool,
                "HOLD_BARRIER_COMPATIBILITY_EVIDENCE",
            )
    return sorted(data["cabinets"], key=lambda c: c["cabinet_code"])


def source_fact(case_id: str, item: dict[str, Any], binding: Any) -> dict[str, Any]:
    require(
        binding is not None, "HOLD_SOURCE_DIMENSIONS_INSTALL_HISTORY_EVIDENCE_REQUIRED"
    )
    fact = evidence.read(binding, "source_fact")
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
        isinstance(fact["installation"], str) and bool(fact["installation"]),
        "HOLD_SOURCE_INSTALLATION_AMBIGUOUS",
    )
    prior = fact["prior_approval"]
    require(
        isinstance(prior, dict) and prior.get("status") in {"NONE", "APPROVED"},
        "HOLD_PRIOR_APPROVAL_UNKNOWN",
    )
    if prior["status"] == "NONE":
        require(set(prior) == {"status"}, "HOLD_PRIOR_APPROVAL_UNKNOWN")
    else:
        require(
            set(prior) == {"status", "cabinet_code", "dimensions_mm"},
            "HOLD_PRIOR_APPROVAL_UNKNOWN",
        )
        _, _, outer = cabinet_identity(prior["cabinet_code"])
        require(prior["dimensions_mm"] == outer, "HOLD_PRIOR_CABINET_IDENTITY")
    return fact


def compatible(unit: dict[str, Any], cab: dict[str, Any], zone: dict[str, Any]) -> bool:
    env = unit["envelope"]
    if env["mounting"] != zone["kind"]:
        return False
    if any(cab["ip"][i] < env["min_ip"][i] for i in range(2)):
        return False
    if env["shock_class"] is not None and cab["shock_class"] != env["shock_class"]:
        return False
    if env["body_reference"] is not None:
        body = env["body_reference"]
        material = zone["panel_material"]
        require(
            material in {"metal", "insulating"}
            and zone["panel_thickness_mm"] is not None,
            "HOLD_PANEL_MOUNTING_MATERIAL_EVIDENCE",
        )
        minimum = (
            body["metal_panel_min_mm"]
            if material == "metal"
            else body["insulating_panel_min_mm"]
        )
        if evidence.number(zone["panel_thickness_mm"]) < evidence.number(minimum):
            return False
        if body["interphase_barriers_required"] and not zone["barriers_compatible"]:
            return False
    return True


def din_layout(
    units: list[dict[str, Any]], cab: dict[str, Any], budget: Budget
) -> tuple[list[dict[str, Any]], dict[str, Any]] | None:
    if len(units) > 1:
        require(
            all(u["envelope"]["pair_gap_mm"][0] == 0 for u in units),
            "HOLD_DIN_VERTICAL_PAIR_CLEARANCE_UNSUPPORTED",
        )
        require(
            sum(z["kind"] == "DIN" for z in cab["zones"]) <= 1
            or all(u["envelope"]["pair_gap_mm"][1] == 0 for u in units),
            "HOLD_DIN_PAIR_CLEARANCE_ACROSS_ZONES_UNSUPPORTED",
        )

    def horizontal_gap(first: dict[str, Any], second: dict[str, Any]) -> Decimal:
        return max(
            evidence.number(value, zero=True)
            for value in (
                first["extra_gap_mm"],
                second["extra_gap_mm"],
                first["pair_gap_mm"][1],
                second["pair_gap_mm"][1],
            )
        )

    rails = []
    for zone in cab["zones"]:
        if zone["kind"] == "DIN":
            for rail in zone["rails_mm"]:
                rails.append((zone, evidence.number(rail, zero=True)))
    total = sum((evidence.dimensions(z["usable_mm"])[1] for z, _ in rails), ZERO)
    width = sum((u["envelope"]["dimensions_mm"][1] for u in units), ZERO)
    if units and (not rails or width * 4 > total * 3):
        return None
    positions: list[list[dict[str, Any]]] = [[] for _ in rails]
    uncertain_cross_rail = False

    def search(remaining: list[dict[str, Any]]) -> bool:
        nonlocal uncertain_cross_rail
        budget.step()
        if not remaining:
            occupied = sum((r[-1]["end"] for r in positions if r), ZERO)
            return occupied * 4 <= total * 3
        unique = set()
        for index, unit in enumerate(remaining):
            env = unit["envelope"]
            signature = digest(serial(env))
            if signature in unique:
                continue
            unique.add(signature)
            require(
                env["rail_offset_mm"] is not None and env["rail_back_mm"] is not None,
                "HOLD_DEVICE_RAIL_MOUNTING_REFERENCE",
            )
            offset = evidence.number(env["rail_offset_mm"], zero=True)
            h, w, d = env["dimensions_mm"]
            require(offset <= h, "HOLD_RAIL_REFERENCE_OUTSIDE_DEVICE")
            top, bottom, left, right = env["clearance_mm"]
            for ri, (zone, y) in enumerate(rails):
                if not compatible(unit, cab, zone):
                    continue
                zh, zw, zd = evidence.dimensions(zone["usable_mm"])
                z = evidence.number(
                    zone["mounting_plane_mm"], zero=True
                ) - evidence.number(env["rail_back_mm"], zero=True)
                row = positions[ri]
                gap = horizontal_gap(env, row[-1]["unit"]["envelope"]) if row else ZERO
                x = max(left, row[-1]["end"] + gap) if row else left
                if (
                    y - offset < top
                    or y - offset + h + bottom > zh
                    or x + w + right > zw
                    or z < 0
                    or z + d > zd
                ):
                    continue
                # Check complete device envelopes across adjacent rails.
                if any(
                    other_zone["zone_id"] == zone["zone_id"]
                    and not (
                        y - offset + h <= entry["y"]
                        or entry["y"] + entry["unit"]["envelope"]["dimensions_mm"][0]
                        <= y - offset
                        or x + w + horizontal_gap(env, entry["unit"]["envelope"])
                        <= entry["x"]
                        or entry["end"] + horizontal_gap(env, entry["unit"]["envelope"])
                        <= x
                    )
                    for rj, (other_zone, _) in enumerate(rails)
                    if rj != ri
                    for entry in positions[rj]
                ):
                    uncertain_cross_rail = True
                    continue
                row.append(
                    {"unit": unit, "x": x, "y": y - offset, "z": z, "end": x + w}
                )
                if search(remaining[:index] + remaining[index + 1 :]):
                    return True
                row.pop()
        return False

    if not search(units):
        require(not uncertain_cross_rail, "HOLD_DIN_CROSS_RAIL_LAYOUT_UNCERTAIN")
        return None
    layout = []
    for (zone, rail), row in zip(rails, positions, strict=True):
        origin = evidence.dimensions(zone["origin_mm"], zero=True)
        for placed in row:
            unit = placed["unit"]
            layout.append(
                {
                    "component_id": unit["component_id"],
                    "unit": unit["unit"],
                    "zone_id": zone["zone_id"],
                    "rail_mm": rail,
                    "origin_mm": [
                        origin[0] + placed["y"],
                        origin[1] + placed["x"],
                        origin[2] + placed["z"],
                    ],
                    "dimensions_mm": unit["envelope"]["dimensions_mm"],
                }
            )
    occupied = sum((row[-1]["end"] for row in positions if row), ZERO)
    return layout, {
        "total_usable_mm": total,
        "occupied_mm": occupied,
        "free_mm": total - occupied,
        "minimum_free_fraction": "0.25",
    }


def coordinates(
    count: int,
    edges: list[tuple[int, int, Decimal]],
    low: list[Decimal],
    high: list[Decimal],
) -> list[Decimal] | None:
    values = list(low)
    for turn in range(count):
        changed = False
        for first, second, distance in edges:
            if values[second] < values[first] + distance:
                values[second] = values[first] + distance
                changed = True
        if not changed:
            return values if all(values[i] <= high[i] for i in range(count)) else None
        if turn == count - 1:
            return None
    return values if all(values[i] <= high[i] for i in range(count)) else None


def pack_panel(
    units: list[dict[str, Any]], zone: dict[str, Any], budget: Budget
) -> list[dict[str, Any]] | None:
    if not units:
        return []
    zh, zw, zd = evidence.dimensions(zone["usable_mm"])
    # Unknown assembly-to-body anchor cannot prove pair geometry. Never overconstrain
    # two body-reference devices and call a smaller cabinet impossible.
    if any(u["envelope"]["body_reference"] is not None for u in units):
        require(len(units) == 1, "HOLD_PANEL_BODY_ASSEMBLY_PAIR_REFERENCE")
    sizes = []
    margins = []
    bodies: list[Any] = []
    for unit in units:
        env = unit["envelope"]
        h, w, d = env["dimensions_mm"]
        if evidence.number(zone["mounting_plane_mm"], zero=True) + d > zd:
            return None
        body = env["body_reference"]
        if body is None:
            sizes.append((h, w))
            margins.append(env["clearance_mm"])
            bodies.append(None)
        else:
            bh, bw, bd = evidence.dimensions(body["dimensions_mm"])
            edge = [evidence.number(n, zero=True) for n in body["edge_mm"]]
            protrusion = h - bh
            require(
                w == bw
                and d == bd
                and protrusion >= 0
                and edge[0] >= protrusion
                and edge[1] >= protrusion,
                "HOLD_BODY_ASSEMBLY_REFERENCE_INCOMPLETE",
            )
            sizes.append((bh, bw))
            margins.append([max(edge[i], env["clearance_mm"][i]) for i in range(4)])
            bodies.append(body)
    low_y = [m[0] for m in margins]
    low_x = [m[2] for m in margins]
    high_y = [zh - sizes[i][0] - margins[i][1] for i in range(len(units))]
    high_x = [zw - sizes[i][1] - margins[i][3] for i in range(len(units))]
    if any(low_y[i] > high_y[i] or low_x[i] > high_x[i] for i in range(len(units))):
        return None
    pairs = list(itertools.combinations(range(len(units)), 2))
    xedges: list[tuple[int, int, Decimal]] = []
    yedges: list[tuple[int, int, Decimal]] = []

    def search(index: int) -> tuple[list[Decimal], list[Decimal]] | None:
        budget.step()
        xs = coordinates(len(units), xedges, low_x, high_x)
        ys = coordinates(len(units), yedges, low_y, high_y)
        if xs is None or ys is None:
            return None
        if index == len(pairs):
            return ys, xs
        first, second = pairs[index]
        for axis in (1, 0):
            edges = xedges if axis else yedges
            gap = max(
                units[first]["envelope"]["pair_gap_mm"][axis],
                units[second]["envelope"]["pair_gap_mm"][axis],
            )
            for a, b in ((first, second), (second, first)):
                edges.append((a, b, sizes[a][axis] + gap))
                found = search(index + 1)
                if found is not None:
                    return found
                edges.pop()
        return None

    found = search(0)
    if found is None:
        return None
    origin = evidence.dimensions(zone["origin_mm"], zero=True)
    ys, xs = found
    return [
        {
            "component_id": u["component_id"],
            "unit": u["unit"],
            "zone_id": zone["zone_id"],
            "origin_mm": [
                origin[0] + ys[i],
                origin[1] + xs[i],
                origin[2] + evidence.number(zone["mounting_plane_mm"], zero=True),
            ],
            "reference": "body" if bodies[i] else "envelope",
            "dimensions_mm": u["envelope"]["dimensions_mm"],
            "body_reference": bodies[i],
        }
        for i, u in enumerate(units)
    ]


def panel_layout(
    units: list[dict[str, Any]], cab: dict[str, Any], budget: Budget
) -> tuple[list[dict[str, Any]], dict[str, Any]] | None:
    zones = [z for z in cab["zones"] if z["kind"] == "PANEL"]
    total = sum(
        (
            evidence.dimensions(z["usable_mm"])[0]
            * evidence.dimensions(z["usable_mm"])[1]
            for z in zones
        ),
        ZERO,
    )
    occupied = sum(
        (
            u["envelope"]["dimensions_mm"][0] * u["envelope"]["dimensions_mm"][1]
            for u in units
        ),
        ZERO,
    )
    if units and (not zones or occupied * 4 > total * 3):
        return None
    for assignment in itertools.product(range(len(zones)), repeat=len(units)):
        budget.step()
        if any(
            not compatible(unit, cab, zones[assignment[i]])
            for i, unit in enumerate(units)
        ):
            continue
        layout = []
        for zi, zone in enumerate(zones):
            packed = pack_panel(
                [u for i, u in enumerate(units) if assignment[i] == zi], zone, budget
            )
            if packed is None:
                break
            layout.extend(packed)
        else:
            return layout, {
                "total_usable_mm2": total,
                "occupied_mm2": occupied,
                "free_mm2": total - occupied,
                "minimum_free_fraction": "0.25",
            }
    return None


def fit(
    units: list[dict[str, Any]], cab: dict[str, Any], fact: dict[str, Any]
) -> dict[str, Any] | None:
    if cab["installation"] != fact["installation"]:
        return None
    budget = Budget()
    din = din_layout(
        [u for u in units if u["envelope"]["mounting"] == "DIN"], cab, budget
    )
    panel = panel_layout(
        [u for u in units if u["envelope"]["mounting"] == "PANEL"], cab, budget
    )
    if din is None or panel is None:
        return None
    return {
        "placements": din[0] + panel[0],
        "reserve": {"DIN": din[1], "PANEL": panel[1]},
    }


def select(case_id: str, items: Any, request: Any = None) -> dict[str, Any]:
    req = validate_request(
        case_id, request_for(case_id) if request is None else request
    )
    require(isinstance(items, (list, tuple)) and bool(items), "HOLD_EMPTY_COMPOSITION")
    ids = [i["item_id"] for i in items]
    require(len(set(ids)) == len(ids), "HOLD_DUPLICATE_ITEM")
    require(set(req["source_facts"]) <= set(ids), "HOLD_UNEXPECTED_SOURCE_FACT_ITEM")
    classes = evidence.envelopes(req["devices"])
    prepared = []
    for item in items:
        units: list[dict[str, Any]] = []
        seen = set()
        for component in item["components"]:
            cid = component["component_id"]
            require(
                isinstance(cid, str) and cid not in seen, "HOLD_DUPLICATE_COMPONENT"
            )
            seen.add(cid)
            class_id = evidence.class_for(component, req["devices"])
            require(class_id in classes, f"HOLD_MISSING_CLASS_EVIDENCE:{class_id}")
            quantity = component.get("quantity", component.get("quantity_guess"))
            require(
                type(quantity) is int and 0 < quantity <= 256, "HOLD_DEVICE_QUANTITY"
            )
            units.extend(
                {"component_id": cid, "unit": n, "envelope": classes[class_id]}
                for n in range(1, quantity + 1)
            )
        require(
            bool(units) and len(units) <= 256, "HOLD_EMPTY_OR_UNBOUNDED_COMPOSITION"
        )
        prepared.append(units)
    cabs = catalogue(req["catalogue"])
    selections = []
    for item, units in zip(items, prepared, strict=True):
        fact = source_fact(case_id, item, req["source_facts"].get(item["item_id"]))
        candidates = cabs
        if fact["dimensions_status"] == "EXPLICIT":
            exact = evidence.dimensions(fact["dimensions_mm"])
            candidates = [
                c for c in cabs if evidence.dimensions(c["dimensions_mm"]) == exact
            ]
            require(
                bool(candidates), "HOLD_SOURCE_DIMENSIONS_NO_APPROVED_INTERIOR_EVIDENCE"
            )
        valid = []
        for cab in candidates:
            layout = fit(units, cab, fact)
            if layout is not None:
                valid.append((cab, layout))
        require(
            bool(valid),
            (
                "HOLD_SOURCE_DIMENSIONS_INCOMPATIBLE"
                if fact["dimensions_status"] == "EXPLICIT"
                else "HOLD_NO_VALID_APPROVED_CABINET"
            ),
        )
        minima = [
            (c, candidate_layout)
            for c, candidate_layout in valid
            if all(
                all(
                    a <= b
                    for a, b in zip(
                        c["dimensions_mm"], other["dimensions_mm"], strict=True
                    )
                )
                for other, _ in valid
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
                "cabinet": {
                    k: cab[k]
                    for k in (
                        "cabinet_code",
                        "cabinet_label",
                        "cabinet_type",
                        "dimensions_mm",
                    )
                },
                "layout": layout,
                "envelopes": {
                    cid: classes[cid]
                    for cid in sorted({u["envelope"]["class_id"] for u in units})
                },
                "provenance": {
                    "policy": POLICY,
                    "source_fact": req["source_facts"][item["item_id"]],
                    "catalogue": req["catalogue"],
                    "devices": req["devices"],
                    "candidate_codes": [c["cabinet_code"] for c in candidates],
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
