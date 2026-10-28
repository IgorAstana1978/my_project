"""Public geometric mechanics; all dimensions here are synthetic examples."""

from __future__ import annotations

import importlib
import importlib.util
from decimal import Decimal, getcontext, localcontext
from typing import Any

import pytest


@pytest.fixture
def api() -> Any:
    if importlib.util.find_spec("engineering_layout_geometry") is None:
        pytest.fail("Public joint geometry API is not implemented")
    return importlib.import_module("engineering_layout_geometry")


def test_exact_union_free_regions_and_depth_touching(api: Any) -> None:
    boundary = api.box("cab", "BOUNDARY", [0, 0, 0], [10, 10, 10])
    a = api.box("a", "SOLID", [0, 0, 0], [6, 6, 2])
    b = api.box("b", "SOLID", [4, 4, 2], [6, 6, 2])
    assert not api.intersects(a, b)  # Different depths only touch.
    assert api.contains(boundary, b)
    proof = api.area_reserve(boundary, [a, b], [2, 2, 1])
    # 36 + 36 - 2*2 = 68, regardless of the projected depth.
    assert Decimal(proof["blocked_mm2"]) == 68
    assert Decimal(proof["free_mm2"]) == 32
    assert proof["scalar_reserve_satisfied"] is True
    assert (
        sum(Decimal(r[2]) * Decimal(r[3]) for r in proof["free_rectangles_xywh"]) == 32
    )
    assert api.intersects(a, api.box("c", "SOLID", [5, 5, 1], [1, 1, 1]))


def test_fragmented_area_is_not_operational_spare(api: Any) -> None:
    cab = api.box("cab", "BOUNDARY", [0, 0, 0], [10, 10, 2])
    stripe = api.box("s", "ACCESS", [4, 0, 0], [2, 10, 2])
    proof = api.area_reserve(cab, [stripe], [2, 5, 1])
    assert proof["free_mm2"] == "80"
    assert proof["scalar_reserve_satisfied"] is True
    assert proof["operational_status"] == "NO_REFERENCE_FIT"
    assert api.area_reserve(cab, [stripe], None)["operational_status"] == "UNKNOWN"


@pytest.mark.parametrize("value", [0, -1, True, "NaN", "0.0000001", "100001"])
def test_invalid_dimensions_fail_closed(api: Any, value: Any) -> None:
    with pytest.raises(ValueError):
        api.box("x", "SOLID", [0, 0, 0], [value, 2, 3])


def test_collision_checks_do_not_waive_known_keepouts(api: Any) -> None:
    cab = api.box("cab", "BOUNDARY", [0, 0, 0], [10, 10, 10])
    a = api.box("a", "KEEPOUT", [1, 1, 0], [3, 3, 3])
    b = api.box("b", "CONNECTION", [2, 2, 0], [3, 3, 3])
    assert api.check_placements(cab, [a, b]) == ["INTERSECTION:a:b"]
    assert api.check_placements(cab, [a, b], [["a", "b"]]) == [
        "SOURCE_KEEPOUT_SHARING_FORBIDDEN:a:b"
    ]
    outside = api.box("out", "SOLID", [9, 0, 0], [2, 2, 2])
    assert api.check_placements(cab, [outside]) == ["OUTSIDE:out"]


def test_duct_graph_requires_real_geometric_attachments(api: Any) -> None:
    trunk = api.box("trunk", "DUCT", [0, 0, 0], [2, 10, 2])
    branch = api.box("branch", "DUCT", [2, 5, 0], [8, 2, 2])
    port = api.box("port", "CONNECTION", [8, 3, 0], [2, 2, 2])
    entry = api.box("entry", "ENTRY", [0, 10, 0], [2, 2, 2])
    graph = api.connection_graph([trunk, branch], [port, entry], "entry")
    assert graph["status"] == "CONNECTED_RESERVATIONS"
    assert graph["reachable"] == ["branch", "entry", "port", "trunk"]
    detached = api.box("branch", "DUCT", [3, 5, 0], [7, 2, 2])
    assert (
        api.connection_graph([trunk, detached], [port, entry], "entry")["status"]
        == "DISCONNECTED"
    )


