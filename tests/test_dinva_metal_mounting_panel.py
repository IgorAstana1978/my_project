"""Approved arithmetic and source admission, isolated from physical FIT gates."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import cabinet_sizing as strict  # type: ignore[import-not-found]
import dinva_metal_mounting_panel as panel  # type: ignore[import-not-found]
import pytest


@pytest.fixture
def source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    """All construction authority here is synthetic and scoped to this test."""
    outer = getattr(request, "param", [800, 600, 250])
    row = {(800, 600, 250): 37, (1000, 600, 250): 42, (600, 400, 250): 28}[tuple(outer)]
    record = {
        "cabinet_code": f"CATALOGUE-METAL-ROW-{row}",
        "cabinet_label": "х".join(map(str, outer)) + " ",
        "family": "METAL",
        "row": row,
        "dimensions_mm": list(outer),
        "label_dimensions_mm": list(outer),
        "qualifier": "",
        "interpretation_status": "LITERAL_HWD",
        "source_issues": [],
        "source": {
            "path": str(tmp_path / "synthetic-catalogue"),
            "sha256": "1" * 64,
            "version": "2026.10.21",
            "sheet": "Лист1",
            "label_cell": f"A{row}",
            "dimension_cells": [f"{axis}{row}" for axis in "EFG"],
            "raw_dimension_values": list(outer),
        },
    }
    monkeypatch.setattr(
        panel.catalogue,
        "inventory",
        lambda **kw: {"records": [copy.deepcopy(record)]},
    )
    raw = tmp_path / "synthetic-construction-source.txt"
    raw.write_text("Synthetic standard enclosure with outer door and mounting panel")
    data = {
        "schema_version": panel.CONSTRUCTION_SCHEMA,
        "catalogue_identity": copy.deepcopy(record),
        "execution": panel.EXECUTION,
        "raw_sources": [
            {"path": str(raw), "sha256": hashlib.sha256(raw.read_bytes()).hexdigest()}
        ],
    }
    path = tmp_path / "synthetic-construction.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    binding = {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    monkeypatch.setattr(
        panel.evidence,
        "AUTHORIZED",
        frozenset({(panel.CONSTRUCTION_ROLE, str(path.resolve()), binding["sha256"])}),
    )
    return record, data, binding


@pytest.mark.parametrize(
    "outer,expected",
    [
        ([800, 600, 250], [700, 520]),
        ([1000, 600, 250], [900, 520]),
        ([600, 400, 250], [500, 320]),
    ],
)
def test_approved_examples(outer: list[int], expected: list[int]) -> None:
    before = list(outer)
    assert panel.panel_hw_mm(outer) == expected
    assert outer == before


@pytest.mark.parametrize(
    "outer",
    [
        None,
        [],
        [800, 600],
        [800, 600, 250, 1],
        [True, 600, 250],
        [800.0, 600, 250],
        ["800", 600, 250],
        [800, 600, 0],
        [100, 600, 250],
        [800, 80, 250],
        [-1, 600, 250],
    ],
)
def test_invalid_or_nonpositive_geometry_holds(outer: Any) -> None:
    with pytest.raises(strict.SizingHold):
        panel.panel_hw_mm(outer)


@pytest.mark.parametrize(
    "source,expected",
    [
        ([800, 600, 250], [700, 520]),
        ([1000, 600, 250], [900, 520]),
        ([600, 400, 250], [500, 320]),
    ],
    indirect=["source"],
)
def test_source_bound_result_provenance_and_physical_hold(
    source: Any, expected: list[int]
) -> None:
    record, _, binding = source
    before = copy.deepcopy(record)
    report = panel.assess_panel(record["cabinet_code"], construction_binding=binding)
    panel.verify_assessment(report)
    assert report["panel_hw_mm"] == expected
    assert report["status"] == "PANEL_DIMENSIONS_BY_APPROVED_RULE"
    assert report["first_missing"] is None
    assert report["catalogue_identity"] == record == before
    assert report["rule_provenance"]["authority"] == "IGOR_DIRECT_HUMAN_DECISION"
    assert report["rule_provenance"]["date"] == "2026-10-30"
    assert report["rule_provenance"]["formula"] == (
        "H_panel = H_outer - 100; W_panel = W_outer - 80"
    )
    assert (
        report["usable_geometry_status"] == report["usable_depth_status"] == "UNKNOWN"
    )
    assert report["physical_status"] == "HOLD"
    assert report["stop_before"] == "HUMAN_APPROVAL_1"
    for before_approval in (False, True):
        with pytest.raises(strict.SizingHold):
            strict.verify_report(
                report,
                [],
                expected_case_id="synthetic",
                before_human_approval_1=before_approval,
            )


def test_unknown_standard_is_hold_even_without_qualifier(source: Any) -> None:
    record, _, _ = source
    report = panel.assess_panel(record["cabinet_code"])
    assert report["status"] == "HOLD"
    assert report["panel_hw_mm"] is None
    assert report["first_missing"] == "HOLD_STANDARD_CONSTRUCTION_EVIDENCE_REQUIRED"
    panel.verify_assessment(report)


@pytest.mark.parametrize("family", ["KRN", "KRV", "KURN", "OTHER"])
def test_other_families_cannot_use_the_rule(source: Any, family: str) -> None:
    record, _, binding = source
    record["family"] = family
    report = panel.assess_panel(record["cabinet_code"], construction_binding=binding)
    assert report["first_missing"] == "HOLD_PANEL_RULE_FAMILY_OUT_OF_SCOPE"
    assert report["panel_hw_mm"] is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("qualifier", "ВРУ"),
        ("qualifier", None),
        ("source_issues", ["HOLD_LABEL_DIMENSION_SOURCE_CONFLICT"]),
        ("interpretation_status", "UNKNOWN"),
        ("label_dimensions_mm", [800, 600, 200]),
    ],
)
def test_special_or_conflicting_record_is_hold(
    source: Any, field: str, value: Any
) -> None:
    record, _, binding = source
    record[field] = value
    report = panel.assess_panel(record["cabinet_code"], construction_binding=binding)
    assert report["first_missing"] == "HOLD_PANEL_SPECIAL_OR_UNCONFIRMED_CONSTRUCTION"
    assert report["panel_hw_mm"] is None


def test_caller_flags_and_matching_sha_are_not_admission(source: Any) -> None:
    record, _, binding = source
    with pytest.raises(strict.SizingHold, match="HOLD_AUTOMATIC_SOURCE_BINDING"):
        panel.assess_panel(
            record["cabinet_code"], construction_binding={**binding, "approved": True}
        )
    panel.evidence.AUTHORIZED = frozenset()
    with pytest.raises(strict.SizingHold, match="HOLD_UNAPPROVED_REUSABLE_SOURCE"):
        panel.assess_panel(record["cabinet_code"], construction_binding=binding)


@pytest.mark.parametrize(
    "damage", ["identity", "execution", "schema", "raw_sources", "approval"]
)
def test_admitted_but_mismatched_construction_holds(
    source: Any, monkeypatch: pytest.MonkeyPatch, damage: str
) -> None:
    record, data, binding = source
    if damage == "identity":
        data["catalogue_identity"]["dimensions_mm"][0] = 1000
    elif damage == "execution":
        data["execution"] = "SPECIAL"
    elif damage == "schema":
        data["schema_version"] = "unknown"
    elif damage == "raw_sources":
        data["raw_sources"] = []
    else:
        data["approved"] = True
    monkeypatch.setattr(panel.evidence, "read", lambda *a: copy.deepcopy(data))
    with pytest.raises(strict.SizingHold, match="HOLD_PANEL_CONSTRUCTION_BINDING"):
        panel.assess_panel(record["cabinet_code"], construction_binding=binding)


@pytest.mark.parametrize("target", ["construction", "raw"])
def test_source_bytes_drift_holds(source: Any, target: str) -> None:
    record, data, binding = source
    path = (
        binding["path"] if target == "construction" else data["raw_sources"][0]["path"]
    )
    Path(path).write_text("changed")
    with pytest.raises(strict.SizingHold, match="HOLD_SOURCE_SHA_DRIFT"):
        panel.assess_panel(record["cabinet_code"], construction_binding=binding)


@pytest.mark.parametrize(
    "damage", ["json", "duplicate", "raw_shape", "raw_missing", "construction_missing"]
)
def test_unavailable_or_malformed_admitted_source_is_controlled_hold(
    source: Any, monkeypatch: pytest.MonkeyPatch, damage: str
) -> None:
    record, data, binding = source
    path = Path(binding["path"])
    if damage == "raw_missing":
        data["raw_sources"][0]["path"] += ".missing"
    elif damage == "raw_shape":
        data["raw_sources"] = [{"path": None}]
    if damage == "construction_missing":
        binding["path"] += ".missing"
    else:
        text = json.dumps(data)
        if damage == "json":
            text = "{"
        elif damage == "duplicate":
            text = '{"execution": "x", "execution": "y"}'
        path.write_text(text, encoding="utf-8")
        binding["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(
        panel.evidence,
        "AUTHORIZED",
        frozenset(
            {
                (
                    panel.CONSTRUCTION_ROLE,
                    str(Path(binding["path"]).resolve()),
                    binding["sha256"],
                )
            }
        ),
    )
    with pytest.raises(
        strict.SizingHold, match="HOLD_PANEL_INVALID_OR_UNAVAILABLE_EVIDENCE"
    ):
        panel.assess_panel(record["cabinet_code"], construction_binding=binding)


@pytest.mark.parametrize("target", ["catalogue", "construction"])
def test_source_rechecks_detect_mid_assessment_drift(
    source: Any, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    record, data, binding = source
    calls = 0

    def drift(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        result: dict[str, Any] = copy.deepcopy(
            {"records": [record]} if target == "catalogue" else data
        )
        if calls == 2:
            result["changed"] = True
        return result

    monkeypatch.setattr(
        panel.catalogue if target == "catalogue" else panel.evidence,
        "inventory" if target == "catalogue" else "read",
        drift,
    )
    with pytest.raises(strict.SizingHold, match="HOLD_PANEL_.*SOURCE_DRIFT"):
        panel.assess_panel(record["cabinet_code"], construction_binding=binding)


@pytest.mark.parametrize(
    "field,value",
    [
        ("panel_hw_mm", [720, 520]),
        ("physical_status", "PASS"),
        ("status", "PASS"),
        ("rule_provenance", {}),
    ],
)
def test_report_tampering_is_not_provenance(
    source: Any, field: str, value: Any
) -> None:
    record, _, binding = source
    report = panel.assess_panel(record["cabinet_code"], construction_binding=binding)
    report[field] = value
    with pytest.raises(strict.SizingHold, match="HOLD_PANEL_REPORT_DRIFT"):
        panel.verify_assessment(report)


@pytest.mark.parametrize("target", ["row", "label", "source"])
def test_equal_outer_dimensions_do_not_transfer_construction_admission(
    source: Any, target: str
) -> None:
    record, _, binding = source
    outer = copy.deepcopy(record["dimensions_mm"])
    if target == "row":
        record["row"] += 1
        record["cabinet_code"] = f"CATALOGUE-METAL-ROW-{record['row']}"
        record["source"]["label_cell"] = f"A{record['row']}"
        record["source"]["dimension_cells"] = [
            f"{axis}{record['row']}" for axis in "EFG"
        ]
    elif target == "label":
        record["cabinet_label"] += "other execution"
    else:
        record["source"]["sha256"] = "2" * 64
    assert record["dimensions_mm"] == record["label_dimensions_mm"] == outer
    with pytest.raises(strict.SizingHold, match="HOLD_PANEL_CONSTRUCTION_BINDING"):
        panel.assess_panel(record["cabinet_code"], construction_binding=binding)


@pytest.mark.parametrize("field", ["row", "cabinet_label", "source", "cabinet_code"])
def test_report_catalogue_identity_substitution_holds(source: Any, field: str) -> None:
    record, _, binding = source
    report = panel.assess_panel(record["cabinet_code"], construction_binding=binding)
    identity = report["catalogue_identity"]
    if field == "row":
        identity[field] += 1
    elif field == "source":
        identity[field]["sha256"] = "2" * 64
    else:
        identity[field] += "other"
    with pytest.raises(strict.SizingHold, match="HOLD_PANEL_"):
        panel.verify_assessment(report)


@pytest.mark.parametrize("status", ["PASS", "PANEL_DIMENSIONS_BY_APPROVED_RULE"])
def test_hold_report_cannot_claim_panel_admission(source: Any, status: str) -> None:
    record, _, _ = source
    report = panel.assess_panel(record["cabinet_code"])
    assert report["status"] == "HOLD"
    report.update(
        status=status,
        first_missing=None,
        panel_hw_mm=panel.panel_hw_mm(record["dimensions_mm"]),
    )
    with pytest.raises(strict.SizingHold, match="HOLD_PANEL_REPORT_DRIFT"):
        panel.verify_assessment(report)


@pytest.mark.parametrize("report", [None, [], {}, {"catalogue_identity": {}}])
def test_malformed_report_holds(report: Any) -> None:
    with pytest.raises(strict.SizingHold, match="HOLD_PANEL_REPORT_SCHEMA"):
        panel.verify_assessment(report)


def test_unknown_identity_and_mutable_source_alias_hold(source: Any) -> None:
    record, _, _ = source
    with pytest.raises(strict.SizingHold, match="HOLD_PANEL_CATALOGUE_IDENTITY"):
        panel.assess_panel("unknown")
    with pytest.raises(
        strict.SizingHold, match="HOLD_PANEL_CONCRETE_SOURCE_VERSION_REQUIRED"
    ):
        panel.assess_panel(record["cabinet_code"], source_version="CURRENT")


def admit_test_construction(
    data: Any, binding: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test-only admission; never authorizes an actual manufacturer's source."""
    path = Path(binding["path"])
    path.write_text(json.dumps(data), encoding="utf-8")
    binding["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(
        panel.evidence,
        "AUTHORIZED",
        frozenset({(panel.CONSTRUCTION_ROLE, str(path.resolve()), binding["sha256"])}),
    )


