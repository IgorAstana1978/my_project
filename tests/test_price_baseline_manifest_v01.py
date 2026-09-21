from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest
from openpyxl import Workbook, load_workbook  # type: ignore[import-untyped]

from scripts import activate_price_baseline_manifest as activation
from scripts import audit_price_baseline_candidate as auditor
from scripts import calc_quote_price_draft as calculator
from scripts import price_baseline_contract as contract


def write_governed_workbook(
    path: Path,
    *,
    material_delta: int = 0,
    unused_delta: int = 0,
) -> None:
    workbook = Workbook()
    krn = workbook.active
    krn.title = "КРН"
    workbook.create_sheet("ЩР")
    for mapping in calculator.SUCCESSOR_COMPONENT_PRICE_MAPPINGS:
        sheet = workbook[mapping.sheet_name]
        sheet.cell(mapping.row, 1, mapping.expected_label)
        sheet.cell(
            mapping.row,
            2,
            mapping.expected_material_price
            + (material_delta if mapping.mapping_id == "COMPONENT-MAPPING-012" else 0),
        )
        sheet.cell(mapping.row, 3, mapping.expected_work_price)
    if material_delta:
        krn["B5"] = 4500 + material_delta
    occupied_component_rows = {
        calculator.normalize_workbook_label(krn.cell(row, 1).value): row
        for row in range(1, calculator.MAX_LOOKUP_ROW + 1)
        if calculator.normalize_workbook_label(krn.cell(row, 1).value) is not None
    }
    next_row = 40
    for definition in calculator.COMPONENT_DEFINITIONS.values():
        if definition.workbook_label is None:
            continue
        label = calculator.normalize_workbook_label(definition.workbook_label)
        if label in occupied_component_rows:
            continue
        krn.cell(next_row, 1, definition.workbook_label)
        dynamic_delta = (
            material_delta if definition.workbook_label == "ВА47 1 полюсный" else 0
        )
        krn.cell(next_row, 2, 1000 + next_row + dynamic_delta)
        krn.cell(next_row, 3, 200 + next_row)
        occupied_component_rows[label] = next_row
        next_row += 1
    for cabinet_mapping in calculator.APPROVED_CABINET_PRICE_MAPPINGS:
        sheet = workbook[cabinet_mapping.sheet_name]
        sheet.cell(cabinet_mapping.row, 12, cabinet_mapping.expected_label)
        sheet.cell(cabinet_mapping.row, 13, cabinet_mapping.expected_price)
    occupied_cabinet_labels = {
        calculator.normalize_workbook_label(krn.cell(row, 12).value)
        for row in range(1, calculator.MAX_LOOKUP_ROW + 1)
    }
    cabinet_row = 40
    for code, label in calculator.CABINET_DEFINITIONS.items():
        if code == calculator.INVOICE519_SCHE_CABINET_CODE:
            continue
        normalized = calculator.normalize_workbook_label(label)
        if normalized in occupied_cabinet_labels:
            continue
        krn.cell(cabinet_row, 12, label)
        krn.cell(cabinet_row, 13, 8000 + cabinet_row)
        occupied_cabinet_labels.add(normalized)
        cabinet_row += 1
    krn["A150"] = "UNUSED PRICE ROW"
    krn["B150"] = 7777 + unused_delta
    krn["C150"] = 333
    workbook.save(path)
    workbook.close()


def build_snapshot(path: Path) -> list[dict[str, Any]]:
    workbook = load_workbook(path, read_only=True, data_only=False, keep_links=False)
    try:
        return calculator.build_governed_mapping_snapshot(
            workbook,
            component_mappings=calculator.SUCCESSOR_COMPONENT_PRICE_MAPPINGS,
        )
    finally:
        workbook.close()


