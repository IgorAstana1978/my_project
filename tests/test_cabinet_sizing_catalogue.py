"""Expanded public contract; synthetic evidence never authorizes production."""

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import cabinet_catalogue as catalogue  # type: ignore[import-not-found]
import cabinet_sizing as sizing  # type: ignore[import-not-found]
import cabinet_sizing_catalogue as selector  # type: ignore[import-not-found]
import pytest
from test_cabinet_sizing_pragmatic import provision
from test_cabinet_sizing_selector import synthetic_record, synthetic_zone
from test_versioned_metal_source import synthetic_sources as synthetic_sources


def expanded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **kwargs: Any) -> Any:
    item, request = provision(tmp_path, monkeypatch, **kwargs)
    request["schema_version"] = "cabinet_sizing.catalogue_request.v0.1"
    return item, request


def record(
    code: str, family: str = "METAL", size: Any = None, issues: Any = None
) -> Any:
    return {
        "cabinet_code": code,
        "cabinet_label": code,
        "family": family,
        "row": 1,
        "dimensions_mm": size or [300, 300, 150],
        "source_issues": issues or [],
        "source": {"raw_dimension_values": size or [300, 300, 150]},
        "pricing_mapping_status": "UNVERIFIED_NEW_TECHNICAL_IDENTITY",
    }


def inject(monkeypatch: pytest.MonkeyPatch, records: Any) -> None:
    import cabinet_catalogue as catalogue  # type: ignore[import-not-found]

    monkeypatch.setattr(
        catalogue,
        "inventory",
        lambda **kwargs: {"records": records, "policy": "SYNTHETIC"},
    )


@pytest.mark.parametrize(
    "widths,expected,occupied,reason",
    [
        ([54] * 9, "PASS", "486", "DIN_CAPACITY_AND_TOTAL_RESERVE_PROVEN"),
        (["54.0001"] * 9, "NO_FIT", "486.0009", "DIN_TOTAL_RESERVE_INSUFFICIENT"),
        (["35.6"] * 13, "PASS", "462.8", "DIN_CAPACITY_AND_TOTAL_RESERVE_PROVEN"),
        ([200, 140, 140], "PASS", "480", "DIN_CAPACITY_AND_TOTAL_RESERVE_PROVEN"),
        ([110] * 4, "NO_FIT", "440", "DIN_ROW_CAPACITY_INSUFFICIENT"),
        ([217], "NO_FIT", "217", "DIN_ROW_CAPACITY_INSUFFICIENT"),
    ],
)
def test_v4_partial_capacity_uses_actual_widths_and_total_reserve(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    synthetic_sources: Any,
    widths: Any,
    expected: str,
    occupied: str,
    reason: str,
) -> None:
    outcome, _, _ = capacity_outcome(tmp_path, monkeypatch, synthetic_sources, widths)
    proof = outcome["din_capacity_assessment"]
    assert proof["status"] == expected and proof["reason"] == reason
    assert proof["occupied_mm"] == occupied
    assert proof["capacity_mm"] == "648" and proof["reserve_required_percent"] == "25"
    assert outcome["status"] == ("NO_FIT" if expected == "NO_FIT" else "UNKNOWN")
    assert (
        outcome["layout"] is None and outcome["physical_installation_status"] == "HOLD"
    )
    if expected == "PASS":
        from decimal import Decimal

        assert sum(Decimal(r["occupied_mm"]) for r in proof["rows"]) == Decimal(
            occupied
        )
        assert all(Decimal(r["occupied_mm"]) <= 216 for r in proof["rows"])
        assert sum(len(r["units"]) for r in proof["rows"]) == len(widths)
        assert (
            "HOLD_PHYSICAL_MOUNTING_DEPTH_INSTALLATION_IP_EVIDENCE_REQUIRED"
            in outcome["reasons"]
        )


def capacity_outcome(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    registry: Any,
    widths: Any,
    *,
    panel: bool = False,
    gap: bool = False,
    full_mount: bool = False,
    budget: bool = False,
) -> Any:
    import cabinet_sizing_catalogue as selector  # type: ignore[import-not-found]
    import cabinet_sizing_selector as exact  # type: ignore[import-not-found]

    records = [synthetic_record(str(i), size=[80, w, 30]) for i, w in enumerate(widths)]
    if gap:
        records[0]["pair_gap_mm"] = [0, 1]
    if panel:
        records.append(synthetic_record("P", mounting="PANEL", size=[90, 20, 30]))
    item = {
        "item_id": "I",
        "product_name": "synthetic",
        "quantity": 1,
        "components": [
            {
                "component_id": r["class_id"],
                "component_code": "TEST_" + r["class_id"],
                "quantity": 1,
            }
            for r in records
        ],
    }
    item, request = expanded(tmp_path, monkeypatch, item=item, records=records)
    request.update(
        schema_version="cabinet_sizing.catalogue_request.v0.4",
        metal_source=registry["2026.10.21"],
    )
    cab = record("CATALOGUE-KRN-ROW-64", "KRN", [540, 330, 100])
    cab["technical_binding"] = {"rail_count": 3}
    cab["din_capacity_binding"] = {
        "rail_count": 3,
        "rail_capacity_mm": 216,
        "total_capacity_mm": 648,
    }
    inject(monkeypatch, [cab])
    if full_mount:
        mount(tmp_path, monkeypatch, cab, width=300, rails=[40, 180, 320], height=400)
    if budget:

        class Exhausted(exact.Budget):
            def __init__(self) -> None:
                self.remaining = -1

        monkeypatch.setattr(selector.exact, "Budget", Exhausted)
    try:
        report = sizing.size_composition("CASE", [item], request)
        outcome = report["items"][0]["provenance"]["candidate_outcomes"][0]
    except sizing.SizingHold as held:
        assert held.details is not None, str(held)
        outcome = held.details["candidate_outcomes"][0]
    return outcome, item, request