def test_corner_contact_is_not_a_duct_aperture(api: Any) -> None:
    a = api.box("a", "DUCT", [0, 0, 0], [2, 2, 2])
    b = api.box("b", "DUCT", [2, 2, 0], [2, 2, 2])
    end = api.box("entry", "ENTRY", [4, 2, 0], [2, 2, 2])
    assert api.connection_graph([a, b], [end], "entry")["status"] == "DISCONNECTED"


def test_connection_cannot_bridge_disconnected_duct_network(api: Any) -> None:
    a = api.box("a", "DUCT", [0, 0, 0], [2, 10, 2])
    b = api.box("b", "DUCT", [4, 0, 0], [2, 10, 2])
    bridge = api.box("peer", "CONNECTION", [2, 0, 0], [2, 10, 2])
    entry = api.box("entry", "ENTRY", [0, 10, 0], [2, 2, 2])
    graph = api.connection_graph([a, b], [entry, bridge], "entry")
    assert graph["status"] == "DISCONNECTED"
    assert "b" not in graph["reachable"]


def test_operational_spare_cannot_intersect_next_duct(api: Any) -> None:
    p = parameters()
    p["future_din_hwd_mm"] = [100, 20, 20]
    result = api.search_joint([350, 100, 50], [unit(f"q{i}") for i in range(4)], p)
    # Existing 40-mm apparatus clears its branch at y50; a 100-mm future
    # apparatus would run through that branch even though 30mm rail is free.
    assert result["witness"] is None
    assert "OPERATIONAL_REFERENCE_NO_FIT:DIN" in result["failed_constraints"]


def test_search_does_not_change_callers_decimal_context(api: Any) -> None:
    with localcontext():
        getcontext().clear_flags()
        before = str(getcontext())
        api.search_joint(
            [400, 250, 60], [unit("panel", 50, "PANEL"), unit("din")], parameters()
        )
        assert str(getcontext()) == before


def unit(cid: str, width: int = 30, mounting: str = "DIN") -> dict[str, Any]:
    return {
        "id": cid,
        "mounting": mounting,
        "dimensions_mm": [40, width, 20],
        "clearance_mm": [0, 0, 0, 0],
        "body_reference": None,
        "pair_gap_mm": [0, 0],
        "extra_gap_mm": 0,
    }


def parameters() -> dict[str, Any]:
    return {
        "insets_mm": [0, 0, 0, 0, 0, 0],
        "mount_offset_mm": 0,
        "duct_width_mm": 10,
        "duct_depth_mm": 10,
        "connection_height_mm": 10,
        "connection_depth_mm": 10,
        "service_height_mm": 20,
        "access_width_mm": 0,
        "assigned_width_mm": 0,
        "auxiliary_width_mm": 20,
        "future_din_hwd_mm": [40, 20, 20],
        "future_panel_hwd_mm": [40, 20, 20],
    }


def test_joint_search_reallocates_rows_and_channels_can_destroy_body_fit(
    api: Any,
) -> None:
    units = [unit(f"q{i}") for i in range(4)]
    result = api.search_joint([350, 100, 50], units, parameters())
    assert result["status"] == "CONDITIONAL_WITNESS"
    witness = result["witness"]
    assert witness["din_rows"] == 2
    assert witness["graph"]["status"] == "CONNECTED_RESERVATIONS"
    assert witness["reserve"]["DIN"]["capacity_mm"] == "180"
    assert witness["reserve"]["DIN"]["occupied_mm"] == "120"
    assert witness["reserve"]["DIN"]["free_mm"] == "60"
    assert (
        api.check_placements(
            witness["boundary"], witness["objects"], witness["allowed_sharing"]
        )
        == []
    )
    changed = parameters()
    changed["duct_width_mm"] = 75
    narrow = api.search_joint([350, 100, 50], units, changed)
    assert narrow["witness"] is None
    assert narrow["status"] == "NO_LAYOUT_IN_EXAMINED_FAMILY"
    assert narrow["search"]["global_optimum_proven"] is False
    assert (
        api.search_joint([350, 100, 50], list(reversed(units)), parameters()) == result
    )


