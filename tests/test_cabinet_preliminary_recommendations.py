"""Public advisory contract; synthetic diagnostics test mechanics, not physics."""

from __future__ import annotations

import copy
import hashlib
import importlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

catalogue = importlib.import_module("cabinet_catalogue")
strict = importlib.import_module("cabinet_sizing")
selector = importlib.import_module("cabinet_sizing_catalogue")


@pytest.fixture
def api() -> Any:
    if importlib.util.find_spec("cabinet_preliminary_recommendations") is None:
        pytest.fail("Public recommendation API is not implemented yet")
    return importlib.import_module("cabinet_preliminary_recommendations")


@pytest.fixture
def mechanical(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    items = [{"item_id": "board", "components": []}]
    request = {
        "schema_version": selector.CURRENT_REQUEST_SCHEMA,
        "case_id": "case",
        "devices": {"shared": "all-items-device-binding"},
        "source_facts": {"board": {"source": "synthetic-only"}},
        "metal_source": {"version": "synthetic-v1"},
    }
    records = []
    for family, start, end in catalogue.RANGES:
        for row in range(start, end + 1):
            records.append(
                {
                    "cabinet_code": f"{family}-{row}",
                    "cabinet_label": f"synthetic {row}",
                    "family": family,
                    "row": row,
                    "dimensions_mm": [900 + row, 900 + row, 900 + row],
                    "source": {"path": "synthetic", "sha256": "a" * 64},
                }
            )
    outcomes = [
        dict(
            record,
            status="UNKNOWN",
            reasons=["MISSING_MOUNTING"],
            layout=None,
            physical_installation_status="HOLD",
        )
        for record in records
    ]
    for index, size, rows in (
        (0, [100, 200, 100], [0]),
        (1, [100, 200, 100], [0]),
        (2, [120, 220, 120], [0]),
        (3, [140, 240, 140], [0, 140]),
    ):
        records[index]["dimensions_mm"] = size
        outcomes[index].update(
            dimensions_mm=size,
            status="FIT",
            reasons=["PLANNING_ONLY"],
            layout={
                "orientation": "HORIZONTAL",
                "required_dimensions_mm": ["90", "190", "90"],
                "zones": [{"kind": "DIN", "row_datums_mm": rows, "origin_mm": [0, 0]}],
                "reserve": {"DIN": {"minimum_free_fraction": "0.25"}},
            },
        )
    records[4]["dimensions_mm"] = [50, 50, 50]
    outcomes[4]["dimensions_mm"] = [50, 50, 50]
    outcomes[5]["din_capacity_assessment"] = {"status": "PASS", "occupied_mm": "35.6"}
    outcomes[6].update(status="NO_FIT", reasons=["PROVEN_BOUND_FAILURE"])
    inventory = {"records": records, "source": {"sha256": "a" * 64}}
    data = {
        "items": items,
        "request": request,
        "inventory": inventory,
        "outcomes": outcomes,
    }

    def evaluate(case_id: str, supplied: Any, bound: Any = None) -> Any:
        assert case_id == "case" and len(supplied) == 1
        assert bound["devices"] == request["devices"]
        assert set(bound["source_facts"]) == {supplied[0]["item_id"]}
        details = {
            "item_id": "board",
            "apparatus_sha256": strict.apparatus_hash(supplied[0]),
            "candidate_outcomes": copy.deepcopy(data["outcomes"]),
            "catalogue": copy.deepcopy(data["inventory"]),
            "frontier": ["KRN-60"],
            "physical_installation_status": "HOLD",
            "first_missing": "STRICT_UNKNOWN",
        }
        details["device_fingerprint"] = data.get("device_fingerprint", "reviewed-v1")
        raise strict.SizingHold("STRICT_UNKNOWN", details)

    monkeypatch.setattr(strict, "size_composition", evaluate)
    monkeypatch.setattr(selector, "request_for", lambda *_: copy.deepcopy(request))
    monkeypatch.setattr(selector, "validate_request", lambda _, value: value)
    monkeypatch.setattr(
        catalogue, "inventory", lambda **_: copy.deepcopy(data["inventory"])
    )
    return data


def test_public_advice_preserves_ties_layout_alternatives_and_unknown(
    api: Any, mechanical: Any
) -> None:
    report = api.recommend_composition("case", mechanical["items"])
    board = report["items"][0]
    assert report["schema_version"] == "cabinet_sizing.preliminary_recommendations.v0.1"
    assert board["supported_frontier"] == ["METAL-8", "METAL-9"]
    assert board["shortlist"] == ["METAL-8", "METAL-9", "METAL-11"]
    assert board["conditional_candidates"] == ["METAL-13"]
    assert "METAL-12" in board["unknown_candidates"]
    assert "METAL-10" in board["supported_candidates"]
    assert board["excluded_no_fit"] == ["METAL-14"]
    assert len(board["candidates"]) == 70
    assert board["strict_status"] == board["physical_installation_status"] == "HOLD"
    assert "cabinet" not in board and "selected_cabinet" not in board
    assert (
        api.verify_recommendations(report, mechanical["items"], expected_case_id="case")
        is None
    )


def test_public_verifier_rejects_report_tampering(api: Any, mechanical: Any) -> None:
    report = api.recommend_composition("case", mechanical["items"])
    report["items"][0]["shortlist"] = ["METAL-10"]
    with pytest.raises(strict.SizingHold, match="RECOMMENDATION"):
        api.verify_recommendations(report, mechanical["items"], expected_case_id="case")


@pytest.mark.parametrize(
    "damage",
    [
        "missing_reserve",
        "empty_reserve",
        "empty_layout",
        "missing_first_hold",
        "bad_frontier",
    ],
)
def test_incomplete_strict_proof_never_becomes_advice(
    api: Any, mechanical: Any, damage: str
) -> None:
    if damage == "missing_reserve":
        del mechanical["outcomes"][0]["layout"]["reserve"]
    elif damage == "empty_reserve":
        mechanical["outcomes"][0]["layout"]["reserve"] = {}
    elif damage == "empty_layout":
        mechanical["outcomes"][0]["layout"] = {"reserve": {"DIN": {}}}
    else:
        old = strict.size_composition

        def incomplete(*args: Any, **kwargs: Any) -> Any:
            try:
                old(*args, **kwargs)
            except strict.SizingHold as exc:
                if damage == "missing_first_hold":
                    del exc.details["first_missing"]
                else:
                    exc.details["frontier"] = ["NOT-A-CANDIDATE"]
                raise

        # Patch only the public strict seam; the layer must reject invalid diagnostics.
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(strict, "size_composition", incomplete)
            with pytest.raises(strict.SizingHold):
                api.recommend_composition("case", mechanical["items"])
        return
    with pytest.raises(strict.SizingHold):
        api.recommend_composition("case", mechanical["items"])


@pytest.mark.parametrize(
    "damage",
    [
        "missing",
        "duplicate",
        "wrong_family",
        "wrong_id",
        "wrong_dimension",
        "status",
        "reasons",
    ],
)
def test_all_seventy_source_bound_candidates_required(
    api: Any, mechanical: Any, damage: str
) -> None:
    if damage == "missing":
        mechanical["outcomes"].pop()
    elif damage == "duplicate":
        mechanical["outcomes"][-1] = copy.deepcopy(mechanical["outcomes"][0])
    elif damage == "wrong_family":
        mechanical["outcomes"][0]["family"] = "KRV"
    elif damage == "wrong_id":
        mechanical["outcomes"][0]["cabinet_code"] = "FAKE"
    elif damage == "wrong_dimension":
        mechanical["outcomes"][0]["dimensions_mm"] = [999, 999, 999]
    elif damage == "status":
        mechanical["outcomes"][0]["status"] = "APPROVED"
    else:
        mechanical["outcomes"][0]["reasons"] = []
    with pytest.raises(strict.SizingHold):
        api.recommend_composition("case", mechanical["items"])


def test_no_advice_fallback_for_missing_strict_source(
    api: Any, mechanical: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable(*_: Any) -> Any:
        raise strict.SizingHold("HOLD_MANUFACTURER_SOURCE_SHA")

    monkeypatch.setattr(strict, "size_composition", unavailable)
    with pytest.raises(strict.SizingHold):
        api.recommend_composition("case", mechanical["items"])


@pytest.mark.parametrize(
    "field", ["source_sha", "source_fingerprint", "dimensions", "manufacturer"]
)
def test_verifier_recomputes_current_sources(
    api: Any, mechanical: Any, field: str
) -> None:
    report = api.recommend_composition("case", mechanical["items"])
    if field == "manufacturer":
        mechanical["device_fingerprint"] = "drifted"
    elif field == "dimensions":
        mechanical["inventory"]["records"][0]["dimensions_mm"] = [101, 200, 100]
        mechanical["outcomes"][0]["dimensions_mm"] = [101, 200, 100]
    else:
        source = mechanical["inventory"]["records"][0]["source"]
        source["sha256" if field == "source_sha" else "fingerprint"] = "b" * 64
    with pytest.raises(strict.SizingHold, match="RECOMMENDATION"):
        api.verify_recommendations(report, mechanical["items"], expected_case_id="case")


def test_source_changes_during_advice_build_are_rejected(
    api: Any, mechanical: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    previous = strict.size_composition
    calls = 0

    def drifting(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 2:
            mechanical["device_fingerprint"] = "drifted-during-build"
        return previous(*args, **kwargs)

    monkeypatch.setattr(strict, "size_composition", drifting)
    with pytest.raises(strict.SizingHold, match="STRICT_SOURCE_DRIFT"):
        api.recommend_composition("case", mechanical["items"])


@pytest.mark.parametrize(
    "schema",
    [
        "cabinet_sizing.pragmatic_metal_request.v0.1",
        "cabinet_sizing.catalogue_request.v0.1",
        "cabinet_sizing.catalogue_request.v0.2",
        "cabinet_sizing.catalogue_request.v0.3",
        "cabinet_sizing.automatic_request.v0.2",
    ],
)
def test_only_current_full_catalogue_requests(
    api: Any, mechanical: Any, schema: str
) -> None:
    request = copy.deepcopy(mechanical["request"])
    request["schema_version"] = schema
    with pytest.raises(strict.SizingHold, match="REQUEST_SCHEMA"):
        api.recommend_composition("case", mechanical["items"], request)


def test_naturally_one_frontier_does_not_hide_unknown_or_choose_cabinet(
    api: Any, mechanical: Any
) -> None:
    for index in (1, 2, 3):
        mechanical["outcomes"][index].update(
            status="UNKNOWN", layout=None, reasons=["MISSING_MOUNTING"]
        )
    board = api.recommend_composition("case", mechanical["items"])["items"][0]
    assert board["shortlist"] == board["supported_frontier"] == ["METAL-8"]
    assert len(board["unknown_candidates"]) == 68
    assert board["conditional_candidates"] == ["METAL-13"]
    assert board["unresolved_dimensional_frontier"] == ["METAL-12"]
    assert "selected_cabinet" not in board and "cabinet" not in board
    assert "локальный" in board["shortlist_scope"]


def test_public_views_show_proofs_residual_scope_and_leave_inputs_and_globals_unchanged(
    api: Any, mechanical: Any
) -> None:
    before = copy.deepcopy(mechanical)
    globals_before = (
        strict.SCHEMA,
        strict.APPROVED_SOURCES,
        catalogue.MOUNTING_SOURCES.copy(),
        sys.stdout,
    )
    report = api.recommend_composition(
        "case", mechanical["items"], mechanical["request"]
    )
    rendered = api.format_recommendations(
        report, mechanical["items"], expected_case_id="case"
    )
    candidate = report["items"][0]["candidates"][0]
    assert candidate["outer_minus_required_mm"] == ["10", "10", "10"]
    assert "NON_USABLE_PLANNING_HEADROOM" in candidate["headroom_scope"]
    assert "PLANNING_PROOF_ONLY" in candidate["reserve_scope"]
    assert all(c["cabinet_code"] in rendered for c in mechanical["outcomes"])
    assert "MISSING_MOUNTING" in rendered and "PROVEN_BOUND_FAILURE" in rendered
    assert "HUMAN_APPROVAL_1" in rendered and "источники" in rendered
    assert mechanical == before
    assert globals_before == (
        strict.SCHEMA,
        strict.APPROVED_SOURCES,
        catalogue.MOUNTING_SOURCES,
        sys.stdout,
    )


@pytest.mark.parametrize("before_a1", [False, True])
def test_old_verifier_rejects_advisory_in_both_modes(
    api: Any, mechanical: Any, before_a1: bool
) -> None:
    report = api.recommend_composition("case", mechanical["items"])
    with pytest.raises(strict.SizingHold):
        strict.verify_report(
            report,
            mechanical["items"],
            expected_case_id="case",
            before_human_approval_1=before_a1,
        )


@pytest.mark.parametrize("kind", ["items", "request"])
def test_case_item_coverage_rejected_before_shortlisting(
    api: Any, mechanical: Any, kind: str
) -> None:
    if kind == "items":
        items = mechanical["items"] * 2
        request = None
    else:
        items = mechanical["items"]
        request = dict(mechanical["request"], source_facts={})
    with pytest.raises(strict.SizingHold):
        api.recommend_composition("case", items, request)


@pytest.mark.parametrize("output_format", ["json", "markdown"])
def test_public_cli_advice_stdout_with_hold_exit_two(
    api: Any,
    mechanical: Any,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    output_format: str,
) -> None:
    composition = tmp_path / "input.json"
    original = json.dumps({"items": mechanical["items"]}).encode()
    composition.write_bytes(original)
    assert (
        api.main(
            [
                "--case-id",
                "case",
                "--composition-json",
                str(composition),
                "--format",
                output_format,
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert captured.err == ""
    if output_format == "json":
        data = json.loads(captured.out)
        assert data["schema_version"] == api.SCHEMA
        assert data["items"][0]["shortlist"]
    else:
        assert (
            "Предварительные рекомендации" in captured.out and "METAL-8" in captured.out
        )
    assert composition.read_bytes() == original
    assert list(tmp_path.iterdir()) == [composition]


@pytest.mark.parametrize(
    "damage",
    [
        "malformed",
        "duplicate_json",
        "request_pair",
        "sha",
        "source_drift",
        "relative_path",
    ],
)
def test_public_cli_errors_produce_hold_without_advice(
    api: Any,
    mechanical: Any,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    damage: str,
) -> None:
    composition = tmp_path / "input.json"
    composition.write_text(json.dumps({"items": mechanical["items"]}), encoding="utf-8")
    args = ["--case-id", "case", "--composition-json", str(composition)]
    if damage == "malformed":
        composition.write_text("{", encoding="utf-8")
    elif damage == "duplicate_json":
        composition.write_text('{"items":[],"items":[]}', encoding="utf-8")
    elif damage in {"request_pair", "sha"}:
        request = tmp_path / "request.json"
        request.write_text(json.dumps(mechanical["request"]), encoding="utf-8")
        args += ["--request-json", str(request)]
        if damage == "sha":
            args += ["--request-sha256", "0" * 64]
    elif damage == "source_drift":
        old = api.verify_recommendations

        def changing(*values: Any, **keywords: Any) -> None:
            old(*values, **keywords)
            composition.write_bytes(b"changed-after-verification")

        monkeypatch.setattr(api, "verify_recommendations", changing)
    else:
        args[-1] = "relative.json"
    assert api.main(args) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "HOLD" and "items" not in result


def test_cli_request_sha_and_shared_devices_remain_exact(
    api: Any, mechanical: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    composition = tmp_path / "input.json"
    request = tmp_path / "request.json"
    composition.write_text(json.dumps({"items": mechanical["items"]}), encoding="utf-8")
    raw = json.dumps(mechanical["request"]).encode()
    request.write_bytes(raw)
    assert (
        api.main(
            [
                "--case-id",
                "case",
                "--composition-json",
                str(composition),
                "--request-json",
                str(request),
                "--request-sha256",
                hashlib.sha256(raw).hexdigest(),
            ]
        )
        == 2
    )
    result = json.loads(capsys.readouterr().out)
    assert result["strict_request"]["devices"] == mechanical["request"]["devices"]
    assert request.read_bytes() == raw


@pytest.mark.parametrize(
    "damage", ["partial_list", "partial_status", "zones", "placements"]
)
def test_malformed_nested_strict_diagnostics_fail_closed(
    api: Any, mechanical: Any, damage: str
) -> None:
    if damage == "partial_list":
        mechanical["outcomes"][5]["din_capacity_assessment"] = []
    elif damage == "partial_status":
        mechanical["outcomes"][5]["din_capacity_assessment"] = {"status": "APPROVED"}
    elif damage == "zones":
        mechanical["outcomes"][0]["layout"]["zones"] = ["fake-zone"]
    else:
        mechanical["outcomes"][0]["layout"]["placements"] = ["fake-placement"]
    with pytest.raises(strict.SizingHold):
        api.recommend_composition("case", mechanical["items"])
