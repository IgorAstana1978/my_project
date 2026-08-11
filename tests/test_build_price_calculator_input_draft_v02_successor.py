import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    PROJECT_ROOT / "scripts" / "build_price_calculator_input_draft_v02_successor.py"
)


def load_script_module(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


successor = cast(Any, load_script_module("v02_successor_for_test", SCRIPT))


ROW_TO_MAPPING = {
    "ROW-DRAFT-0001": "COMPONENT-MAPPING-001",
    "ROW-DRAFT-0004": "COMPONENT-MAPPING-001",
    "ROW-DRAFT-0002": "COMPONENT-MAPPING-002",
    "ROW-DRAFT-0003": "COMPONENT-MAPPING-002",
    "ROW-DRAFT-0006": "COMPONENT-MAPPING-002",
    "ROW-DRAFT-0008": "COMPONENT-MAPPING-002",
    "ROW-DRAFT-0005": "COMPONENT-MAPPING-003",
    "ROW-DRAFT-0007": "COMPONENT-MAPPING-003",
    "ROW-DRAFT-0009": "COMPONENT-MAPPING-003",
    "ROW-DRAFT-0010": "COMPONENT-MAPPING-003",
    "ROW-DRAFT-0011": "COMPONENT-MAPPING-004",
    "ROW-DRAFT-0012": "COMPONENT-MAPPING-004",
    "ROW-DRAFT-0013": "COMPONENT-MAPPING-004",
    "ROW-DRAFT-0014": "COMPONENT-MAPPING-004",
    "ROW-DRAFT-0016": "COMPONENT-MAPPING-006",
    "ROW-DRAFT-0018": "COMPONENT-MAPPING-006",
    "ROW-DRAFT-0017": "COMPONENT-MAPPING-007",
    "ROW-DRAFT-0019": "COMPONENT-MAPPING-007",
}
ROW_TO_SECTION = {
    "ROW-DRAFT-0001": "11",
    "ROW-DRAFT-0002": "13",
    "ROW-DRAFT-0003": "9",
    "ROW-DRAFT-0004": "15",
    "ROW-DRAFT-0005": "9",
    "ROW-DRAFT-0006": "11",
    "ROW-DRAFT-0007": "13",
    "ROW-DRAFT-0008": "15",
    "ROW-DRAFT-0009": "11",
    "ROW-DRAFT-0010": "15",
    "ROW-DRAFT-0011": "9",
    "ROW-DRAFT-0012": "13",
    "ROW-DRAFT-0013": "15",
    "ROW-DRAFT-0014": "11",
    "ROW-DRAFT-0016": "9",
    "ROW-DRAFT-0017": "11",
    "ROW-DRAFT-0018": "13",
    "ROW-DRAFT-0019": "15",
}


def fixture_contracts() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    row_ids = [f"ROW-DRAFT-{index:04d}" for index in range(1, 110)]
    base_rows = []
    for row_id in row_ids:
        quantity = 2 if row_id in successor.QUANTITY_ROW_IDS else 1
        mapping_id = ROW_TO_MAPPING.get(row_id, "COMPONENT-MAPPING-UNCHANGED")
        base_rows.append(
            {
                "row_id": row_id,
                "cabinet_group_id": "CABINET-GROUP-001",
                "calculator_values": {
                    "product_name": "ПР",
                    "cabinet_code": "PR",
                    "consumables_factor": 1.1,
                    "component_code": "CODE",
                    "component_qty": quantity,
                    "install_type": "modular",
                },
                "source_quantity": {
                    "decision_id": f"HDA-022-{row_id}",
                    "decision_kind": "DIRECT_COMPONENT_QUANTITY",
                    "quantity_per_cabinet": quantity,
                },
                "source_component_evidence_ids": [f"EVIDENCE-{row_id}"],
                "approved_signature": {"mapping_request_id": mapping_id},
                "mapping_status": "APPROVED",
            }
        )
    base = {
        "schema_version": successor.BASE_SCHEMA,
        "draft_type": "price_calculator_input_draft",
        "source": {"project_id": successor.PROJECT_ID, "existing": "unchanged"},
        "cabinet_groups": [
            {
                "cabinet_group_id": f"CABINET-GROUP-{index:03d}",
                "row_draft_ids": row_ids if index == 1 else [],
                "marker": index,
            }
            for index in range(1, 15)
        ],
        "calculator_input_format": {
            "kind": "confirmed_composition_csv_row_drafts",
            "delimiter": ";",
            "columns": ["component_qty"],
            "row_drafts": base_rows,
        },
        "coverage": {"pricing_row_draft_count": 109, "cabinet_group_count": 14},
        "safety": {"priced": False},
        "next_required_human_actions": [],
    }

    corrections = []
    section_components: dict[str, list[dict[str, Any]]] = {
        section: [] for section in ("9", "11", "13", "15")
    }
    for row_id in successor.AFFECTED_ROW_IDS:
        quantity_required = row_id in successor.QUANTITY_ROW_IDS
        current_quantity = 2 if quantity_required else 1
        evidence_id = f"EVIDENCE-{row_id}"
        signature = {"mapping_request_id": ROW_TO_MAPPING[row_id]}
        corrections.append(
            {
                "row_draft_id": row_id,
                "section": ROW_TO_SECTION[row_id],
                "component_evidence_id": evidence_id,
                "mapping_request_id": ROW_TO_MAPPING[row_id],
                "technical_signature": signature,
                "current_pricing_component_qty": current_quantity,
                "corrected_component_qty": 1,
                "superseded_quantity": current_quantity if quantity_required else None,
                "quantity_correction_required": quantity_required,
                "decision_effect": (
                    successor.QUANTITY_EFFECT
                    if quantity_required
                    else successor.PROVENANCE_EFFECT
                ),
                "decision_status": "IGOR_CORRECTION_APPROVED_NOT_APPLIED",
                "source_quantity_decision_id": f"HDA-022-{row_id}",
                "source_paths": {
                    "pricing_row": (
                        f"$.calculator_input_format.row_drafts[{int(row_id[-4:]) - 1}]"
                    )
                },
            }
        )
        section_components[ROW_TO_SECTION[row_id]].append(
            {
                "row_draft_id": row_id,
                "component_evidence_id": evidence_id,
                "quantity_per_individual_cabinet": 1,
            }
        )
    correction = {
        "schema_version": successor.CORRECTION_SCHEMA,
        "artifact_type": "human_decisions",
        "project_id": successor.PROJECT_ID,
        "decision_id": successor.DECISION_ID,
        "authority": {
            "authority": "IGOR_DIRECT_HUMAN_APPROVAL",
            "no_scope_expansion": True,
        },
        "immutable_state": {
            "immutable": True,
            "no_overwrite": True,
            "application_status": "NOT_APPLIED",
        },
        "exact_section_compositions": [
            {"section": section, "calculator_components": components}
            for section, components in section_components.items()
        ],
        "exact_row_corrections": corrections,
        "application_boundary": {"corrections_applied": False},
    }

    grouped_rows: dict[str, list[str]] = {
        f"COMPONENT-MAPPING-{index:03d}": [] for index in range(1, 32)
    }
    unaffected_mapping_ids = [
        mapping_id
        for mapping_id in grouped_rows
        if mapping_id not in set(ROW_TO_MAPPING.values())
    ]
    unaffected_position = 0
    for row_id in row_ids:
        mapped_id = ROW_TO_MAPPING.get(row_id)
        if mapped_id is None:
            mapped_id = unaffected_mapping_ids[
                unaffected_position % len(unaffected_mapping_ids)
            ]
            unaffected_position += 1
        grouped_rows[mapped_id].append(row_id)

    component_groups = []
    for mapping_id, mapping_rows in grouped_rows.items():
        affected_rows = [row_id for row_id in mapping_rows if row_id in ROW_TO_MAPPING]
        signature = {"mapping_request_id": mapping_id}
        correction_positions = [
            index
            for index, item in enumerate(corrections)
            if item["mapping_request_id"] == mapping_id
        ]
        group = {
            "review_group_id": mapping_id.replace("MAPPING", "LABEL-REVIEW"),
            "mapping_request_id": mapping_id,
            "row_draft_ids": mapping_rows,
            "row_component_qty_per_individual_cabinet": {
                row_id: 1 for row_id in mapping_rows
            },
            "component_evidence_ids": [f"EVIDENCE-{row_id}" for row_id in mapping_rows],
            "technical_signature": signature,
            "quantity_decision_ids": (
                [successor.DECISION_ID] if affected_rows else ["HDA-022-UNCHANGED"]
            ),
            "superseded_quantity_decision_ids": [
                f"HDA-022-{row_id}" for row_id in affected_rows
            ],
            "scope": {
                "affected_rows_exact": mapping_rows,
                "section_provenance_verified": bool(affected_rows),
            },
            "authoritative_correction_provenance": {
                "sha256": successor.CORRECTION_SHA256,
                "json_paths": [
                    f"$.exact_row_corrections[{position}]"
                    for position in correction_positions
                ],
            },
        }
        component_groups.append(group)
    parent = {
        "schema_version": successor.PARENT_SCHEMA,
        "project_id": successor.PROJECT_ID,
        "source_lineage": {
            "pr_section_composition_human_decision": {
                "path": "UNBOUND-CORRECTION-PATH",
                "sha256": successor.CORRECTION_SHA256,
                "schema_version": successor.CORRECTION_SCHEMA,
                "immutable": True,
                "application_status": "NOT_APPLIED",
            }
        },
        "pr_section_composition_correction": {
            "decision_id": successor.DECISION_ID,
            "decision_artifact_path": "UNBOUND-CORRECTION-PATH",
            "corrected_row_count": 18,
        },
        "component_label_review_groups": component_groups,
    }
    return base, correction, parent


def bind_parent_correction_path(parent: dict[str, Any], correction_path: Path) -> None:
    exact_path = str(correction_path)
    parent["source_lineage"]["pr_section_composition_human_decision"][
        "path"
    ] = exact_path
    parent["pr_section_composition_correction"]["decision_artifact_path"] = exact_path
    for group in parent["component_label_review_groups"]:
        if any(
            row_id in successor.AFFECTED_ROW_IDS for row_id in group["row_draft_ids"]
        ):
            group["authoritative_correction_provenance"]["path"] = exact_path


def build_fixture(
    tmp_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    base, correction, parent = fixture_contracts()
    correction_path = tmp_path / "correction.json"
    bind_parent_correction_path(parent, correction_path)
    payload = successor.build_successor_payload(
        base,
        correction,
        parent,
        base_path=tmp_path / "base.json",
        correction_path=correction_path,
        parent_path=tmp_path / "parent.json",
    )
    return payload, base, correction, parent


def row_index(value: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        row["row_id"]: row for row in value["calculator_input_format"]["row_drafts"]
    }


def test_successor_changes_exact_10_quantities_and_18_provenances(
    tmp_path: Path,
) -> None:
    payload, base, _correction, _parent = build_fixture(tmp_path)
    actual = row_index(payload)
    original = row_index(base)

    for row_id in successor.QUANTITY_ROW_IDS:
        expected = copy.deepcopy(original[row_id])
        expected["calculator_values"]["component_qty"] = 1
        expected["source_quantity"] = actual[row_id]["source_quantity"]
        assert actual[row_id] == expected
        assert actual[row_id]["source_quantity"]["decision_effect"] == (
            successor.QUANTITY_EFFECT
        )
    for row_id in successor.PROVENANCE_ROW_IDS:
        expected = copy.deepcopy(original[row_id])
        expected["source_quantity"] = actual[row_id]["source_quantity"]
        assert actual[row_id] == expected
        assert actual[row_id]["calculator_values"]["component_qty"] == 1
        assert actual[row_id]["source_quantity"]["decision_effect"] == (
            successor.PROVENANCE_EFFECT
        )


def test_successor_preserves_91_rows_with_hda_and_all_14_cabinet_groups(
    tmp_path: Path,
) -> None:
    payload, base, correction, parent = build_fixture(tmp_path)
    actual = row_index(payload)
    original = row_index(base)
    unaffected = sorted(set(original) - set(successor.AFFECTED_ROW_IDS))

    assert len(unaffected) == 91
    assert all(actual[row_id] == original[row_id] for row_id in unaffected)
    assert all(
        "HDA-022" in actual[row_id]["source_quantity"]["decision_id"]
        for row_id in unaffected
    )
    assert payload["cabinet_groups"] == base["cabinet_groups"]
    assert "status" not in correction
    successor.validate_successor_payload(
        payload,
        base,
        correction,
        parent,
        base_path=tmp_path / "base.json",
        correction_path=tmp_path / "correction.json",
        parent_path=tmp_path / "parent.json",
    )


def test_successor_metadata_has_exact_split_and_sorted_lists(tmp_path: Path) -> None:
    payload, base, _correction, _parent = build_fixture(tmp_path)
    metadata = payload["source"]["quantity_correction_successor"]
    all_ids = sorted(row_index(base))
    unaffected = sorted(set(all_ids) - set(successor.AFFECTED_ROW_IDS))

    assert metadata["affected_row_count"] == 18
    assert metadata["quantity_corrected_row_count"] == 10
    assert metadata["provenance_reconfirmed_row_count"] == 8
    assert metadata["unchanged_row_count"] == 91
    assert metadata["quantity_corrected_row_ids"] == sorted(
        metadata["quantity_corrected_row_ids"]
    )
    assert metadata["provenance_reconfirmed_row_ids"] == sorted(
        metadata["provenance_reconfirmed_row_ids"]
    )
    assert metadata["unchanged_row_ids"] == unaffected
    assert metadata["scope_expansion"] is False


def test_hda_022_is_forbidden_only_in_affected_source_quantity(
    tmp_path: Path,
) -> None:
    payload, base, correction, parent = build_fixture(tmp_path)
    actual = row_index(payload)

    assert all(
        not successor.contains_hda_022(actual[row_id]["source_quantity"])
        for row_id in successor.AFFECTED_ROW_IDS
    )
    assert "HDA-022" in json.dumps(payload, ensure_ascii=False)
    successor.validate_successor_payload(
        payload,
        base,
        correction,
        parent,
        base_path=tmp_path / "base.json",
        correction_path=tmp_path / "correction.json",
        parent_path=tmp_path / "parent.json",
    )


def test_changing_unaffected_source_quantity_fails(tmp_path: Path) -> None:
    payload, base, correction, parent = build_fixture(tmp_path)
    row_index(payload)["ROW-DRAFT-0020"]["source_quantity"] = {
        "decision_id": successor.DECISION_ID
    }

    with pytest.raises(successor.SuccessorError, match="unaffected row changed"):
        successor.validate_successor_payload(
            payload,
            base,
            correction,
            parent,
            base_path=tmp_path / "base.json",
            correction_path=tmp_path / "correction.json",
            parent_path=tmp_path / "parent.json",
        )


def test_reordered_successor_rows_fail(tmp_path: Path) -> None:
    payload, base, correction, parent = build_fixture(tmp_path)
    rows = payload["calculator_input_format"]["row_drafts"]
    rows[0], rows[1] = rows[1], rows[0]

    with pytest.raises(successor.SuccessorError, match="row order"):
        successor.validate_successor_payload(
            payload,
            base,
            correction,
            parent,
            base_path=tmp_path / "base.json",
            correction_path=tmp_path / "correction.json",
            parent_path=tmp_path / "parent.json",
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("evidence", "correction scope|authority mismatch"),
        ("mapping", "authority mismatch"),
        ("signature", "authority mismatch"),
        ("pricing_path", "authority mismatch"),
        ("section", "correction scope"),
        ("parent_sha", "per-group correction provenance"),
        ("parent_json_path", "per-group correction provenance"),
        ("parent_scope", "authority mismatch"),
    ],
)
def test_affected_exact_provenance_mismatch_fails(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    payload, base, correction, parent = build_fixture(tmp_path)
    item = correction["exact_row_corrections"][0]
    parent_group = parent["component_label_review_groups"][0]
    if mutation == "evidence":
        item["component_evidence_id"] = "WRONG-EVIDENCE"
    elif mutation == "mapping":
        item["mapping_request_id"] = "COMPONENT-MAPPING-999"
    elif mutation == "signature":
        item["technical_signature"] = {"wrong": True}
    elif mutation == "pricing_path":
        item["source_paths"]["pricing_row"] = "$.calculator_input_format.row_drafts[1]"
    elif mutation == "section":
        item["section"] = "999"
    elif mutation == "parent_sha":
        parent_group["authoritative_correction_provenance"]["sha256"] = "0" * 64
    elif mutation == "parent_json_path":
        parent_group["authoritative_correction_provenance"]["json_paths"].remove(
            "$.exact_row_corrections[0]"
        )
    else:
        parent_group["scope"]["section_provenance_verified"] = False

    with pytest.raises(successor.SuccessorError, match=message):
        successor.validate_successor_payload(
            payload,
            base,
            correction,
            parent,
            base_path=tmp_path / "base.json",
            correction_path=tmp_path / "correction.json",
            parent_path=tmp_path / "parent.json",
        )


def test_affected_source_quantity_with_hda_022_fails(tmp_path: Path) -> None:
    payload, base, correction, parent = build_fixture(tmp_path)
    row_index(payload)["ROW-DRAFT-0001"]["source_quantity"][
        "legacy_decision_id"
    ] = "HDA-022-STALE"

    with pytest.raises(successor.SuccessorError, match="HDA-022"):
        successor.validate_successor_payload(
            payload,
            base,
            correction,
            parent,
            base_path=tmp_path / "base.json",
            correction_path=tmp_path / "correction.json",
            parent_path=tmp_path / "parent.json",
        )


def test_wrong_affected_source_quantity_correction_json_path_fails(
    tmp_path: Path,
) -> None:
    payload, base, correction, parent = build_fixture(tmp_path)
    row_index(payload)["ROW-DRAFT-0001"]["source_quantity"][
        "decision_json_path"
    ] = "$.exact_row_corrections[1]"

    with pytest.raises(successor.SuccessorError, match="outside exact scope"):
        successor.validate_successor_payload(
            payload,
            base,
            correction,
            parent,
            base_path=tmp_path / "base.json",
            correction_path=tmp_path / "correction.json",
            parent_path=tmp_path / "parent.json",
        )


def test_correction_source_quantity_decision_must_match_base(
    tmp_path: Path,
) -> None:
    payload, base, correction, parent = build_fixture(tmp_path)
    correction["exact_row_corrections"][0][
        "source_quantity_decision_id"
    ] = "HDA-022-WRONG"

    with pytest.raises(successor.SuccessorError, match="authority mismatch"):
        successor.validate_successor_payload(
            payload,
            base,
            correction,
            parent,
            base_path=tmp_path / "base.json",
            correction_path=tmp_path / "correction.json",
            parent_path=tmp_path / "parent.json",
        )


@pytest.mark.parametrize(
    ("row_id", "value", "message"),
    [
        ("ROW-DRAFT-0001", None, "superseded quantity mismatch"),
        ("ROW-DRAFT-0001", 999, "superseded quantity mismatch"),
        ("ROW-DRAFT-0006", 1, "provenance-only quantity semantics"),
    ],
)
def test_superseded_quantity_semantics_are_exact(
    tmp_path: Path,
    row_id: str,
    value: int | None,
    message: str,
) -> None:
    payload, base, correction, parent = build_fixture(tmp_path)
    correction_item = next(
        item
        for item in correction["exact_row_corrections"]
        if item["row_draft_id"] == row_id
    )
    correction_item["superseded_quantity"] = value

    with pytest.raises(successor.SuccessorError, match=message):
        successor.validate_successor_payload(
            payload,
            base,
            correction,
            parent,
            base_path=tmp_path / "base.json",
            correction_path=tmp_path / "correction.json",
            parent_path=tmp_path / "parent.json",
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("lineage_path", "parent correction lineage"),
        ("lineage_sha", "parent correction lineage"),
        ("lineage_schema", "parent correction lineage"),
        ("lineage_immutable", "parent correction lineage"),
        ("lineage_application", "parent correction lineage"),
        ("summary_path", "parent correction summary"),
        ("summary_decision", "parent correction summary"),
        ("summary_count", "parent correction summary"),
        ("group_path", "per-group correction provenance"),
        ("group_paths_extra", "per-group correction provenance"),
        ("group_paths_reordered", "per-group correction provenance"),
    ],
)
def test_parent_correction_lineage_is_fully_exact_bound(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    payload, base, correction, parent = build_fixture(tmp_path)
    lineage = parent["source_lineage"]["pr_section_composition_human_decision"]
    summary = parent["pr_section_composition_correction"]
    provenance = parent["component_label_review_groups"][0][
        "authoritative_correction_provenance"
    ]
    if mutation == "lineage_path":
        lineage["path"] = str(tmp_path / "wrong.json")
    elif mutation == "lineage_sha":
        lineage["sha256"] = "0" * 64
    elif mutation == "lineage_schema":
        lineage["schema_version"] = "wrong"
    elif mutation == "lineage_immutable":
        lineage["immutable"] = False
    elif mutation == "lineage_application":
        lineage["application_status"] = "APPLIED"
    elif mutation == "summary_path":
        summary["decision_artifact_path"] = str(tmp_path / "wrong.json")
    elif mutation == "summary_decision":
        summary["decision_id"] = "WRONG"
    elif mutation == "summary_count":
        summary["corrected_row_count"] = 17
    elif mutation == "group_path":
        provenance["path"] = str(tmp_path / "wrong.json")
    elif mutation == "group_paths_extra":
        provenance["json_paths"].append("$.exact_row_corrections[17]")
    else:
        provenance["json_paths"].reverse()

    with pytest.raises(successor.SuccessorError, match=message):
        successor.validate_successor_payload(
            payload,
            base,
            correction,
            parent,
            base_path=tmp_path / "base.json",
            correction_path=tmp_path / "correction.json",
            parent_path=tmp_path / "parent.json",
        )


@pytest.mark.parametrize("mutation", ["missing", "extra", "wrong", "misclassified"])
def test_missing_extra_or_misclassified_correction_scope_fails(
    mutation: str,
) -> None:
    _base, correction, _parent = fixture_contracts()
    if mutation == "missing":
        correction["exact_row_corrections"].pop()
    elif mutation == "extra":
        correction["exact_row_corrections"].append(
            copy.deepcopy(correction["exact_row_corrections"][0])
        )
    elif mutation == "wrong":
        correction["exact_row_corrections"][0]["row_draft_id"] = "ROW-DRAFT-0020"
    else:
        correction["exact_row_corrections"][0]["quantity_correction_required"] = False

    with pytest.raises(successor.SuccessorError):
        successor.validate_correction(correction)


def write_json(path: Path, value: Any) -> str:
    content = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def exact_bound_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, Path]:
    base, correction, parent = fixture_contracts()
    correction_path = tmp_path / "correction.json"
    correction_sha = write_json(correction_path, correction)
    monkeypatch.setattr(successor, "CORRECTION_SHA256", correction_sha)
    parent["source_lineage"]["pr_section_composition_human_decision"][
        "sha256"
    ] = correction_sha
    for group in parent["component_label_review_groups"]:
        group["authoritative_correction_provenance"]["sha256"] = correction_sha
    bind_parent_correction_path(parent, correction_path)
    base_path = tmp_path / "base.json"
    base_sha = write_json(base_path, base)
    monkeypatch.setattr(successor, "BASE_SHA256", base_sha)
    parent_path = tmp_path / "parent.json"
    parent_sha = write_json(parent_path, parent)
    monkeypatch.setattr(successor, "PARENT_SHA256", parent_sha)
    return base_path, correction_path, parent_path


def exact_bound_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, Any], Path, Path, Path]:
    base_path, correction_path, parent_path = exact_bound_files(tmp_path, monkeypatch)
    base = json.loads(base_path.read_text(encoding="utf-8"))
    correction = json.loads(correction_path.read_text(encoding="utf-8"))
    parent = json.loads(parent_path.read_text(encoding="utf-8"))
    payload = successor.build_successor_payload(
        base,
        correction,
        parent,
        base_path=base_path,
        correction_path=correction_path,
        parent_path=parent_path,
    )
    return payload, base_path, correction_path, parent_path


