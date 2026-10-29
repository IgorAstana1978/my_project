"""Research policy, source recomputation and geometry boundaries."""

import copy
import hashlib
import importlib
import json
from decimal import Decimal
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
