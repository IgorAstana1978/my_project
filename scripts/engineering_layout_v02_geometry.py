"""Research geometry only: route envelopes never establish safe installation."""

from __future__ import annotations

from decimal import ROUND_CEILING, Decimal, localcontext
from typing import Any

import engineering_layout_geometry as g

PITCH = Decimal(150)
DIN_FREE = Decimal("0.10")
METHODS = ("DUCTED", "RESTRAINED_WIRING")


def _evaluate(
    size: Any, units: Any, parameters: Any, future: Any, rail_limit: Any = None
) -> dict[str, Any]:
    """Enumerate bounded shelf arrangements, without cabinet targets."""
    h, w, d = g.vector(size, 3)
    top, bottom, left, right, front, back = g.vector(
        parameters["insets_mm"], 6, zero=True
    )
    h, w, d = h - top - bottom, w - left - right, d - front - back
    if min(h, w, d) <= 0:
        return {"status": "NO_LAYOUT_IN_EXAMINED_FAMILY", "witness": None}
    din = sorted(
        (u for u in units if u["mounting"] == "DIN"),
        key=lambda u: (-g._footprint(u)[1], u["id"]),
    )
    panel = [u for u in units if u["mounting"] == "PANEL"]
    if not din:
        return {"status": "UNKNOWN", "reason": "PANEL_ONLY_UNSUPPORTED"}
    if len(panel) > 1 or any(
        any(g.vector(u["pair_gap_mm"], 2, zero=True))
        or g.number(u["extra_gap_mm"], zero=True)
        for u in units
    ):
        return {"status": "UNKNOWN", "reason": "UNSUPPORTED_PAIR_ANCHORS"}
    rw, rd = g.vector(parameters["route_hwd_mm"], 2)
    ch, cd = g.vector(parameters["connection_hd_mm"], 2)
    service = g.number(parameters["service_height_mm"], zero=True)
    boundary = g.box("boundary", "SCENARIO_BOUNDARY", [0, 0, 0], [w, h, d])
    tried = 0
    failures: set[str] = set()
    counts = [rail_limit["count"]] if rail_limit and din else range(1, len(din) + 2)
    for orientation in ("BESIDE", "ABOVE"):
        for count in counts:
            tried += 1
            rows: list[list[Any]] = [[] for _ in range(count)]
            loads = [Decimal(0)] * count
            for u in din:
                row_index = min(range(count), key=lambda i: (loads[i], i))
                rows[row_index].append(u)
                loads[row_index] += g._footprint(u)[1]
            ph, pw, pd = g._footprint(panel[0]) if panel else [Decimal(0)] * 3
            # PANEL 25% remains independent; clearance cannot become spare area.
            if panel:
                if orientation == "BESIDE":
                    pw = ((pw + rw) * Decimal(4) / 3).quantize(
                        Decimal("0.000001"), rounding=ROUND_CEILING
                    )
                else:
                    ph = ((ph + ch + rw) * Decimal(4) / 3).quantize(
                        Decimal("0.000001"), rounding=ROUND_CEILING
                    )
            x, y = rw + (pw if orientation == "BESIDE" else 0), (
                ph if orientation == "ABOVE" else Decimal(0)
            )
            width = w - x
            if rail_limit:
                width = min(width, g.number(rail_limit["length_mm"]))
            if width <= 0 or h - service - y <= 0:
                failures.add("ZONE_BOUNDARY")
                continue
            objects = [g.box("trunk", "ROUTE", [0, 0, 0], [rw, h, rd])]
            connections = []
            free_rows = []
            din_zone = g.box("DIN", "ZONE", [x, y, 0], [width, h - service - y, d])
            for ri, row in enumerate(rows):
                ry = y + ri * PITCH
                rh = max(
                    (g._footprint(u)[0] for u in row),
                    default=max(g._footprint(u)[0] for u in din),
                )
                if rh + ch + rw > PITCH and count > 1:
                    failures.add("PITCH_WITH_CONNECTION_AND_ROUTE")
                    break
                if ry + rh + ch + rw > h - service:
                    failures.add("ROW_INTRUDES_SERVICE_RESERVATION")
                    break
                xx = x
                for u in row:
                    uh, uw, ud = g._footprint(u)
                    objects.append(g.box(u["id"], "KEEPOUT", [xx, ry, 0], [uw, uh, ud]))
                    port = g.box(
                        u["id"] + ":connection",
                        "CONNECTION",
                        [xx, ry + rh, 0],
                        [uw, ch, cd],
                    )
                    objects.append(port)
                    connections.append(port)
                    xx += uw
                objects.append(
                    g.box(
                        f"branch:{ri}",
                        "ROUTE",
                        [0, ry + rh + ch, 0],
                        [x + width, rw, rd],
                    )
                )
                intervals = [
                    (g._axes(o)[0][0], g._axes(o)[0][1])
                    for o in objects
                    if g._axes(o)[1][0] < ry + rh + ch and g._axes(o)[1][1] > ry
                ]
                free_rows.append(
                    {
                        "y_mm": str(ry),
                        "height_budget_mm": str(rh),
                        "segments_mm": g.free_segments(x, width, intervals),
                    }
                )
            else:
                panel_zone = None
                if panel:
                    px, py = rw, Decimal(0)
                    panel_zone = g.box("PANEL", "ZONE", [px, py, 0], [pw, ph, d])
                    uh, uw, ud = g._footprint(panel[0])
                    objects.append(
                        g.box(panel[0]["id"], "KEEPOUT", [px, py, 0], [uw, uh, ud])
                    )
                    port = g.box(
                        "panel:connection", "CONNECTION", [px, py + uh, 0], [uw, ch, cd]
                    )
                    objects.append(port)
                    connections.append(port)
                    objects.append(
                        g.box(
                            "panel:branch",
                            "ROUTE",
                            [0, py + uh + ch, 0],
                            [rw + pw, rw, rd],
                        )
                    )
                routes = [o for o in objects if o["kind"] == "ROUTE"]
                sharing = [
                    [a["id"], b["id"]]
                    for i, a in enumerate(routes)
                    for b in routes[i + 1 :]
                    if g.intersects(a, b)
                ]
                failed = g.check_placements(boundary, objects, sharing)
                if panel_zone and ph > h - service:
                    failed.append("PANEL_INTRUDES_SERVICE_RESERVATION")
                if not g.contains(boundary, din_zone) or (
                    panel_zone and not g.contains(boundary, panel_zone)
                ):
                    failed.append("ZONE_OUTSIDE_BOUNDARY")
                if panel_zone and any(
                    not g.contains(panel_zone, o)
                    for o in objects
                    if o["id"] in {panel[0]["id"], "panel:connection"}
                ):
                    failed.append("PANEL_CONTAINMENT")
                if any(
                    not g.contains(din_zone, o)
                    for o in objects
                    if o["kind"] == "KEEPOUT"
                    and o["id"] != (panel[0]["id"] if panel else None)
                ):
                    failed.append("DIN_CONTAINMENT")
                # Reuse graph/contact mechanics only, not DUCT installation authority.
                routing = [dict(o, kind="DUCT") for o in routes]
                graph = g.connection_graph(routing, connections, "trunk")
                if graph["status"] != "CONNECTED_RESERVATIONS":
                    failed.append("ROUTE_CONNECTIVITY")
                if any(not any(g.attached(c, r) for r in routes) for c in connections):
                    failed.append("CONNECTION_ROUTE_CONTACT")
                cap = width * count
                free = sum(
                    (
                        Decimal(b) - Decimal(a)
                        for r in free_rows
                        for a, b in r["segments_mm"]
                    ),
                    Decimal(0),
                )
                reserve: dict[str, Any] = {
                    "DIN": {
                        "capacity_mm": cap,
                        "free_mm": free,
                        "occupied_mm": sum(
                            (g.number(u["dimensions_mm"][1]) for u in din), Decimal(0)
                        ),
                        "minimum_free_fraction": DIN_FREE,
                        "scalar_reserve_satisfied": free >= cap * DIN_FREE,
                    }
                }
                if panel_zone:
                    reserve["PANEL"] = g.area_reserve(panel_zone, objects, None)
                for kind, proof in reserve.items():
                    if not proof["scalar_reserve_satisfied"]:
                        failed.append("RESERVE:" + kind)
                    ref = future["reference_hwd_mm"].get(kind)
                    if future["status"] == "REQUIRED":
                        zone = din_zone if kind == "DIN" else panel_zone
                        fit = g._future_fit(
                            zone,
                            [
                                dict(o, kind="DUCT") if o["kind"] == "ROUTE" else o
                                for o in objects
                            ],
                            ref,
                            ch,
                            cd,
                            free_rows if kind == "DIN" else None,
                        )
                        proof["operational_status"] = (
                            "REFERENCE_FITS" if fit else "NO_REFERENCE_FIT"
                        )
                        proof["future_witness"] = fit
                        if not fit:
                            failed.append("REQUIRED_REFERENCE:" + kind)
                    else:
                        proof["operational_status"] = future["status"]
                if not failed:
                    result: dict[str, Any] = g.serial(
                        {
                            "status": "CONDITIONAL_GEOMETRY",
                            "witness": {
                                "boundary": boundary,
                                "objects": objects,
                                "reserve": reserve,
                                "orientation": orientation,
                                "rows": count,
                                "pitch_mm": PITCH,
                                "graph": graph,
                                "examined": tried,
                            },
                        }
                    )
                    return result
                failures.update(failed)
    return {
        "status": "NO_LAYOUT_IN_EXAMINED_FAMILY",
        "witness": None,
        "failed_constraints": sorted(failures),
        "examined": tried,
    }


def evaluate(
    size: Any, units: Any, parameters: Any, future: Any, rail_limit: Any = None
) -> dict[str, Any]:
    with localcontext() as context:
        context.prec = 40
        return _evaluate(size, units, parameters, future, rail_limit)
