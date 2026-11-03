"""Family policy gates, with synthetic source facts and no KURN admission."""

from __future__ import annotations

import copy
from decimal import Decimal
from typing import Any

import cabinet_catalogue as catalogue  # type: ignore[import-not-found]
import cabinet_reserve_policy as rules  # type: ignore[import-not-found]
import cabinet_sizing as sizing  # type: ignore[import-not-found]
import cabinet_sizing_catalogue as expanded  # type: ignore[import-not-found]
import cabinet_sizing_module_accounting as modules  # type: ignore[import-not-found]
import pytest
from test_cabinet_sizing_module_accounting import calculate, shape
from test_cabinet_sizing_module_accounting import chain as chain
from test_cabinet_sizing_selector import (
    provide,
    synthetic_cab,
    synthetic_record,
    synthetic_zone,
)
from test_versioned_metal_source import synthetic_sources as synthetic_sources


def set_family(chain: Any, monkeypatch: pytest.MonkeyPatch, family: str) -> None:
    item = chain["items"][0]
    if family == "KURN":
        # Source-reader replacement is a test authority, not a production row.
        cab = {
            "cabinet_code": "TEST-CONFIRMED-KURN",
            "cabinet_label": "TEST",
            "cabinet_type": "KURN",
            "dimensions_mm": [400, 400, 200],
        }
        record = {
            "cabinet_code": cab["cabinet_code"],
            "family": "KURN",
            "dimensions_mm": cab["dimensions_mm"],
            "source_issues": [],
            "source": chain["data"]["raw_sources"][0],
        }
        monkeypatch.setattr(
            catalogue, "inventory", lambda **kwargs: {"records": [record]}
        )
        chain["base"]["sources"] = {
            "schema_version": "cabinet_sizing.catalogue_request.v0.1"
        }
    else:
        code = (
            "METAL-500X400X250-D22"
            if family == "METAL"
            else next(
                code
                for code in sizing.CABINETS
                if sizing.cabinet_identity(code)[1] == family
            )
        )
        label, kind, dimensions = sizing.cabinet_identity(code)
        cab = {
            "cabinet_code": code,
            "cabinet_label": label,
            "cabinet_type": kind,
            "dimensions_mm": dimensions,
        }
    item["cabinet"] = cab
    chain["data"]["composition_sha256"] = modules.composition_hash(chain["items"])
    chain["data"]["sizing_sha256"] = sizing.digest(chain["base"])
    chain["data"]["boards"][0]["cabinet_sha256"] = sizing.digest(cab)


@pytest.mark.parametrize(
    "family,minimum", [("KRN", 0), ("KRV", 0), ("KURN", 0), ("METAL", 10)]
)
def test_source_bound_family_thresholds_and_saturation(
    chain: Any, monkeypatch: pytest.MonkeyPatch, family: str, minimum: int
) -> None:
    set_family(chain, monkeypatch, family)
    shape(chain, 10, 100)
    if family == "METAL":
        with pytest.raises(sizing.SizingHold, match="HOLD_MODULE_RESERVE:DIN"):
            calculate(chain, monkeypatch)
        shape(chain, 9, 90)
    result = calculate(chain, monkeypatch)
    board = result["items"][0]
    assert board["reserve_identity"]["family"] == family
    assert board["reserve"]["DIN"]["minimum_free_percent"] == str(minimum)
    if minimum == 0:
        assert board["zones"][0]["free_mm"] == "0"
        assert board["zones"][0]["free_modules"] == "0"
    assert "KURN" not in {r[0] for r in catalogue.RANGES}