def test_depth_and_known_rail_capacity_cannot_be_waived(api: Any) -> None:
    units = [unit(f"q{i}") for i in range(4)]
    assert api.search_joint([350, 100, 15], units, parameters())["witness"] is None
    limited = api.search_joint(
        [350, 100, 50], units, parameters(), {"count": 1, "length_mm": 50}
    )
    assert limited["witness"] is None
    assert "KNOWN_DIN_CAPACITY" in limited["failed_constraints"]
    assert (
        api.search_joint([350, 100, 50], units, parameters(), budget=0)["status"]
        == "SEARCH_BUDGET_EXHAUSTED"
    )


def test_independent_panel_reserve_and_unknown_body_anchor(api: Any) -> None:
    panel = unit("panel", 50, "PANEL")
    panel["body_reference"] = {"dimensions_mm": [20, 50, 20], "edge_mm": [30, 30, 5, 5]}
    panel["clearance_mm"] = [10, 10, 5, 5]
    result = api.search_joint([400, 250, 60], [panel, unit("din")], parameters())
    assert result["status"] == "CONDITIONAL_WITNESS"
    witness = result["witness"]
    assert set(witness["reserve"]) == {"DIN", "PANEL"}
    assert all(
        proof["scalar_reserve_satisfied"] for proof in witness["reserve"].values()
    )
    placement = next(p for p in witness["apparatus"] if p["id"] == "panel")
    assert placement["footprint_hwd_mm"] == ["80", "60", "20"]
    assert placement["assembly_origin_mm"] is None
    assert placement["body_reference"] == panel["body_reference"]
    proof = witness["reserve"]["PANEL"]
    assert proof["occupied_mm2"] == "4800"  # conservative 80x60 keepout
    assert Decimal(proof["capacity_mm2"]) == sum(
        Decimal(proof[k]) for k in ("occupied_mm2", "blocked_mm2", "free_mm2")
    )


def test_known_rail_length_is_not_silently_shortened(api: Any) -> None:
    result = api.search_joint(
        [350, 100, 50], [unit("q")], parameters(), {"count": 1, "length_mm": 216}
    )
    assert result["witness"] is None
    assert (
        "KNOWN_DIN_RAIL_LENGTH_EXCEEDS_SCENARIO_BOUNDARY"
        in result["failed_constraints"]
    )


def test_reserve_distinguishes_hardware_and_blocked_keepout(api: Any) -> None:
    units = [unit(f"q{i}", 20) for i in range(4)]
    for u in units:
        u["clearance_mm"] = [0, 0, 5, 5]
    result = api.search_joint([350, 100, 50], units, parameters())
    proof = result["witness"]["reserve"]["DIN"]
    assert proof["occupied_mm"] == "80"
    assert proof["blocked_mm"] == "40"
    assert proof["free_mm"] == "60"


def test_assembly_origin_accounts_for_source_top_and_left_clearance(api: Any) -> None:
    apparatus = unit("q")
    apparatus["clearance_mm"] = [5, 7, 3, 11]
    result = api.search_joint([350, 100, 50], [apparatus], parameters())
    assert result["status"] == "CONDITIONAL_WITNESS"
    witness = result["witness"]
    placement = witness["apparatus"][0]
    keepout = next(o for o in witness["objects"] if o["id"] == "q")
    assert keepout["origin_xyz_mm"] == ["10", "0", "0"]
    # Source top5/left3 shift the assembly inside its keepout; XYZ != HWD.
    assert placement["assembly_origin_mm"] == ["13", "5", "0"]