def test_valid_synthetic_embedded_successor_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload, _base_path, _correction_path, _parent_path = exact_bound_payload(
        tmp_path, monkeypatch
    )

    successor.validate_embedded_successor(payload)


@pytest.mark.parametrize("drift_role", ["base", "correction", "parent"])
def test_each_transitive_input_drift_during_validation_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    drift_role: str,
) -> None:
    payload, base_path, correction_path, parent_path = exact_bound_payload(
        tmp_path, monkeypatch
    )
    paths = {
        "base": base_path,
        "correction": correction_path,
        "parent": parent_path,
    }
    original_validate = successor.validate_successor_payload

    def validate_then_drift(*args: Any, **kwargs: Any) -> None:
        original_validate(*args, **kwargs)
        paths[drift_role].write_text("drift", encoding="utf-8")

    monkeypatch.setattr(successor, "validate_successor_payload", validate_then_drift)
    descriptions = {
        "base": "base draft",
        "correction": "correction artifact",
        "parent": "parent packet",
    }
    with pytest.raises(
        successor.SuccessorError,
        match=f"transitive {descriptions[drift_role]} changed",
    ):
        successor.validate_embedded_successor(payload)


def test_builder_requires_authorization_without_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base_path, correction_path, parent_path = exact_bound_files(tmp_path, monkeypatch)
    output = tmp_path / "unauthorized.json"

    with pytest.raises(successor.SuccessorError, match="authorization required"):
        successor.publish_successor(
            base_json=base_path,
            correction_json=correction_path,
            parent_packet_json=parent_path,
            output_json=output,
            successor_build_authorized_by_igor=False,
        )
    assert not output.exists()


