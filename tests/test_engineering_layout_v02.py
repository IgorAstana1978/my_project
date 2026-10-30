"""Research policy, source recomputation and geometry boundaries."""

import copy
import hashlib
import importlib
import json
from decimal import Decimal
from fractions import Fraction
from itertools import combinations
from pathlib import Path
from typing import Any

import pytest

api = importlib.import_module("engineering_layout_v02")
geo = importlib.import_module("engineering_layout_v02_geometry")


def request() -> dict[str, Any]:
    return {
        "schema_version": api.REQUEST_SCHEMA,
        "profiles": [
            {
                "id": "research",
                "author": "test",
                "rationale": "synthetic mechanics",
                "parameters": {
                    "insets_mm": [0] * 6,
                    "route_hwd_mm": {"DUCTED": [10, 10], "RESTRAINED_WIRING": [5, 5]},
                    "connection_hd_mm": [10, 10],
                    "service_height_mm": 0,
                },
                "future": {
                    "status": "UNKNOWN",
                    "reference_hwd_mm": {},
                    "policy_binding": None,
                },
            }
        ],
    }


def evaluate(size: Any, u: Any, parameters: Any, future: Any) -> Any:
    return geo.evaluate(
        size,
        u,
        dict(parameters, route_hwd_mm=parameters["route_hwd_mm"]["DUCTED"]),
        future,
    )


def units() -> list[dict[str, Any]]:
    return [
        {
            "id": str(i),
            "mounting": "DIN",
            "dimensions_mm": [40, 20, 20],
            "clearance_mm": [0] * 4,
            "pair_gap_mm": [0, 0],
            "extra_gap_mm": 0,
            "body_reference": None,
        }
        for i in range(4)
    ]


def test_geometry_reserve_routes_and_unknown_future() -> None:
    p = api.normalize(request())["profiles"][0]
    result = evaluate([400, 150, 50], units(), p["parameters"], p["future"])
    assert result["status"] == "CONDITIONAL_GEOMETRY"
    w = result["witness"]
    assert w["pitch_mm"] == "150"
    assert all(o["kind"] != "DUCT" for o in w["objects"])
    proof = w["reserve"]["DIN"]
    assert Decimal(proof["free_mm"]) >= Decimal(proof["capacity_mm"]) / 10
    assert proof["operational_status"] == "UNKNOWN"


@pytest.mark.parametrize("damage", ["future", "approval", "extra", "negative"])
def test_untrusted_policy_and_invalid_geometry(damage: str) -> None:
    r = request()
    p = r["profiles"][0]
    if damage == "future":
        p["future"]["status"] = "NOT_REQUIRED_BY_AUTHORIZED_POLICY"
    elif damage == "approval":
        p["future"]["approved"] = True
    elif damage == "extra":
        p["parameters"]["cabinet"] = "target"
    else:
        p["parameters"]["route_hwd_mm"]["DUCTED"] = [-1, 10]
    with pytest.raises((api.strict.SizingHold, ValueError)):
        api.normalize(r)


def test_required_reference_cannot_borrow_scalar_spare() -> None:
    p = api.normalize(request())["profiles"][0]
    f = {"status": "REQUIRED", "reference_hwd_mm": {"DIN": [500, 500, 20]}}
    result = evaluate([400, 150, 50], units(), p["parameters"], f)
    assert result["status"] == "NO_LAYOUT_IN_EXAMINED_FAMILY"
    assert "REQUIRED_REFERENCE:DIN" in result["failed_constraints"]


def test_panel_and_unsupported_pair_constraints() -> None:
    p = api.normalize(request())["profiles"][0]
    u = units()
    u[0]["pair_gap_mm"] = [1, 0]
    assert (
        evaluate([400, 150, 50], u, p["parameters"], p["future"])["status"] == "UNKNOWN"
    )
    panel = dict(units()[0], id="panel", mounting="PANEL")
    r = evaluate([600, 500, 100], [*units(), panel], p["parameters"], p["future"])
    assert r["status"] == "CONDITIONAL_GEOMETRY"
    assert r["witness"]["reserve"]["PANEL"]["minimum_free_fraction"] == "0.25"