def publish_initial_chain(root: Path, workbook: Path) -> tuple[Path, Path]:
    manifests = root / "manifests"
    manifests.mkdir(parents=True)
    manifest_path = manifests / "PBM-INITIAL.json"
    manifest = {
        "schema_version": contract.MANIFEST_SCHEMA,
        "manifest_id": "PBM-INITIAL",
        "created_at": "2099-01-01T00:00:00Z",
        "predecessor": None,
        "workbook": {
            "path": str(workbook.resolve()),
            "sha256": contract.sha256_file(workbook),
            "structural_fingerprint": auditor.inspect_workbook(
                workbook
            ).structural_fingerprint,
        },
        "mapping_snapshot": build_snapshot(workbook),
        "approval": {
            "schema_version": contract.APPROVAL_SCHEMA,
            "authority": contract.APPROVAL_AUTHORITY,
            "approval_id": "IGOR-BASELINE-INITIAL",
            "approved_by": "Igor",
            "approved_at": "2099-01-01T00:00:00Z",
            "candidate_audit_sha256": "a" * 64,
            "approval_fingerprint": "b" * 64,
        },
        "scope": {
            "future_cases_only": True,
            "historical_repricing_authorized": False,
        },
    }
    contract.validate_manifest(manifest)
    manifest_raw = contract.canonical_json_bytes(manifest)
    manifest_path.write_bytes(manifest_raw)
    selector_path = root / "active-price-baseline.json"
    selector = {
        "schema_version": contract.SELECTOR_SCHEMA,
        "manifest_id": "PBM-INITIAL",
        "manifest_path": str(manifest_path.resolve()),
        "manifest_sha256": contract.sha256_bytes(manifest_raw),
        "activated_at": "2099-01-01T00:00:00Z",
        "approval_id": "IGOR-BASELINE-INITIAL",
    }
    selector_path.write_bytes(contract.canonical_json_bytes(selector))
    return selector_path, manifest_path


@pytest.fixture
def active_chain(tmp_path: Path) -> dict[str, Path]:
    root = tmp_path / "prices"
    current = root / "current"
    current.mkdir(parents=True)
    workbook = current / "approved.xlsx"
    write_governed_workbook(workbook)
    selector, manifest = publish_initial_chain(root, workbook)
    return {
        "root": root,
        "workbook": workbook,
        "selector": selector,
        "manifest": manifest,
    }


def write_candidate(active_chain: dict[str, Path], tmp_path: Path) -> Path:
    candidate = active_chain["root"] / "current" / "candidate.xlsx"
    write_governed_workbook(candidate, material_delta=100)
    return candidate


def test_active_selector_manifest_workbook_chain_is_exact_and_fail_closed(
    active_chain: dict[str, Path],
) -> None:
    resolved = contract.resolve_active_price_baseline(active_chain["selector"])
    assert resolved.version == contract.ACTIVE_VERSION
    assert resolved.path == active_chain["workbook"].resolve()
    assert resolved.manifest_id == "PBM-INITIAL"
    assert resolved.mapping_snapshot

    selector = json.loads(active_chain["selector"].read_text(encoding="utf-8"))
    selector["manifest_sha256"] = "0" * 64
    active_chain["selector"].write_bytes(contract.canonical_json_bytes(selector))
    with pytest.raises(contract.BaselineContractError, match="manifest SHA-256"):
        contract.resolve_active_price_baseline(active_chain["selector"])


def test_corrupt_manifest_and_missing_selector_fail_closed(
    active_chain: dict[str, Path], tmp_path: Path
) -> None:
    active_chain["manifest"].write_text("corrupt", encoding="utf-8")
    with pytest.raises(contract.BaselineContractError, match="manifest SHA-256"):
        contract.resolve_active_price_baseline(active_chain["selector"])
    with pytest.raises(contract.BaselineContractError, match="does not exist"):
        contract.resolve_active_price_baseline(tmp_path / "missing-selector.json")


