"""Mandatory exact-SKU accounting, without physical FIT or real authority."""

from __future__ import annotations

import copy
import json
from decimal import ROUND_DOWN, Inexact, localcontext
from pathlib import Path
from typing import Any

import cabinet_sizing as sizing  # type: ignore[import-not-found]
import cabinet_sizing_evidence as evidence  # type: ignore[import-not-found]
import cabinet_sizing_module_accounting as modules  # type: ignore[import-not-found]
import pytest
from module_accounting_fixtures import NATIVE_BUILD, provision_modules, repin


@pytest.fixture
def chain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    items = [
        {
            "item_id": "BOARD",
            "product_name": "TEST",
            "quantity": 1,
            "cabinet": {
                "cabinet_code": "METAL-500X400X250-D22",
                "cabinet_label": "TEST LABEL",
                "cabinet_type": "METAL",
                "dimensions_mm": [500, 400, 250],
            },
            "components": [
                {"component_id": "C1", "quantity": 1, "install_type": "ANY_DIN_TYPE"}
            ],
        }
    ]
    base = {
        "case_id": "CASE-TEST",
        "schema_version": "TEST",
        "items": [],
        "sources": {},
    }
    binding, data = provision_modules(tmp_path, monkeypatch, "CASE-TEST", items, base)
    data["boards"][0]["zones"][0].update(capacity_modules=10, capacity_mm=100)
    binding = repin(monkeypatch, Path(binding["path"]), data)
    return {"items": items, "base": base, "data": data, "binding": binding}