def test_source_binding_report_recompute_and_production_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    b = {
        "strict_request": {},
        "items": [
            {
                "item_id": "item",
                "apparatus_sha256": "hash",
                "units": units(),
                "source_fact": {"prior_approval": {"status": "NONE"}},
                "project_cables": {"first_missing": "UNKNOWN_CABLES"},
                "candidates": [
                    {
                        "cabinet_code": "synthetic",
                        "strict_baseline": {
                            "dimensions_mm": [400, 150, 50],
                            "reasons": [],
                        },
                    }
                ],
            }
        ],
    }
    monkeypatch.setattr(
        api.legacy, "assess_composition", lambda *a, **k: copy.deepcopy(b)
    )
    items = [{"item_id": "item"}]
    r = api.assess_composition("case", items, request())
    api.verify_assessment(r, items, expected_case_id="case")
    assert r["physical_status"] == "HOLD"
    assert len(r["items"][0]["assessments"]) == 2
    a, b2 = r["items"][0]["assessments"]
    assert a["method_envelope_mm"] != b2["method_envelope_mm"]
    assert a["result"]["witness"]["objects"] != b2["result"]["witness"]["objects"]
    for before in (False, True):
        with pytest.raises(api.strict.SizingHold):
            api.strict.verify_report(
                r, items, expected_case_id="case", before_human_approval_1=before
            )
    r["policy"] = "tampered"
    with pytest.raises(api.strict.SizingHold):
        api.verify_assessment(r, items, expected_case_id="case")
    count = 0

    def drift(*a: Any, **k: Any) -> Any:
        nonlocal count
        count += 1
        return copy.deepcopy(b) if count == 1 else dict(b, changed=True)

    monkeypatch.setattr(api.legacy, "assess_composition", drift)
    with pytest.raises(api.strict.SizingHold, match="SOURCE_DRIFT"):
        api.assess_composition("case", items, request())


def test_no_phantom_spare_row_or_panel_only_capacity() -> None:
    p = api.normalize(request())["profiles"][0]
    u = units()[:1]
    u[0]["dimensions_mm"] = [40, 90, 20]
    assert (
        evaluate([180, 105, 50], u, p["parameters"], p["future"])["status"]
        == "NO_LAYOUT_IN_EXAMINED_FAMILY"
    )
    u[0]["mounting"] = "PANEL"
    assert (
        evaluate([500, 500, 100], u, p["parameters"], p["future"])["status"]
        == "UNKNOWN"
    )


def test_authorized_future_policy_and_sha_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "synthetic-policy.json"
    path.write_text(
        json.dumps(
            {
                "policy": api.POLICY,
                "future_reference": "NOT_REQUIRED_BY_AUTHORIZED_POLICY",
            }
        )
    )
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(api, "FUTURE_POLICY_SOURCES", frozenset({(str(path), sha)}))
    r = request()
    f = r["profiles"][0]["future"]
    f.update(
        status="NOT_REQUIRED_BY_AUTHORIZED_POLICY",
        policy_binding={"path": str(path), "sha256": sha},
    )
    assert (
        api.normalize(r)["profiles"][0]["future"]["status"]
        == "NOT_REQUIRED_BY_AUTHORIZED_POLICY"
    )
    path.write_text("{}")
    with pytest.raises(api.strict.SizingHold, match="SHA_DRIFT"):
        api.normalize(r)


def test_malformed_report_is_controlled_hold() -> None:
    bad_baselines: list[Any] = [[], None, "bad"]
    for baseline in bad_baselines:
        with pytest.raises(api.strict.SizingHold):
            api.verify_assessment(
                {
                    "schema_version": api.SCHEMA,
                    "case_id": "case",
                    "source_baseline": baseline,
                },
                [],
                expected_case_id="case",
            )


def test_service_reservation_is_not_connection_capacity() -> None:
    p = api.normalize(request())["profiles"][0]
    p["parameters"]["service_height_mm"] = 20
    r = evaluate([60, 100, 50], units()[:1], p["parameters"], p["future"])
    assert r["status"] == "NO_LAYOUT_IN_EXAMINED_FAMILY"
    assert "ROW_INTRUDES_SERVICE_RESERVATION" in r["failed_constraints"]