def test_source_140_pitch_cannot_expand_to_fit_connections(api: Any) -> None:
    p = parameters()
    p["connection_height_mm"] = 100
    result = api.search_joint([350, 100, 50], [unit(f"q{i}") for i in range(4)], p)
    # Legacy40+100+10 needs150; source pitch stays140 in every topology.
    # The riser family cannot solve this narrow boundary with25% reserve.
    assert result["witness"] is None
    assert (
        "SOURCE_DIN_PITCH_140_INFRASTRUCTURE_CONFLICT" in result["failed_constraints"]
    )


def routing_parameters() -> dict[str, Any]:
    """The unchanged explore-a dimensions, only a synthetic mechanics fixture."""
    return {
        "insets_mm": [10, 10, 10, 10, 10, 10],
        "mount_offset_mm": 10,
        "duct_width_mm": 25,
        "duct_depth_mm": 25,
        "connection_height_mm": 35,
        "connection_depth_mm": 40,
        "service_height_mm": 80,
        "access_width_mm": 20,
        "assigned_width_mm": 0,
        "auxiliary_width_mm": 30,
        "future_din_hwd_mm": [86.4, 35.6, 67.9],
        "future_panel_hwd_mm": [100, 60, 100],
    }


def routing_units(count: int = 8) -> list[dict[str, Any]]:
    result = [unit(f"synthetic-din-{i}") for i in range(count)]
    for apparatus in result:
        apparatus["dimensions_mm"] = [86.4, 35.6, 67.9]
    return result


@pytest.mark.parametrize(
    "size,duct,rows,capacity,blocked,free",
    [
        ([800, 600, 200], 25, 4, "1368", "300", "356"),
        ([800, 800, 200], 55, 4, "2048", "660", "676"),
        ([1000, 600, 250], 55, 6, "1872", "660", "500"),
    ],
)
def test_shared_din_public_certificate(
    api: Any, size: Any, duct: int, rows: int, capacity: str, blocked: str, free: str
) -> None:
    # Independently derived certificates in the approved T11 specification.
    p = routing_parameters()
    p["duct_width_mm"] = duct
    panel = unit("panel", 133, "PANEL")
    panel.update(
        dimensions_mm=[253, 133, 97.8],
        body_reference={
            "dimensions_mm": [151.2, 133, 97.8],
            "edge_mm": [122.5, 122.5, 0, 0],
        },
    )
    result = api.search_joint(size, [*routing_units(20), panel], p)
    assert result["status"] == "CONDITIONAL_WITNESS"
    witness = result["witness"]
    assert witness["routing_topology"] == "DIN_SHARED_COLUMN_RISERS"
    assert witness["din_rows"] == rows
    proof = witness["reserve"]["DIN"]
    assert proof["capacity_mm"] == capacity
    assert proof["occupied_mm"] == "712"
    assert proof["blocked_mm"] == blocked
    assert proof["free_mm"] == free
    assert all(v["scalar_reserve_satisfied"] for v in witness["reserve"].values())
    assert result["search"]["routing_topologies"] == [
        "BELOW_ROW_DUCTS",
        "DIN_COLUMN_RISERS",
        "DIN_SHARED_COLUMN_RISERS",
    ]
    assert witness["reserve"]["PANEL"]["future_witness"]["kind"] == "FUTURE_REFERENCE"
    assert (
        next(a for a in witness["apparatus"] if a["id"] == "panel")[
            "assembly_origin_mm"
        ]
        is None
    )
    assert_shared_raw(witness)
    # The third certificate has six rows and twenty units: four empty cells
    # are genuine free geometry, without pseudo-apparatus or invented loading.
    assert len(witness["apparatus"]) == 21
    assert result == api.search_joint(size, [panel, *reversed(routing_units(20))], p)