def test_builder_refuses_existing_output_without_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base_path, correction_path, parent_path = exact_bound_files(tmp_path, monkeypatch)
    output = tmp_path / "existing.json"
    output.write_text("keep", encoding="utf-8")

    with pytest.raises(successor.SuccessorError, match="overwrite is forbidden"):
        successor.publish_successor(
            base_json=base_path,
            correction_json=correction_path,
            parent_packet_json=parent_path,
            output_json=output,
            successor_build_authorized_by_igor=True,
        )
    assert output.read_text(encoding="utf-8") == "keep"


def test_builder_refuses_output_inside_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base_path, correction_path, parent_path = exact_bound_files(tmp_path, monkeypatch)
    output = successor.PROJECT_ROOT / "forbidden-successor-test-output.json"
    assert not output.exists()

    with pytest.raises(successor.SuccessorError, match="outside the Git project"):
        successor.publish_successor(
            base_json=base_path,
            correction_json=correction_path,
            parent_packet_json=parent_path,
            output_json=output,
            successor_build_authorized_by_igor=True,
        )
    assert not output.exists()


@pytest.mark.parametrize(
    "role",
    ["BASE_SHA256", "CORRECTION_SHA256", "PARENT_SHA256"],
)
def test_builder_rejects_each_exact_sha_mismatch_without_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    role: str,
) -> None:
    base_path, correction_path, parent_path = exact_bound_files(tmp_path, monkeypatch)
    output = tmp_path / f"sha-mismatch-{role}.json"
    monkeypatch.setattr(successor, role, "0" * 64)

    with pytest.raises(successor.SuccessorError, match="SHA-256 mismatch"):
        successor.publish_successor(
            base_json=base_path,
            correction_json=correction_path,
            parent_packet_json=parent_path,
            output_json=output,
            successor_build_authorized_by_igor=True,
        )
    assert not output.exists()


