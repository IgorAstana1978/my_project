"""Exact, bounded rectangular planning mechanics; no cabinet/source authority.

Coordinates are x(width), y(height), z(depth), in mm. Public box sizes are XYZ;
search dimensions and device/reference dimensions are HWD. No rotations occur.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_CEILING, Decimal, InvalidOperation, localcontext
from itertools import combinations
from typing import Any

ZERO = Decimal(0)
PITCH = Decimal(140)
MAX_OBJECTS = 1024


def number(value: Any, *, zero: bool = False) -> Decimal:
    if type(value) not in (int, float, str, Decimal):
        raise ValueError("NUMBER_TYPE")
    try:
        with localcontext():
            result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("NUMBER_INVALID") from exc
    exponent = result.as_tuple().exponent
    if (
        not result.is_finite()
        or result < 0
        or not zero
        and result == 0
        or result > 100000
        or not isinstance(exponent, int)
        or exponent < -6
    ):
        raise ValueError("NUMBER_RANGE_OR_PRECISION")
    return result


def serial(value: Any) -> Any:
    if isinstance(value, Decimal):
        return (
            format(value, "f").rstrip("0").rstrip(".")
            if "." in format(value, "f")
            else str(value)
        )
    if isinstance(value, dict):
        return {key: serial(v) for key, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [serial(v) for v in value]
    return value


def vector(value: Any, length: int, *, zero: bool = False) -> list[Decimal]:
    if not isinstance(value, (list, tuple)) or len(value) != length:
        raise ValueError("VECTOR_LENGTH")
    return [number(v, zero=zero) for v in value]


def box(identity: str, kind: str, origin: Any, size: Any) -> dict[str, Any]:
    if (
        not isinstance(identity, str)
        or not identity
        or not isinstance(kind, str)
        or not kind
    ):
        raise ValueError("BOX_IDENTITY")
    return dict(
        serial(
            {
                "id": identity,
                "kind": kind,
                "origin_xyz_mm": vector(origin, 3, zero=True),
                "size_xyz_mm": vector(size, 3),
            }
        )
    )


def _axes(value: Any) -> list[tuple[Decimal, Decimal]]:
    origin = vector(value["origin_xyz_mm"], 3, zero=True)
    size = vector(value["size_xyz_mm"], 3)
    return [(a, a + b) for a, b in zip(origin, size, strict=True)]


def intersects(first: Any, second: Any) -> bool:
    return all(
        max(a, c) < min(b, d)
        for (a, b), (c, d) in zip(_axes(first), _axes(second), strict=True)
    )


def contains(boundary: Any, value: Any) -> bool:
    return all(
        a <= c and d <= b
        for (a, b), (c, d) in zip(_axes(boundary), _axes(value), strict=True)
    )


def attached(first: Any, second: Any) -> bool:
    """A volume or face contact; edges/corners do not attach routing volumes."""
    lengths = [
        min(b, d) - max(a, c)
        for (a, b), (c, d) in zip(_axes(first), _axes(second), strict=True)
    ]
    return (
        all(length >= 0 for length in lengths)
        and sum(length > 0 for length in lengths) >= 2
    )


def check_placements(
    boundary: Any, objects: Sequence[Any], allowed_sharing: Any = ()
) -> list[str]:
    if len(objects) > MAX_OBJECTS or len({o["id"] for o in objects}) != len(objects):
        raise ValueError("OBJECT_BOUND_OR_DUPLICATE")
    allowed = {frozenset(pair) for pair in allowed_sharing}
    failures = ["OUTSIDE:" + o["id"] for o in objects if not contains(boundary, o)]
    for a, b in combinations(objects, 2):
        if intersects(a, b):
            pair = frozenset((a["id"], b["id"]))
            if pair in allowed and "KEEPOUT" in {a["kind"], b["kind"]}:
                failures.append(f"SOURCE_KEEPOUT_SHARING_FORBIDDEN:{a['id']}:{b['id']}")
            elif pair not in allowed:
                failures.append(f"INTERSECTION:{a['id']}:{b['id']}")
    return failures


def free_segments(start: Any, length: Any, blocked: Any) -> list[list[str]]:
    lo, hi = number(start, zero=True), number(start, zero=True) + number(length)
    clipped = sorted(
        (max(lo, number(a, zero=True)), min(hi, number(b, zero=True)))
        for a, b in blocked
        if number(a, zero=True) < hi and number(b, zero=True) > lo
    )
    cursor = lo
    result = []
    for a, b in clipped:
        if b <= a:
            continue
        if a > cursor:
            result.append([cursor, a])
        cursor = max(cursor, b)
    if cursor < hi:
        result.append([cursor, hi])
    return list(serial(result))


def free_rectangles(boundary: Any, blocked: Sequence[Any]) -> list[list[str]]:
    """Exact disjoint x-slab complement of the union of XY projections.

    Adjacent slabs with the same free y interval coalesce. No numerical grid.
    Future-fit checks below also examine boundary critical coordinates, so slab
    fragmentation cannot produce a false negative for a rectangular reference.
    """
    if len(blocked) > MAX_OBJECTS:
        raise ValueError("OBJECT_BOUND")
    (x0, x1), (y0, y1), _ = _axes(boundary)
    rectangles = []
    for obj in blocked:
        (a, b), (c, d), _ = _axes(obj)
        if max(a, x0) < min(b, x1) and max(c, y0) < min(d, y1):
            rectangles.append((max(a, x0), min(b, x1), max(c, y0), min(d, y1)))
    xs = sorted({x0, x1, *(v for r in rectangles for v in r[:2])})
    result: list[list[Decimal]] = []
    active: dict[tuple[Decimal, Decimal], int] = {}
    for a, b in zip(xs[:-1], xs[1:], strict=True):
        segments = free_segments(
            y0,
            y1 - y0,
            [(c, d) for left, right, c, d in rectangles if left < b and right > a],
        )
        next_active = {}
        for c_raw, d_raw in segments:
            c, d = Decimal(c_raw), Decimal(d_raw)
            key = (c, d)
            if key in active and result[active[key]][0] + result[active[key]][2] == a:
                index = active[key]
                result[index][2] += b - a
            else:
                index = len(result)
                result.append([a, c, b - a, d - c])
            next_active[key] = index
        active = next_active
    return list(serial(result))


def area_reserve(
    boundary: Any, blocked: Sequence[Any], future_hwd_mm: Any
) -> dict[str, Any]:
    free = free_rectangles(boundary, blocked)
    axes = _axes(boundary)
    capacity = (axes[0][1] - axes[0][0]) * (axes[1][1] - axes[1][0])
    area = sum((Decimal(r[2]) * Decimal(r[3]) for r in free), ZERO)
    fit = None
    if future_hwd_mm is not None:
        h, w, depth = vector(future_hwd_mm, 3)
        xs = sorted({axes[0][0], *(Decimal(r[0]) for r in free)})
        ys = sorted({axes[1][0], *(Decimal(r[1]) for r in free)})
        for x in xs:
            for y in ys:
                reference = box(
                    "future", "FUTURE_REFERENCE", [x, y, axes[2][0]], [w, h, depth]
                )
                if contains(boundary, reference) and not any(
                    max(x, _axes(o)[0][0]) < min(x + w, _axes(o)[0][1])
                    and max(y, _axes(o)[1][0]) < min(y + h, _axes(o)[1][1])
                    for o in blocked
                ):
                    fit = reference
                    break
            if fit:
                break
    return dict(
        serial(
            {
                "capacity_mm2": capacity,
                "blocked_mm2": capacity - area,
                "free_mm2": area,
                "free_rectangles_xywh": free,
                "minimum_free_fraction": "0.25",
                "scalar_reserve_satisfied": area * 4 >= capacity,
                "operational_status": (
                    "UNKNOWN"
                    if future_hwd_mm is None
                    else "REFERENCE_FITS" if fit else "NO_REFERENCE_FIT"
                ),
                "future_reference_hwd_mm": future_hwd_mm,
                "future_witness": fit,
            }
        )
    )


def connection_graph(
    ducts: Sequence[Any], endpoints: Sequence[Any], root: str
) -> dict[str, Any]:
    objects = [*ducts, *endpoints]
    if len(objects) > MAX_OBJECTS or len({o["id"] for o in objects}) != len(objects):
        raise ValueError("GRAPH_BOUND_OR_DUPLICATE")
    duct_ids = {o["id"] for o in ducts}
    edges = sorted(
        [
            sorted([a["id"], b["id"]])
            for a, b in combinations(objects, 2)
            if (a["id"] in duct_ids or b["id"] in duct_ids) and attached(a, b)
        ]
    )
    # Endpoints attach to a duct network; they cannot carry transit between
    # otherwise disconnected ducts, even when touching both opposing faces.
    roots = sorted(
        {node for edge in edges if root in edge for node in edge if node in duct_ids}
    )
    reachable_ducts = {root} if root in duct_ids else set(roots[:1])
    while True:
        updated = reachable_ducts | {
            a
            for edge in edges
            if set(edge) <= duct_ids and reachable_ducts.intersection(edge)
            for a in edge
        }
        if updated == reachable_ducts:
            break
        reachable_ducts = updated
    reachable = reachable_ducts | {
        node for edge in edges if reachable_ducts.intersection(edge) for node in edge
    }
    if root in {o["id"] for o in objects}:
        reachable.add(root)
    return {
        "status": (
            "CONNECTED_RESERVATIONS"
            if len(reachable) == len(objects) and objects
            else "DISCONNECTED"
        ),
        "root": root,
        "nodes": sorted(o["id"] for o in objects),
        "edges": edges,
        "reachable": sorted(reachable),
        "scope": (
            "Reservation face/volume adjacency only; no device-port or bend proof."
        ),
    }


def _footprint(unit: Any) -> tuple[Decimal, Decimal, Decimal]:
    h, w, d = vector(unit["dimensions_mm"], 3)
    top, bottom, left, right = vector(unit["clearance_mm"], 4, zero=True)
    body = unit.get("body_reference")
    if body is not None:
        bh, bw, bd = vector(body["dimensions_mm"], 3)
        edges = vector(body["edge_mm"], 4, zero=True)
        if bw != w or bd != d or bh > h:
            raise ValueError("BODY_ASSEMBLY_REFERENCE_UNSUPPORTED")
        h = max(h + top + bottom, bh + edges[0] + edges[1])
        w = max(w + left + right, bw + edges[2] + edges[3])
    else:
        h, w = h + top + bottom, w + left + right
    return h, w, d


def _future_fit(
    zone: Any,
    objects: Sequence[Any],
    future: Any,
    connection_height: Decimal,
    connection_depth: Decimal,
    rows: Any = None,
) -> Any:
    """Find an unoccupied body+connection with direct positive duct contact.

    Critical coordinates come from reservation faces, without a numerical grid.
    DIN references stay on existing row origins and within their height budget.
    """
    if future is None:
        return None
    h, w, d = vector(future, 3)
    axes = _axes(zone)
    reservations = [(obj["kind"], _axes(obj)) for obj in objects]
    xs = {axes[0][0], axes[0][1] - w}
    ys = {axes[1][0], axes[1][1] - h - connection_height}
    for _, ((a, b), (c, e), _) in reservations:
        xs.update((a - w, b))
        ys.update((c - h - connection_height, e))
    if rows is not None:
        ys = {
            Decimal(row["y_mm"])
            for row in rows
            if h <= Decimal(row["height_budget_mm"])
        }

    def overlap(first: Any, second: Any) -> bool:
        return all(
            max(a, c) < min(b, e) for (a, b), (c, e) in zip(first, second, strict=True)
        )

    for y in sorted(ys):
        for x in sorted(xs):
            if (
                x < axes[0][0]
                or x + w > axes[0][1]
                or y < axes[1][0]
                or y + h + connection_height > axes[1][1]
                or axes[2][0] + max(d, connection_depth) > axes[2][1]
            ):
                continue
            body_axes = [(x, x + w), (y, y + h), (axes[2][0], axes[2][0] + d)]
            port_axes = [
                (x, x + w),
                (y + h, y + h + connection_height),
                (axes[2][0], axes[2][0] + connection_depth),
            ]
            if any(
                overlap(body_axes, other) or overlap(port_axes, other)
                for _, other in reservations
            ):
                continue
            for kind, other in reservations:
                lengths = [
                    min(b, e) - max(a, c)
                    for (a, b), (c, e) in zip(port_axes, other, strict=True)
                ]
                if (
                    kind == "DUCT"
                    and all(v >= 0 for v in lengths)
                    and sum(v > 0 for v in lengths) >= 2
                ):
                    return {
                        "body": box(
                            "future:body",
                            "FUTURE_REFERENCE",
                            [x, y, axes[2][0]],
                            [w, h, d],
                        ),
                        "connection": box(
                            "future:connection",
                            "CONNECTION",
                            [x, y + h, axes[2][0]],
                            [w, connection_height, connection_depth],
                        ),
                    }
    return None


def _layout(
    size: Any,
    units: Any,
    p: Any,
    row_count: int,
    orientation: str,
    rail_limit: Any,
    topology: str,
) -> tuple[Any, list[str]]:
    h, w, d = vector(size, 3)
    top, bottom, left, right, front, back = vector(p["insets_mm"], 6, zero=True)
    h, w, d = h - top - bottom, w - left - right, d - front - back
    if min(h, w, d) <= 0:
        return None, ["SCENARIO_USEFUL_BOUNDARY_EMPTY"]
    boundary = box("useful", "SCENARIO_BOUNDARY", [left, top, front], [w, h, d])
    dw, dd = number(p["duct_width_mm"]), number(p["duct_depth_mm"])
    ch, cd = number(p["connection_height_mm"]), number(p["connection_depth_mm"])
    service = number(p["service_height_mm"])
    access, assigned = number(p["access_width_mm"], zero=True), number(
        p["assigned_width_mm"], zero=True
    )
    aux = number(p["auxiliary_width_mm"])
    offset = number(p["mount_offset_mm"], zero=True)
    available_w, available_h = w - dw - access - assigned, h - service - dw
    if min(available_w, available_h) <= 0 or 3 * aux + dw > w - access - assigned:
        return None, ["INFRASTRUCTURE_BOUNDARY"]
    din = sorted(
        (u for u in units if u["mounting"] == "DIN"),
        key=lambda u: (-_footprint(u)[1], u["id"]),
    )
    panel = sorted(
        (u for u in units if u["mounting"] == "PANEL"), key=lambda u: u["id"]
    )
    if len(panel) > 1:
        return None, ["MULTIPLE_PANEL_ANCHORS_UNSUPPORTED"]
    ph = pw = ZERO
    if panel:
        fh, fw, _ = _footprint(panel[0])
        # Reserve uses actual union including the separate connection band.
        ph, pw = fh + ch + dw, fw
        if orientation == "BESIDE":
            pw = max(
                (pw * 4 / 3).quantize(Decimal("0.000001"), rounding=ROUND_CEILING),
                (
                    pw + number(p["future_panel_hwd_mm"][1])
                    if p["future_panel_hwd_mm"]
                    else pw
                ),
            )
        else:
            ph = max(
                (ph * 4 / 3).quantize(Decimal("0.000001"), rounding=ROUND_CEILING),
                (
                    ph + number(p["future_panel_hwd_mm"][0]) + ch
                    if p["future_panel_hwd_mm"]
                    else ph
                ),
            )
    din_x, din_y = left + dw, top
    panel_x, panel_y = din_x, top
    din_w, din_h = available_w, available_h
    if panel and din:
        if orientation == "BESIDE":
            din_x += pw
            din_w -= pw
        else:
            din_y += ph
            din_h -= ph
    elif panel:
        ph, pw = available_h, available_w
    if panel and (ph > available_h or pw > available_w):
        return None, ["PANEL_ZONE_BOUNDARY"]
    if din and (min(din_w, din_h) <= 0 or row_count <= 0):
        return None, ["DIN_ZONE_BOUNDARY"]
    if rail_limit and din:
        if row_count != rail_limit["count"]:
            return None, ["KNOWN_DIN_CAPACITY"]
        rail_length = number(rail_limit["length_mm"])
        if din_w < rail_length:
            return None, ["KNOWN_DIN_RAIL_LENGTH_EXCEEDS_SCENARIO_BOUNDARY"]
        din_w = rail_length
    rows: list[list[Any]] = [[] for _ in range(row_count)]
    loads = [ZERO] * row_count
    for u in din:
        index = min(range(row_count), key=lambda i: (loads[i], i))
        rows[index].append(u)
        loads[index] += _footprint(u)[1]
    columns = [
        max((_footprint(row[i])[1] for row in rows if len(row) > i), default=ZERO)
        for i in range(max((len(row) for row in rows), default=0))
    ]
    shared = topology == "DIN_SHARED_COLUMN_RISERS"
    risers = topology == "DIN_COLUMN_RISERS" or shared
    duct_count = (len(columns) + 1) // 2 if shared else len(columns)
    required_width = (
        sum(columns, ZERO) + dw * duct_count if risers else max(loads, default=ZERO)
    )
    if din and required_width > din_w:
        return None, ["DIN_WIDTH_WITH_CONNECTION_INFRASTRUCTURE"]
    max_height = max((_footprint(u)[0] for u in din), default=ZERO)
    row_step = PITCH
    below = ZERO if risers else dw
    if din and row_count > 1 and max_height + ch + below > PITCH:
        return None, ["SOURCE_DIN_PITCH_140_INFRASTRUCTURE_CONFLICT"]
    used_h = (row_count - 1) * row_step + max_height + ch + below if din else ZERO
    if used_h > din_h:
        return None, ["DIN_HEIGHT_WITH_CONNECTION_INFRASTRUCTURE"]
    objects = [
        box("trunk", "DUCT", [left, top, front + offset], [dw, h - service, dd]),
        box(
            "service-duct",
            "DUCT",
            [left, top + h - service - dw, front + offset],
            [w - access - assigned, dw, dd],
        ),
        box(
            "entry",
            "ENTRY",
            [left, top + h - service, front + offset],
            [dw, service, cd],
        ),
    ]
    for i, role in enumerate(("N", "PE", "DISTRIBUTION")):
        objects.append(
            box(
                role,
                "AUXILIARY",
                [left + dw + i * aux, top + h - service, front + offset],
                [aux, service, cd],
            )
        )
    if access:
        objects.append(
            box("access", "ACCESS", [left + w - access, top, front], [access, h, d])
        )
    if assigned:
        objects.append(
            box(
                "assigned",
                "ASSIGNED",
                [left + w - access - assigned, top, front],
                [assigned, h, d],
            )
        )
    column_origins = []
    if risers:
        x = din_x
        for ci, column in enumerate(columns):
            column_origins.append(x)
            x += column
            if shared and ci % 2:
                continue
            objects.append(
                box(
                    f"DIN:riser:{ci}",
                    "DUCT",
                    [x, din_y, front + offset],
                    [dw, top + h - service - din_y, dd],
                )
            )
            x += dw
    apparatus = []
    connections = []
    reserves = {}
    zones = []
    for kind, origin_x, origin_y, width, height, grouped in (
        ("DIN", din_x, din_y, din_w, din_h, rows if din else []),
        ("PANEL", panel_x, panel_y, pw, ph, [panel] if panel else []),
    ):
        if not grouped:
            continue
        zone = box(
            kind,
            "ZONE",
            [origin_x, origin_y, front + offset],
            [width, height, d - offset],
        )
        zones.append(zone)
        blocked: list[dict[str, Any]] = []
        free_rows = []
        for ri, row in enumerate(grouped):
            y = origin_y + ri * row_step if kind == "DIN" else origin_y
            row_height = max((_footprint(u)[0] for u in row), default=max_height)
            x = origin_x
            for ci, u in enumerate(row):
                fh, fw, fd = _footprint(u)
                if kind == "DIN" and risers:
                    # Adjacent paired columns face opposite sides of one duct.
                    # Even columns align right, odd shared columns align left.
                    x = column_origins[ci]
                    if not shared or ci % 2 == 0:
                        x += columns[ci] - fw
                keepout = box(u["id"], "KEEPOUT", [x, y, front + offset], [fw, fh, fd])
                port = box(
                    u["id"] + ":connection",
                    "CONNECTION",
                    [
                        x,
                        y + (fh if kind == "DIN" and risers else row_height),
                        front + offset,
                    ],
                    [fw, ch, cd],
                )
                objects.extend((keepout, port))
                blocked.extend((keepout, port))
                connections.append(port)
                apparatus.append(
                    {
                        "id": u["id"],
                        "mounting": kind,
                        "keepout_id": u["id"],
                        "connection_id": port["id"],
                        "footprint_hwd_mm": serial([fh, fw, fd]),
                        "source_dimensions_hwd_mm": serial(u["dimensions_mm"]),
                        "body_reference": u.get("body_reference"),
                        "assembly_origin_mm": (
                            None
                            if u.get("body_reference") is not None
                            else serial(
                                [
                                    x + number(u["clearance_mm"][2], zero=True),
                                    y + number(u["clearance_mm"][0], zero=True),
                                    front + offset,
                                ]
                            )
                        ),
                        "port_origin_status": "SCENARIO_RESERVATION_NOT_DEVICE_PORT",
                    }
                )
                x += fw
                if kind == "DIN" and risers:
                    x += dw
            if kind != "DIN" or not risers:
                branch_y = y + row_height + ch
                branch = box(
                    f"{kind}:branch:{ri}",
                    "DUCT",
                    [left, branch_y, front + offset],
                    [origin_x + width - left, dw, dd],
                )
                objects.append(branch)
                blocked.append(branch)
            if kind == "DIN":
                intervals = [
                    (_axes(o)[0][0], _axes(o)[0][1])
                    for o in objects
                    if _axes(o)[1][0] < y + row_height + ch and _axes(o)[1][1] > y
                ]
                free_rows.append(
                    {
                        "row": ri,
                        "y_mm": serial(y),
                        "height_budget_mm": serial(row_height),
                        "segments_mm": free_segments(origin_x, width, intervals),
                    }
                )
        if kind == "DIN":
            free_length = sum(
                (
                    Decimal(b) - Decimal(a)
                    for r in free_rows
                    for a, b in r["segments_mm"]
                ),
                ZERO,
            )
            capacity = width * row_count
            occupied = sum((number(u["dimensions_mm"][1]) for u in din), ZERO)
            future = p["future_din_hwd_mm"]
            reference = _future_fit(zone, objects, future, ch, cd, free_rows)
            reserves[kind] = serial(
                {
                    "capacity_mm": capacity,
                    "occupied_mm": occupied,
                    "blocked_mm": capacity - free_length - occupied,
                    "assigned_mm": ZERO,
                    "free_mm": free_length,
                    "free_segments": free_rows,
                    "minimum_free_fraction": "0.25",
                    "scalar_reserve_satisfied": free_length * 4 >= capacity,
                    "operational_status": (
                        "UNKNOWN"
                        if future is None
                        else "REFERENCE_FITS" if reference else "NO_REFERENCE_FIT"
                    ),
                    "future_reference_hwd_mm": future,
                    "future_witness": reference,
                    "scope": (
                        "Total rail capacity, not 25% on every rail; "
                        "union of apparatus and infrastructure projections excluded; "
                        "future body+connection collision/duct attachment checked."
                    ),
                }
            )
        else:
            future_panel = p["future_panel_hwd_mm"]
            operational = (
                None
                if future_panel is None
                else [
                    number(future_panel[0]) + ch,
                    number(future_panel[1]),
                    max(number(future_panel[2]), cd),
                ]
            )
            blocked = list(objects)
            reserves[kind] = area_reserve(zone, blocked, operational)
            reference = _future_fit(zone, objects, future_panel, ch, cd)
            reserves[kind]["operational_status"] = (
                "UNKNOWN"
                if future_panel is None
                else "REFERENCE_FITS" if reference else "NO_REFERENCE_FIT"
            )
            reserves[kind]["future_witness"] = (
                box(
                    "future",
                    "FUTURE_REFERENCE",
                    reference["body"]["origin_xyz_mm"],
                    [operational[1], operational[0], operational[2]],
                )
                if reference is not None and operational is not None
                else None
            )
            reserves[kind]["future_body_witness"] = (
                reference["body"] if reference else None
            )
            reserves[kind]["future_connection_witness"] = (
                reference["connection"] if reference else None
            )
            reserves[kind]["future_device_keepout_hwd_mm"] = future_panel
            unavailable = Decimal(reserves[kind]["blocked_mm2"])
            occupied_area = Decimal(
                area_reserve(
                    zone, [o for o in blocked if o["kind"] == "KEEPOUT"], None
                )["blocked_mm2"]
            )
            reserves[kind].update(
                occupied_mm2=serial(occupied_area),
                blocked_mm2=serial(unavailable - occupied_area),
                assigned_mm2="0",
                unavailable_union_mm2=serial(unavailable),
                occupied_basis=(
                    "Conservative source apparatus keepout; "
                    "actual body anchor may be UNKNOWN"
                ),
            )
    ducts = [o for o in objects if o["kind"] == "DUCT"]
    allowed = [
        sorted([a["id"], b["id"]])
        for a, b in combinations(ducts, 2)
        if intersects(a, b)
    ]
    failures = check_placements(boundary, objects, allowed)
    for kind, proof in reserves.items():
        if not proof["scalar_reserve_satisfied"]:
            failures.append("RESERVE_25_PERCENT:" + kind)
        if proof["operational_status"] == "NO_REFERENCE_FIT":
            failures.append("OPERATIONAL_REFERENCE_NO_FIT:" + kind)
    graph = connection_graph(
        ducts,
        [*connections, *(o for o in objects if o["kind"] in {"ENTRY", "AUXILIARY"})],
        "entry",
    )
    if graph["status"] != "CONNECTED_RESERVATIONS":
        failures.append("DISCONNECTED_RESERVATIONS")
    if any(not any(attached(port, duct) for duct in ducts) for port in connections):
        failures.append("CONNECTION_WITHOUT_DIRECT_DUCT_ATTACHMENT")
    if failures:
        return None, failures
    return {
        "boundary": boundary,
        "boundary_basis": "SCENARIO insets from source outer HWD; not known interior",
        "orientation": orientation,
        "routing_topology": topology,
        "din_rows": row_count,
        "din_row_pitch_mm": serial(row_step),
        "zones": zones,
        "objects": objects,
        "apparatus": apparatus,
        "allowed_sharing": allowed,
        "sharing_basis": "SCENARIO connected duct junctions only",
        "reserve": reserves,
        "graph": graph,
    }, []


def search_joint(
    dimensions_hwd_mm: Any,
    units: Sequence[Any],
    parameters: Any,
    rail_limit: Any = None,
    *,
    budget: int = 512,
) -> dict[str, Any]:
    """Run finite-family search without modifying caller Decimal context."""
    with localcontext() as context:
        context.prec = 40
        return _search_joint(dimensions_hwd_mm, units, parameters, rail_limit, budget)


def _search_joint(
    dimensions_hwd_mm: Any,
    units: Sequence[Any],
    parameters: Any,
    rail_limit: Any,
    budget: int,
) -> dict[str, Any]:
    """Finite shelves, greedy width-balanced rows, PANEL beside/above DIN.

    Enumerates row counts, never cabinet winners or global factory layouts.
    Infrastructure is allocated before apparatus packing. Source footprints are
    conservative keepouts; absent body/assembly and port anchors stay unknown.
    """
    vector(dimensions_hwd_mm, 3)
    if (
        type(budget) is not int
        or budget < 0
        or budget > 4096
        or not units
        or len(units) > 256
    ):
        raise ValueError("SEARCH_BOUND")
    if len({u["id"] for u in units}) != len(units):
        raise ValueError("DUPLICATE_DEVICE")
    for u in units:
        if u["mounting"] not in {"DIN", "PANEL"}:
            return {
                "status": "UNKNOWN",
                "witness": None,
                "failed_constraints": ["UNSUPPORTED_MOUNTING"],
                "search": {"examined": 0, "global_optimum_proven": False},
            }
        if any(vector(u.get("pair_gap_mm", [0, 0]), 2, zero=True)) or number(
            u.get("extra_gap_mm", 0), zero=True
        ):
            return {
                "status": "UNKNOWN",
                "witness": None,
                "failed_constraints": ["PAIR_GAP_LAYOUT_UNSUPPORTED"],
                "search": {"examined": 0, "global_optimum_proven": False},
            }
        _footprint(u)
    n = sum(u["mounting"] == "DIN" for u in units)
    rows = [rail_limit["count"]] if rail_limit and n else range(1, n + 2) if n else [0]
    examined = 0
    failures: set[str] = set()
    diagnostics: dict[str, Any] = {}
    family = (
        "balanced shelves; PANEL beside/above; ascending row counts; "
        "legacy below-row ducts then DIN column risers then paired shared risers"
    )
    topologies = (
        ("BELOW_ROW_DUCTS", "DIN_COLUMN_RISERS", "DIN_SHARED_COLUMN_RISERS")
        if n
        else ("BELOW_ROW_DUCTS",)
    )

    def search_state(complete: bool) -> dict[str, Any]:
        return {
            "examined": examined,
            "budget": budget,
            "family_complete": complete,
            "global_optimum_proven": False,
            "family": family,
            "routing_topologies": list(topologies),
            "topology_diagnostics": diagnostics,
        }

    for topology in topologies:
        diagnostic: dict[str, Any] = {"examined": 0, "failed_constraints": []}
        diagnostics[topology] = diagnostic
        for orientation in ("BESIDE", "ABOVE"):
            for row_count in rows:
                if examined >= budget:
                    return {
                        "status": "SEARCH_BUDGET_EXHAUSTED",
                        "witness": None,
                        "failed_constraints": sorted(failures),
                        "search": search_state(False),
                    }
                examined += 1
                diagnostic["examined"] += 1
                try:
                    witness, failed = _layout(
                        dimensions_hwd_mm,
                        units,
                        parameters,
                        row_count,
                        orientation,
                        rail_limit,
                        topology,
                    )
                except (InvalidOperation, ValueError) as exc:
                    witness, failed = None, ["GEOMETRY:" + str(exc)]
                failures.update(failed)
                diagnostic["failed_constraints"] = sorted(
                    set(diagnostic["failed_constraints"]) | set(failed)
                )
                if witness is not None:
                    return {
                        "status": "CONDITIONAL_WITNESS",
                        "witness": witness,
                        "failed_constraints": [],
                        "search": search_state(False),
                    }
    if rail_limit and n:
        failures.add("KNOWN_DIN_CAPACITY")
    return {
        "status": "NO_LAYOUT_IN_EXAMINED_FAMILY",
        "witness": None,
        "failed_constraints": sorted(failures),
        "search": search_state(True),
    }