@pytest.mark.parametrize(
    "mode",
    ["gap", "budget", "panel_pass", "panel_fail", "mount_fail", "mount_fragmentation"],
)
def test_v4_capacity_uncertainty_panel_and_full_mount_cannot_bypass_cap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    synthetic_sources: Any,
    mode: str,
) -> None:
    widths = (
        [110] * 4
        if mode in {"budget", "mount_fragmentation"}
        else [54] * (10 if mode.endswith("fail") else 9)
    )
    outcome, _, _ = capacity_outcome(
        tmp_path,
        monkeypatch,
        synthetic_sources,
        widths,
        panel=mode.startswith("panel"),
        gap=mode == "gap",
        budget=mode == "budget",
        full_mount=mode.startswith("mount"),
    )
    proof = outcome["din_capacity_assessment"]
    expected = (
        "UNKNOWN"
        if mode in {"gap", "budget"}
        else (
            "NO_FIT"
            if mode.endswith("fail") or mode == "mount_fragmentation"
            else "PASS"
        )
    )
    assert proof["status"] == expected
    assert outcome["status"] == ("NO_FIT" if expected == "NO_FIT" else "UNKNOWN")
    assert outcome["layout"] is None
    if mode.startswith("panel"):
        assert proof["panel_assessment"]["status"] == "UNKNOWN"
        assert proof["panel_assessment"]["unit_count"] == 1


def test_default_capacity_schema_is_v4(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, synthetic_sources: Any
) -> None:
    import cabinet_sizing_catalogue as selector  # type: ignore[import-not-found]

    item, _ = expanded(tmp_path, monkeypatch)
    assert selector.request_for("CASE", [item])["schema_version"] == (
        "cabinet_sizing.catalogue_request.v0.4"
    )


def test_construction_rail_count_cannot_supply_mounting_or_hide_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    item, request = expanded(tmp_path, monkeypatch)
    cab = record("KRN36", "KRN", [540, 330, 100])
    cab["technical_binding"] = {"rail_count": 3}
    inject(monkeypatch, [cab])
    with pytest.raises(sizing.SizingHold) as held:
        sizing.size_composition("CASE", [item], request)
    outcome = held.value.details["candidate_outcomes"][0]
    assert outcome["status"] == "UNKNOWN" and outcome["layout"] is None
    mount(tmp_path, monkeypatch, cab, rails=[40])
    with pytest.raises(sizing.SizingHold, match="HOLD_CATALOGUE_UNRESOLVED") as held:
        sizing.size_composition("CASE", [item], request)
    assert held.value.details["candidate_outcomes"][0]["reasons"] == [
        "HOLD_CONSTRUCTION_MOUNTING_RAIL_COUNT_CONFLICT"
    ]
    mount(tmp_path, monkeypatch, cab, rails=[40, 180, 320], height=400)
    report = sizing.size_composition("CASE", [item], request)
    assert report["items"][0]["provenance"]["candidate_outcomes"][0]["status"] == "FIT"


@pytest.mark.skipif(
    not catalogue.GENESIS_PATH.exists(),
    reason="Pinned local catalogue sources are not distributed with code",
)
def test_expanded_request_accounts_for_full_catalogue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    item, request = provision(tmp_path, monkeypatch)
    request["schema_version"] = "cabinet_sizing.catalogue_request.v0.1"
    with pytest.raises(sizing.SizingHold) as held:
        sizing.size_composition("CASE", [item], request)
    details: dict[str, Any] = getattr(held.value, "details", {})
    assert len(details.get("candidate_outcomes", [])) == 70
    assert {c["family"] for c in details["candidate_outcomes"]} == {
        "METAL",
        "KRN",
        "KRV",
    }
    assert any(
        c["row"] == 34 and c["status"] == "UNKNOWN"
        for c in details["candidate_outcomes"]
    )
    assert "frontier" in details and "first_missing" in details


def test_explicit_size_can_refute_unrelated_conflict_without_silent_repair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    item, request = expanded(
        tmp_path,
        monkeypatch,
        fact={"dimensions_status": "EXPLICIT", "dimensions_mm": [300, 300, 150]},
    )
    damaged = record(
        "DAMAGED",
        size=[700, 500, "=400"],
        issues=["HOLD_LABEL_DIMENSION_SOURCE_CONFLICT"],
    )
    damaged["dimensions_mm"] = None
    inject(monkeypatch, [record("EXACT"), damaged])
    report = sizing.size_composition("CASE", [item], request)
    selected = report["items"][0]
    assert selected["cabinet"]["cabinet_code"] == "EXACT"
    outcome = selected["provenance"]["candidate_outcomes"][1]
    assert outcome["status"] == "NO_FIT"
    assert outcome["source_issues"] == ["HOLD_LABEL_DIMENSION_SOURCE_CONFLICT"]


@pytest.mark.parametrize(
    "dimensions,compatible", [([300, 300, 150], True), ([70, 30, 20], False)]
)
def test_explicit_source_hwd_integer_string_equivalence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    dimensions: Any,
    compatible: bool,
) -> None:
    outcomes = []
    for index, raw_dimensions in enumerate((dimensions, [str(v) for v in dimensions])):
        source_root = tmp_path / str(index)
        source_root.mkdir()
        item, request = expanded(
            source_root,
            monkeypatch,
            fact={"dimensions_status": "EXPLICIT", "dimensions_mm": raw_dimensions},
        )
        inject(monkeypatch, [record("EXACT"), record("BIGGER", size=[400, 400, 200])])
        if compatible:
            selected = sizing.size_composition("CASE", [item], request)["items"][0]
            assert (
                selected["provenance"]["source_fact"]["dimensions_mm"] == raw_dimensions
            )
            outcomes.append(selected["cabinet"])
        else:
            with pytest.raises(
                sizing.SizingHold, match="HOLD_SOURCE_DIMENSIONS_INCOMPATIBLE"
            ) as held:
                sizing.size_composition("CASE", [item], request)
            outcomes.append(
                [
                    (c["cabinet_code"], c["status"], c["reasons"])
                    for c in held.value.details["candidate_outcomes"]
                ]
            )
    assert outcomes[0] == outcomes[1]
    if compatible:
        assert outcomes[0]["cabinet_code"] == "EXACT"


@pytest.mark.parametrize("version", [1, 2, 3, 4])
def test_new_report_builder_summary_names_all_families(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    synthetic_sources: Any,
    version: int,
) -> None:
    import build_confirmed_composition_from_preliminary_bundle as builder  # type: ignore[import-not-found]

    item, request = expanded(tmp_path, monkeypatch)
    if version > 1:
        request.update(
            schema_version=f"cabinet_sizing.catalogue_request.v0.{version}",
            metal_source=synthetic_sources["2026.10.21"],
        )
    inject(monkeypatch, [record("SMALL")])
    report = sizing.size_composition("CASE", [item], request)
    state = builder.classify_composition({"items": [item]}, automatic_cabinet=True)
    state.cabinet_sizing = report
    state.items[0]["cabinet"] = report["items"][0]["cabinet"]
    text = builder.render_final_summary(
        case_id="CASE", confirmation_id="TEST", state=state
    )
    assert "ПРЕДВАРИТЕЛЬНЫЙ" in text and "METAL/KRN/KRV" in text
    assert "IP" in text and "не проверен" in text