def test_candidate_audit_is_read_only_and_separates_identity_from_prices(
    active_chain: dict[str, Path], tmp_path: Path
) -> None:
    candidate = write_candidate(active_chain, tmp_path)
    candidate_before = candidate.read_bytes()
    selector_before = active_chain["selector"].read_bytes()
    audit = auditor.audit_candidate(active_chain["selector"], candidate)
    assert audit["status"] == "PASS_CANDIDATE_ONLY"
    assert audit["hold_reasons"] == []
    assert audit["changed_prices"]
    assert all(change["currently_governed"] for change in audit["changed_prices"])
    assert "COMPONENT-MAPPING-012" in {
        mapping_id
        for change in audit["changed_prices"]
        for mapping_id in change["governed_mapping_ids"]
    }
    assert audit["mapping_snapshot"] != []
    assert all(
        "material_kzt" not in entry["identity"]
        and "work_kzt" not in entry["identity"]
        and "price_kzt" not in entry["identity"]
        for entry in audit["mapping_snapshot"]
    )
    assert candidate.read_bytes() == candidate_before
    assert active_chain["selector"].read_bytes() == selector_before


def test_unused_price_row_change_is_visible_without_becoming_mapping_authority(
    active_chain: dict[str, Path], tmp_path: Path
) -> None:
    candidate = active_chain["root"] / "current" / "unused-change.xlsx"
    write_governed_workbook(candidate, unused_delta=100)
    predecessor = contract.resolve_active_price_baseline(active_chain["selector"])
    audit = auditor.audit_candidate(active_chain["selector"], candidate)

    assert audit["status"] == "PASS_CANDIDATE_ONLY"
    assert audit["structural_compatibility"] is True
    assert audit["added_names"] == []
    assert audit["removed_names"] == []
    assert audit["changed_prices"] == [
        {
            "kind": "component",
            "sheet": "КРН",
            "row": 150,
            "label": "UNUSED PRICE ROW",
            "label_cell": "КРН!A150",
            "price_cells": ["КРН!B150", "КРН!C150"],
            "before": {"КРН!B150": 7777, "КРН!C150": 333},
            "after": {"КРН!B150": 7877, "КРН!C150": 333},
            "currently_governed": False,
            "governed_mapping_ids": [],
        }
    ]
    assert audit["mapping_snapshot"] == [
        dict(entry) for entry in predecessor.mapping_snapshot
    ]
    assert audit["approval_payload"]["candidate_workbook_sha256"] == (
        contract.sha256_file(candidate)
    )

    audit_path = tmp_path / "unused-row-audit.json"
    audit_path.write_bytes(contract.canonical_json_bytes(audit))
    approval_path = tmp_path / "unused-row-approval.json"
    approval_path.write_bytes(
        contract.canonical_json_bytes(approval_for(audit_path, audit))
    )
    workbook = load_workbook(candidate)
    workbook["КРН"]["B150"] = 7977
    workbook.save(candidate)
    workbook.close()
    with pytest.raises(activation.ActivationError, match="SHA-256 drifted"):
        activation.activate(
            candidate_audit_json=audit_path,
            approval_json=approval_path,
            active_selector=active_chain["selector"],
        )


@pytest.mark.parametrize(
    "invalid_value",
    [None, 0, -1, 1.5, "not a price"],
)
def test_unused_price_row_invalid_value_holds_without_mapping_expansion(
    active_chain: dict[str, Path], tmp_path: Path, invalid_value: Any
) -> None:
    candidate = active_chain["root"] / "current" / "unused-invalid.xlsx"
    write_governed_workbook(candidate)
    workbook = load_workbook(candidate)
    workbook["КРН"]["B150"] = invalid_value
    workbook.save(candidate)
    workbook.close()

    predecessor = contract.resolve_active_price_baseline(active_chain["selector"])
    audit = auditor.audit_candidate(active_chain["selector"], candidate)

    assert audit["status"] == "HOLD"
    assert "missing conflicts detected" in audit["hold_reasons"]
    assert any(
        finding.startswith("КРН!B150:") for finding in audit["conflicts"]["missing"]
    )
    assert audit["changed_prices"][0]["kind"] == "component"
    assert audit["changed_prices"][0]["row"] == 150
    assert audit["changed_prices"][0]["after"]["КРН!B150"] == invalid_value
    assert audit["changed_prices"][0]["currently_governed"] is False
    assert audit["changed_prices"][0]["governed_mapping_ids"] == []
    assert audit["mapping_snapshot"] == [
        dict(entry) for entry in predecessor.mapping_snapshot
    ]