def assert_shared_raw(witness: Any) -> None:
    objects = witness["objects"]
    ducts = [o for o in objects if o["kind"] == "DUCT"]
    paired = 0
    for i, obj in enumerate(objects):
        assert all(
            lo <= a < b <= hi
            for (lo, hi), (a, b) in zip(
                raw_axes(witness["boundary"]), raw_axes(obj), strict=True
            )
        )
        for other in objects[i + 1 :]:
            assert not raw_overlap(obj, other) or obj["kind"] == other["kind"] == "DUCT"
        if obj["kind"] == "CONNECTION":
            assert any(raw_attached(obj, duct) for duct in ducts)
    for duct in ducts:
        if not duct["id"].startswith("DIN:riser:"):
            continue
        da = raw_axes(duct)
        ports = [
            o for o in objects if o["kind"] == "CONNECTION" and raw_attached(o, duct)
        ]
        left = [o for o in ports if raw_axes(o)[0][1] == da[0][0]]
        right = [o for o in ports if raw_axes(o)[0][0] == da[0][1]]
        paired += bool(left and right)
    assert paired > 0
    for zone, proof in witness["reserve"].items():
        if zone == "DIN":
            future = proof["future_witness"]
            rows = proof["free_segments"]
            assert all(
                Decimal(b["y_mm"]) - Decimal(a["y_mm"]) == 140
                for a, b in zip(rows[:-1], rows[1:], strict=True)
            )
        else:
            future = {
                "body": proof["future_body_witness"],
                "connection": proof["future_connection_witness"],
            }
        for reference in future.values():
            assert not any(raw_overlap(reference, obj) for obj in objects)
        assert any(raw_attached(future["connection"], duct) for duct in ducts)


@pytest.mark.parametrize("count", [19, 20, 21])
def test_shared_heterogeneous_widths_and_odd_even_columns(api: Any, count: int) -> None:
    units = routing_units(count)
    units[0]["dimensions_mm"][1] = 54
    units[1].update(dimensions_mm=[60, 25.6, 67.9], clearance_mm=[10, 16.4, 5, 5])
    p = routing_parameters()
    p["duct_width_mm"] = 55
    panel = unit("panel", 133, "PANEL")
    panel.update(
        dimensions_mm=[253, 133, 97.8],
        body_reference={
            "dimensions_mm": [151.2, 133, 97.8],
            "edge_mm": [122.5, 122.5, 0, 0],
        },
    )
    units.append(panel)
    result = api.search_joint([800, 800, 200], units, p)
    witness = result["witness"]
    assert witness["routing_topology"] == "DIN_SHARED_COLUMN_RISERS"
    assert len(witness["apparatus"]) == count + 1
    assert_shared_raw(witness)
    assert result == api.search_joint([800, 800, 200], list(reversed(units)), p)


def test_public_multirow_alternative_preserves_pitch_and_subtracts_risers(
    api: Any,
) -> None:
    result = api.search_joint([1000, 400, 250], routing_units(), routing_parameters())
    # 86.4 + 35 = 121.4 fits pitch140; the legacy extra25 below each row
    # gives146.4. Four columns of35.6 plus25 riser use242.4 of335 per rail.
    assert result["status"] == "CONDITIONAL_WITNESS"
    witness = result["witness"]
    assert witness["routing_topology"] == "DIN_COLUMN_RISERS"
    assert witness["din_rows"] == 2 and witness["din_row_pitch_mm"] == "140"
    proof = witness["reserve"]["DIN"]
    assert proof["capacity_mm"] == "670"
    assert proof["occupied_mm"] == "284.8"
    assert proof["blocked_mm"] == "200"
    assert proof["free_mm"] == "185.2"
    assert proof["operational_status"] == "REFERENCE_FITS"
    assert proof["future_witness"]["connection"]["kind"] == "CONNECTION"
    assert result == api.search_joint(
        [1000, 400, 250], list(reversed(routing_units())), routing_parameters()
    )


def raw_axes(obj: Any) -> list[tuple[Decimal, Decimal]]:
    return [
        (Decimal(a), Decimal(a) + Decimal(b))
        for a, b in zip(obj["origin_xyz_mm"], obj["size_xyz_mm"], strict=True)
    ]


def raw_overlap(a: Any, b: Any) -> bool:
    return all(
        min(hi, end) > max(lo, start)
        for (lo, hi), (start, end) in zip(raw_axes(a), raw_axes(b), strict=True)
    )