def test_source_change_during_comparison_is_not_a_valid_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cabinet_sizing_catalogue as expanded_selector  # type: ignore[import-not-found]

    item, request = expanded(tmp_path, monkeypatch)
    inject(monkeypatch, [record("SMALL")])
    original = expanded_selector.candidate

    def drifting(*args: Any) -> Any:
        result = original(*args)
        path = Path(request["source_facts"]["I"]["path"])
        path.write_bytes(path.read_bytes() + b" ")
        return result

    monkeypatch.setattr(expanded_selector, "candidate", drifting)
    with pytest.raises(sizing.SizingHold, match="HOLD_SOURCE_SHA_DRIFT"):
        sizing.size_composition("CASE", [item], request)


def test_mounting_source_change_during_comparison_is_hold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cabinet_catalogue as catalogue  # type: ignore[import-not-found]
    import cabinet_sizing_catalogue as expanded_selector  # type: ignore[import-not-found]

    item, request = expanded(tmp_path, monkeypatch)
    cab = record("KRN", "KRN")
    inject(monkeypatch, [cab])
    mount(tmp_path, monkeypatch, cab)
    original = expanded_selector.candidate

    def drifting(*args: Any) -> Any:
        result = original(*args)
        path = Path(catalogue.MOUNTING_SOURCES["KRN"]["path"])
        path.write_bytes(path.read_bytes() + b" ")
        return result

    monkeypatch.setattr(expanded_selector, "candidate", drifting)
    with pytest.raises(sizing.SizingHold, match="HOLD_SOURCE_SHA_DRIFT"):
        sizing.size_composition("CASE", [item], request)


def mount(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cab: Any,
    width: Any = 81,
    rails: Any = None,
    height: Any = 200,
) -> None:
    import cabinet_catalogue as catalogue  # type: ignore[import-not-found]
    import cabinet_sizing_evidence as evidence  # type: ignore[import-not-found]

    zone = synthetic_zone(width=width, height=height)
    zone["rails_mm"] = rails or [40]
    data = {
        "cabinet_code": cab["cabinet_code"],
        "dimensions_mm": cab["dimensions_mm"],
        "mounting_kinds": ["DIN"],
        "installation": "SURFACE",
        "ip": [3, 0],
        "shock_class": "I",
        "zones": [zone],
    }
    path = tmp_path / (cab["cabinet_code"] + ".json")
    path.write_text(json.dumps(data), encoding="utf-8")
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(
        catalogue,
        "MOUNTING_SOURCES",
        dict(
            catalogue.MOUNTING_SOURCES,
            **{cab["cabinet_code"]: {"path": str(path), "sha256": sha}},
        ),
    )
    monkeypatch.setattr(
        evidence,
        "AUTHORIZED",
        evidence.AUTHORIZED | {("catalogue_mounting", str(path.resolve()), sha)},
    )


@pytest.mark.parametrize("family", ["METAL", "KRN", "KRV"])
def test_no_family_priority_with_proven_reusable_din_capacity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, family: str
) -> None:
    item, request = expanded(tmp_path, monkeypatch)
    small = record("SMALL", family)
    large = [
        record("LARGE_" + kind, kind, [400, 400, 200])
        for kind in ("METAL", "KRN", "KRV")
    ]
    inject(monkeypatch, [*large, small])
    for cab in [small, *large]:
        mount(tmp_path, monkeypatch, cab)
    report = sizing.size_composition("CASE", [item], request)
    chosen = report["items"][0]
    assert chosen["cabinet"]["cabinet_code"] == "SMALL"
    assert chosen["cabinet"]["cabinet_type"] == family
    assert chosen["layout"]["reserve"]["DIN"]["occupied_mm"] == "60.75"
    assert chosen["layout"]["reserve"]["DIN"]["total_usable_mm"] == "81"
    assert "module" not in json.dumps(chosen["layout"])
    item["cabinet"] = chosen["cabinet"]
    sizing.verify_report(
        report, [item], expected_case_id="CASE", before_human_approval_1=True
    )
    changed = copy.deepcopy(report)
    changed["items"][0]["cabinet"]["dimensions_mm"][0] += 1
    with pytest.raises(sizing.SizingHold, match="HOLD_SIZING_REPORT_DRIFT"):
        sizing.verify_report(
            changed, [item], expected_case_id="CASE", before_human_approval_1=True
        )


@pytest.mark.parametrize("width,passes", [(81, True), ("80.999", False)])
def test_actual_width_reserve_boundary_without_nominal_suffix_inference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, width: Any, passes: bool
) -> None:
    item, request = expanded(tmp_path, monkeypatch)
    cab = record("KRN_192_IS_ONLY_A_NAME", "KRN")
    inject(monkeypatch, [cab])
    mount(tmp_path, monkeypatch, cab, width)
    if passes:
        assert (
            sizing.size_composition("CASE", [item], request)["items"][0]["cabinet"][
                "cabinet_code"
            ]
            == cab["cabinet_code"]
        )
    else:
        with pytest.raises(
            sizing.SizingHold, match="HOLD_NO_FITTING_CATALOGUE_CABINET"
        ) as held:
            sizing.size_composition("CASE", [item], request)
        assert held.value.details["candidate_outcomes"][0]["status"] == "NO_FIT"


