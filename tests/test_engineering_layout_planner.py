"""Source/report boundaries; synthetic seventy-record inputs prove mechanics."""

from __future__ import annotations

import copy
import importlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

strict = importlib.import_module("cabinet_sizing")


@pytest.fixture
def api() -> Any:
    if importlib.util.find_spec("engineering_layout_planner") is None:
        pytest.fail("Public source-bound joint planner is not implemented")
    return importlib.import_module("engineering_layout_planner")


def profile(identity: str = "exploration", duct: int = 10) -> dict[str, Any]:
    return {
        "id": identity,
        "author": "synthetic-test-author",
        "version": "test-v1",
        "rationale": "Hypothesis for synthetic geometric mechanics only",
        "unit": "mm",
        "parameters": {
            "insets_mm": [0, 0, 0, 0, 0, 0],
            "mount_offset_mm": 0,
            "duct_width_mm": duct,
            "duct_depth_mm": 10,
            "connection_height_mm": 10,
            "connection_depth_mm": 10,
            "service_height_mm": 20,
            "access_width_mm": 0,
            "assigned_width_mm": 0,
            "auxiliary_width_mm": 20,
            "future_din_hwd_mm": [40, 20, 20],
            "future_panel_hwd_mm": [40, 20, 20],
        },
    }


def scenarios(*profiles: Any) -> dict[str, Any]:
    return {
        "schema_version": "engineering_layout.scenarios.v0.1",
        "profiles": list(profiles),
    }