def independent_witness_check(result: Any, source: Any, parameters: Any) -> None:
    """Rational raw-box oracle; never call the producer's geometry validators."""
    w = result["witness"]

    def axes(o: Any) -> Any:
        return [
            (Fraction(a), Fraction(a) + Fraction(b))
            for a, b in zip(o["origin_xyz_mm"], o["size_xyz_mm"], strict=True)
        ]

    def inside(outer: Any, inner: Any) -> bool:
        return all(
            a <= c and d <= b for (a, b), (c, d) in zip(outer, inner, strict=True)
        )

    def overlap(a: Any, b: Any) -> bool:
        return all(
            max(lo, x) < min(hi, y) for (lo, hi), (x, y) in zip(a, b, strict=True)
        )

    def contact(a: Any, b: Any) -> bool:
        lengths = [
            min(hi, y) - max(lo, x) for (lo, hi), (x, y) in zip(a, b, strict=True)
        ]
        return all(v >= 0 for v in lengths) and sum(v > 0 for v in lengths) >= 2

    bounds = axes(w["boundary"])
    objects = w["objects"]
    indexed = {o["id"]: o for o in objects}
    assert len(indexed) == len(objects)
    for u in source:
        h, width, depth = map(Fraction, map(str, u["dimensions_mm"]))
        t, b, left, right = map(Fraction, map(str, u["clearance_mm"]))
        height, width = h + t + b, width + left + right
        if u["body_reference"]:
            body = u["body_reference"]
            bh, bw, _ = map(Fraction, map(str, body["dimensions_mm"]))
            et, eb, el, er = map(Fraction, map(str, body["edge_mm"]))
            height, width = max(height, bh + et + eb), max(width, bw + el + er)
        assert list(map(Fraction, indexed[u["id"]]["size_xyz_mm"])) == [
            width,
            height,
            depth,
        ]
    for o in objects:
        assert inside(bounds, axes(o))
        if o["kind"] != "ROUTE":
            assert axes(o)[1][1] <= bounds[1][1] - Fraction(
                str(parameters["service_height_mm"])
            )
    for a, b in combinations(objects, 2):
        if {a["kind"], b["kind"]} != {"ROUTE"}:
            assert not overlap(axes(a), axes(b))
    routes = [o for o in objects if o["kind"] == "ROUTE"]
    reached = {"trunk"}
    while True:
        expanded = reached | {
            o["id"]
            for o in routes
            if any(p["id"] in reached and contact(axes(o), axes(p)) for p in routes)
        }
        if expanded == reached:
            break
        reached = expanded
    assert reached == {o["id"] for o in routes}
    for c in (o for o in objects if o["kind"] == "CONNECTION"):
        assert any(contact(axes(c), axes(r)) for r in routes)
    assert w["graph"]["status"] == "CONNECTED_RESERVATIONS"

    panel = next(u for u in source if u["mounting"] == "PANEL")
    panel_box = indexed[panel["id"]]
    px, py, _ = [a for a, _ in axes(panel_box)]
    din = [indexed[u["id"]] for u in source if u["mounting"] == "DIN"]
    dx, dy = min(axes(o)[0][0] for o in din), min(axes(o)[1][0] for o in din)
    capacity = Fraction(w["reserve"]["PANEL"]["capacity_mm2"])
    pw = (
        axes(indexed["trunk"])[0][0] - px
        if w["orientation"] == "BESIDE"
        else axes(panel_box)[0][1] - px
    )
    ph = capacity / pw
    panel_zone = [(px, px + pw), (py, py + ph), bounds[2]]
    assert inside(bounds, panel_zone)
    assert inside(panel_zone, axes(panel_box))
    assert inside(panel_zone, axes(indexed["panel:connection"]))
    xs = sorted(
        {px, px + pw, *(max(px, min(px + pw, x)) for o in objects for x in axes(o)[0])}
    )
    ys = sorted(
        {py, py + ph, *(max(py, min(py + ph, y)) for o in objects for y in axes(o)[1])}
    )
    blocked = sum(
        (b - a) * (d - c)
        for a, b in zip(xs[:-1], xs[1:], strict=True)
        for c, d in zip(ys[:-1], ys[1:], strict=True)
        if any(overlap([(a, b), (c, d)], axes(o)[:2]) for o in objects)
    )
    assert capacity - blocked == Fraction(w["reserve"]["PANEL"]["free_mm2"])
    assert (capacity - blocked) * 4 >= capacity
    din_capacity = (bounds[0][1] - dx) * w["rows"]
    occupied = sum(axes(o)[0][1] - axes(o)[0][0] for o in din)
    # These fixtures have no cross-row obstructions: body+connection widths match.
    assert din_capacity == Fraction(w["reserve"]["DIN"]["capacity_mm"])
    assert din_capacity - occupied == Fraction(w["reserve"]["DIN"]["free_mm"])
    assert (din_capacity - occupied) * 10 >= din_capacity
    assert {axes(o)[1][0] - dy for o in din} == {
        Fraction(i * 150) for i in range(w["rows"])
    }
    future_objects: list[Any] = []
    for kind, proof in w["reserve"].items():
        future = proof.get("future_witness")
        if future:
            zone = (
                panel_zone
                if kind == "PANEL"
                else [
                    (dx, bounds[0][1]),
                    (dy, bounds[1][1] - Fraction(str(parameters["service_height_mm"]))),
                    bounds[2],
                ]
            )
            for o in future.values():
                assert inside(zone, axes(o))
                assert all(not overlap(axes(o), axes(p)) for p in objects)
                assert all(not overlap(axes(o), axes(p)) for p in future_objects)
                future_objects.append(o)
            assert any(contact(axes(future["connection"]), axes(r)) for r in routes)