@pytest.mark.parametrize(
    "kind", ["equal", "incomparable", "unknown", "too_small_unknown"]
)
def test_equal_incomparable_and_unknown_alternatives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    item, request = expanded(tmp_path, monkeypatch)
    cabs = [
        record("FIRST", size=[300, 400, 150]),
        record("SECOND", size=[400, 300, 150]),
    ]
    if kind == "equal":
        cabs[1]["dimensions_mm"] = cabs[0]["dimensions_mm"]
    elif kind in {"unknown", "too_small_unknown"}:
        cabs[1] = record(
            "KRV_72", "KRV", [200, 200, 125] if kind == "unknown" else [70, 20, 20]
        )
    inject(monkeypatch, cabs)
    if kind == "too_small_unknown":
        report = sizing.size_composition("CASE", [item], request)
        assert report["items"][0]["cabinet"]["cabinet_code"] == "FIRST"
    else:
        with pytest.raises(
            sizing.SizingHold,
            match=(
                "HOLD_CATALOGUE_UNRESOLVED"
                if kind == "unknown"
                else "HOLD_SMALLEST_CABINET_AMBIGUOUS"
            ),
        ) as held:
            sizing.size_composition("CASE", [item], request)
        assert len(held.value.details["candidate_outcomes"]) == 2
        assert len(held.value.details["frontier"]) == 2 if kind != "unknown" else True


def test_explicit_never_enlarges_and_prior_approval_never_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    item, request = expanded(
        tmp_path,
        monkeypatch,
        fact={"dimensions_status": "EXPLICIT", "dimensions_mm": [70, 30, 20]},
    )
    inject(monkeypatch, [record("EXPLICIT", size=[70, 30, 20]), record("BIGGER")])
    with pytest.raises(sizing.SizingHold, match="HOLD_SOURCE_DIMENSIONS_INCOMPATIBLE"):
        sizing.size_composition("CASE", [item], request)
    item, request = expanded(
        tmp_path,
        monkeypatch,
        fact={
            "prior_approval": {
                "status": "APPROVED",
                "cabinet_code": "METAL-600X400X250-D28",
                "dimensions_mm": [600, 400, 250],
            }
        },
    )
    inject(monkeypatch, [record("SMALLER")])
    with pytest.raises(
        sizing.SizingHold, match="HOLD_CABINET_CHANGE_REQUIRES_NEW_HUMAN_APPROVAL"
    ):
        sizing.size_composition("CASE", [item], request)


def test_real_default_cli_expands_all_three_families_and_preserves_explicit_replay(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import cabinet_sizing_evidence as evidence  # type: ignore[import-not-found]
    import cabinet_sizing_pragmatic as pragmatic  # type: ignore[import-not-found]

    path = (
        Path("C:/Users/IgorN/Documents/production_ai_cases/telegram-employee-cases")
        / evidence.WU15_CASE
        / "preliminary-composition-draft.json"
    )
    if not path.exists():
        pytest.skip("Pinned local WU15 draft is not distributed")
    items = json.loads(path.read_bytes())["items"]
    output = tmp_path / "composition.json"
    output.write_text(json.dumps({"items": items}), encoding="utf-8")
    assert (
        sizing.main(
            ["--case-id", evidence.WU15_CASE, "--composition-json", str(output)]
        )
        == 2
    )
    results = json.loads(capsys.readouterr().out)["results"]
    assert len(results) == 3
    assert (
        sum(sum(c.get("quantity_guess", 0) for c in i["components"]) for i in items)
        == 46
    )
    for item, result in zip(items, results, strict=True):
        assert result["status"] == "HOLD"
        assert len(result["details"]["candidate_outcomes"]) == 70
        assert result["details"]["apparatus_sha256"] == sizing.apparatus_hash(item)
        assert result["details"]["physical_installation_status"] == "HOLD"
    old_request = pragmatic.request_for(evidence.WU15_CASE, [items[0]])
    old = sizing.size_composition(evidence.WU15_CASE, [items[0]], old_request)
    assert old == pragmatic.select(evidence.WU15_CASE, [items[0]], old_request)
    assert old["items"][0]["cabinet"]["dimensions_mm"] == [600, 400, 250]


def builder_request(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, items: Any) -> Any:
    import cabinet_sizing_evidence as evidence  # type: ignore[import-not-found]
    from test_cabinet_sizing import provision_auto

    request, _ = provision_auto(tmp_path, monkeypatch, "CASE-TEST-001", items)
    request["schema_version"] = "cabinet_sizing.catalogue_request.v0.1"
    del request["catalogue"]
    for binding in request["source_facts"].values():
        path = Path(binding["path"])
        fact = json.loads(path.read_bytes())
        fact.update(dimensions_status="ABSENT", dimensions_mm=None, installation=None)
        path.write_text(json.dumps(fact), encoding="utf-8")
        binding["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        monkeypatch.setattr(
            evidence,
            "AUTHORIZED",
            evidence.AUTHORIZED
            | {("pragmatic_source_fact", str(path.resolve()), binding["sha256"])},
        )
    return request


@pytest.mark.parametrize("stage", ["before_phrase", "after_phrase", "publication"])
@pytest.mark.parametrize("current_source", [False, True, "technical", "capacity"])
def test_builder_expanded_rechecks_every_approval_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    current_source: bool | str,
    synthetic_sources: Any,
) -> None:
    from test_build_confirmed_composition_from_preliminary_bundle import (
        builder,
        create_batch_bundle,
        fixed_now,
    )

    root, _, decisions_path = create_batch_bundle(tmp_path)
    decisions = json.loads(decisions_path.read_bytes())
    for entry in decisions["items"]:
        entry["cabinet"].pop("code")
        entry["cabinet"].pop("label")
    decisions_path.write_text(json.dumps(decisions), encoding="utf-8")
    snapshot = builder.load_snapshot(
        builder.resolve_case_paths("CASE-TEST-001", canonical_root=root)
    )
    state = builder.apply_batch_decisions(
        snapshot,
        builder.load_decisions_input(decisions_path),
        case_id="CASE-TEST-001",
        automatic_cabinet=True,
    )
    request = builder_request(tmp_path, monkeypatch, state.items)
    if current_source:
        request.update(
            schema_version=(
                "cabinet_sizing.catalogue_request.v0.4"
                if current_source == "capacity"
                else (
                    "cabinet_sizing.catalogue_request.v0.3"
                    if current_source == "technical"
                    else "cabinet_sizing.catalogue_request.v0.2"
                )
            ),
            metal_source=synthetic_sources["2026.10.21"],
        )
    inject(monkeypatch, [record("NEW_TECHNICAL_IDENTITY")])
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request), encoding="utf-8")
    prompts = []

    def drift() -> None:
        source = Path(
            request["metal_source"]["path"]
            if current_source
            else request["devices"]["path"]
        )
        source.write_bytes(source.read_bytes() + b" ")

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
            pytest.fail("publication must have stopped on changed sizing source")

        monkeypatch.setattr(builder, "publish_atomically", publication)
    result = builder.run_builder(
        case_id="CASE-TEST-001",
        confirmation_id="SYNTHETIC",
        approval_channel="synthetic",
        canonical_root=root,
        decisions_json=decisions_path,
        cabinet_sizing_json=path,
        cabinet_sizing_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        approval_phrase="SYNTHETIC APPROVAL",
        input_fn=ask,
        output_fn=output,
        now_fn=fixed_now,
        before_drift_check=drift if stage == "after_phrase" else None,
    )
    assert result.status == "HOLD" and not result.output_created
    assert len(prompts) == (0 if stage == "before_phrase" else 1)
    assert not (root / "CASE-TEST-001" / "confirmed").exists()