@pytest.fixture
def admitted_standard(
    source: Any, request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Any:
    """Portable complete raw chain; actual 40 HWD are checked by local replay."""
    record, data, binding = source
    row = getattr(request, "param", 37)
    record["row"] = row
    record["cabinet_code"] = f"CATALOGUE-METAL-ROW-{row}"
    record["source"]["label_cell"] = f"A{row}"
    record["source"]["dimension_cells"] = [f"{axis}{row}" for axis in "EFG"]
    catalogue_path = Path(record["source"]["path"])
    catalogue_path.write_text(f"Synthetic catalogue standard row {row}")
    record["source"]["sha256"] = hashlib.sha256(catalogue_path.read_bytes()).hexdigest()
    data["catalogue_identity"] = copy.deepcopy(record)
    data["raw_sources"].append(
        {"path": str(catalogue_path), "sha256": record["source"]["sha256"]}
    )
    admit_test_construction(data, binding, monkeypatch)
    monkeypatch.setattr(
        panel.evidence, "METAL_STANDARD_BINDINGS", {record["cabinet_code"]: binding}
    )
    return record, data, binding


def test_code_admission_roster_is_exactly_the_40_manufacturer_identities() -> None:
    bindings = panel.evidence.METAL_STANDARD_BINDINGS
    assert set(bindings) == {f"CATALOGUE-METAL-ROW-{r}" for r in range(8, 48)}
    authorized = {
        (role, path, sha)
        for role, path, sha in panel.evidence.AUTHORIZED
        if role == panel.CONSTRUCTION_ROLE
    }
    assert len(authorized) == 40
    assert authorized == {
        (panel.CONSTRUCTION_ROLE, str(Path(b["path"]).resolve()), b["sha256"])
        for b in bindings.values()
    }


@pytest.mark.parametrize("admitted_standard", range(8, 48), indirect=True)
def test_explicit_admitted_standard_rows_preserve_physical_hold(
    admitted_standard: Any,
) -> None:
    record, _, binding = admitted_standard
    selected = panel.standard_construction_binding(record["cabinet_code"])
    assert selected == binding and selected is not binding
    report = panel.assess_panel(record["cabinet_code"], construction_binding=selected)
    panel.verify_assessment(report)
    assert report["status"] == "PANEL_DIMENSIONS_BY_APPROVED_RULE"
    assert report["catalogue_identity"] == record
    assert report["construction_binding"] == binding
    assert report["panel_hw_mm"] == [700, 520]
    assert (
        report["usable_geometry_status"] == report["usable_depth_status"] == "UNKNOWN"
    )
    assert report["physical_status"] == "HOLD"
    assert report["stop_before"] == "HUMAN_APPROVAL_1"
    # An admitted source is still an explicit opt-in, never an inferred default.
    assert panel.assess_panel(record["cabinet_code"])["status"] == "HOLD"


def test_standard_binding_returns_a_copy(admitted_standard: Any) -> None:
    record, _, binding = admitted_standard
    selected = panel.standard_construction_binding(record["cabinet_code"])
    selected["sha256"] = "0" * 64
    assert panel.standard_construction_binding(record["cabinet_code"]) == binding


@pytest.mark.parametrize(
    "code",
    [
        "CATALOGUE-METAL-ROW-7",
        *(f"CATALOGUE-METAL-ROW-{row}" for row in range(48, 57)),
        "CATALOGUE-KRN-ROW-64",
        "CATALOGUE-KRV-ROW-75",
        "unknown",
        None,
        [],
        37,
    ],
)
def test_other_identities_cannot_resolve_a_standard_binding(code: Any) -> None:
    with pytest.raises(
        strict.SizingHold, match="HOLD_PANEL_STANDARD_CONSTRUCTION_NOT_ADMITTED"
    ):
        panel.standard_construction_binding(code)


@pytest.mark.parametrize("version", ["CURRENT", "2026.06.18", "2026.10.22"])
def test_other_catalogue_versions_cannot_resolve_a_standard_binding(
    version: str,
) -> None:
    with pytest.raises(
        strict.SizingHold, match="HOLD_PANEL_STANDARD_CONSTRUCTION_NOT_ADMITTED"
    ):
        panel.standard_construction_binding(
            "CATALOGUE-METAL-ROW-37", source_version=version
        )


def test_binding_cannot_be_replayed_against_another_catalogue_version(
    admitted_standard: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    record, _, binding = admitted_standard

    def inventory(*, source_version: str) -> Any:
        other = copy.deepcopy(record)
        other["source"]["version"] = source_version
        return {"records": [other]}

    monkeypatch.setattr(panel.catalogue, "inventory", inventory)
    with pytest.raises(strict.SizingHold, match="HOLD_PANEL_CONSTRUCTION_BINDING"):
        panel.assess_panel(
            record["cabinet_code"],
            source_version="2026.06.18",
            construction_binding=binding,
        )


@pytest.mark.parametrize("target", ["authority", "catalogue", "construction"])
def test_standard_helper_never_bypasses_raw_source_drift(
    admitted_standard: Any, target: str
) -> None:
    record, data, binding = admitted_standard
    path = binding["path"]
    if target != "construction":
        path = data["raw_sources"][0 if target == "authority" else 1]["path"]
    Path(path).write_text("changed source")
    selected = panel.standard_construction_binding(record["cabinet_code"])
    with pytest.raises(strict.SizingHold, match="HOLD_SOURCE_SHA_DRIFT"):
        panel.assess_panel(record["cabinet_code"], construction_binding=selected)


@pytest.mark.parametrize(
    "execution",
    ["INTERNAL_DOOR", "OUTER_DOOR_WITH_MOUNTING_PANEL_AND_FALSE_PANEL"],
)
def test_even_test_admission_cannot_change_the_approved_execution(
    admitted_standard: Any, monkeypatch: pytest.MonkeyPatch, execution: str
) -> None:
    record, data, binding = admitted_standard
    data["execution"] = execution
    admit_test_construction(data, binding, monkeypatch)
    with pytest.raises(strict.SizingHold, match="HOLD_PANEL_CONSTRUCTION_BINDING"):
        panel.assess_panel(
            record["cabinet_code"],
            construction_binding=panel.standard_construction_binding(
                record["cabinet_code"]
            ),
        )


def test_internal_door_qualifier_is_not_the_admitted_standard(
    admitted_standard: Any,
) -> None:
    record, _, _ = admitted_standard
    record["qualifier"] = "внутренняя дверь"
    record["cabinet_label"] += "внутренняя дверь"
    report = panel.assess_panel(
        record["cabinet_code"],
        construction_binding=panel.standard_construction_binding(
            record["cabinet_code"]
        ),
    )
    assert report["first_missing"] == "HOLD_PANEL_SPECIAL_OR_UNCONFIRMED_CONSTRUCTION"
    assert report["panel_hw_mm"] is None