@pytest.fixture
def mechanical(api: Any, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    items = [{"item_id": "board", "components": [{"component_id": "q", "quantity": 4}]}]
    candidates = [
        {
            "cabinet_code": f"SYN-{i:02}",
            "dimensions_mm": [350, 100, 50],
            "status": "UNKNOWN",
            "reasons": ["MISSING_PHYSICAL"],
            "physical_installation_status": "HOLD",
        }
        for i in range(70)
    ]
    advice = {
        "schema_version": "cabinet_sizing.preliminary_recommendations.v0.1",
        "case_id": "case",
        "strict_request": {"devices": {}},
        "items": [
            {
                "item_id": "board",
                "apparatus_sha256": strict.apparatus_hash(items[0]),
                "strict_status": "HOLD",
                "candidates": candidates,
            }
        ],
    }
    units = [
        {
            "id": f"q:{i}",
            "mounting": "DIN",
            "dimensions_mm": [40, 30, 20],
            "clearance_mm": [0, 0, 0, 0],
            "body_reference": None,
            "pair_gap_mm": [0, 0],
            "extra_gap_mm": 0,
        }
        for i in range(1, 5)
    ]
    facts = {
        "dimensions_status": "ABSENT",
        "dimensions_mm": None,
        "prior_approval": {"status": "NONE"},
    }
    data = {
        "items": items,
        "advice": advice,
        "units": units,
        "facts": facts,
        "source_units_api": api.source_units,
        "project_cables_api": api.project_cables,
    }
    monkeypatch.setattr(
        api.advisory, "recommend_composition", lambda *_: copy.deepcopy(data["advice"])
    )
    monkeypatch.setattr(
        api,
        "project_cables",
        lambda *_: copy.deepcopy(
            data.get(
                "cables",
                {
                    "status": "UNKNOWN",
                    "first_missing": "CABLE_MAPPING_UNKNOWN",
                    "outgoing": [],
                    "feeder": None,
                },
            )
        ),
    )
    monkeypatch.setattr(api, "source_units", lambda *_: copy.deepcopy(data["units"]))
    monkeypatch.setattr(
        api.planning, "source_fact", lambda *_: copy.deepcopy(data["facts"])
    )
    return data


def test_all_seventy_default_unknown_and_three_scenarios(
    api: Any, mechanical: Any
) -> None:
    default = api.assess_composition("case", mechanical["items"])
    assert len(default["items"][0]["candidates"]) == 70
    assert all(
        c["assessments"][0]["status"] == "UNKNOWN"
        for c in default["items"][0]["candidates"]
    )
    supplied = scenarios(profile("a"), profile("b", 15), profile("c", 75))
    before = copy.deepcopy([mechanical["items"], supplied])
    report = api.assess_composition("case", mechanical["items"], supplied)
    assert report["schema_version"] == "engineering_layout.assessment.v0.1"
    assert report["real_status"] == report["physical_status"] == "HOLD"
    assert report["stop_before"] == "HUMAN_APPROVAL_1"
    assert len(report["items"][0]["candidates"]) == 70
    for candidate in report["items"][0]["candidates"]:
        assert candidate["strict_baseline"]["status"] == "UNKNOWN"
        assert [a["status"] for a in candidate["assessments"]] == [
            "CONDITIONAL_WITNESS",
            "CONDITIONAL_WITNESS",
            "NO_LAYOUT_IN_EXAMINED_FAMILY",
        ]
        assert all(
            "CABLE_MAPPING_UNKNOWN" in a["real_missing_evidence"]
            for a in candidate["assessments"]
        )
    assert report["sensitivity"][0]["parameter_differences"] == {
        "duct_width_mm": {"a": "10", "b": "15"}
    }
    assert before == [mechanical["items"], supplied]
    assert (
        api.verify_assessment(report, mechanical["items"], expected_case_id="case")
        is None
    )
    for mode in (False, True):
        with pytest.raises(strict.SizingHold):
            strict.verify_report(
                report,
                mechanical["items"],
                expected_case_id="case",
                before_human_approval_1=mode,
            )


def test_catalogue_construction_identity_stays_unknown_beside_witness(
    api: Any, mechanical: Any
) -> None:
    originals = mechanical["advice"]["items"][0]["candidates"]
    forms = [
        ("METAL", "ВРУ"),
        ("METAL", "ШРС"),
        ("METAL", "ЩО-70"),
        ("KRN", ""),
        ("KRV", ""),
    ]
    for i, candidate in enumerate(originals):
        family, qualifier = forms[i % len(forms)]
        candidate.update(
            cabinet_label=f"Исходное имя {i} {qualifier} ",
            family=family,
            qualifier=qualifier,
            source_issues=["SOURCE_CONSTRUCTION_UNPROVEN"],
            reasons=["HOLD_SPECIAL_FORM_FACTOR_MOUNTING_EVIDENCE_REQUIRED"],
            technical_binding={"source_decision": f"synthetic-{i}"},
        )
    before = copy.deepcopy(originals)
    report = api.assess_composition("case", mechanical["items"], scenarios(profile()))
    for candidate, source in zip(report["items"][0]["candidates"], before, strict=True):
        assert candidate["strict_baseline"] == source
        identity = candidate["catalogue_identity"]
        assert identity == {
            key: source[key]
            for key in (
                "cabinet_code",
                "cabinet_label",
                "family",
                "qualifier",
                "dimensions_mm",
                "source_issues",
                "technical_binding",
            )
        }
        compatibility = candidate["construction_compatibility"]
        assert compatibility["status"] == "UNKNOWN"
        assert compatibility["source_reasons"] == source["reasons"]
        assert candidate["assessments"][0]["status"] == "CONDITIONAL_WITNESS"
        assert candidate["assessments"][0]["physical_status"] == "HOLD"
    assert originals == before
    text = api.format_assessment(report, mechanical["items"], expected_case_id="case")
    assert "Construction compatibility" in text
    assert "ВРУ" in text and "ШРС" in text and "ЩО-70" in text


def test_generic_nondesignated_composition_uses_source_envelopes_with_unknown_cables(
    api: Any, mechanical: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Synthetic controlled envelope admission proves mechanics, not WU15 facts.
    item = {
        "item_id": "OTHER-BOARD",
        "product_name": "Пульт управления",
        "components": [
            {"component_id": "control", "component_code": "TEST_CONTROL", "quantity": 2}
        ],
    }
    mechanical["items"] = [item]
    mechanical["advice"]["case_id"] = "CASE-OTHER"
    board = mechanical["advice"]["items"][0]
    board.update(item_id=item["item_id"], apparatus_sha256=strict.apparatus_hash(item))
    envelope = copy.deepcopy(mechanical["units"][0])
    envelope["class_id"] = "CONTROL"
    monkeypatch.setattr(api.evidence, "envelopes", lambda _: {"CONTROL": envelope})
    monkeypatch.setattr(api.evidence, "class_for", lambda *_: "CONTROL")
    monkeypatch.setattr(api, "source_units", mechanical["source_units_api"])
    monkeypatch.setattr(api, "project_cables", mechanical["project_cables_api"])
    report = api.assess_composition("CASE-OTHER", [item], scenarios(profile()))
    result = report["items"][0]
    assert {u["id"] for u in result["units"]} == {"control:1", "control:2"}
    assert all(u["source_designation"] is None for u in result["units"])
    assert result["project_cables"]["status"] == "UNKNOWN"
    assert (
        result["project_cables"]["first_missing"]
        == "PROJECT_CABLE_MAPPING_NOT_ADMITTED"
    )
    assert len(result["candidates"]) == 70
    assert all(
        c["assessments"][0]["status"] == "CONDITIONAL_WITNESS"
        for c in result["candidates"]
    )
    assert all(
        c["assessments"][0]["witness"]["graph"]["logical_endpoints"] == []
        for c in result["candidates"]
    )
    assert report["real_status"] == report["physical_status"] == "HOLD"


@pytest.mark.parametrize(
    "damage",
    [
        "approved",
        "placements",
        "bad_unit",
        "author",
        "negative",
        "unknown_parameter",
        "missing",
        "duplicate",
    ],
)
def test_scenario_input_cannot_admit_facts_or_placements(
    api: Any, mechanical: Any, damage: str
) -> None:
    p = profile()
    if damage in {"approved", "placements"}:
        p[damage] = True
    elif damage == "bad_unit":
        p["unit"] = "inch"
    elif damage == "author":
        p["author"] = ""
    elif damage == "negative":
        p["parameters"]["duct_width_mm"] = -1
    elif damage == "unknown_parameter":
        p["parameters"]["waive_clearance"] = True
    elif damage == "missing":
        del p["parameters"]["duct_depth_mm"]
    request = scenarios(p, p) if damage == "duplicate" else scenarios(p)
    with pytest.raises(strict.SizingHold, match="SCENARIO"):
        api.assess_composition("case", mechanical["items"], request)


def test_missing_reference_and_capacity_inputs_are_not_zero(
    api: Any, mechanical: Any
) -> None:
    p = profile()
    p["parameters"]["future_din_hwd_mm"] = None
    report = api.assess_composition("case", mechanical["items"], scenarios(p))
    result = report["items"][0]["candidates"][0]["assessments"][0]
    assert result["witness"] is not None
    assert result["witness"]["reserve"]["DIN"]["operational_status"] == "UNKNOWN"
    assert result["routing_capacity"]["status"] == "UNKNOWN"
    assert "BEND_RADIUS_UNKNOWN" in result["model_missing_evidence"]


@pytest.mark.parametrize("damage", ["report", "case", "source", "coverage", "units"])
def test_recomputation_and_complete_source_binding(
    api: Any, mechanical: Any, damage: str
) -> None:
    report = api.assess_composition("case", mechanical["items"], scenarios(profile()))
    if damage == "report":
        report["items"][0]["candidates"][0]["assessments"][0]["status"] = "FIT"
    elif damage == "source":
        mechanical["advice"]["items"][0]["candidates"][0]["dimensions_mm"][0] = 351
    elif damage == "coverage":
        mechanical["advice"]["items"][0]["candidates"].pop()
    elif damage == "units":
        mechanical["units"][0]["dimensions_mm"][1] = 31
    with pytest.raises(strict.SizingHold):
        api.verify_assessment(
            report,
            mechanical["items"],
            expected_case_id="wrong" if damage == "case" else "case",
        )


def test_source_constraints_survive_scenario_and_prior_approval(
    api: Any, mechanical: Any
) -> None:
    mechanical["facts"].update(
        dimensions_status="EXPLICIT", dimensions_mm=[999, 999, 999]
    )
    report = api.assess_composition("case", mechanical["items"], scenarios(profile()))
    assert all(
        "SOURCE_EXACT_DIMENSIONS_ONLY" in c["assessments"][0]["failed_constraints"]
        for c in report["items"][0]["candidates"]
    )
    mechanical["facts"].update(
        dimensions_status="ABSENT",
        dimensions_mm=None,
        prior_approval={
            "status": "APPROVED",
            "cabinet_code": "SYN-00",
            "dimensions_mm": [350, 100, 50],
        },
    )
    report = api.assess_composition("case", mechanical["items"], scenarios(profile()))
    assert (
        "CABINET_CHANGE_REQUIRES_HUMAN_APPROVAL"
        in report["items"][0]["candidates"][1]["assessments"][0]["failed_constraints"]
    )


def test_verified_svg_is_view_only_and_escapes_labels(
    api: Any, mechanical: Any
) -> None:
    mechanical["advice"]["items"][0]["candidates"][0]["cabinet_code"] = "<unsafe&>"
    report = api.assess_composition("case", mechanical["items"], scenarios(profile()))
    before = copy.deepcopy(report)
    svg = api.render_witness_svg(
        report,
        mechanical["items"],
        expected_case_id="case",
        item_id="board",
        cabinet_code="<unsafe&>",
        scenario_id="exploration",
    )
    assert "&lt;unsafe&amp;&gt;" in svg
    assert "PHYSICAL HOLD" in svg and "SCENARIO" in svg
    assert "&lt;" in svg and "<unsafe" not in svg
    assert report == before


def test_cli_stdout_only_path_pairs_and_duplicate_keys(
    api: Any, tmp_path: Path, capsys: Any
) -> None:
    composition = tmp_path / "composition.json"
    composition.write_text('{"items":[],"items":[]}', encoding="utf-8")
    assert api.main(["--case-id", "case", "--composition-json", str(composition)]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "HOLD"
    assert (
        api.main(
            [
                "--case-id",
                "case",
                "--composition-json",
                str(composition),
                "--scenarios-sha256",
                "a" * 64,
            ]
        )
        == 2
    )
    assert "PATH_AND_SHA" in capsys.readouterr().out


def test_actual_admitted_cables_and_source_unit_designations(api: Any) -> None:
    e = api.evidence
    path = (
        Path("C:/Users/IgorN/Documents/production_ai_cases/telegram-employee-cases")
        / e.WU15_CASE
        / "preliminary-composition-draft.json"
    )
    if not path.exists() or not e.REFERENCE.exists():
        pytest.skip(
            "Actual admitted local WU15 sources unavailable; no synthetic physics claim"
        )
    items = json.loads(e.safe_bytes(path, e.WU15_DRAFT_SHA))["items"]
    result = api.project_cables(e.WU15_CASE, items[0])
    assert result["summary"] == {
        "outgoing_count": 20,
        "logical_core_endpoints": 60,
        "length_m": 1073,
        "section_counts": {"2.5": 10, "4": 5, "6": 5},
        "phase_counts": {"L1": 7, "L2": 6, "L3": 7},
    }
    assert (
        result["feeder"]["cores"]
        is result["feeder"]["mark"]
        is result["feeder"]["section_mm2"]
        is None
    )
    assert result["outgoing"][7]["phase"] == result["outgoing"][8]["phase"] == "L3"
    assert result["outgoing"][2]["group"] == "Р4"
    assert result["outgoing"][4]["group"] == "Р13"
    assert result["outgoing"][12]["group"] == "Р3"
    units = api.source_units(items[0], e.default_binding())
    assert {u["source_designation"] for u in units} == {f"QF{i}" for i in range(21)}
    assert api.project_cables(e.WU15_CASE, items[1])["status"] == "UNKNOWN"
    altered = copy.deepcopy(items[0])
    altered["components"][0]["quantity_guess"] = 2
    with pytest.raises(strict.SizingHold, match="BINDING"):
        api.project_cables(e.WU15_CASE, altered)


def test_source_endpoints_keep_individual_neutral_and_pe_paths(
    api: Any, mechanical: Any
) -> None:
    mechanical["units"][0]["source_designation"] = "QF1"
    mechanical["cables"] = {
        "status": "SOURCE_BOUND_PARTIAL",
        "first_missing": "FEEDER_UNKNOWN",
        "feeder": None,
        "outgoing": [
            {
                "qf": "QF1",
                "section_mm2": "6",
                "endpoints": ["QF1:L", "QF1:N_individual_RCBO", "QF1:PE"],
            }
        ],
    }
    report = api.assess_composition("case", mechanical["items"], scenarios(profile()))
    graph = report["items"][0]["candidates"][0]["assessments"][0]["witness"]["graph"]
    endpoints = {e["id"]: e for e in graph["logical_endpoints"]}
    assert set(endpoints) == {"QF1:L", "QF1:N_individual_RCBO", "QF1:PE"}
    assert endpoints["QF1:N_individual_RCBO"]["path"][-1] == "entry"
    assert "N" not in endpoints["QF1:N_individual_RCBO"]["path"]
    assert endpoints["QF1:PE"]["path"][-1] == "PE"
    assert all(
        e["section_mm2"] == "6" and e["port_status"] == "UNKNOWN"
        for e in endpoints.values()
    )


def test_verifier_malformed_report_is_a_precise_hold(api: Any, mechanical: Any) -> None:
    report = {"schema_version": api.SCHEMA, "case_id": "case"}
    with pytest.raises(strict.SizingHold, match="ENGINEERING_REPORT"):
        api.verify_assessment(report, mechanical["items"], expected_case_id="case")


def test_krn36_requires_exact_capacity_binding_even_in_scenario(
    api: Any, mechanical: Any
) -> None:
    candidate = mechanical["advice"]["items"][0]["candidates"][0]
    candidate.update(
        cabinet_code="CATALOGUE-KRN-ROW-64",
        dimensions_mm=[540, 330, 100],
        technical_binding={"rail_count": 3},
        din_capacity_binding={
            "rail_count": 3,
            "rail_capacity_mm": 216,
            "total_capacity_mm": 648,
        },
    )
    report = api.assess_composition("case", mechanical["items"], scenarios(profile()))
    witness = report["items"][0]["candidates"][0]["assessments"][0]["witness"]
    assert witness["din_rows"] == 3
    assert witness["reserve"]["DIN"]["capacity_mm"] == "648"
    candidate["din_capacity_binding"]["rail_capacity_mm"] = 217
    with pytest.raises(strict.SizingHold, match="KRN36_SOURCE_BINDING"):
        api.assess_composition("case", mechanical["items"], scenarios(profile()))


def test_capacity_uses_source_counts_sections_and_explicit_medium(
    api: Any, mechanical: Any
) -> None:
    mechanical["units"][0]["source_designation"] = "QF1"
    mechanical["cables"] = {
        "status": "SOURCE_BOUND_PARTIAL",
        "first_missing": "FEEDER_UNKNOWN",
        "feeder": None,
        "summary": {"logical_core_endpoints": 60, "outgoing_count": 20},
        "outgoing": [
            {
                "qf": "QF1",
                "section_mm2": "6",
                "endpoints": ["QF1:L", "QF1:N_individual_RCBO", "QF1:PE"],
            }
        ],
    }
    p = profile()
    p["parameters"]["routing"] = {
        "medium": "INSULATED_CORES",
        "diameter_mm": "1",
        "count": 60,
        "fill_fraction": "1",
        "usable_width_mm": "10",
        "usable_depth_mm": "10",
        "bend_radius_mm": "5",
        "termination_max_section_mm2": "6",
    }
    report = api.assess_composition("case", mechanical["items"], scenarios(p))
    a = report["items"][0]["candidates"][0]["assessments"][0]
    assert a["routing_capacity"]["status"] == "CONDITIONAL_AREA_OK"
    assert a["routing_capacity"]["occupied_mm2_upper_bound"] == "47.12388980384691"
    assert a["routing_capacity"]["bend_status"] == "UNKNOWN_ACTUAL_PATH"
    p["parameters"]["routing"].update(
        count=59, termination_max_section_mm2="4", diameter_mm="10"
    )
    report = api.assess_composition("case", mechanical["items"], scenarios(p))
    a = report["items"][0]["candidates"][0]["assessments"][0]
    assert a["witness"] is None
    assert set(a["failed_constraints"]) == {
        "SOURCE_ENDPOINT_COUNT_EXCEEDS_SCENARIO",
        "SOURCE_SECTION_EXCEEDS_SCENARIO_TERMINATION",
        "SCENARIO_DUCT_CROSS_SECTION_EXCEEDED",
    }


def test_cli_valid_hold_and_scenario_sha_drift_are_read_only(
    api: Any, mechanical: Any, tmp_path: Path, capsys: Any
) -> None:
    import hashlib

    composition = tmp_path / "composition.json"
    composition.write_text(json.dumps({"items": mechanical["items"]}), encoding="utf-8")
    scenario = tmp_path / "scenarios.json"
    raw = json.dumps(scenarios(profile())).encode()
    scenario.write_bytes(raw)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    base = [
        "--case-id",
        "case",
        "--composition-json",
        str(composition),
        "--scenarios-json",
        str(scenario),
        "--scenarios-sha256",
    ]
    assert api.main(base + [hashlib.sha256(raw).hexdigest()]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["schema_version"] == api.SCHEMA
    assert len(report["items"][0]["candidates"]) == 70
    assert api.main(base + ["0" * 64]) == 2
    assert "INPUT_SHA" in capsys.readouterr().out
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}


def test_source_reread_and_request_mutation_fail_closed(
    api: Any, mechanical: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = api.advisory.recommend_composition
    calls = 0

    def drifting(*args: Any) -> Any:
        nonlocal calls
        calls += 1
        value = original(*args)
        if calls == 2:
            value["items"][0]["candidates"][0]["reasons"] = ["DRIFT"]
        return value

    monkeypatch.setattr(api.advisory, "recommend_composition", drifting)
    with pytest.raises(strict.SizingHold, match="STRICT_SOURCE_DRIFT"):
        api.assess_composition("case", mechanical["items"], scenarios(profile()))


def test_json_approval_cannot_admit_device_geometry(api: Any) -> None:
    with pytest.raises(strict.SizingHold, match="SOURCE_BINDING"):
        api.source_units(
            {"components": []},
            {"path": "C:/fake.json", "sha256": "a" * 64, "approved": True},
        )


def test_multirow_topology_is_visible_without_promoting_construction_or_physics(
    api: Any, mechanical: Any
) -> None:
    mechanical["units"] = [copy.deepcopy(mechanical["units"][0]) for _ in range(8)]
    for i, apparatus in enumerate(mechanical["units"]):
        apparatus.update(id=f"control:{i}", dimensions_mm=[86.4, 35.6, 67.9])
    for candidate in mechanical["advice"]["items"][0]["candidates"]:
        candidate["dimensions_mm"] = [1000, 400, 250]
    p = profile(duct=25)
    p["parameters"].update(
        connection_height_mm=35,
        future_din_hwd_mm=[86.4, 35.6, 67.9],
    )
    report = api.assess_composition("case", mechanical["items"], scenarios(p))
    for candidate in report["items"][0]["candidates"]:
        assessment = candidate["assessments"][0]
        assert assessment["witness"]["routing_topology"] == "DIN_COLUMN_RISERS"
        assert assessment["physical_status"] == "HOLD"
        assert candidate["construction_compatibility"]["status"] == "UNKNOWN"
        assert "DEVICE_PORT_ORIGINS_UNKNOWN" in assessment["model_missing_evidence"]
    text = api.format_assessment(report, mechanical["items"], expected_case_id="case")
    assert "Routing topology" in text
    assert "| DIN_COLUMN_RISERS |" in text
    assert report["real_status"] == report["physical_status"] == "HOLD"


def test_shared_topology_discloses_unknown_branch_compatibility(
    api: Any, mechanical: Any
) -> None:
    mechanical["units"] = [copy.deepcopy(mechanical["units"][0]) for _ in range(20)]
    for i, apparatus in enumerate(mechanical["units"]):
        apparatus.update(id=f"control:{i}", dimensions_mm=[86.4, 35.6, 67.9])
    for candidate in mechanical["advice"]["items"][0]["candidates"]:
        candidate["dimensions_mm"] = [1000, 400, 200]
    p = profile(duct=55)
    p["parameters"].update(
        connection_height_mm=35,
        future_din_hwd_mm=[86.4, 35.6, 67.9],
    )
    report = api.assess_composition("case", mechanical["items"], scenarios(p))
    for candidate in report["items"][0]["candidates"]:
        assessment = candidate["assessments"][0]
        assert assessment["witness"]["routing_topology"] == "DIN_SHARED_COLUMN_RISERS"
        assert (
            "SHARED_DUCT_BRANCH_COMPATIBILITY_UNKNOWN"
            in assessment["model_missing_evidence"]
        )
        assert assessment["routing_capacity"]["status"] == "UNKNOWN"
        assert assessment["physical_status"] == "HOLD"
        assert candidate["construction_compatibility"]["status"] == "UNKNOWN"