@pytest.mark.parametrize("current_source", [False, True, "technical", "capacity"])
def test_confirmed_validator_recomputes_expanded_schema_before_a1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    current_source: bool | str,
    synthetic_sources: Any,
) -> None:
    import cabinet_sizing_module_accounting as modules  # type: ignore[import-not-found]
    import validate_confirmed_composition_artifact as validator  # type: ignore[import-not-found]
    from module_accounting_fixtures import provision_modules

    data = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "examples/confirmed_composition_artifact.example.json"
        ).read_bytes()
    )
    request = builder_request(tmp_path, monkeypatch, data["items"])
    if current_source:
        request.update(
            schema_version=(
                "cabinet_sizing.catalogue_request.v0.4"
                if current_source == "capacity"
                else (
                    "cabinet_sizing.catalogue_request.v0.3"
                    if current_source == "technical"
                    else "cabinet_sizing.catalogue_request.v0.2"
                )
            ),
            metal_source=synthetic_sources["2026.10.21"],
        )
    inject(monkeypatch, [record("NEW_TECHNICAL_IDENTITY")])
    report = sizing.size_composition("CASE-TEST-001", data["items"], request)
    data.update(case_id="CASE-TEST-001", cabinet_sizing=report)
    for item, selected in zip(data["items"], report["items"], strict=True):
        item["cabinet"] = selected["cabinet"]
    module_source, _ = provision_modules(
        tmp_path, monkeypatch, "CASE-TEST-001", data["items"], report
    )
    report = modules.build_sizing_report(
        "CASE-TEST-001", data["items"], report, module_source
    )
    data["cabinet_sizing"] = report
    path = tmp_path / "confirmed.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    checked = validator.validate_confirmed_composition_artifact(
        path, before_human_approval_1=True, expected_case_id="CASE-TEST-001"
    )
    assert checked.status == "PASS", checked.red_flags
    report["base_report"]["items"][0]["provenance"]["candidate_outcomes"][0][
        "status"
    ] = "UNKNOWN"
    path.write_text(json.dumps(data), encoding="utf-8")
    checked = validator.validate_confirmed_composition_artifact(
        path, before_human_approval_1=True, expected_case_id="CASE-TEST-001"
    )
    assert checked.status == "FAIL"
    assert any("HOLD_SIZING_REPORT_DRIFT" in flag for flag in checked.red_flags)


def test_missing_mount_rows_are_unknown_and_request_cannot_supply_geometry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    item, request = expanded(tmp_path, monkeypatch)
    cab = record("KRV_72", "KRV")
    inject(monkeypatch, [cab])
    mount(tmp_path, monkeypatch, cab)
    import cabinet_catalogue as catalogue  # type: ignore[import-not-found]
    import cabinet_sizing_evidence as evidence  # type: ignore[import-not-found]

    binding = catalogue.MOUNTING_SOURCES[cab["cabinet_code"]]
    path = Path(binding["path"])
    data = json.loads(path.read_bytes())
    data["zones"][0]["rails_mm"] = []
    path.write_text(json.dumps(data), encoding="utf-8")
    binding["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(
        evidence,
        "AUTHORIZED",
        evidence.AUTHORIZED
        | {("catalogue_mounting", str(path.resolve()), binding["sha256"])},
    )
    with pytest.raises(sizing.SizingHold, match="HOLD_CATALOGUE_UNRESOLVED") as held:
        sizing.size_composition("CASE", [item], request)
    assert held.value.details["candidate_outcomes"][0]["status"] == "UNKNOWN"
    request["catalogue"] = {"cabinet": cab}
    with pytest.raises(sizing.SizingHold, match="HOLD_PRAGMATIC_REQUEST_SCHEMA"):
        sizing.size_composition("CASE", [item], request)


def quote_request(request: Any, registry: Any, choices: Any) -> Any:
    return dict(
        request,
        schema_version=selector.QUOTE_REQUEST_SCHEMA,
        metal_source=registry["2026.10.21"],
        quote_choices=choices,
    )


@pytest.mark.parametrize("kind", ["unknown", "equal", "incomparable", "larger"])
def test_quote_choice_is_checked_without_claiming_minimality(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, synthetic_sources: Any, kind: str
) -> None:
    item, request = expanded(tmp_path, monkeypatch)
    second = record("SECOND", size=[300, 400, 150])
    if kind == "unknown":
        second = record("SECOND", "KRV")
    elif kind == "incomparable":
        second["dimensions_mm"] = second["source"]["raw_dimension_values"] = [
            400,
            300,
            150,
        ]
    elif kind == "larger":
        second["dimensions_mm"] = second["source"]["raw_dimension_values"] = [
            200,
            300,
            150,
        ]
    inject(monkeypatch, [record("FIRST", size=[300, 400, 150]), second])
    request = quote_request(request, synthetic_sources, {"I": "FIRST"})
    report = sizing.size_composition("CASE", [item], request)
    selection = report["items"][0]
    assert report["schema_version"] == selector.QUOTE_SCHEMA
    assert selection["engineering_scope"] == "QUOTE_PREPARATION"
    assert selection["calculation_status"] == "PASS"
    assert (
        selection["physical_fit_status"]
        == selection["minimality_status"]
        == ("NOT_VERIFIED")
    )
    assert selection["cabinet"]["cabinet_code"] == "FIRST"
    assert "FIRST" in selection["provenance"]["quote_candidates"]
    if kind == "unknown":
        other = selection["provenance"]["candidate_outcomes"][1]
        assert other["status"] == "UNKNOWN"
        assert other["quote_assessment"]["calculation_status"] == "HOLD"
    item["cabinet"] = selection["cabinet"]
    with pytest.raises(
        sizing.SizingHold, match="HOLD_MODULE_LEDGER_REQUIRED_FOR_QUOTE"
    ):
        sizing.verify_report(report, [item], expected_case_id="CASE")
    with pytest.raises(sizing.SizingHold, match="HOLD_MODULE_LEDGER_REQUIRED"):
        sizing.verify_before_ha1(report, [item], expected_case_id="CASE")