@pytest.mark.parametrize("drift", ["formula", "missing", "identity", "duplicate"])
def test_candidate_audit_holds_formula_identity_and_duplicate_drift(
    active_chain: dict[str, Path], tmp_path: Path, drift: str
) -> None:
    candidate = write_candidate(active_chain, tmp_path)
    workbook = load_workbook(candidate)
    krn = workbook["КРН"]
    if drift == "formula":
        krn["B5"] = "=4500"
    elif drift == "missing":
        krn["B5"] = None
    elif drift == "identity":
        krn["A5"] = "different technical identity"
    else:
        krn["A100"] = krn["A5"].value
        krn["B100"] = krn["B5"].value
        krn["C100"] = krn["C5"].value
    workbook.save(candidate)
    workbook.close()
    audit = auditor.audit_candidate(active_chain["selector"], candidate)
    assert audit["status"] == "HOLD"
    assert audit["hold_reasons"]
    if drift == "identity":
        assert audit["conflicts"]["mapping_identity_drift"]
    else:
        assert audit["conflicts"][drift]


def approval_for(audit_path: Path, audit: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": contract.APPROVAL_SCHEMA,
        "authority": contract.APPROVAL_AUTHORITY,
        "approval_id": "IGOR-BASELINE-CANDIDATE",
        "approved_by": "Igor",
        "approved_at": "2099-01-02T00:00:00Z",
        "candidate_audit_sha256": contract.sha256_file(audit_path),
        "approval_fingerprint": audit["approval_fingerprint"],
    }


def activate_candidate(
    active_chain: dict[str, Path], tmp_path: Path
) -> tuple[Path, dict[str, Any], activation.ActivationResult]:
    candidate = write_candidate(active_chain, tmp_path)
    audit = auditor.audit_candidate(active_chain["selector"], candidate)
    audit_path = tmp_path / "candidate-audit.json"
    audit_path.write_bytes(contract.canonical_json_bytes(audit))
    approval_path = tmp_path / "approval.json"
    approval_path.write_bytes(
        contract.canonical_json_bytes(approval_for(audit_path, audit))
    )
    result = activation.activate(
        candidate_audit_json=audit_path,
        approval_json=approval_path,
        active_selector=active_chain["selector"],
    )
    return candidate, audit, result


def test_activation_is_immutable_atomic_and_exactly_approved(
    active_chain: dict[str, Path], tmp_path: Path
) -> None:
    candidate, audit, result = activate_candidate(active_chain, tmp_path)
    assert result.manifest_path.is_file()
    assert contract.sha256_file(result.manifest_path) == result.manifest_sha256
    resolved = contract.resolve_active_price_baseline(active_chain["selector"])
    assert resolved.path == candidate.resolve()
    assert resolved.manifest_id == audit["manifest_id"]
    assert resolved.approval_id == "IGOR-BASELINE-CANDIDATE"
    with pytest.raises(activation.ActivationError):
        activation.activate(
            candidate_audit_json=tmp_path / "candidate-audit.json",
            approval_json=tmp_path / "approval.json",
            active_selector=active_chain["selector"],
        )


def test_activation_rejects_approval_not_bound_to_exact_audit(
    active_chain: dict[str, Path], tmp_path: Path
) -> None:
    candidate = write_candidate(active_chain, tmp_path)
    audit = auditor.audit_candidate(active_chain["selector"], candidate)
    audit_path = tmp_path / "candidate-audit.json"
    audit_path.write_bytes(contract.canonical_json_bytes(audit))
    approval = approval_for(audit_path, audit)
    approval["candidate_audit_sha256"] = "0" * 64
    approval_path = tmp_path / "approval.json"
    approval_path.write_bytes(contract.canonical_json_bytes(approval))
    with pytest.raises(activation.ActivationError, match="exact candidate audit"):
        activation.activate(
            candidate_audit_json=audit_path,
            approval_json=approval_path,
            active_selector=active_chain["selector"],
        )