def raw_attached(a: Any, b: Any) -> bool:
    extents = [
        min(hi, end) - max(lo, start)
        for (lo, hi), (start, end) in zip(raw_axes(a), raw_axes(b), strict=True)
    ]
    return min(extents) >= 0 and sum(v > 0 for v in extents) >= 2


@pytest.mark.parametrize("variant", ["known_rails", "clearance", "panel", "unequal"])
def test_riser_raw_geometry_reserve_future_and_source_constraints(
    api: Any, variant: str
) -> None:
    units = routing_units(6)
    size = [1000, 650, 250]
    limits = {"count": 3, "length_mm": 216}
    if variant == "clearance":
        for apparatus in units:
            apparatus.update(
                dimensions_mm=[60, 25.6, 67.9], clearance_mm=[10, 16.4, 5, 5]
            )
    if variant == "unequal":
        units[0]["dimensions_mm"][1] = 17.8
    if variant == "panel":
        panel = unit("panel", 100, "PANEL")
        panel.update(
            dimensions_mm=[253, 100, 100],
            clearance_mm=[50, 50, 20, 20],
            body_reference={
                "dimensions_mm": [151.2, 100, 100],
                "edge_mm": [122.5, 122.5, 0, 0],
            },
        )
        units.append(panel)
    result = api.search_joint(size, units, routing_parameters(), limits)
    assert result["status"] == "CONDITIONAL_WITNESS"
    witness = result["witness"]
    assert witness["routing_topology"] == "DIN_COLUMN_RISERS"
    assert witness["din_rows"] == 3 and witness["din_row_pitch_mm"] == "140"
    assert (
        "SOURCE_DIN_PITCH_140_INFRASTRUCTURE_CONFLICT"
        in result["search"]["topology_diagnostics"]["BELOW_ROW_DUCTS"][
            "failed_constraints"
        ]
    )
    objects = witness["objects"]
    ducts = [o for o in objects if o["kind"] == "DUCT"]
    bounds = raw_axes(witness["boundary"])
    for i, obj in enumerate(objects):
        assert all(
            low <= start < end <= high
            for (low, high), (start, end) in zip(bounds, raw_axes(obj), strict=True)
        )
        for other in objects[i + 1 :]:
            if raw_overlap(obj, other):
                assert obj["kind"] == other["kind"] == "DUCT"
        if obj["kind"] == "CONNECTION":
            assert any(raw_attached(obj, duct) for duct in ducts)
    assert witness["graph"]["status"] == "CONNECTED_RESERVATIONS"
    assert set(witness["graph"]["reachable"]) == set(witness["graph"]["nodes"])
    proof = witness["reserve"]["DIN"]
    assert Decimal(proof["capacity_mm"]) == 3 * 216
    assert Decimal(proof["blocked_mm"]) >= 3 * 2 * 25
    for kind, proof in witness["reserve"].items():
        suffix = "mm" if kind == "DIN" else "mm2"
        capacity, occupied, blocked, free = (
            Decimal(proof[f"{field}_{suffix}"])
            for field in ("capacity", "occupied", "blocked", "free")
        )
        assert capacity == occupied + blocked + free
        assert 4 * free >= capacity
        if kind == "PANEL":
            # Preserve the existing public Box; body/connection proofs are additive.
            assert proof["future_witness"]["kind"] == "FUTURE_REFERENCE"
            future = {
                "body": proof["future_body_witness"],
                "connection": proof["future_connection_witness"],
            }
        else:
            future = proof["future_witness"]
        zone = next(z for z in witness["zones"] if z["id"] == kind)
        for reference in future.values():
            assert not any(raw_overlap(reference, obj) for obj in objects)
            assert all(
                lo <= a < b <= hi
                for (lo, hi), (a, b) in zip(
                    raw_axes(zone), raw_axes(reference), strict=True
                )
            )
        assert raw_attached(future["body"], future["connection"])
        assert any(raw_attached(future["connection"], duct) for duct in ducts)
    if variant == "clearance":
        placed = witness["apparatus"][0]
        source = next(o for o in objects if o["id"] == placed["id"])
        assert placed["assembly_origin_mm"][:2] == [
            str(Decimal(source["origin_xyz_mm"][0]) + 5),
            str(Decimal(source["origin_xyz_mm"][1]) + 10),
        ]
    if variant == "panel":
        placed = next(a for a in witness["apparatus"] if a["id"] == "panel")
        assert Decimal(str(placed["source_dimensions_hwd_mm"][0])) == 253
        assert placed["footprint_hwd_mm"][0] == "396.2"
        assert placed["assembly_origin_mm"] is None