def synthetic_panel_case(count: int, width: int = 29) -> tuple[Any, Any, Any]:
    apparatus = [
        dict(
            units()[0],
            id=f"din-{i}",
            dimensions_mm=[63, width, 27],
            clearance_mm=[2, 3, 1, 2],
        )
        for i in range(count)
    ]
    apparatus.append(
        dict(
            units()[0],
            id="panel",
            mounting="PANEL",
            dimensions_mm=[174, 67, 41],
            clearance_mm=[4, 7, 3, 6],
        )
    )
    parameters = {
        "insets_mm": [3, 5, 7, 11, 2, 4],
        "route_hwd_mm": [13, 9],
        "connection_hd_mm": [17, 19],
        "service_height_mm": 29,
    }
    future = {
        "status": "REQUIRED",
        # Existing future search anchors the body at the row origin; this
        # reference aligns its connection with the row branch (63+2+3 mm).
        "reference_hwd_mm": {"DIN": [68, 11, 24], "PANEL": [40, 29, 33]},
    }
    return apparatus, parameters, future


@pytest.mark.parametrize(
    "count,width,size,rows,orientation",
    [
        (3, 23, [500, 260, 90], 1, "BESIDE"),
        (6, 29, [500, 260, 90], 2, "BESIDE"),
        (7, 31, [500, 260, 90], 3, "BESIDE"),
        (10, 31, [650, 260, 90], 4, "BESIDE"),
        (6, 29, [700, 180, 90], 2, "ABOVE"),
    ],
)
def test_synthetic_panel_rows_and_positions(
    count: int, width: int, size: Any, rows: int, orientation: str
) -> None:
    u, p, f = synthetic_panel_case(count, width)
    result = geo.evaluate(size, u, p, f)
    assert result["status"] == "CONDITIONAL_GEOMETRY"
    assert result["witness"]["rows"] == rows
    assert result["witness"]["orientation"] == orientation
    independent_witness_check(result, u, p)
    assert all(
        x["operational_status"] == "REFERENCE_FITS"
        for x in result["witness"]["reserve"].values()
    )


