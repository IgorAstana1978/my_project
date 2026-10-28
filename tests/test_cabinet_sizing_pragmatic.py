"""Public preliminary sizing contract; injected source facts are synthetic."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import cabinet_sizing as sizing  # type: ignore[import-not-found]
import cabinet_sizing_evidence as evidence  # type: ignore[import-not-found]
import pytest
from test_cabinet_sizing_selector import provide, synthetic_record


@pytest.mark.skipif(
    not evidence.PRAGMATIC_REVIEW.exists(),
    reason="Local WU15 source pins not distributed",
)
def test_wu15_structural_canonical_projection_preserves_apparatus() -> None:
    source = json.loads(evidence.PRAGMATIC_REVIEW.read_bytes())["case_source"]
    case_id = evidence.WU15_CASE
    path = (
        Path(source["path"]).parents[2]
        / "telegram-employee-cases"
        / case_id
        / "preliminary-composition-draft.json"
    )
    draft = json.loads(path.read_bytes())
    item = dict(draft["items"][0], product_name="ЩО6", quantity=1)
    item["components"] = [
        {
            "component_id": c["component_id"],
            "component_code": c["component_code_guess"],
            "component_label": c["component_label_guess"],
            "quantity": c["quantity_guess"],
            "install_type": c["install_type_guess"],
        }
        for c in item["components"]
    ]
    import cabinet_sizing_pragmatic as pragmatic  # type: ignore[import-not-found]

    request = pragmatic.request_for(case_id, [item])
    result = sizing.size_composition(case_id, [item], request)["items"][0]
    assert result["apparatus_sha256"] == sizing.apparatus_hash(item)
    assert result["cabinet"]["dimensions_mm"] == [600, 400, 250]
    item["components"][0]["component_label"] += " changed"
    with pytest.raises(sizing.SizingHold, match="HOLD_SOURCE_FACT_COMPOSITION_BINDING"):
        sizing.size_composition(case_id, [item], request)


def provision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **kwargs: Any
) -> tuple[dict[str, Any], dict[str, Any]]:
    item, old, paths = provide(tmp_path, monkeypatch, **kwargs)
    binding = old["source_facts"][item["item_id"]]
    monkeypatch.setattr(
        evidence,
        "AUTHORIZED",
        evidence.AUTHORIZED
        | {
            (
                "pragmatic_source_fact",
                str(paths["source_fact"].resolve()),
                binding["sha256"],
            )
        },
    )
    return item, {
        "schema_version": "cabinet_sizing.pragmatic_metal_request.v0.1",
        "case_id": "CASE",
        "devices": old["devices"],
        "source_facts": old["source_facts"],
    }


def test_preliminary_public_seam_without_cabinet_interior_or_placements(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    item, request = provision(tmp_path, monkeypatch)
    report = sizing.size_composition("CASE", [item], request)
    selected = report["items"][0]
    assert report["schema_version"] == "cabinet_sizing.pragmatic_metal.v0.1"
    assert selected["cabinet"]["cabinet_code"] == "METAL-500X400X250-D22"
    # Three20.25mm units: reserve denominator81mm, free20.25mm; height80/depth30.
    assert selected["required_dimensions_mm"] == ["80", "81", "30"]
    assert selected["layout"]["reserve"]["DIN"]["occupied_mm"] == "60.75"
    assert selected["layout"]["reserve"]["DIN"]["capacity_mm"] == "81"
    assert selected["preliminary_only"] is True
    assert selected["unverified"]["cabinet_ip"] is None
    assert "usable_mm" not in json.dumps(report)
    assert "cabinet" not in item and "placements" not in request
    item["cabinet"] = selected["cabinet"]
    sizing.verify_report(
        report, [item], expected_case_id="CASE", before_human_approval_1=True
    )


def test_panel_body_edges_do_not_double_count_assembly_and_reserve_is_independent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    panel = synthetic_record("PANEL", mounting="PANEL", size=[253, 93, "97.8"])
    panel["body_reference"] = {
        "dimensions_mm": ["151.2", 93, "97.8"],
        "edge_mm": ["122.5", "122.5", 20, 20],
        "pair_gap_mm": ["122.5", 50],
        "metal_panel_min_mm": "1.5",
        "insulating_panel_min_mm": 6,
        "interphase_barriers_required": True,
    }
    item = {
        "item_id": "I",
        "product_name": "mixed",
        "quantity": 1,
        "components": [
            {"component_id": "P", "component_code": "TEST_PANEL", "quantity": 1},
            {"component_id": "D", "component_code": "TEST_DIN", "quantity": 20},
        ],
    }
    item, request = provision(
        tmp_path,
        monkeypatch,
        item=item,
        records=[panel, synthetic_record(size=["86.4", "35.6", "67.9"])],
        fact={"installation": None},
    )
    selected = sizing.size_composition("CASE", [item], request)["items"][0]
    panel_zone = next(z for z in selected["layout"]["zones"] if z["kind"] == "PANEL")
    # Body151.2 + two122.5 edge clearances; assembly253 is NOT added to245.
    assert panel_zone["planning_extent_mm"][:2] == ["396.2", "133"]
    assert selected["cabinet"]["dimensions_mm"] == [600, 400, 250]
    reserve = selected["layout"]["reserve"]
    assert reserve["DIN"]["occupied_mm"] == "712"
    assert reserve["PANEL"]["occupied_mm2"] == "23529"
    from decimal import Decimal

    for zone in reserve.values():
        occupied = zone.get("occupied_mm", zone.get("occupied_mm2"))
        capacity = zone.get("capacity_mm", zone.get("capacity_mm2"))
        assert Decimal(occupied) * 4 <= Decimal(capacity) * 3
    assert selected["unverified"]["installation_compatibility"] is None
    # A bigger approved600x400 candidate exists, but explicit500x400 cannot grow.
    binding = request["source_facts"]["I"]
    path = Path(binding["path"])
    fact = json.loads(path.read_bytes())
    fact.update(dimensions_status="EXPLICIT", dimensions_mm=[500, 400, 250])
    path.write_text(json.dumps(fact), encoding="utf-8")
    binding["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(
        evidence,
        "AUTHORIZED",
        evidence.AUTHORIZED
        | {("pragmatic_source_fact", str(path.resolve()), binding["sha256"])},
    )
    with pytest.raises(sizing.SizingHold, match="HOLD_SOURCE_DIMENSIONS_INCOMPATIBLE"):
        sizing.size_composition("CASE", [item], request)


def test_report_states_preliminary_limits_in_builder_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import build_confirmed_composition_from_preliminary_bundle as builder  # type: ignore[import-not-found]

    item, request = provision(tmp_path, monkeypatch)
    report = sizing.size_composition("CASE", [item], request)
    state = builder.classify_composition({"items": [item]}, automatic_cabinet=True)
    state.cabinet_sizing = report
    state.items[0]["cabinet"] = report["items"][0]["cabinet"]
    text = builder.render_final_summary(
        case_id="CASE", confirmation_id="TEST", state=state
    )
    assert "ПРЕДВАРИТЕЛЬНЫЙ" in text
    assert "IP" in text and "не проверен" in text


def test_pragmatic_builder_rechecks_sources_before_and_after_phrase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_build_confirmed_composition_from_preliminary_bundle import (
        builder,
        create_batch_bundle,
        fixed_now,
    )
    from test_cabinet_sizing import provision_auto

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
    request, _ = provision_auto(tmp_path, monkeypatch, "CASE-TEST-001", state.items)
    request["schema_version"] = "cabinet_sizing.pragmatic_metal_request.v0.1"
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
    path = tmp_path / "pragmatic-request.json"
    path.write_text(json.dumps(request), encoding="utf-8")
    prompts: list[str] = []
    summaries: list[str] = []

    def ask(prompt: str) -> str:
        prompts.append(prompt)
        return "SYNTHETIC APPROVAL"

    def drift() -> None:
        source = Path(request["devices"]["path"])
        source.write_bytes(source.read_bytes() + b" ")

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
        output_fn=summaries.append,
        now_fn=fixed_now,
        before_drift_check=drift,
    )
    assert "ПРЕДВАРИТЕЛЬНЫЙ" in "\n".join(summaries)
    assert len(prompts) == 1 and "exact approval phrase" in prompts[0]
    assert result.status == "HOLD" and not result.output_created
    assert not (root / "CASE-TEST-001" / "confirmed").exists()


def test_cli_refuses_unexpected_source_fact_instead_of_silently_slicing_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    item, request = provision(tmp_path, monkeypatch)
    request["source_facts"]["OTHER"] = request["source_facts"]["I"]
    composition = tmp_path / "composition.json"
    composition.write_text(json.dumps({"items": [item]}), encoding="utf-8")
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request), encoding="utf-8")
    assert (
        sizing.main(
            [
                "--composition-json",
                str(composition),
                "--case-id",
                "CASE",
                "--request-json",
                str(path),
                "--request-sha256",
                hashlib.sha256(path.read_bytes()).hexdigest(),
            ]
        )
        == 2
    )
    assert (
        json.loads(capsys.readouterr().out)["first_missing"]
        == "HOLD_SOURCE_FACT_COVERAGE"
    )


@pytest.mark.parametrize(
    "fault,reason",
    [
        ("source_drift", "HOLD_SOURCE_SHA_DRIFT"),
        ("apparatus_transplant", "HOLD_SOURCE_FACT_COMPOSITION_BINDING"),
        ("case_transplant", "HOLD_CASE_BINDING"),
        ("caller_cabinet", "HOLD_PRAGMATIC_REQUEST_SCHEMA"),
        ("caller_placements", "HOLD_PRAGMATIC_REQUEST_SCHEMA"),
        ("no_fit", "HOLD_NO_FITTING_APPROVED_METAL"),
        ("ambiguous_source", "HOLD_SOURCE_DIMENSIONS_AMBIGUOUS"),
        ("prior_shrink", "HOLD_CABINET_CHANGE_REQUIRES_NEW_HUMAN_APPROVAL"),
        ("whitelist_drift", "HOLD_METAL_WHITELIST_DRIFT"),
        ("uncertain_search", "HOLD_LAYOUT_SEARCH_UNCERTAIN"),
    ],
)
def test_preliminary_trust_and_stop_boundaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str, reason: str
) -> None:
    import cabinet_sizing_pragmatic as pragmatic  # type: ignore[import-not-found]
    import cabinet_sizing_selector as selector  # type: ignore[import-not-found]

    kwargs: dict[str, Any] = {}
    if fault == "no_fit":
        kwargs["records"] = [synthetic_record(size=[80, 1001, 30])]
    if fault == "ambiguous_source":
        kwargs["fact"] = {"dimensions_status": "UNKNOWN"}
    if fault == "prior_shrink":
        kwargs["fact"] = {
            "prior_approval": {
                "status": "APPROVED",
                "cabinet_code": "METAL-600X400X250-D28",
                "dimensions_mm": [600, 400, 250],
            }
        }
    item, request = provision(tmp_path, monkeypatch, **kwargs)
    if fault == "source_drift":
        path = Path(request["source_facts"]["I"]["path"])
        path.write_bytes(path.read_bytes() + b" ")
    elif fault == "apparatus_transplant":
        item["components"][0]["quantity"] += 1
    elif fault == "case_transplant":
        request["case_id"] = "OTHER"
    elif fault.startswith("caller_"):
        request[fault.removeprefix("caller_")] = {}
    elif fault == "whitelist_drift":
        monkeypatch.setattr(pragmatic, "METAL_SIZES", {(500, 400, 251): (22,)})
    elif fault == "uncertain_search":
        item["components"][0]["quantity"] = 5
        # Rebind the legitimate synthetic source fact, then exhaust the planner.
        path = Path(request["source_facts"]["I"]["path"])
        fact = json.loads(path.read_bytes())
        fact["apparatus_sha256"] = sizing.apparatus_hash(item)
        path.write_text(json.dumps(fact), encoding="utf-8")
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        request["source_facts"]["I"]["sha256"] = sha
        monkeypatch.setattr(
            evidence,
            "AUTHORIZED",
            evidence.AUTHORIZED | {("pragmatic_source_fact", str(path.resolve()), sha)},
        )
        monkeypatch.setattr(selector, "SEARCH_LIMIT", 0)
    with pytest.raises(sizing.SizingHold, match=reason):
        sizing.size_composition("CASE", [item], request)


@pytest.mark.parametrize(
    "dimensions,passes", [([500, 400, 250], True), ([500, 400, 249], False)]
)
def test_source_explicit_dimensions_are_validated_without_enlargement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, dimensions: Any, passes: bool
) -> None:
    item, request = provision(
        tmp_path,
        monkeypatch,
        fact={"dimensions_status": "EXPLICIT", "dimensions_mm": dimensions},
    )
    if passes:
        assert (
            sizing.size_composition("CASE", [item], request)["items"][0]["cabinet"][
                "dimensions_mm"
            ]
            == dimensions
        )
    else:
        with pytest.raises(
            sizing.SizingHold, match="HOLD_SOURCE_DIMENSIONS_OUTSIDE_METAL_WHITELIST"
        ):
            sizing.size_composition("CASE", [item], request)


def test_panel_reserve_cannot_borrow_free_din_capacity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    item = {
        "item_id": "I",
        "components": [
            {"component_id": "P", "component_code": "TEST_PANEL", "quantity": 1},
            {"component_id": "D", "component_code": "TEST_DIN", "quantity": 1},
        ],
    }
    item, request = provision(
        tmp_path,
        monkeypatch,
        item=item,
        records=[
            synthetic_record("PANEL", mounting="PANEL", size=[900, 700, 30]),
            synthetic_record(size=[80, 1, 30]),
        ],
    )
    selected = sizing.size_composition("CASE", [item], request)["items"][0]
    # 1000x800 has <840000mm2 even before the DIN zone; panel needs840000.
    assert selected["cabinet"]["dimensions_mm"] == [1200, 800, 300]
    assert selected["layout"]["reserve"]["PANEL"]["occupied_mm2"] == "630000"


def test_mixed_din_heights_cannot_make_a_smaller_candidate_falsely_impossible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cabinet_sizing_pragmatic as pragmatic  # type: ignore[import-not-found]

    # Synthetic whitelist isolates four-row geometry: three100mm bodies and
    # one40mm last body need460mm, not a uniform520mm approximation.
    catalogue = {(500, 100, 250): (22,), (600, 100, 250): (28,)}
    monkeypatch.setattr(pragmatic, "METAL_SIZES", catalogue)
    monkeypatch.setattr(
        pragmatic,
        "WHITELIST_SHA",
        sizing.digest([[*size, row[0]] for size, row in catalogue.items()]),
    )
    item = {
        "item_id": "I",
        "components": [
            {"component_id": "T", "component_code": "TEST_TALL", "quantity": 3},
            {"component_id": "S", "component_code": "TEST_SHORT", "quantity": 1},
        ],
    }
    item, request = provision(
        tmp_path,
        monkeypatch,
        item=item,
        records=[
            synthetic_record("TALL", size=[100, 75, 30]),
            synthetic_record("SHORT", size=[40, 75, 30]),
        ],
    )
    selected = sizing.size_composition("CASE", [item], request)["items"][0]
    assert selected["cabinet"]["dimensions_mm"] == [500, 100, 250]
    assert selected["required_dimensions_mm"] == ["460", "100", "30"]


def test_spare_row_capacity_contains_a_complete_admitted_envelope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    item = {
        "item_id": "I",
        "components": [
            {"component_id": "C", "component_code": "TEST_DIN", "quantity": 1}
        ],
    }
    item, request = provision(
        tmp_path, monkeypatch, item=item, records=[synthetic_record(size=[80, 350, 30])]
    )
    selected = sizing.size_composition("CASE", [item], request)["items"][0]
    assert selected["required_dimensions_mm"] == ["220", "350", "30"]
    zone = selected["layout"]["zones"][0]
    assert zone["row_planning_heights_mm"] == ["80", "80"]
    assert zone["spare_row_reference_dimensions_mm"] == [None, ["80", "350", "30"]]