def test_quote_discovery_evaluates_candidates_without_selecting_or_approving(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, synthetic_sources: Any
) -> None:
    item, request = expanded(tmp_path, monkeypatch)
    monkeypatch.setattr(selector.planning, "request_for", lambda *args: request)
    inject(
        monkeypatch,
        [record("FIT"), record("UNKNOWN", "KRV"), record("SMALL", size=[1, 1, 1])],
    )
    proposed = selector.quote_request_for("CASE", [item])
    assert proposed["quote_choices"] == {}
    with pytest.raises(sizing.SizingHold, match="HOLD_QUOTE_CHOICE_REQUIRED") as held:
        sizing.size_composition("CASE", [item], proposed)
    assert held.value.details["quote_candidates"] == ["FIT"]
    assert "cabinet" not in held.value.details
    assert selector.request_for("CASE", [item])["schema_version"] == (
        selector.CURRENT_REQUEST_SCHEMA
    )


@pytest.mark.parametrize(
    "mode", ["panel", "gap", "budget", "overflow", "mount_fail", "ok"]
)
def test_quote_capacity_requires_complete_calculational_proof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, synthetic_sources: Any, mode: str
) -> None:
    _, item, request = capacity_outcome(
        tmp_path,
        monkeypatch,
        synthetic_sources,
        (
            [110] * 4
            if mode == "budget"
            else [217] if mode in {"overflow", "mount_fail"} else [54] * 9
        ),
        panel=mode == "panel",
        gap=mode == "gap",
        budget=mode == "budget",
        full_mount=mode == "mount_fail",
    )
    request = quote_request(request, synthetic_sources, {"I": "CATALOGUE-KRN-ROW-64"})
    if mode != "ok":
        with pytest.raises(sizing.SizingHold, match="HOLD_QUOTE_CHOICE_CALCULATION"):
            sizing.size_composition("CASE", [item], request)
        return
    selection = sizing.size_composition("CASE", [item], request)["items"][0]
    assert selection["calculation_status"] == "PASS"
    assert selection["provenance"]["candidate_outcomes"][0]["status"] == "UNKNOWN"
    assert selection["layout"]["din_capacity_assessment"]["capacity_only"] is True
    assert selection["physical_fit_status"] == "NOT_VERIFIED"


@pytest.mark.parametrize(
    "fault,reason",
    [
        ("identity", "HOLD_QUOTE_CHOICE_IDENTITY"),
        ("duplicate_identity", "HOLD_QUOTE_CHOICE_IDENTITY"),
        ("no_fit", "HOLD_QUOTE_CHOICE_CALCULATION"),
        ("source_gap", "HOLD_QUOTE_CHOICE_CALCULATION"),
        ("source_hwd", "HOLD_QUOTE_CHOICE_CALCULATION"),
        ("prior", "HOLD_CABINET_CHANGE_REQUIRES_NEW_HUMAN_APPROVAL"),
        ("extra_item", "HOLD_QUOTE_CHOICE_SCHEMA_OR_COVERAGE"),
        ("flag", "HOLD_QUOTE_CHOICE_SCHEMA_OR_COVERAGE"),
        ("injected_dimensions", "HOLD_PRAGMATIC_REQUEST_SCHEMA"),
    ],
)
def test_quote_choice_cannot_supply_authority_or_override_constraints(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    synthetic_sources: Any,
    fault: str,
    reason: str,
) -> None:
    fact: Any = None
    if fault == "source_hwd":
        fact = {"dimensions_status": "EXPLICIT", "dimensions_mm": [70, 30, 20]}
    elif fault == "prior":
        fact = {
            "prior_approval": {
                "status": "APPROVED",
                "cabinet_code": "METAL-600X400X250-D28",
                "dimensions_mm": [600, 400, 250],
            }
        }
    item, request = expanded(tmp_path, monkeypatch, **({"fact": fact} if fact else {}))
    cabs = [record("CHOSEN")]
    if fault == "duplicate_identity":
        cabs.append(record("CHOSEN"))
    elif fault == "no_fit":
        cabs = [record("CHOSEN", size=[1, 1, 1])]
    elif fault == "source_gap":
        cabs[0]["source_issues"] = ["HOLD_LABEL_DIMENSION_SOURCE_CONFLICT"]
    inject(monkeypatch, cabs)
    choices: Any = {"I": "ABSENT" if fault == "identity" else "CHOSEN"}
    if fault == "extra_item":
        choices["EXTRA"] = "CHOSEN"
    elif fault == "flag":
        choices["I"] = {"cabinet_code": "CHOSEN", "approved": True}
    request = quote_request(request, synthetic_sources, choices)
    if fault == "injected_dimensions":
        request["dimensions_mm"] = [999, 999, 999]
    with pytest.raises(sizing.SizingHold, match=reason):
        sizing.size_composition("CASE", [item], request)


@pytest.mark.parametrize(
    "tamper", ["status", "minimality", "physical", "scope", "choice", "source"]
)
def test_quote_report_recompute_rejects_tamper_and_source_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, synthetic_sources: Any, tamper: str
) -> None:
    item, request = expanded(tmp_path, monkeypatch)
    inject(monkeypatch, [record("FIRST"), record("SECOND")])
    request = quote_request(request, synthetic_sources, {"I": "FIRST"})
    import cabinet_sizing_module_accounting as modules  # type: ignore[import-not-found]
    from module_accounting_fixtures import provision_modules, repin

    base = sizing.size_composition("CASE", [item], request)
    item["cabinet"] = base["items"][0]["cabinet"]
    binding, data = provision_modules(tmp_path, monkeypatch, "CASE", [item], base)
    base = modules.size_base("CASE", [item], request, binding)
    data["sizing_sha256"] = sizing.digest(base)
    binding = repin(monkeypatch, Path(binding["path"]), data)
    report = modules.build_sizing_report("CASE", [item], base, binding)
    sizing.verify_report(report, [item], expected_case_id="CASE")
    if tamper == "choice":
        report["base_report"]["sources"]["request"]["quote_choices"]["I"] = "SECOND"
    elif tamper == "source":
        path = Path(request["devices"]["path"])
        path.write_bytes(path.read_bytes() + b" ")
    else:
        field = {
            "status": "calculation_status",
            "minimality": "minimality_status",
            "physical": "physical_fit_status",
            "scope": "engineering_scope",
        }[tamper]
        report["base_report"]["items"][0][field] = "FORGED"
    with pytest.raises(
        sizing.SizingHold, match="HOLD_SIZING_REPORT_DRIFT|HOLD_SOURCE_SHA_DRIFT"
    ):
        sizing.verify_report(report, [item], expected_case_id="CASE")