def test_riser_fragmented_future_and_blocked_capacity_cannot_be_called_spare(
    api: Any,
) -> None:
    p = routing_parameters()
    p["future_din_hwd_mm"] = [86.4, 100, 67.9]
    fragmented = api.search_joint([400, 400, 250], routing_units(), p)
    assert fragmented["witness"] is None
    assert (
        "OPERATIONAL_REFERENCE_NO_FIT:DIN"
        in fragmented["search"]["topology_diagnostics"]["DIN_COLUMN_RISERS"][
            "failed_constraints"
        ]
    )
    blocked = api.search_joint(
        [540, 330, 250],
        routing_units(),
        routing_parameters(),
        {"count": 3, "length_mm": 216},
    )
    # 648-284.8 alone looks sufficient. Three25-mm risers on each of three
    # unchanged216-mm rails leave138.2, below162: capacity cannot be shortened.
    witness = blocked["witness"]
    assert witness["routing_topology"] == "DIN_SHARED_COLUMN_RISERS"
    assert witness["din_rows"] == 3
    proof = witness["reserve"]["DIN"]
    assert [
        proof[k] for k in ("capacity_mm", "occupied_mm", "blocked_mm", "free_mm")
    ] == ["648", "284.8", "150", "213.2"]
    assert Decimal(proof["free_mm"]) * 4 >= 648
    assert (
        api.check_placements(
            witness["boundary"], witness["objects"], witness["allowed_sharing"]
        )
        == []
    )
    for reference in proof["future_witness"].values():
        assert not any(raw_overlap(reference, obj) for obj in witness["objects"])
    assert any(
        raw_attached(proof["future_witness"]["connection"], obj)
        for obj in witness["objects"]
        if obj["kind"] == "DUCT"
    )
    assert (
        "RESERVE_25_PERCENT:DIN"
        in blocked["search"]["topology_diagnostics"]["DIN_COLUMN_RISERS"][
            "failed_constraints"
        ]
    )


def test_topology_budget_and_source_pitch_are_separate_constraints(api: Any) -> None:
    # The18 legacy attempts must not be reported as a completed expanded family.
    limited = api.search_joint(
        [1000, 400, 250], routing_units(), routing_parameters(), budget=18
    )
    assert limited["status"] == "SEARCH_BUDGET_EXHAUSTED"
    assert limited["search"]["family_complete"] is False
    assert (
        limited["search"]["topology_diagnostics"]["DIN_COLUMN_RISERS"]["examined"] == 0
    )
    shared_parameters = routing_parameters()
    shared_parameters["duct_width_mm"] = 55
    shared_not_examined = api.search_joint(
        [1000, 400, 250], routing_units(20), shared_parameters, budget=84
    )
    assert shared_not_examined["status"] == "SEARCH_BUDGET_EXHAUSTED"
    assert shared_not_examined["search"]["family_complete"] is False
    assert (
        shared_not_examined["search"]["routing_topologies"][-1]
        == "DIN_SHARED_COLUMN_RISERS"
    )
    p = routing_parameters()
    p["connection_height_mm"] = 60  # 86.4+60 already exceeds140 without a duct.
    conflict = api.search_joint([1000, 400, 250], routing_units(), p)
    assert conflict["witness"] is None
    for diagnostics in conflict["search"]["topology_diagnostics"].values():
        assert (
            "SOURCE_DIN_PITCH_140_INFRASTRUCTURE_CONFLICT"
            in diagnostics["failed_constraints"]
        )