def test_builder_input_drift_cleans_output_and_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base_path, correction_path, parent_path = exact_bound_files(tmp_path, monkeypatch)
    output = tmp_path / "input-drift.json"
    original_build = successor.build_successor_payload

    def build_then_drift(*args: Any, **kwargs: Any) -> dict[str, Any]:
        payload = original_build(*args, **kwargs)
        base_path.write_text("drift", encoding="utf-8")
        return cast(dict[str, Any], payload)

    monkeypatch.setattr(successor, "build_successor_payload", build_then_drift)
    with pytest.raises(successor.SuccessorError, match="input changed"):
        successor.publish_successor(
            base_json=base_path,
            correction_json=correction_path,
            parent_packet_json=parent_path,
            output_json=output,
            successor_build_authorized_by_igor=True,
        )
    assert not output.exists()
    assert not list(tmp_path.glob(".*.staging"))


def test_publication_is_exclusive_and_cleans_staging_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base_path, correction_path, parent_path = exact_bound_files(tmp_path, monkeypatch)
    output = tmp_path / "successor.json"

    def fail_link(_source: Path, _target: Path) -> None:
        raise OSError("simulated publication failure")

    monkeypatch.setattr(successor.os, "link", fail_link)
    with pytest.raises(successor.SuccessorError, match="publication failed"):
        successor.publish_successor(
            base_json=base_path,
            correction_json=correction_path,
            parent_packet_json=parent_path,
            output_json=output,
            successor_build_authorized_by_igor=True,
        )
    assert not output.exists()
    assert not list(tmp_path.glob(".*.staging"))