@pytest.mark.parametrize(
    "stage",
    [
        "success",
        "wrong_phrase",
        "missing",
        "before_phrase",
        "after_phrase",
        "publication",
    ],
)
def test_quote_native_ha1_boundaries_and_calculator_transition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, synthetic_sources: Any, stage: str
) -> None:
    import cabinet_sizing_module_accounting as modules  # type: ignore[import-not-found]
    import validate_confirmed_composition_artifact as validator  # type: ignore[import-not-found]
    from module_accounting_fixtures import NATIVE_BUILD, provision_modules, repin
    from test_build_confirmed_composition_from_preliminary_bundle import (
        builder,
        create_batch_bundle,
        fixed_now,
    )

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
    request = quote_request(
        builder_request(tmp_path, monkeypatch, state.items),
        synthetic_sources,
        {i["item_id"]: "CATALOGUE-METAL-ROW-22" for i in state.items},
    )
    inject(monkeypatch, [record("CATALOGUE-METAL-ROW-22"), record("UNKNOWN", "KRV")])
    monkeypatch.setattr(modules, "build_sizing_report", NATIVE_BUILD)
    base = sizing.size_composition("CASE-TEST-001", state.items, request)
    for item, selection in zip(state.items, base["items"], strict=True):
        item["cabinet"] = selection["cabinet"]
    binding, data = provision_modules(
        tmp_path, monkeypatch, "CASE-TEST-001", state.items, base
    )
    base = modules.size_base("CASE-TEST-001", state.items, request, binding)
    data["sizing_sha256"] = sizing.digest(base)
    binding = repin(monkeypatch, Path(binding["path"]), data)
    request_path = tmp_path / "quote-request.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")
    prompts: list[str] = []
    reviews: list[str] = []

    def drift() -> None:
        path = Path(binding["path"])
        path.write_bytes(path.read_bytes() + b" ")

    def output(text: str) -> None:
        reviews.append(text)
        if stage == "before_phrase" and "FINAL TECHNICAL" in text:
            drift()

    def ask(prompt: str) -> str:
        prompts.append(prompt)
        return "WRONG" if stage == "wrong_phrase" else "SYNTHETIC APPROVAL"

    if stage == "publication":

        def publication(**kwargs: Any) -> None:
            drift()
            kwargs["recheck"]()
            pytest.fail("publication must HOLD on drift")

        monkeypatch.setattr(builder, "publish_atomically", publication)
    kwargs = dict(
        case_id="CASE-TEST-001",
        confirmation_id="TEST-QUOTE",
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
    result = builder.run_builder(**kwargs)
    if stage != "success":
        assert result.status == (
            "FAIL" if stage == "wrong_phrase" else "HOLD"
        ), result.red_flags
        assert not result.output_created
        assert len(prompts) == (0 if stage in {"missing", "before_phrase"} else 1)
        assert not (root / "CASE-TEST-001" / "confirmed").exists()
        return
    assert result.status == "PASS", result.red_flags
    path = result.output_dir / builder.ARTIFACT_NAME
    artifact = json.loads(path.read_bytes())
    assert (
        validator.validate_confirmed_composition_artifact(
            path, before_human_approval_1=True, expected_case_id="CASE-TEST-001"
        ).status
        == "PASS"
    )
    assert artifact["safety"]["production_authorized"] is False
    assert artifact["safety"]["price_approved_by_igor"] is False
    review = "\n".join(reviews)
    receipt = (result.output_dir / builder.RECEIPT_NAME).read_text(encoding="utf-8")
    assert "Human Approval: REQUIRED" in review
    assert "Human Approval: recorded" in receipt
    for text in (review, receipt):
        assert "QUOTE_PREPARATION" in text
        assert "calculation_status=PASS" in text
        assert "Physical FIT=NOT_VERIFIED" in text and "minimality=NOT_VERIFIED" in text
    before = path.read_bytes()
    repeated = builder.run_builder(**kwargs)
    assert repeated.status == "FAIL" and not repeated.output_created
    assert any("exists" in flag for flag in repeated.red_flags)
    assert path.read_bytes() == before
    import build_price_calculator_input_draft_from_confirmed_composition as pricing  # type: ignore[import-not-found]

    output_path = tmp_path / "synthetic-calculator-input.json"
    calculated = pricing.build_price_calculator_input_draft(path, output_path)
    assert calculated.status == "PASS", calculated.red_flags
    payload = json.loads(output_path.read_bytes())
    assert payload["safety"]["price_calculation_executed"] is False
    assert payload["safety"]["sending_authorized"] is False
    assert payload["safety"]["production_authorized"] is False


def test_quote_cli_projects_choices_and_rejects_extra_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    synthetic_sources: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "examples/confirmed_composition_artifact.example.json"
        ).read_bytes()
    )
    items = [copy.deepcopy(data["items"][0]) for _ in range(2)]
    items[1]["item_id"] = "SECOND-ITEM"
    request = quote_request(
        builder_request(tmp_path, monkeypatch, items),
        synthetic_sources,
        {items[0]["item_id"]: "TEST-A", items[1]["item_id"]: "TEST-B"},
    )
    inject(monkeypatch, [record("TEST-A"), record("TEST-B")])
    composition = tmp_path / "composition.json"
    composition.write_text(json.dumps({"items": items}), encoding="utf-8")
    path = tmp_path / "request.json"

    def run() -> int:
        path.write_text(json.dumps(request), encoding="utf-8")
        return int(
            sizing.main(
                [
                    "--case-id",
                    "CASE-TEST-001",
                    "--composition-json",
                    str(composition),
                    "--request-json",
                    str(path),
                    "--request-sha256",
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                ]
            )
        )

    assert run() == 0
    result = json.loads(capsys.readouterr().out)
    assert len(result["results"]) == 2
    for entry in result["results"]:
        assert entry["status"] == "PROPOSED"
        assert set(entry["report"]["sources"]["quote_choices"]) == {entry["item_id"]}
        assert (
            entry["report"]["items"][0]["cabinet"]["cabinet_code"]
            == request["quote_choices"][entry["item_id"]]
        )
    del request["quote_choices"][items[1]["item_id"]]
    assert run() == 2
    result = json.loads(capsys.readouterr().out)
    assert result["results"][0]["status"] == "PROPOSED"
    assert result["results"][1]["first_missing"] == "HOLD_QUOTE_CHOICE_REQUIRED"
    assert result["results"][1]["details"]["quote_candidates"] == ["TEST-A", "TEST-B"]
    request["quote_choices"]["EXTRA"] = "TEST-A"
    assert run() == 2
    assert "HOLD_QUOTE_CHOICE_SCHEMA_OR_COVERAGE" in capsys.readouterr().out