def calculate(chain: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    chain["binding"] = repin(monkeypatch, Path(chain["binding"]["path"]), chain["data"])
    return modules.build_ledger(
        "CASE-TEST", chain["items"], chain["base"], chain["binding"]
    )


def shape(chain: Any, nominal: Any, width: Any) -> None:
    for record in (chain["data"]["products"][0], chain["data"]["profiles"][0]):
        record.update(nominal_modules=nominal, width_mm=width)


@pytest.mark.parametrize(
    "kind",
    [
        "MCB",
        "RCBO",
        "RCD",
        "RN-47",
        "relay",
        "contactor",
        "timer",
        "indicator",
        "load switch",
        "auxiliary",
        "UNRECOGNIZED_NEW_KIND",
    ],
)
def test_all_types_and_exact_ten_percent(
    chain: Any, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    chain["data"]["products"][0]["sku"] = kind
    shape(chain, 9, 90)
    result = calculate(chain, monkeypatch)
    measures = result["items"][0]["reserve"]["DIN"]["measures"]
    assert measures["modules"]["free_percent"] == "10"
    assert measures["mm"]["free_percent"] == "10"
    assert "NOT_ESTABLISHED" in result["items"][0]["physical_fit"]


def test_compact_two_pole_is_not_two_modules(
    chain: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    chain["items"][0]["components"][0]["install_type"] = "modular_2p"
    chain["data"]["composition_sha256"] = modules.composition_hash(chain["items"])
    shape(chain, 1, 17.8)
    result = calculate(chain, monkeypatch)
    assert result["items"][0]["zones"][0]["occupied_modules"] == "1"
    assert result["items"][0]["zones"][0]["occupied_mm"] == "17.8"


@pytest.mark.parametrize("nominal,width", [("9.01", 90), (9, "90.01")])
def test_independent_ten_percent_limits(
    chain: Any, monkeypatch: pytest.MonkeyPatch, nominal: Any, width: Any
) -> None:
    shape(chain, nominal, width)
    with pytest.raises(sizing.SizingHold, match="HOLD_MODULE_RESERVE:DIN"):
        calculate(chain, monkeypatch)


@pytest.mark.parametrize("nominal,width", [(11, 1), (1, 101)])
def test_per_rail_overload_even_with_total_spare(
    chain: Any, monkeypatch: pytest.MonkeyPatch, nominal: Any, width: Any
) -> None:
    shape(chain, nominal, width)
    other = copy.deepcopy(chain["data"]["boards"][0]["zones"][0])
    other.update(id="EMPTY", capacity_modules=100, capacity_mm=1000)
    chain["data"]["boards"][0]["zones"].append(other)
    with pytest.raises(sizing.SizingHold, match="HOLD_MODULE_ROW_OVERFLOW"):
        calculate(chain, monkeypatch)


def test_no_per_rail_percentage(chain: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    shape(chain, 10, 100)
    other = copy.deepcopy(chain["data"]["boards"][0]["zones"][0])
    other.update(id="EMPTY", capacity_modules=10, capacity_mm=100)
    chain["data"]["boards"][0]["zones"].append(other)
    result = calculate(chain, monkeypatch)
    assert result["items"][0]["zones"][0]["free_modules"] == "0"
    assert (
        result["items"][0]["reserve"]["DIN"]["measures"]["mm"]["free_percent"] == "50"
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("nominal_modules", None),
        ("width_mm", None),
        ("nominal_modules", 0),
        ("width_mm", True),
        ("revision", ""),
    ],
)
def test_missing_or_untrusted_sku_fields(
    chain: Any, monkeypatch: pytest.MonkeyPatch, field: str, value: Any
) -> None:
    chain["data"]["products"][0][field] = value
    with pytest.raises(sizing.SizingHold):
        calculate(chain, monkeypatch)


@pytest.mark.parametrize(
    "override,pass_expected",
    [(0, True), (5, True), (10, True), (20, False), (100, False), (None, False)],
)
def test_stricter_project_din_policy(
    chain: Any, monkeypatch: pytest.MonkeyPatch, override: Any, pass_expected: bool
) -> None:
    shape(chain, 9, 90)
    chain["data"]["boards"][0]["project_min_din_free_percent"] = override
    if pass_expected:
        calculate(chain, monkeypatch)
    else:
        with pytest.raises(sizing.SizingHold):
            calculate(chain, monkeypatch)


@pytest.mark.parametrize(
    "mounting,area,override,pass_expected",
    [
        ("PANEL", 75, 0, True),
        ("PANEL", 76, 0, False),
        ("PANEL", 70, 40, False),
        ("OTHER", 100, 0, True),
    ],
)
def test_non_din_zones_and_panel_quarter(
    chain: Any,
    monkeypatch: pytest.MonkeyPatch,
    mounting: str,
    area: int,
    override: int,
    pass_expected: bool,
) -> None:
    chain["data"]["products"][0].update(
        mounting=mounting, nominal_modules=None, width_mm=None, area_mm2=area
    )
    chain["data"]["profiles"][0].update(
        nominal_modules=None, width_mm=None, area_mm2=area, allowed_zones=[mounting]
    )
    board = chain["data"]["boards"][0]
    zone = next(z for z in board["zones"] if z["kind"] == mounting)
    zone["capacity_area_mm2"] = 100
    board["groups"][0]["zone_id"] = mounting
    board["project_min_panel_free_percent"] = override
    if not pass_expected:
        with pytest.raises(sizing.SizingHold):
            calculate(chain, monkeypatch)
    else:
        result = calculate(chain, monkeypatch)
        assert result["items"][0]["reserve"]["DIN"]["measures"]["mm"]["occupied"] == "0"


def test_accessory_shared_footprint_counted_once(
    chain: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = chain["data"]
    board = data["boards"][0]
    accessory = copy.deepcopy(data["products"][0])
    accessory.update(id="AUX", sku="TEST-AUX")
    data["products"].append(accessory)
    board["instances"].append(
        {"id": "AUX1", "component_id": None, "unit": 1, "product_id": "AUX"}
    )
    data["profiles"][0].update(
        product_ids=[data["products"][0]["id"], "AUX"], nominal_modules=2, width_mm=36
    )
    board["groups"][0]["instance_ids"].append("AUX1")
    result = calculate(chain, monkeypatch)
    assert result["items"][0]["zones"][0]["occupied_mm"] == "36"
    assert len(result["items"][0]["instances"]) == 2
    board["groups"][0]["instance_ids"].reverse()
    with pytest.raises(sizing.SizingHold, match="FOOTPRINT_MEMBERS"):
        calculate(chain, monkeypatch)
    board["groups"][0]["instance_ids"].reverse()
    board["groups"].append(copy.deepcopy(board["groups"][0]))
    board["groups"][-1]["id"] = "DUPLICATE"
    with pytest.raises(sizing.SizingHold, match="DUPLICATE_OR_UNKNOWN_FOOTPRINT"):
        calculate(chain, monkeypatch)


@pytest.mark.parametrize(
    "attack",
    [
        "missing_instance",
        "extra_core",
        "unassigned",
        "wrong_zone",
        "disallowed_zone",
        "missing_profile",
        "different_members",
        "unbound_source",
        "extra_field",
        "false_quantity",
        "duplicate_id",
        "stale_composition",
        "stale_sizing",
    ],
)
def test_fail_closed_coverage_and_schema(
    chain: Any, monkeypatch: pytest.MonkeyPatch, attack: str
) -> None:
    d = chain["data"]
    b = d["boards"][0]
    if attack == "missing_instance":
        b["instances"] = []
    elif attack == "extra_core":
        b["instances"][0]["component_id"] = "UNKNOWN"
    elif attack == "unassigned":
        b["groups"] = []
    elif attack == "wrong_zone":
        b["groups"][0]["zone_id"] = "PANEL"
    elif attack == "disallowed_zone":
        d["profiles"][0]["allowed_zones"] = ["OTHER"]
    elif attack == "missing_profile":
        b["groups"][0]["profile_id"] = "MISSING"
    elif attack == "different_members":
        d["profiles"][0]["product_ids"] *= 2
    elif attack == "unbound_source":
        d["products"][0]["source"]["sha256"] = "0" * 64
    elif attack == "extra_field":
        d["products"][0]["approval"] = True
    elif attack == "false_quantity":
        b["quantity"] = True
    elif attack == "duplicate_id":
        b["instances"].append(copy.deepcopy(b["instances"][0]))
    elif attack == "stale_composition":
        d["composition_sha256"] = "0" * 64
    elif attack == "stale_sizing":
        d["sizing_sha256"] = "0" * 64
    with pytest.raises(sizing.SizingHold):
        calculate(chain, monkeypatch)


def test_quantity_expansion_and_missing_unit(
    chain: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    chain["items"][0]["components"][0]["quantity"] = 2
    chain["data"]["composition_sha256"] = modules.composition_hash(chain["items"])
    with pytest.raises(sizing.SizingHold, match="INSTANCE_COVERAGE"):
        calculate(chain, monkeypatch)
    b = chain["data"]["boards"][0]
    inst = copy.deepcopy(b["instances"][0])
    inst.update(id="UNIT2", unit=2)
    b["instances"].append(inst)
    group = copy.deepcopy(b["groups"][0])
    group.update(id="UNIT2", instance_ids=["UNIT2"])
    b["groups"].append(group)
    result = calculate(chain, monkeypatch)
    assert result["items"][0]["zones"][0]["occupied_modules"] == "2"


def test_source_drift_and_no_implicit_admission(
    chain: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(evidence, "AUTHORIZED", frozenset())
    with pytest.raises(sizing.SizingHold, match="UNAPPROVED_REUSABLE_SOURCE"):
        modules.build_ledger(
            "CASE-TEST", chain["items"], chain["base"], chain["binding"]
        )
    calculate(chain, monkeypatch)
    Path(chain["data"]["raw_sources"][0]["path"]).write_text("DRIFT")
    with pytest.raises(sizing.SizingHold, match="SOURCE_SHA_DRIFT"):
        modules.build_ledger(
            "CASE-TEST", chain["items"], chain["base"], chain["binding"]
        )


def test_ledger_recompute_and_missing_evidence(
    chain: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = calculate(chain, monkeypatch)
    modules.verify_ledger(ledger, "CASE-TEST", chain["items"], chain["base"])
    ledger["items"][0]["zones"][0]["occupied_mm"] = "0"
    with pytest.raises(sizing.SizingHold, match="LEDGER_DRIFT"):
        modules.verify_ledger(ledger, "CASE-TEST", chain["items"], chain["base"])
    with pytest.raises(sizing.SizingHold, match="EVIDENCE_REQUIRED"):
        modules.build_ledger("CASE-TEST", chain["items"], chain["base"], None)
    with pytest.raises(sizing.SizingHold, match="LEDGER_REQUIRED"):
        modules.verify_ledger(None, "CASE-TEST", chain["items"], chain["base"])


def test_duplicate_json_key_rejected(
    chain: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = Path(chain["binding"]["path"])
    path.write_text('{"schema_version":"x","schema_version":"y"}')
    import hashlib

    binding = {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    monkeypatch.setattr(
        evidence, "AUTHORIZED", {(modules.ROLE, str(path.resolve()), binding["sha256"])}
    )
    with pytest.raises(sizing.SizingHold):
        modules.build_ledger("CASE-TEST", chain["items"], chain["base"], binding)


def test_before_ha1_rejects_legacy_without_ledger() -> None:
    with pytest.raises(sizing.SizingHold, match="LEDGER_REQUIRED_BEFORE_HA1"):
        sizing.verify_before_ha1(
            {"schema_version": "cabinet_sizing.auto.v0.2"},
            [],
            expected_case_id="CASE-TEST",
        )


@pytest.mark.parametrize("precision", [2, 6, 28])
def test_caller_precision_cannot_round_short_reserve_into_pass(
    chain: Any, monkeypatch: pytest.MonkeyPatch, precision: int
) -> None:
    shape(chain, "9.01", 90)
    with localcontext() as context:
        context.prec = precision
        with pytest.raises(sizing.SizingHold, match="HOLD_MODULE_RESERVE:DIN:modules"):
            calculate(chain, monkeypatch)
        assert context.prec == precision


def test_ledger_is_independent_of_caller_rounding_and_traps(
    chain: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    chain["data"]["boards"][0]["zones"][0]["capacity_modules"] = 7
    expected = calculate(chain, monkeypatch)
    with localcontext() as context:
        context.prec = 2
        context.rounding = ROUND_DOWN
        context.traps[Inexact] = True
        assert calculate(chain, monkeypatch) == expected
        assert context.prec == 2 and context.rounding == ROUND_DOWN
        assert context.traps[Inexact]


def test_duplicate_exact_sku_revision_is_ambiguous(
    chain: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    product = copy.deepcopy(chain["data"]["products"][0])
    product["id"] = "SECOND"
    chain["data"]["products"].append(product)
    with pytest.raises(sizing.SizingHold, match="AMBIGUOUS_SKU_REVISION"):
        calculate(chain, monkeypatch)


def test_required_gap_consumes_actual_resource(
    chain: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    shape(chain, 9, 90)
    chain["data"]["profiles"][0]["left_gap_mm"] = "0.01"
    with pytest.raises(sizing.SizingHold, match="HOLD_MODULE_RESERVE:DIN:mm"):
        calculate(chain, monkeypatch)


@pytest.mark.parametrize("revision", ["UNKNOWN", "TBD", "?"])
def test_unknown_revision_is_not_exact(
    chain: Any, monkeypatch: pytest.MonkeyPatch, revision: str
) -> None:
    chain["data"]["products"][0]["revision"] = revision
    with pytest.raises(sizing.SizingHold, match="EXACT_SKU_OR_REVISION"):
        calculate(chain, monkeypatch)


@pytest.mark.parametrize(
    "stage",
    [
        "missing",
        "before_phrase",
        "after_phrase",
        "publication",
        "wrong_mounting",
        "underbound",
        "success",
    ],
)
def test_real_builder_module_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    from test_build_confirmed_composition_from_preliminary_bundle import (
        builder,
        create_batch_bundle,
        fixed_now,
    )
    from test_cabinet_sizing import provision_auto

    root, _, decisions = create_batch_bundle(tmp_path)
    snapshot = builder.load_snapshot(
        builder.resolve_case_paths("CASE-TEST-001", canonical_root=root)
    )
    state = builder.apply_batch_decisions(
        snapshot,
        builder.load_decisions_input(decisions),
        case_id="CASE-TEST-001",
        automatic_cabinet=True,
    )
    request, _ = provision_auto(
        tmp_path,
        monkeypatch,
        "CASE-TEST-001",
        state.items,
        device_dimensions_mm=[1, 90, 1],
    )
    monkeypatch.setattr(modules, "build_sizing_report", NATIVE_BUILD)
    base = sizing.size_composition("CASE-TEST-001", state.items, request)
    for item, selection in zip(state.items, base["items"], strict=True):
        item["cabinet"] = selection["cabinet"]
    binding, _ = provision_modules(
        tmp_path, monkeypatch, "CASE-TEST-001", state.items, base
    )
    module_data = json.loads(Path(binding["path"]).read_text())
    base = modules.size_base("CASE-TEST-001", state.items, request, binding)
    for item, selection in zip(state.items, base["items"], strict=True):
        item["cabinet"] = selection["cabinet"]
    module_data["composition_sha256"] = modules.composition_hash(state.items)
    module_data["sizing_sha256"] = sizing.digest(base)
    module_data["boards"][0]["cabinet_sha256"] = sizing.digest(
        state.items[0]["cabinet"]
    )
    for product in module_data["products"]:
        product.update(nominal_modules=9, width_mm=90)
    for profile in module_data["profiles"]:
        profile.update(nominal_modules=9, width_mm=90)
    module_data["boards"][0]["zones"][0].update(capacity_modules=20, capacity_mm=200)
    if stage == "wrong_mounting":
        for product in module_data["products"]:
            product.update(
                mounting="PANEL", nominal_modules=None, width_mm=None, area_mm2=1
            )
        for profile in module_data["profiles"]:
            profile.update(
                nominal_modules=None, width_mm=None, area_mm2=1, allowed_zones=["PANEL"]
            )
        for group in module_data["boards"][0]["groups"]:
            group["zone_id"] = "PANEL"
    if stage == "underbound":
        for product in module_data["products"]:
            product["width_mm"] = 91
        for profile in module_data["profiles"]:
            profile["width_mm"] = 91
        module_data["boards"][0]["zones"][0]["capacity_mm"] = 220
    binding = repin(monkeypatch, Path(binding["path"]), module_data)
    request_path = tmp_path / "sizing.json"
    request_path.write_text(json.dumps(request))
    import hashlib

    prompts = []

    def drift() -> None:
        Path(binding["path"]).write_text("DRIFT")

    def output(text: str) -> None:
        if stage == "before_phrase" and "FINAL TECHNICAL" in text:
            drift()

    def ask(prompt: str) -> str:
        prompts.append(prompt)
        return "SYNTHETIC APPROVAL"

    if stage == "publication":

        def publication(**kwargs: Any) -> None:
            drift()
            kwargs["recheck"]()
            pytest.fail("publication recheck must HOLD")

        monkeypatch.setattr(builder, "publish_atomically", publication)
    result = builder.run_builder(
        case_id="CASE-TEST-001",
        confirmation_id="TEST",
        approval_channel="synthetic",
        canonical_root=root,
        decisions_json=decisions,
        cabinet_sizing_json=request_path,
        cabinet_sizing_sha256=hashlib.sha256(request_path.read_bytes()).hexdigest(),
        module_evidence_json=None if stage == "missing" else Path(binding["path"]),
        module_evidence_sha256=None if stage == "missing" else binding["sha256"],
        input_fn=ask,
        output_fn=output,
        approval_phrase="SYNTHETIC APPROVAL",
        now_fn=fixed_now,
        before_drift_check=drift if stage == "after_phrase" else None,
    )
    if stage == "success":
        assert result.status == "PASS", result.red_flags
        import validate_confirmed_composition_artifact as validator  # type: ignore[import-not-found]

        path = result.output_dir / builder.ARTIFACT_NAME
        artifact = json.loads(path.read_bytes())
        ledger = artifact["cabinet_sizing"]["module_ledger"]
        assert (
            ledger["items"][0]["reserve"]["DIN"]["measures"]["mm"]["free_percent"]
            == "10"
        )
        assert (
            validator.validate_confirmed_composition_artifact(
                path, before_human_approval_1=True, expected_case_id="CASE-TEST-001"
            ).status
            == "PASS"
        )
    else:
        assert result.status == "HOLD" and not result.output_created, result.red_flags
        if stage == "wrong_mounting":
            assert any("BASE_MOUNTING_CONFLICT" in flag for flag in result.red_flags)
        if stage == "underbound":
            assert any("BASE_FOOTPRINT_UNDERBOUND" in flag for flag in result.red_flags)
        assert len(prompts) == (
            0
            if stage in {"missing", "before_phrase", "wrong_mounting", "underbound"}
            else 1
        )