@pytest.mark.parametrize("family", ["KRN", "KRV", "KURN", "METAL"])
def test_project_stricter_than_family(
    chain: Any, monkeypatch: pytest.MonkeyPatch, family: str
) -> None:
    set_family(chain, monkeypatch, family)
    chain["data"]["boards"][0]["project_min_din_free_percent"] = 20
    shape(chain, 9, 90)
    with pytest.raises(sizing.SizingHold, match="HOLD_MODULE_RESERVE:DIN"):
        calculate(chain, monkeypatch)
    shape(chain, 8, 80)
    result = calculate(chain, monkeypatch)
    assert result["items"][0]["reserve"]["DIN"]["minimum_free_percent"] == "20"


@pytest.mark.parametrize("nominal,width", [(11, 100), (10, 101)])
def test_zero_percent_does_not_allow_single_rail_overload(
    chain: Any, monkeypatch: pytest.MonkeyPatch, nominal: int, width: int
) -> None:
    set_family(chain, monkeypatch, "KRN")
    empty = copy.deepcopy(chain["data"]["boards"][0]["zones"][0])
    empty["id"] = "UNUSED"
    chain["data"]["boards"][0]["zones"].append(empty)
    shape(chain, nominal, width)
    with pytest.raises(sizing.SizingHold, match="HOLD_MODULE_ROW_OVERFLOW"):
        calculate(chain, monkeypatch)