def test_publication_recheck_read_error_is_controlled_and_cleans_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_path, correction_path, parent_path = exact_bound_files(tmp_path, monkeypatch)
    output = tmp_path / "read-error.json"
    original_read_bytes = Path.read_bytes
    base_reads = 0

    def fail_second_base_read(path: Path) -> bytes:
        nonlocal base_reads
        if path == base_path:
            base_reads += 1
            if base_reads == 2:
                raise OSError("simulated publication recheck read failure")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", fail_second_base_read)
    with pytest.raises(successor.SuccessorError, match="cannot be rechecked"):
        successor.publish_successor(
            base_json=base_path,
            correction_json=correction_path,
            parent_packet_json=parent_path,
            output_json=output,
            successor_build_authorized_by_igor=True,
        )
    assert not output.exists()
    assert not list(tmp_path.glob(".*.staging"))


def test_builder_is_hard_bound_to_authoritative_hashes() -> None:
    assert successor.BASE_SHA256 == (
        "571647f920f2ffcbfda66339c20be4673eb41127c0534054695c3d4cfc15fbf3"
    )
    assert successor.CORRECTION_SHA256 == (
        "12d6887edd44c3f13e5b7b5126a8441fa9a6aff350f7eae6ea81da7b4c1abc13"
    )
    assert successor.PARENT_SHA256 == (
        "1c68b9af8edfef2ca42f89c69e70a873553595d096413f197f9bfe77ec80fc00"
    )