@pytest.mark.parametrize("route", [25, 10])
def test_reported_side_panel_connection_and_keepout_regression(route: int) -> None:
    u = [
        dict(units()[0], id=f"d{i}", dimensions_mm=[86.4, 35.6, 67.9])
        for i in range(20)
    ]
    u.append(
        dict(
            units()[0],
            id="panel",
            mounting="PANEL",
            dimensions_mm=[253, 93, 97.8],
            clearance_mm=[50, 50, 20, 20],
            body_reference={
                "dimensions_mm": [151.2, 93, 97.8],
                "edge_mm": [122.5, 122.5, 20, 20],
            },
        )
    )
    p = {
        "insets_mm": [10] * 6,
        "route_hwd_mm": [route, route],
        "connection_hd_mm": [35, 40],
        "service_height_mm": 80,
    }
    f = {
        "status": "REQUIRED",
        "reference_hwd_mm": {"DIN": [86.4, 35.6, 67.9], "PANEL": [100, 60, 100]},
    }
    result = geo.evaluate([720, 520, 200], u, p, f)
    assert result["status"] == "CONDITIONAL_GEOMETRY"
    assert result["witness"]["orientation"] == "BESIDE"
    assert result["witness"]["rows"] == 3
    independent_witness_check(result, u, p)


def test_short_future_reference_keeps_existing_row_anchor_limitation() -> None:
    u, p, f = synthetic_panel_case(6)
    f["reference_hwd_mm"]["DIN"][0] = 48
    r = geo.evaluate([500, 260, 90], u, p, f)
    assert r["status"] == "NO_LAYOUT_IN_EXAMINED_FAMILY"
    assert "REQUIRED_REFERENCE:DIN" in r["failed_constraints"]


@pytest.mark.parametrize("damage", ["depth", "clearance", "future_din", "future_panel"])
def test_synthetic_panel_rejects_unsafe_bounds(damage: str) -> None:
    u, p, f = synthetic_panel_case(6)
    size = [500, 260, 90]
    if damage == "depth":
        size[2] = 30
    elif damage == "clearance":
        u[-1]["clearance_mm"] = [400, 400, 400, 400]
    elif damage == "future_din":
        f["reference_hwd_mm"]["DIN"] = [200, 500, 24]
    else:
        f["reference_hwd_mm"]["PANEL"] = [200, 500, 33]
    assert geo.evaluate(size, u, p, f)["status"] == "NO_LAYOUT_IN_EXAMINED_FAMILY"


def test_panel_area_and_din_resource_are_independent_gates() -> None:
    p = api.normalize(request())["profiles"][0]["parameters"]
    p = dict(p, route_hwd_mm=[100, 10])
    u = [
        units()[0],
        dict(units()[0], id="panel", mounting="PANEL", dimensions_mm=[10, 20, 20]),
    ]
    f = {"status": "UNKNOWN", "reference_hwd_mm": {}}
    r = geo.evaluate([200, 400, 50], u, p, f)
    assert r["status"] == "NO_LAYOUT_IN_EXAMINED_FAMILY"
    assert "RESERVE:PANEL" in r["failed_constraints"]
    p["route_hwd_mm"] = [10, 10]
    u = [dict(units()[0], id=f"d{i}") for i in range(6)] + [u[-1]]
    r = geo.evaluate([600, 400, 50], u, p, f, {"count": 2, "length_mm": 60})
    assert r["status"] == "NO_LAYOUT_IN_EXAMINED_FAMILY"
    assert "RESERVE:DIN" in r["failed_constraints"]


@pytest.mark.parametrize("damage", ["collision", "disconnection"])
def test_corrupt_side_routes_cannot_produce_fit(
    monkeypatch: pytest.MonkeyPatch, damage: str
) -> None:
    u, p, f = synthetic_panel_case(6)
    size = [350, 260, 90]
    baseline = geo.evaluate(size, u, p, f)
    assert baseline["status"] == "CONDITIONAL_GEOMETRY"
    assert baseline["witness"]["orientation"] == "BESIDE"
    original = geo.g.box

    def corrupt(identity: str, kind: str, origin: Any, size: Any) -> Any:
        if damage == "collision" and identity == "din-0":
            origin = [20, 20, 0]
        if damage == "disconnection" and identity == "panel:branch":
            size = [20, *size[1:]]
        return original(identity, kind, origin, size)

    monkeypatch.setattr(geo.g, "box", corrupt)
    r = geo.evaluate(size, u, p, f)
    assert r["status"] == "NO_LAYOUT_IN_EXAMINED_FAMILY"
    assert (
        any(reason.startswith("INTERSECTION:") for reason in r["failed_constraints"])
        if damage == "collision"
        else "ROUTE_CONNECTIVITY" in r["failed_constraints"]
    )