def test_activation_rejects_mapping_identity_change_even_when_approved(
    active_chain: dict[str, Path], tmp_path: Path
) -> None:
    candidate = write_candidate(active_chain, tmp_path)
    audit = auditor.audit_candidate(active_chain["selector"], candidate)
    audit["mapping_snapshot"][0]["identity"]["expected_label"] = "new identity"
    audit["mapping_snapshot"][0]["identity_fingerprint"] = (
        contract.mapping_identity_fingerprint(audit["mapping_snapshot"][0]["identity"])
    )
    audit["approval_payload"]["mapping_snapshot_sha256"] = contract.sha256_bytes(
        contract.canonical_json_bytes(audit["mapping_snapshot"])
    )
    audit["approval_fingerprint"] = contract.sha256_bytes(
        contract.canonical_json_bytes(audit["approval_payload"])
    )
    audit_path = tmp_path / "candidate-audit.json"
    audit_path.write_bytes(contract.canonical_json_bytes(audit))
    approval_path = tmp_path / "approval.json"
    approval_path.write_bytes(
        contract.canonical_json_bytes(approval_for(audit_path, audit))
    )
    with pytest.raises(activation.ActivationError, match="mapping identity drift"):
        activation.activate(
            candidate_audit_json=audit_path,
            approval_json=approval_path,
            active_selector=active_chain["selector"],
        )


def test_activation_rejects_workbook_toctou_drift(
    active_chain: dict[str, Path], tmp_path: Path
) -> None:
    candidate = write_candidate(active_chain, tmp_path)
    audit = auditor.audit_candidate(active_chain["selector"], candidate)
    audit_path = tmp_path / "candidate-audit.json"
    audit_path.write_bytes(contract.canonical_json_bytes(audit))
    approval_path = tmp_path / "approval.json"
    approval_path.write_bytes(
        contract.canonical_json_bytes(approval_for(audit_path, audit))
    )
    workbook = load_workbook(candidate)
    workbook["КРН"]["B5"] = 9999
    workbook.save(candidate)
    workbook.close()
    with pytest.raises(activation.ActivationError, match="SHA-256 drifted"):
        activation.activate(
            candidate_audit_json=audit_path,
            approval_json=approval_path,
            active_selector=active_chain["selector"],
        )


def write_input_csv(path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, delimiter=";", lineterminator="\n")
        writer.writerow(calculator.REQUIRED_COLUMNS)
        writer.writerow(
            [
                "TEST",
                "CAB-KRN-24",
                "1.20",
                "EKF-VA47-29-1P",
                "1",
                "modular_1p",
            ]
        )


def test_future_calculation_follows_active_manifest_without_python_edit(
    active_chain: dict[str, Path], tmp_path: Path
) -> None:
    input_csv = tmp_path / "input.csv"
    write_input_csv(input_csv)
    before = calculator.calculate_price_draft(
        None,
        input_csv,
        active_selector_path=active_chain["selector"],
    )
    assert before.status == "PASS"
    candidate, _, _ = activate_candidate(active_chain, tmp_path)
    after = calculator.calculate_price_draft(
        None,
        input_csv,
        active_selector_path=active_chain["selector"],
    )
    assert after.status == "PASS"
    assert after.price_workbook == candidate.resolve()
    assert after.price_baseline_manifest_id is not None
    assert after.total_preliminary_price != before.total_preliminary_price


def test_explicit_historical_binding_never_reads_active_selector(
    active_chain: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    historical = tmp_path / "historical.xlsx"
    historical.write_bytes(b"frozen historical bytes")
    frozen = contract.PriceBaseline(
        contract.HISTORICAL.version,
        historical,
        contract.sha256_file(historical),
    )
    monkeypatch.setitem(contract.BASELINES, contract.HISTORICAL.version, frozen)
    active_chain["selector"].write_text("corrupt", encoding="utf-8")
    assert (
        contract.require_price_baseline(historical, contract.HISTORICAL.version)
        == frozen
    )


def test_manifest_schema_file_is_valid_json() -> None:
    schema = (
        Path(__file__).resolve().parents[1]
        / "schemas"
        / "price_baseline_manifest_v0_1.schema.json"
    )
    payload = json.loads(schema.read_text(encoding="utf-8"))
    assert payload["properties"]["schema_version"]["const"] == (
        contract.MANIFEST_SCHEMA
    )