@pytest.mark.parametrize("field", ["capacity_modules", "capacity_mm"])
def test_zero_percent_still_requires_capacity_evidence(
    chain: Any, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    set_family(chain, monkeypatch, "KRV")
    chain["data"]["boards"][0]["zones"][0][field] = None
    with pytest.raises(sizing.SizingHold):
        calculate(chain, monkeypatch)


def test_label_cannot_select_zero_policy(
    chain: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    set_family(chain, monkeypatch, "METAL")
    chain["items"][0]["cabinet"]["cabinet_label"] = "KRN KRV KURN"
    chain["data"]["composition_sha256"] = modules.composition_hash(chain["items"])
    chain["data"]["boards"][0]["cabinet_sha256"] = sizing.digest(
        chain["items"][0]["cabinet"]
    )
    shape(chain, 10, 100)
    with pytest.raises(sizing.SizingHold, match="HOLD_MODULE_RESERVE:DIN"):
        calculate(chain, monkeypatch)
    chain["items"][0]["cabinet"]["cabinet_type"] = "KRN"
    chain["data"]["composition_sha256"] = modules.composition_hash(chain["items"])
    chain["data"]["boards"][0]["cabinet_sha256"] = sizing.digest(
        chain["items"][0]["cabinet"]
    )
    with pytest.raises(sizing.SizingHold, match="IDENTITY_CONFLICT"):
        calculate(chain, monkeypatch)


def test_unadmitted_kurn_identity_is_not_enabled(
    chain: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    cab = chain["items"][0]["cabinet"]
    cab.update(cabinet_code="TEST-KURN-NOT-IN-CATALOGUE", cabinet_type="KURN")
    chain["data"]["composition_sha256"] = modules.composition_hash(chain["items"])
    chain["data"]["boards"][0]["cabinet_sha256"] = sizing.digest(cab)
    with pytest.raises(sizing.SizingHold, match="IDENTITY_SOURCE_REQUIRED"):
        calculate(chain, monkeypatch)
    assert "KURN" not in {r[0] for r in catalogue.RANGES}


def test_stored_reserve_policy_cannot_override_admitted_project(
    chain: Any,
) -> None:
    wrong = rules.make("CASE-TEST", {"BOARD": {"DIN": 1, "PANEL": 0}})
    base = {
        "schema_version": rules.BASE_SCHEMA,
        "case_id": "CASE-TEST",
        "items": [],
        "sources": {"request": {}, "reserve_policy": wrong, "algorithm_schema": "TEST"},
    }
    report = {
        "schema_version": modules.REPORT_SCHEMA,
        "case_id": "CASE-TEST",
        "items": [],
        "sources": {
            "base_sizing_sources": base["sources"],
            "module_evidence": chain["binding"],
        },
        "base_report": base,
        "module_ledger": {},
    }
    with pytest.raises(sizing.SizingHold, match="HOLD_MODULE_RESERVE_POLICY_DRIFT"):
        modules.verify_sizing_report(report, chain["items"], "CASE-TEST")


@pytest.mark.parametrize("family", ["KRN", "KRV", "KURN", "METAL"])
def test_panel_quarter_and_project_override_independent(
    chain: Any, monkeypatch: pytest.MonkeyPatch, family: str
) -> None:
    set_family(chain, monkeypatch, family)
    data = chain["data"]
    board = data["boards"][0]
    product = copy.deepcopy(data["products"][0])
    product.update(
        id="PANEL-P",
        sku="TEST-PANEL",
        mounting="PANEL",
        nominal_modules=None,
        width_mm=None,
        area_mm2=75,
    )
    data["products"].append(product)
    profile = copy.deepcopy(data["profiles"][0])
    profile.update(
        id="PANEL-P",
        product_ids=["PANEL-P"],
        nominal_modules=None,
        width_mm=None,
        area_mm2=75,
        allowed_zones=["PANEL"],
    )
    data["profiles"].append(profile)
    board["instances"].append(
        {"id": "PANEL-I", "component_id": None, "unit": 1, "product_id": "PANEL-P"}
    )
    board["groups"].append(
        {
            "id": "PANEL-G",
            "profile_id": "PANEL-P",
            "instance_ids": ["PANEL-I"],
            "zone_id": "PANEL",
        }
    )
    next(z for z in board["zones"] if z["kind"] == "PANEL")["capacity_area_mm2"] = 100
    result = calculate(chain, monkeypatch)
    assert result["items"][0]["reserve"]["PANEL"]["minimum_free_percent"] == "25"
    product["area_mm2"] = profile["area_mm2"] = 76
    with pytest.raises(sizing.SizingHold, match="HOLD_MODULE_RESERVE:PANEL"):
        calculate(chain, monkeypatch)
    product["area_mm2"] = profile["area_mm2"] = 75
    board["project_min_panel_free_percent"] = 30
    with pytest.raises(sizing.SizingHold, match="HOLD_MODULE_RESERVE:PANEL"):
        calculate(chain, monkeypatch)


@pytest.mark.parametrize(
    "family,occupied,expected",
    [("KRN", 100, "0"), ("KRV", 100, "0"), ("METAL", 90, "0.1")],
)
def test_exact_base_gate_no_longer_applies_legacy_quarter(
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
    family: str,
    occupied: int,
    expected: str,
) -> None:
    code = (
        "METAL-500X400X250-D22"
        if family == "METAL"
        else next(c for c in sizing.CABINETS if sizing.cabinet_identity(c)[1] == family)
    )
    cab = synthetic_cab(code, [synthetic_zone(width=100)])
    record = synthetic_record(size=[80, occupied, 30])
    item = {
        "item_id": "I",
        "product_name": "TEST",
        "quantity": 1,
        "components": [
            {"component_id": "C", "component_code": "TEST_DIN", "quantity": 1}
        ],
    }
    item, request, _ = provide(
        tmp_path, monkeypatch, item=item, records=[record], cabinets=[cab]
    )
    with pytest.raises(sizing.SizingHold):
        sizing.size_composition("CASE", [item], request)
    policy = rules.make("CASE", {"I": {"DIN": 0, "PANEL": 0}})
    report = sizing.size_composition("CASE", [item], request, reserve_policy=policy)
    assert report["schema_version"] == rules.BASE_SCHEMA
    assert (
        report["items"][0]["layout"]["reserve"]["DIN"]["minimum_free_fraction"]
        == expected
    )
    strict = rules.make("CASE", {"I": {"DIN": 20, "PANEL": 0}})
    with pytest.raises(sizing.SizingHold):
        sizing.size_composition("CASE", [item], request, reserve_policy=strict)


def test_krn36_capacity_zero_allows_full_source_capacity_only() -> None:
    record = {
        "cabinet_code": "CATALOGUE-KRN-ROW-64",
        "dimensions_mm": [540, 330, 100],
        "technical_binding": {"rail_count": 3},
        "din_capacity_binding": {
            "rail_count": 3,
            "rail_capacity_mm": 216,
            "total_capacity_mm": 648,
        },
    }
    env = synthetic_record(size=[80, 216, 30])
    env["mounting"] = "DIN"
    units: list[dict[str, Any]] = [
        {"component_id": "C", "unit": n, "envelope": copy.deepcopy(env)}
        for n in range(1, 4)
    ]
    assert expanded.din_capacity(record, units)["status"] == "NO_FIT"
    proof = expanded.din_capacity(record, units, free_percent=Decimal(0))
    assert proof["status"] == "PASS" and proof["free_mm"] == 0
    assert all(r["occupied_mm"] == 216 for r in proof["rows"])
    assert (
        expanded.din_capacity(record, units, free_percent=Decimal(5))["status"]
        == "NO_FIT"
    )
    units = copy.deepcopy(units)
    units[0]["envelope"]["dimensions_mm"][1] = Decimal(217)
    units[1]["envelope"]["dimensions_mm"][1] = Decimal(215)
    assert (
        expanded.din_capacity(record, units, free_percent=Decimal(0))["reason"]
        == "DIN_ROW_CAPACITY_INSUFFICIENT"
    )


def test_catalogue_mounting_gate_also_uses_zero(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, synthetic_sources: Any
) -> None:
    from test_cabinet_sizing_catalogue import capacity_outcome

    old, item, request = capacity_outcome(
        tmp_path, monkeypatch, synthetic_sources, [216, 216, 216], full_mount=True
    )
    assert old["status"] == "NO_FIT"
    policy = rules.make("CASE", {"I": {"DIN": 0, "PANEL": 0}})
    report = sizing.size_composition("CASE", [item], request, reserve_policy=policy)
    result = report["items"][0]["provenance"]["candidate_outcomes"][0]
    assert result["status"] == "FIT"
    assert result["din_capacity_assessment"]["reserve_required_percent"] == "0"
    assert result["layout"]["reserve"]["DIN"]["minimum_free_fraction"] == "0"


def test_metal_planning_lower_bound_uses_ten_not_quarter() -> None:
    import cabinet_sizing_pragmatic as planning  # type: ignore[import-not-found]

    env = synthetic_record(size=[80, 90, 30])
    units = [{"component_id": "C", "unit": 1, "envelope": env}]
    old, panel = planning.planning_shapes(units, Decimal(80))
    new, _ = planning.planning_shapes(units, Decimal(80), din_free_percent=Decimal(10))
    bound = [Decimal(80), Decimal(100), Decimal(30)]
    assert planning.construct(old[0], panel, bound, "VERTICAL") is None
    result = planning.construct(
        new[0], panel, bound, "VERTICAL", din_free_percent=Decimal(10)
    )
    assert (
        result is not None
        and result["reserve"]["DIN"]["minimum_free_fraction"] == "0.1"
    )


def test_planning_panel_still_requires_quarter() -> None:
    import cabinet_sizing_pragmatic as planning  # type: ignore[import-not-found]

    env = synthetic_record(mounting="PANEL", size=[10, Decimal("7.5"), 1])
    _, panel = planning.planning_shapes(
        [{"component_id": "P", "unit": 1, "envelope": env}], Decimal(10)
    )
    bound = [Decimal(10), Decimal(10), Decimal(1)]
    result = planning.construct(
        None, panel, bound, "VERTICAL", din_free_percent=Decimal(0)
    )
    assert (
        result is not None
        and result["reserve"]["PANEL"]["minimum_free_fraction"] == "0.25"
    )
    assert (
        planning.construct(
            None, panel, bound, "VERTICAL", panel_free_percent=Decimal(30)
        )
        is None
    )