def test_quote_bare_report_cannot_bypass_ledger_via_ordinary_confirmed_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, synthetic_sources: Any
) -> None:
    import build_price_calculator_input_draft_from_confirmed_composition as pricing  # type: ignore[import-not-found]
    import validate_confirmed_composition_artifact as validator  # type: ignore[import-not-found]

    data = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "examples/confirmed_composition_artifact.example.json"
        ).read_bytes()
    )
    request = quote_request(
        builder_request(tmp_path, monkeypatch, data["items"]),
        synthetic_sources,
        {i["item_id"]: "TEST-CAB" for i in data["items"]},
    )
    inject(monkeypatch, [record("TEST-CAB")])
    report = sizing.size_composition("CASE-TEST-001", data["items"], request)
    for item, selection in zip(data["items"], report["items"], strict=True):
        item["cabinet"] = selection["cabinet"]
    data.update(case_id="CASE-TEST-001", cabinet_sizing=report)
    path = tmp_path / "synthetic-bare-confirmed.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    for before_ha1 in (False, True):
        result = validator.validate_confirmed_composition_artifact(
            path, before_human_approval_1=before_ha1, expected_case_id="CASE-TEST-001"
        )
        assert result.status == "FAIL"
        assert any("HOLD_MODULE_LEDGER_REQUIRED" in flag for flag in result.red_flags)
    output = tmp_path / "forbidden-calculator-input.json"
    result = pricing.build_price_calculator_input_draft(path, output)
    assert result.status == "FAIL" and not output.exists()
    assert any(
        "HOLD_MODULE_LEDGER_REQUIRED_FOR_QUOTE" in flag for flag in result.red_flags
    )


@pytest.mark.parametrize("accessory_kind", [None, "PANEL", "OTHER"])
@pytest.mark.parametrize("model", ["capacity", "metal", "metal_core_panel"])
def test_quote_capacity_ledger_cannot_hide_required_non_din_accessory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    synthetic_sources: Any,
    accessory_kind: str | None,
    model: str,
) -> None:
    import cabinet_sizing_module_accounting as modules  # type: ignore[import-not-found]
    from module_accounting_fixtures import provision_modules, repin

    if model == "capacity":
        _, item, request = capacity_outcome(
            tmp_path, monkeypatch, synthetic_sources, [54] * 3
        )
        code = "CATALOGUE-KRN-ROW-64"
    else:
        supplied = {}
        if model == "metal_core_panel":
            supplied = {
                "item": {
                    "item_id": "I",
                    "product_name": "TEST",
                    "quantity": 1,
                    "components": [
                        {
                            "component_id": "C",
                            "component_code": "TEST_PANEL",
                            "quantity": 1,
                        }
                    ],
                },
                "records": [
                    synthetic_record("PANEL", mounting="PANEL", size=[80, 30, 30])
                ],
            }
        item, request = expanded(tmp_path, monkeypatch, **supplied)
        code = "METAL-TEST"
        inject(monkeypatch, [record(code)])
    request = quote_request(request, synthetic_sources, {"I": code})
    base = sizing.size_composition("CASE", [item], request)
    item["cabinet"] = base["items"][0]["cabinet"]
    binding, data = provision_modules(
        tmp_path,
        monkeypatch,
        "CASE",
        [item],
        base,
        {"I": "PANEL"} if model == "metal_core_panel" else None,
    )
    if accessory_kind:
        product = dict(
            data["products"][0],
            id="ACCESSORY",
            sku="TEST-ACCESSORY",
            mounting=accessory_kind,
            nominal_modules=None,
            width_mm=None,
            area_mm2=75,
        )
        data["products"].append(product)
        data["profiles"].append(
            dict(
                data["profiles"][0],
                id="ACCESSORY",
                product_ids=["ACCESSORY"],
                allowed_zones=[accessory_kind],
                nominal_modules=None,
                width_mm=None,
                area_mm2=75,
            )
        )
        board = data["boards"][0]
        board["instances"].append(
            dict(id="ACCESSORY", component_id=None, unit=1, product_id="ACCESSORY")
        )
        board["groups"].append(
            dict(
                id="ACCESSORY",
                profile_id="ACCESSORY",
                instance_ids=["ACCESSORY"],
                zone_id=accessory_kind,
            )
        )
        binding = repin(monkeypatch, Path(binding["path"]), data)
    base = modules.size_base("CASE", [item], request, binding)
    data["sizing_sha256"] = sizing.digest(base)
    binding = repin(monkeypatch, Path(binding["path"]), data)
    report = modules.build_sizing_report("CASE", [item], base, binding)
    # The ordinary ledger proves resource reserve, not non-DIN geometry.
    modules.verify_sizing_report(report, [item], "CASE")
    if accessory_kind:
        reason = (
            "HOLD_QUOTE_CAPACITY_ONLY_NON_DIN"
            if model == "capacity"
            else "HOLD_QUOTE_NON_DIN_ACCESSORY_GEOMETRY"
        )
        with pytest.raises(sizing.SizingHold, match=reason):
            sizing.verify_report(report, [item], expected_case_id="CASE")
        with pytest.raises(sizing.SizingHold, match=reason):
            sizing.verify_before_ha1(report, [item], expected_case_id="CASE")
    else:
        sizing.verify_before_ha1(report, [item], expected_case_id="CASE")
