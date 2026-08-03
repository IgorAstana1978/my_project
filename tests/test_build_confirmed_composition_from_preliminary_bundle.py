import copy
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, cast

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    PROJECT_ROOT / "scripts" / "build_confirmed_composition_from_preliminary_bundle.py"
)


def load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "confirmed_composition_builder_for_test",
        SCRIPT,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


builder = cast(Any, load_module())


def canonical_json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def provenance() -> list[dict[str, Any]]:
    return [
        {
            "source_file": "spec.xlsx",
            "source_type": "workbook",
            "locator": "sheet=Spec row=2 cells=A2:J2",
            "raw_text": "VRU-1 Breaker VA47 2 pcs",
            "confidence": 0.95,
            "reason": "synthetic test evidence",
            "sheet": "Spec",
            "row": 2,
            "cell_range": "A2:J2",
        }
    ]


def valid_draft(manifest_hash: str) -> dict[str, Any]:
    return {
        "schema_version": "preliminary_composition_draft.v0.1",
        "draft_id": "PRELIM-TEST-001",
        "created_by": "test",
        "created_at": "2099-01-01T00:00:00+05:00",
        "source": {
            "source_type": "other",
            "source_summary": "Synthetic source bundle.",
            "raw_input_sha256": manifest_hash,
            "source_files": [
                {
                    "file_name": "spec.xlsx",
                    "source_type": "workbook",
                    "sha256": "1" * 64,
                    "status": "text_available",
                    "sheets": [{"sheet": "Spec", "rows_checked": 10}],
                }
            ],
        },
        "safety": {
            "status": "preliminary_only",
            "confirmed_by_igor": False,
            "price_execution_authorized": False,
            "commercial_csv_authorized": False,
            "client_style_export_authorized": False,
            "sending_authorized": False,
            "production_authorized": False,
        },
        "items": [
            {
                "item_id": "ITEM-001",
                "product_name_guess": "Panel VRU-1",
                "product_type_guess": "switchboard",
                "quantity_guess": 1,
                "cabinet_guess": {
                    "code_guess": "CAB-24",
                    "label_guess": "24-module cabinet",
                    "confidence": 0.8,
                    "evidence": ["Synthetic cabinet evidence."],
                    "red_flags": [],
                },
                "components": [
                    {
                        "component_id": "COMP-001",
                        "component_code_guess": "VA47",
                        "component_label_guess": "Breaker VA47",
                        "quantity_guess": 2,
                        "install_type_guess": "modular_1p",
                        "confidence": 0.95,
                        "evidence": ["Synthetic component evidence."],
                        "red_flags": [],
                        "assumptions": [],
                        "requires_igor_confirmation": True,
                        "provenance": provenance(),
                        "conflicts": [],
                        "missing_fields": [],
                        "review_status": "requires_igor_review",
                    }
                ],
                "confidence": 0.9,
                "evidence": ["Synthetic item evidence."],
                "red_flags": [],
                "assumptions": [],
                "requires_igor_confirmation": True,
                "provenance": provenance(),
                "conflicts": [],
                "missing_fields": [],
                "questions_for_igor": [],
                "review_status": "requires_igor_review",
            }
        ],
        "overall_confidence": 0.9,
        "red_flags": [],
        "assumptions": [],
        "next_required_human_actions": ["Igor reviews technical composition."],
    }


def create_bundle(
    tmp_path: Path,
    *,
    case_id: str = "CASE-TEST-001",
    mutate_draft: Any = None,
    mismatched_manifest_hash: bool = False,
) -> tuple[Path, dict[str, Any]]:
    root = tmp_path / "production_ai_cases"
    case_dir = root / case_id
    case_dir.mkdir(parents=True)
    manifest_bytes = b'{"manifest_version":"mixed_source_bundle.v0.1","sources":[]}\n'
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    draft = valid_draft("0" * 64 if mismatched_manifest_hash else manifest_hash)
    if mutate_draft is not None:
        mutate_draft(draft)
    (case_dir / builder.MANIFEST_NAME).write_bytes(manifest_bytes)
    (case_dir / builder.DRAFT_NAME).write_bytes(canonical_json_bytes(draft))
    review = "\n".join(
        [
            "# Igor review",
            "",
            f"- raw_input_sha256: {draft['source']['raw_input_sha256']}",
            f"- draft_id: {draft['draft_id']}",
            "",
        ]
    )
    (case_dir / builder.REVIEW_NAME).write_text(review, encoding="utf-8")
    return root, draft


def create_batch_bundle(tmp_path: Path) -> tuple[Path, dict[str, Any], Path]:
    def add_batch_review_data(draft: dict[str, Any]) -> None:
        draft["red_flags"] = ["Synthetic source-quality warning."]
        draft["assumptions"] = ["Synthetic technical extraction assumption."]
        item = draft["items"][0]
        item["red_flags"] = ["Synthetic item review required."]
        item["cabinet_guess"]["red_flags"] = ["Synthetic cabinet review required."]
        component = item["components"][0]
        component.update(
            {
                "model_guess": "VA47",
                "brand_guess": None,
                "rating_guess": "16A",
                "note_guess": "Synthetic source note.",
                "red_flags": [
                    "Synthetic component review required.",
                    "Synthetic component has missing values.",
                ],
                "missing_fields": ["brand_guess"],
            }
        )

    root, draft = create_bundle(tmp_path, mutate_draft=add_batch_review_data)
    case_dir = root / "CASE-TEST-001"
    decisions = valid_batch_decisions(case_dir, draft)
    path = tmp_path / "batch-decisions.json"
    path.write_bytes(canonical_json_bytes(decisions))
    return root, draft, path


def valid_batch_decisions(case_dir: Path, draft: dict[str, Any]) -> dict[str, Any]:
    hashes = {
        "source_bundle_manifest": hashlib.sha256(
            (case_dir / builder.MANIFEST_NAME).read_bytes()
        ).hexdigest(),
        "preliminary_composition_draft": hashlib.sha256(
            (case_dir / builder.DRAFT_NAME).read_bytes()
        ).hexdigest(),
        "igor_review_card": hashlib.sha256(
            (case_dir / builder.REVIEW_NAME).read_bytes()
        ).hexdigest(),
    }
    component = draft["items"][0]["components"][0]
    return {
        "schema_version": builder.DECISIONS_INPUT_SCHEMA,
        "case_id": "CASE-TEST-001",
        "draft_id": draft["draft_id"],
        "input_sha256": hashes,
        "items": [
            {
                "item_id": "ITEM-001",
                "product_name": "Normalized panel VRU-1",
                "quantity": 1,
                "manufacturer": "CHINT",
                "acknowledged_red_flags": draft["items"][0]["red_flags"],
                "cabinet": {
                    "code": "CAB-24",
                    "label": "24-module cabinet",
                    "acknowledged_red_flags": draft["items"][0]["cabinet_guess"][
                        "red_flags"
                    ],
                },
                "component_groups": [
                    {
                        "component_ids": [component["component_id"]],
                        "total_quantity": component["quantity_guess"],
                        "final_description": "CHINT, automatic breaker 1P 16A",
                        "install_type": "modular_1p",
                        "substitution": None,
                        "acknowledged_red_flags": component["red_flags"],
                    }
                ],
            }
        ],
        "source_quality_acknowledgements": [
            {
                "source_path": "red_flags[0]",
                "warning": draft["red_flags"][0],
                "reason": "Igor reviewed the synthetic source warning.",
            }
        ],
        "technical_assumption_resolutions": [
            {
                "source_path": "assumptions[0]",
                "assumption": draft["assumptions"][0],
                "resolution": "resolved_by_explicit_composition_decisions",
                "reason": "Every synthetic component is explicitly decided.",
            }
        ],
        "supply_boundary": "Synthetic panel supply only.",
    }


SYNTHETIC_APPROVAL = "SYNTHETIC TECHNICAL APPROVAL"


def run_batch(
    root: Path,
    decisions_path: Path,
    *,
    approval: str = SYNTHETIC_APPROVAL,
    before_drift_check: Any = None,
) -> Any:
    return builder.run_builder(
        case_id="CASE-TEST-001",
        confirmation_id="CONFIRM-TEST-BATCH-001",
        approval_channel="synthetic_test",
        decisions_json=decisions_path,
        canonical_root=root,
        input_fn=answers([approval]),
        output_fn=lambda _value: None,
        now_fn=fixed_now,
        before_drift_check=before_drift_check,
        approval_phrase=SYNTHETIC_APPROVAL,
    )


def fixed_now() -> datetime:
    return datetime(2099, 1, 1, 12, 30, tzinfo=timezone(timedelta(hours=5)))


def answers(values: list[str]) -> Any:
    iterator = iter(values)
    return lambda _prompt: next(iterator)


def recording_answers(prompts: list[str]) -> Any:
    def ask(prompt: str) -> str:
        prompts.append(prompt)
        return ""

    return ask


def successful_answers() -> list[str]:
    return [
        "correct",
        "CAB-24 | 24-module cabinet",
        "correct",
        "Panel supply only",
        builder.APPROVAL_PHRASE,
    ]


def run_success(tmp_path: Path) -> Any:
    root, _draft = create_bundle(tmp_path)
    return builder.run_builder(
        case_id="CASE-TEST-001",
        confirmation_id="CONFIRM-TEST-001",
        approval_channel="local_terminal",
        canonical_root=root,
        input_fn=answers(successful_answers()),
        output_fn=lambda _value: None,
        now_fn=fixed_now,
    )


def read_outputs(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any], str]:
    output = (
        tmp_path / "production_ai_cases" / "CASE-TEST-001" / builder.OUTPUT_DIR_NAME
    )
    artifact = json.loads((output / builder.ARTIFACT_NAME).read_text("utf-8"))
    decisions = json.loads((output / builder.DECISIONS_NAME).read_text("utf-8"))
    receipt = (output / builder.RECEIPT_NAME).read_text("utf-8")
    return artifact, decisions, receipt


def applied_signature(label: str) -> dict[str, Any]:
    return {
        "cabinet_template": "SYNTHETIC-CABINET",
        "component_identity": label,
        "model_type": "SYNTHETIC",
        "ratings": ["16A"],
        "poles": 1,
        "functional_role": "synthetic test component",
    }


def applied_overlay_signature(label: str) -> dict[str, Any]:
    value = applied_signature(label)
    del value["cabinet_template"]
    return value


def applied_member(component_id: str, label: str, index: int) -> dict[str, Any]:
    return {
        "component_evidence_id": component_id,
        "evidence_position_id": f"POS-{index:03d}",
        "section": "SYNTHETIC",
        "source_locator": f"row={index}",
        "canonical_label": label,
        "canonical_document_id": "DOC-SYNTHETIC",
        "canonical_source_status": "identified",
        "canonical_provenance": {"row_locator": f"row={index}"},
    }


def valid_applied_bundle() -> dict[str, Any]:
    canonical_records: list[dict[str, Any]] = []
    direct: list[dict[str, Any]] = []
    aggregates: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    overlays: list[dict[str, Any]] = []
    reserved: list[dict[str, Any]] = []
    for index in range(1, 23):
        component_id = f"COMP-{index:03d}"
        label = f"Synthetic component {index}"
        canonical_records.append(
            {
                "component_evidence_id": component_id,
                "document_id": "DOC-SYNTHETIC",
                "label": label,
                "position_id": f"POS-{index:03d}",
                "provenance": {"row_locator": f"row={index}"},
                "section_id": "SYNTHETIC",
                "source_status": "identified",
            }
        )
        member = applied_member(component_id, label, index)
        signature = applied_signature(label)
        common = {
            "decision_id": f"DEC-{index:03d}",
            "decision_code": f"CODE-{index:03d}",
            "component_signature": signature,
            "members": [member],
            "application_status": "APPLIED",
        }
        if index <= 17:
            direct.append(
                {
                    **common,
                    "decision_kind": "DIRECT_COMPONENT_QUANTITY",
                    "quantity_per_cabinet": index,
                }
            )
        elif index == 18:
            aggregates.append(
                {
                    **common,
                    "decision_kind": "CABINET_LEVEL_AGGREGATE",
                    "aggregate_quantity_per_cabinet": 3,
                    "applies_once_per_cabinet": True,
                    "multiply_by_member_count": False,
                }
            )
        else:
            exclusions.append(
                {
                    **common,
                    "decision_kind": "SCOPE_EXCLUSION",
                    "scope_status": "EXCLUDED_RESERVED_SPACE_ONLY",
                    "future_inclusion_requires": "SEPARATE_IGOR_APPROVAL",
                    "prohibited_downstream": ["pricing", "production"],
                }
            )
        if index <= 18:
            kind = (
                "COMPONENT_SIGNATURE_CORRECTION"
                if index <= 12
                else "COMPONENT_RECONFIRMATION"
            )
            overlays.append(
                {
                    "item_id": f"ITEM-{index:03d}",
                    "item_kind": kind,
                    "cabinet_record_id": f"CAB-{index:03d}",
                    "cabinet_template": "SYNTHETIC-CABINET",
                    "component_evidence_id": component_id,
                    "position_id": f"POS-{index:03d}",
                    "section": "SYNTHETIC",
                    "source_locator": f"row={index}",
                    "original_signature": applied_overlay_signature(label),
                    "approved_signature": applied_overlay_signature(label),
                    "quantity_per_cabinet": index,
                    "provenance": {"source_locator": f"row={index}"},
                    "correction_reason": "synthetic confirmation",
                    "canonical_evidence_modified": False,
                    "application_status": "APPLIED",
                }
            )
        else:
            reserved.append(
                {
                    "item_id": f"ITEM-{index:03d}",
                    "item_kind": "RESERVED_METER_SPACE",
                    "cabinet_record_id": f"CAB-{index:03d}",
                    "cabinet_template": "SYNTHETIC-CABINET",
                    "component_evidence_id": component_id,
                    "position_id": f"POS-{index:03d}",
                    "section": "SYNTHETIC",
                    "source_locator": f"row={index}",
                    "requirement_kind": "RESERVED_METER_SPACE",
                    "meter_connection": "THREE_PHASE_DIRECT",
                    "reserved_space_per_cabinet": 1,
                    "installed_component": False,
                    "original_identity": label,
                    "provenance": {"source_locator": f"row={index}"},
                    "future_inclusion_requires": "SEPARATE_IGOR_APPROVAL",
                    "prohibited_downstream": ["pricing", "production"],
                    "canonical_evidence_modified": False,
                    "application_status": "APPLIED",
                }
            )
    coverage = {
        "canonical_component_count": 22,
        "prior_direct_component_count": 17,
        "prior_aggregate_member_count": 1,
        "prior_exclusion_component_count": 4,
        "prior_union_component_count": 22,
        "component_signature_correction_count": 12,
        "component_reconfirmation_count": 6,
        "reserved_meter_space_count": 4,
        "overlay_component_count": 22,
    }
    return {
        "schema_version": "component_replay_applied_bundle.v0.23",
        "project_id": "CASE-SYNTHETIC-V023",
        "application_status": "APPLIED",
        "authority": "IGOR_DIRECT_HUMAN_APPROVAL",
        "application_order": [
            "human_decisions_batch.v0.22",
            "human_decisions_batch.v0.23",
        ],
        "source_lineage": {
            "canonical_replay_sha256": "1" * 64,
            "canonical_replay_schema_version": (
                "component_replay_readiness_bundle.v0.2"
            ),
            "prior_batch_sha256": "2" * 64,
            "prior_batch_schema_version": "human_decisions_batch.v0.22",
            "prior_batch_id": "022",
            "correction_batch_sha256": "3" * 64,
            "correction_batch_schema_version": "human_decisions_batch.v0.23",
            "correction_batch_id": "023",
            "correction_prior_batch_id": "022",
        },
        "canonical_component_evidence_records": canonical_records,
        "prior_v0_22_application": {
            "application_status": "APPLIED",
            "direct_component_quantities": direct,
            "cabinet_level_aggregates": aggregates,
            "scope_exclusions": exclusions,
            "coverage": {
                "direct_component_count": 17,
                "aggregate_member_count": 1,
                "exclusion_component_count": 4,
                "union_component_count": 22,
            },
        },
        "component_signature_overlays": overlays,
        "reserved_meter_space_requirements": reserved,
        "coverage": coverage,
        "confirmed_composition_created": False,
        "pricing_started": False,
        "downstream_started": False,
    }


def write_applied_bundle(
    tmp_path: Path,
    data: dict[str, Any] | None = None,
) -> Path:
    source_dir = tmp_path / "applied-source"
    source_dir.mkdir()
    path = source_dir / "component-replay-applied-bundle-v0.23.json"
    path.write_bytes(canonical_json_bytes(data or valid_applied_bundle()))
    return path


def read_applied_outputs(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    output_dir = path.parent / builder.OUTPUT_DIR_NAME
    artifact = json.loads(
        (output_dir / builder.ARTIFACT_NAME).read_text(encoding="utf-8")
    )
    decisions = json.loads(
        (output_dir / builder.DECISIONS_NAME).read_text(encoding="utf-8")
    )
    return artifact, decisions


def test_valid_automatic_transfer_classifies_reliable_values(tmp_path: Path) -> None:
    root, _draft = create_bundle(tmp_path)
    paths = builder.resolve_case_paths("CASE-TEST-001", canonical_root=root)
    snapshot = builder.load_snapshot(paths)

    state = builder.classify_composition(snapshot.draft)
    targets = {value.target_path for value in state.automatic_transfers}

    assert "items[0].product_name" in targets
    assert "items[0].quantity" in targets
    assert "items[0].components[0].component_code" in targets
    assert "items[0].components[0].component_label" in targets
    assert "items[0].components[0].quantity" in targets
    assert "items[0].components[0].install_type" in targets


def test_conflict_requires_explicit_correction(tmp_path: Path) -> None:
    def add_conflict(draft: dict[str, Any]) -> None:
        component = draft["items"][0]["components"][0]
        component["conflicts"] = [
            {
                "conflict_id": "CONFLICT-1",
                "type": "component_quantity_mismatch",
                "field": "quantity",
                "message": "different quantities",
                "sources": provenance(),
            }
        ]

    root, _draft = create_bundle(tmp_path, mutate_draft=add_conflict)
    snapshot = builder.load_snapshot(
        builder.resolve_case_paths("CASE-TEST-001", canonical_root=root)
    )

    state = builder.classify_composition(snapshot.draft)

    assert any(
        issue.target_path == ("items", 0, "components", 0, "quantity")
        and "correct" in issue.allowed_actions
        for issue in state.issues
    )
    assert not any(
        transfer.target_path == "items[0].components[0].quantity"
        for transfer in state.automatic_transfers
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("product_name_guess", None),
        ("product_name_guess", "unresolved"),
    ],
)
def test_missing_or_unresolved_required_field_blocks_output(
    tmp_path: Path,
    field: str,
    value: Any,
) -> None:
    def mutate(draft: dict[str, Any]) -> None:
        draft["items"][0][field] = value
        draft["items"][0]["missing_fields"] = [field]

    root, _draft = create_bundle(tmp_path, mutate_draft=mutate)
    result = builder.run_builder(
        case_id="CASE-TEST-001",
        confirmation_id="CONFIRM-TEST-001",
        approval_channel="local_terminal",
        canonical_root=root,
        input_fn=answers(["cancel"]),
        output_fn=lambda _value: None,
        now_fn=fixed_now,
    )

    assert result.status == "FAIL"
    assert not (root / "CASE-TEST-001" / builder.OUTPUT_DIR_NAME).exists()


def test_manual_review_required_is_never_transferred_automatically(
    tmp_path: Path,
) -> None:
    def manual_install(draft: dict[str, Any]) -> None:
        component = draft["items"][0]["components"][0]
        component["install_type_guess"] = "manual_review_required"

    root, _draft = create_bundle(tmp_path, mutate_draft=manual_install)
    snapshot = builder.load_snapshot(
        builder.resolve_case_paths("CASE-TEST-001", canonical_root=root)
    )

    state = builder.classify_composition(snapshot.draft)

    assert any(issue.kind == "manual_review_required" for issue in state.issues)
    assert not any(
        transfer.target_path.endswith(".install_type")
        for transfer in state.automatic_transfers
    )


@pytest.mark.parametrize(
    ("status", "source"),
    [
        ("NOT_APPLICABLE_WITH_REASON", "contract"),
        ("MODEL_OR_TYPE_SEMANTICS", "raw_model_semantics"),
    ],
)
def test_preclassified_rating_has_no_false_technical_detail_issue(
    status: str,
    source: str,
) -> None:
    draft = valid_draft("0" * 64)
    component = draft["items"][0]["components"][0]
    component["rating_guess"] = None
    component["field_applicability"] = [
        {
            "field": "rating_guess",
            "status": status,
            "reason": "Bounded rating applicability regression.",
            "source": source,
        }
    ]
    component["missing_fields"] = []

    state = builder.classify_composition(draft)

    assert not any(issue.kind == "technical_details" for issue in state.issues)
    assert len(state.items[0]["components"]) == 1
    assert not any(
        "field_applicability" in transfer.target_path
        for transfer in state.automatic_transfers
    )


def test_rating_applicability_does_not_remove_real_component_blockers() -> None:
    draft = valid_draft("0" * 64)
    component = draft["items"][0]["components"][0]
    component["rating_guess"] = None
    component["quantity_guess"] = None
    component["install_type_guess"] = "manual_review_required"
    component["missing_fields"] = ["quantity_guess"]
    component["field_applicability"] = [
        {
            "field": "rating_guess",
            "status": "NOT_APPLICABLE_WITH_REASON",
            "reason": (
                "Exact normalized N/PE bus identity has no separate rating field."
            ),
            "source": "contract",
        }
    ]
    component["conflicts"] = [
        {
            "conflict_id": "COMP-040-QTY",
            "type": "component_quantity_mismatch",
            "field": "quantity_guess",
            "message": "bounded frozen quantity conflict",
            "sources": provenance(),
        }
    ]

    state = builder.classify_composition(draft)

    assert len(state.items[0]["components"]) == 1
    assert any(
        issue.target_path == ("items", 0, "components", 0, "quantity")
        for issue in state.issues
    )
    assert any(issue.kind == "manual_review_required" for issue in state.issues)
    assert not any(
        transfer.target_path == "items[0].components[0].quantity"
        for transfer in state.automatic_transfers
    )
    assert not any(issue.kind == "technical_details" for issue in state.issues)


def test_cabinet_is_one_linked_exception_and_assumption_cannot_be_rejected(
    tmp_path: Path,
) -> None:
    def add_assumption(draft: dict[str, Any]) -> None:
        draft["items"][0]["assumptions"] = ["Verify enclosure dimensions."]

    root, _draft = create_bundle(tmp_path, mutate_draft=add_assumption)
    snapshot = builder.load_snapshot(
        builder.resolve_case_paths("CASE-TEST-001", canonical_root=root)
    )

    state = builder.classify_composition(snapshot.draft)
    cabinet_issues = [issue for issue in state.issues if issue.kind == "cabinet"]
    assumption_issues = [issue for issue in state.issues if issue.kind == "assumption"]

    assert len(cabinet_issues) == 1
    assert cabinet_issues[0].target_path == ("items", 0, "cabinet")
    assert assumption_issues
    assert all("reject" not in issue.allowed_actions for issue in assumption_issues)


def test_wrong_approval_phrase_creates_no_outputs(tmp_path: Path) -> None:
    root, _draft = create_bundle(tmp_path)
    provided = successful_answers()
    provided[-1] = "confirm technical composition"

    result = builder.run_builder(
        case_id="CASE-TEST-001",
        confirmation_id="CONFIRM-TEST-001",
        approval_channel="local_terminal",
        canonical_root=root,
        input_fn=answers(provided),
        output_fn=lambda _value: None,
        now_fn=fixed_now,
    )

    assert result.status == "FAIL"
    assert "exact technical composition approval phrase" in result.red_flags[0]
    assert not (root / "CASE-TEST-001" / builder.OUTPUT_DIR_NAME).exists()


def test_correct_approval_phrase_publishes_outputs(tmp_path: Path) -> None:
    result = run_success(tmp_path)

    assert result.status == "PASS"
    assert result.output_created is True
    assert result.output_dir is not None
    assert {path.name for path in result.output_dir.iterdir()} == {
        builder.ARTIFACT_NAME,
        builder.DECISIONS_NAME,
        builder.RECEIPT_NAME,
    }


def test_case_id_and_path_mismatch_is_rejected(tmp_path: Path) -> None:
    root, _draft = create_bundle(tmp_path)
    paths = builder.resolve_case_paths("CASE-TEST-001", canonical_root=root)
    mismatched = builder.CasePaths(
        case_id=paths.case_id,
        root=paths.root,
        case_dir=paths.root / "CASE-OTHER",
        manifest=paths.manifest,
        draft=paths.draft,
        review=paths.review,
        output_dir=paths.output_dir,
    )

    with pytest.raises(builder.WorkflowError, match="does not match"):
        builder.validate_case_directory(mismatched)


def test_missing_canonical_input_is_rejected(tmp_path: Path) -> None:
    root, _draft = create_bundle(tmp_path)
    (root / "CASE-TEST-001" / builder.REVIEW_NAME).unlink()
    paths = builder.resolve_case_paths("CASE-TEST-001", canonical_root=root)

    with pytest.raises(builder.WorkflowError, match="missing canonical input"):
        builder.load_snapshot(paths)


def test_input_outside_canonical_layout_is_rejected(tmp_path: Path) -> None:
    root, _draft = create_bundle(tmp_path)
    paths = builder.resolve_case_paths("CASE-TEST-001", canonical_root=root)
    outside = tmp_path / builder.DRAFT_NAME
    outside.write_text("{}", encoding="utf-8")
    unsafe = builder.CasePaths(
        case_id=paths.case_id,
        root=paths.root,
        case_dir=paths.case_dir,
        manifest=paths.manifest,
        draft=outside,
        review=paths.review,
        output_dir=paths.output_dir,
    )

    with pytest.raises(builder.WorkflowError, match="outside"):
        builder.validate_case_directory(unsafe)


def test_preliminary_validator_failure_blocks_output(tmp_path: Path) -> None:
    def invalidate(draft: dict[str, Any]) -> None:
        draft["safety"]["price_execution_authorized"] = True

    root, _draft = create_bundle(tmp_path, mutate_draft=invalidate)
    result = builder.run_builder(
        case_id="CASE-TEST-001",
        confirmation_id="CONFIRM-TEST-001",
        approval_channel="local_terminal",
        canonical_root=root,
        input_fn=answers([]),
        output_fn=lambda _value: None,
        now_fn=fixed_now,
    )

    assert result.status == "FAIL"
    assert "preliminary validator failed" in result.red_flags[0]


def test_source_bundle_verifier_failure_blocks_output(tmp_path: Path) -> None:
    root, _draft = create_bundle(tmp_path, mismatched_manifest_hash=True)
    result = builder.run_builder(
        case_id="CASE-TEST-001",
        confirmation_id="CONFIRM-TEST-001",
        approval_channel="local_terminal",
        canonical_root=root,
        input_fn=answers([]),
        output_fn=lambda _value: None,
        now_fn=fixed_now,
    )

    assert result.status == "FAIL"
    assert "source-bundle verifier failed" in result.red_flags[0]


def test_input_hash_drift_blocks_publication(tmp_path: Path) -> None:
    root, _draft = create_bundle(tmp_path)
    review = root / "CASE-TEST-001" / builder.REVIEW_NAME

    result = builder.run_builder(
        case_id="CASE-TEST-001",
        confirmation_id="CONFIRM-TEST-001",
        approval_channel="local_terminal",
        canonical_root=root,
        input_fn=answers(successful_answers()),
        output_fn=lambda _value: None,
        now_fn=fixed_now,
        before_drift_check=lambda: review.write_text(
            review.read_text(encoding="utf-8") + "changed\n",
            encoding="utf-8",
        ),
    )

    assert result.status == "FAIL"
    assert "hash drift" in result.red_flags[0]
    assert not (root / "CASE-TEST-001" / builder.OUTPUT_DIR_NAME).exists()


def test_existing_confirmed_directory_blocks_run(tmp_path: Path) -> None:
    root, _draft = create_bundle(tmp_path)
    output = root / "CASE-TEST-001" / builder.OUTPUT_DIR_NAME
    output.mkdir()

    result = builder.run_builder(
        case_id="CASE-TEST-001",
        confirmation_id="CONFIRM-TEST-001",
        approval_channel="local_terminal",
        canonical_root=root,
        input_fn=answers([]),
        output_fn=lambda _value: None,
        now_fn=fixed_now,
    )

    assert result.status == "FAIL"
    assert "already exists" in result.red_flags[0]


def test_confirmed_validator_failure_cleans_staging(tmp_path: Path) -> None:
    root, _draft = create_bundle(tmp_path)
    failure = SimpleNamespace(status="FAIL", red_flags=["synthetic failure"])

    result = builder.run_builder(
        case_id="CASE-TEST-001",
        confirmation_id="CONFIRM-TEST-001",
        approval_channel="local_terminal",
        canonical_root=root,
        input_fn=answers(successful_answers()),
        output_fn=lambda _value: None,
        now_fn=fixed_now,
        confirmed_validator=lambda _path: failure,
    )
    case_dir = root / "CASE-TEST-001"

    assert result.status == "FAIL"
    assert "confirmed artifact validator failed" in result.red_flags[0]
    assert not (case_dir / builder.OUTPUT_DIR_NAME).exists()
    assert not list(case_dir.glob(".confirmed-staging-*"))


def test_nonempty_final_root_red_flags_are_rejected(tmp_path: Path) -> None:
    root, _draft = create_bundle(tmp_path)
    paths = builder.resolve_case_paths("CASE-TEST-001", canonical_root=root)
    artifact = {
        "schema_version": "confirmed_composition_artifact.v0.1",
        "red_flags": ["must fail"],
    }
    passed = SimpleNamespace(status="PASS", red_flags=[])

    with pytest.raises(builder.WorkflowError, match="red_flags must be empty"):
        builder.publish_atomically(
            paths=paths,
            artifact=artifact,
            record_factory=lambda _hash: {},
            receipt_factory=lambda _record, _hash: "",
            confirmed_validator=lambda _path: passed,
        )

    assert not paths.output_dir.exists()
    assert not list(paths.case_dir.glob(".confirmed-staging-*"))


def test_batch_mode_expands_components_and_preserves_source_audit(
    tmp_path: Path,
) -> None:
    root, draft, decisions_path = create_batch_bundle(tmp_path)

    result = run_batch(root, decisions_path)

    assert result.status == "PASS"
    artifact, decisions, receipt = read_outputs(tmp_path)
    component = artifact["items"][0]["components"][0]
    assert artifact["items"][0]["product_name"] == "Normalized panel VRU-1"
    assert component == {
        "component_id": "COMP-001",
        "component_code": "VA47",
        "component_label": "CHINT, automatic breaker 1P 16A",
        "quantity": 2,
        "install_type": "modular_1p",
    }
    assert decisions["record_type"] == "igor_composition_decisions.v0.2"
    assert decisions["decision_mode"] == "batch_json"
    expanded = decisions["batch_decisions"]["expanded_component_decisions"][0]
    source = expanded["source_component"]
    original = draft["items"][0]["components"][0]
    for field_name in (
        "component_code_guess",
        "model_guess",
        "component_label_guess",
        "rating_guess",
        "note_guess",
        "provenance",
    ):
        assert source[field_name] == original.get(field_name)
    assert expanded["source_code_semantics"] == (
        "project_designation_not_manufacturer_catalog_number"
    )
    assert "Synthetic source-quality warning." in receipt
    assert "resolved_by_explicit_composition_decisions" in receipt


def test_batch_mode_reaches_only_final_human_approval_before_output(
    tmp_path: Path,
) -> None:
    root, _draft, decisions_path = create_batch_bundle(tmp_path)
    prompts: list[str] = []

    def reject_approval(prompt: str) -> str:
        prompts.append(prompt)
        return "WRONG"

    result = builder.run_builder(
        case_id="CASE-TEST-001",
        confirmation_id="CONFIRM-TEST-BATCH-001",
        approval_channel="synthetic_test",
        decisions_json=decisions_path,
        canonical_root=root,
        input_fn=reject_approval,
        output_fn=lambda _value: None,
        now_fn=fixed_now,
        approval_phrase=SYNTHETIC_APPROVAL,
    )

    assert result.status == "FAIL"
    assert prompts == [f"Type exact approval phrase [{SYNTHETIC_APPROVAL}]: "]
    assert not (root / "CASE-TEST-001" / builder.OUTPUT_DIR_NAME).exists()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.pop("supply_boundary"), "missing required fields"),
        (lambda value: value.update({"unknown": True}), "unknown fields"),
        (lambda value: value.update({"case_id": "CASE-WRONG"}), "Case ID"),
        (lambda value: value.update({"draft_id": "PRELIM-WRONG"}), "draft ID"),
        (
            lambda value: value["input_sha256"].update(
                {"preliminary_composition_draft": "0" * 64}
            ),
            "hash binding",
        ),
        (lambda value: value.update({"supply_boundary": "  "}), "supply_boundary"),
    ],
)
def test_batch_root_contract_fails_closed(
    tmp_path: Path,
    mutation: Any,
    message: str,
) -> None:
    root, _draft, decisions_path = create_batch_bundle(tmp_path)
    value = json.loads(decisions_path.read_text("utf-8"))
    mutation(value)
    decisions_path.write_bytes(canonical_json_bytes(value))

    result = run_batch(root, decisions_path)

    assert result.status == "FAIL"
    assert message in result.red_flags[0]
    assert not (root / "CASE-TEST-001" / builder.OUTPUT_DIR_NAME).exists()


def test_batch_duplicate_json_field_fails_closed(tmp_path: Path) -> None:
    root, _draft, decisions_path = create_batch_bundle(tmp_path)
    text = decisions_path.read_text("utf-8")
    decisions_path.write_text(
        text.replace(
            '  "case_id": "CASE-TEST-001",',
            '  "case_id": "CASE-TEST-001",\n  "case_id": "CASE-TEST-001",',
        ),
        encoding="utf-8",
    )

    result = run_batch(root, decisions_path)

    assert result.status == "FAIL"
    assert "duplicate JSON field: case_id" in result.red_flags[0]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda value: value["items"][0]["component_groups"][0].update(
                {"component_ids": []}
            ),
            "must not be empty",
        ),
        (
            lambda value: value["items"][0]["component_groups"][0].update(
                {"component_ids": ["COMP-001", "COMP-001"]}
            ),
            "duplicate values",
        ),
        (
            lambda value: value["items"][0]["component_groups"][0].update(
                {"component_ids": ["COMP-UNKNOWN"]}
            ),
            "unknown component_id",
        ),
        (
            lambda value: value["items"][0]["component_groups"][0].update(
                {"total_quantity": 15}
            ),
            "total_quantity",
        ),
        (
            lambda value: value["items"][0]["component_groups"][0].update(
                {"acknowledged_red_flags": []}
            ),
            "does not exactly match",
        ),
    ],
)
def test_batch_component_coverage_and_total_quantity_fail_closed(
    tmp_path: Path,
    mutation: Any,
    message: str,
) -> None:
    root, _draft, decisions_path = create_batch_bundle(tmp_path)
    value = json.loads(decisions_path.read_text("utf-8"))
    mutation(value)
    decisions_path.write_bytes(canonical_json_bytes(value))

    result = run_batch(root, decisions_path)

    assert result.status == "FAIL"
    assert message in result.red_flags[0]


def test_batch_null_source_quantity_fails_closed(tmp_path: Path) -> None:
    root, draft, decisions_path = create_batch_bundle(tmp_path)
    case_dir = root / "CASE-TEST-001"
    draft["items"][0]["components"][0]["quantity_guess"] = None
    (case_dir / builder.DRAFT_NAME).write_bytes(canonical_json_bytes(draft))
    decisions = valid_batch_decisions(case_dir, draft)
    decisions["items"][0]["component_groups"][0]["total_quantity"] = 2
    decisions_path.write_bytes(canonical_json_bytes(decisions))

    result = run_batch(root, decisions_path)

    assert result.status == "FAIL"
    assert "quantity_guess" in result.red_flags[0]


@pytest.mark.parametrize(
    ("section", "message"),
    [
        ("source_quality_acknowledgements", "source-quality warnings"),
        ("technical_assumption_resolutions", "technical assumptions"),
    ],
)
def test_batch_warnings_and_assumptions_require_exact_coverage(
    tmp_path: Path,
    section: str,
    message: str,
) -> None:
    root, _draft, decisions_path = create_batch_bundle(tmp_path)
    value = json.loads(decisions_path.read_text("utf-8"))
    value[section] = []
    decisions_path.write_bytes(canonical_json_bytes(value))

    result = run_batch(root, decisions_path)

    assert result.status == "FAIL"
    assert message in result.red_flags[0]


def test_batch_explicit_substitution_is_expanded_per_component(
    tmp_path: Path,
) -> None:
    root, draft, decisions_path = create_batch_bundle(tmp_path)
    case_dir = root / "CASE-TEST-001"
    component = draft["items"][0]["components"][0]
    component["component_label_guess"] = "QF0 VN-32 3P 25A"
    component["component_code_guess"] = "VN-32"
    component["model_guess"] = "VN-32"
    component["rating_guess"] = "25A"
    (case_dir / builder.DRAFT_NAME).write_bytes(canonical_json_bytes(draft))
    decisions = valid_batch_decisions(case_dir, draft)
    group = decisions["items"][0]["component_groups"][0]
    group["final_description"] = "CHINT, load switch 3P 32A"
    group["install_type"] = "load_switch_3p"
    group["substitution"] = {
        "original": "QF0 VN-32 3P 25A",
        "final": "CHINT, load switch 3P 32A",
        "reason": "Explicit synthetic Igor substitution.",
    }
    decisions_path.write_bytes(canonical_json_bytes(decisions))

    result = run_batch(root, decisions_path)

    assert result.status == "PASS"
    _artifact, record, receipt = read_outputs(tmp_path)
    substitution = record["batch_decisions"]["expanded_component_decisions"][0][
        "substitution"
    ]
    assert substitution == {
        "source_component_id": "COMP-001",
        "original": "QF0 VN-32 3P 25A",
        "final": "CHINT, load switch 3P 32A",
        "reason": "Explicit synthetic Igor substitution.",
        "explicit_igor_decision": True,
    }
    assert "COMP-001" in receipt
    assert "25A -> CHINT, load switch 3P 32A" in receipt


def test_batch_hidden_rating_change_requires_substitution(tmp_path: Path) -> None:
    root, _draft, decisions_path = create_batch_bundle(tmp_path)
    value = json.loads(decisions_path.read_text("utf-8"))
    group = value["items"][0]["component_groups"][0]
    group["final_description"] = "CHINT, automatic breaker 1P 20A"
    decisions_path.write_bytes(canonical_json_bytes(value))

    result = run_batch(root, decisions_path)

    assert result.status == "FAIL"
    assert "explicit substitution is required" in result.red_flags[0]


def test_batch_decisions_hash_drift_after_approval_blocks_output(
    tmp_path: Path,
) -> None:
    root, _draft, decisions_path = create_batch_bundle(tmp_path)

    result = run_batch(
        root,
        decisions_path,
        before_drift_check=lambda: decisions_path.write_text(
            decisions_path.read_text("utf-8") + " ", encoding="utf-8"
        ),
    )

    assert result.status == "FAIL"
    assert "decisions JSON hash drift" in result.red_flags[0]
    assert not (root / "CASE-TEST-001" / builder.OUTPUT_DIR_NAME).exists()


def test_successful_publication_uses_exact_hash_links(tmp_path: Path) -> None:
    result = run_success(tmp_path)
    assert result.status == "PASS"
    artifact, decisions, receipt = read_outputs(tmp_path)
    output = cast(Path, result.output_dir)
    artifact_bytes = (output / builder.ARTIFACT_NAME).read_bytes()
    decisions_bytes = (output / builder.DECISIONS_NAME).read_bytes()

    assert (
        decisions["confirmed_artifact"]["sha256"]
        == hashlib.sha256(artifact_bytes).hexdigest()
    )
    decision_hash = hashlib.sha256(decisions_bytes).hexdigest()
    assert f"Decision JSON SHA-256: {decision_hash}" in receipt
    assert artifact["red_flags"] == []
    assert "- Items: 1" in receipt
    assert "- Components: 1" in receipt
    assert "- Corrections: 2" in receipt
    assert "- Resolved conflicts: 0" in receipt
    assert "- Accepted nontechnical assumptions: 0" in receipt
    assert "- Not-applicable technical details: 0" in receipt
    assert "full confirmed technical composition is in" in receipt


def test_all_commercial_and_production_approval_flags_remain_false(
    tmp_path: Path,
) -> None:
    result = run_success(tmp_path)
    assert result.status == "PASS"
    artifact, decisions, _receipt = read_outputs(tmp_path)

    assert artifact["safety"]["price_approved_by_igor"] is False
    assert artifact["safety"]["commercial_csv_authorized"] is False
    assert artifact["safety"]["sending_authorized"] is False
    assert artifact["safety"]["production_authorized"] is False
    approvals = decisions["approvals"]
    assert approvals["technical_composition"] is True
    assert all(
        value is False
        for key, value in approvals.items()
        if key != "technical_composition"
    )


def test_script_has_no_calculator_csv_xlsx_quote_api_or_clipboard_side_effects() -> (
    None
):
    source = SCRIPT.read_text(encoding="utf-8").casefold()

    for forbidden in (
        "calc_quote_price_draft",
        "openpyxl",
        "load_workbook",
        "create_quote",
        "export_client",
        "clipboard",
        "openai_api_key",
        "requests.",
        "urllib.",
        "subprocess",
    ):
        assert forbidden not in source


@pytest.mark.parametrize(
    ("location", "expected_path"),
    [
        ("root", "red_flags[0]"),
        ("item", "items[0].red_flags[0]"),
        ("component", "items[0].components[0].red_flags[0]"),
    ],
)
def test_preliminary_red_flag_blocks_before_questions(
    tmp_path: Path,
    location: str,
    expected_path: str,
) -> None:
    def add_red_flag(draft: dict[str, Any]) -> None:
        target: Any = draft
        if location == "item":
            target = draft["items"][0]
        elif location == "component":
            target = draft["items"][0]["components"][0]
        target["red_flags"] = ["synthetic unresolved risk"]

    root, _draft = create_bundle(tmp_path, mutate_draft=add_red_flag)
    prompts: list[str] = []
    output: list[str] = []
    result = builder.run_builder(
        case_id="CASE-TEST-001",
        confirmation_id="CONFIRM-TEST-001",
        approval_channel="local_terminal",
        canonical_root=root,
        input_fn=recording_answers(prompts),
        output_fn=output.append,
        now_fn=fixed_now,
    )

    assert result.status == "FAIL"
    assert expected_path in result.red_flags[0]
    assert expected_path in "\n".join(output)
    assert prompts == []
    assert not (root / "CASE-TEST-001" / builder.OUTPUT_DIR_NAME).exists()


def test_multiple_red_flags_preserve_exact_source_paths(tmp_path: Path) -> None:
    def add_red_flags(draft: dict[str, Any]) -> None:
        draft["red_flags"] = ["root risk"]
        draft["items"][0]["red_flags"] = ["item risk"]
        draft["items"][0]["components"][0]["red_flags"] = ["component risk"]

    root, _draft = create_bundle(tmp_path, mutate_draft=add_red_flags)
    output: list[str] = []
    result = builder.run_builder(
        case_id="CASE-TEST-001",
        confirmation_id="CONFIRM-TEST-001",
        approval_channel="local_terminal",
        canonical_root=root,
        input_fn=lambda _prompt: pytest.fail("approval question must not be asked"),
        output_fn=output.append,
        now_fn=fixed_now,
    )

    rendered = "\n".join(output)
    assert result.status == "FAIL"
    assert "red_flags[0]" in rendered
    assert "items[0].red_flags[0]" in rendered
    assert "items[0].components[0].red_flags[0]" in rendered


def test_conflict_cannot_be_accepted_without_correction(tmp_path: Path) -> None:
    def add_conflict(draft: dict[str, Any]) -> None:
        draft["items"][0]["components"][0]["conflicts"] = [
            {
                "conflict_id": "CONFLICT-QUANTITY",
                "type": "quantity_mismatch",
                "field": "quantity",
                "message": "1 versus 2",
                "sources": provenance(),
            }
        ]

    root, _draft = create_bundle(tmp_path, mutate_draft=add_conflict)
    snapshot = builder.load_snapshot(
        builder.resolve_case_paths("CASE-TEST-001", canonical_root=root)
    )
    state = builder.classify_composition(snapshot.draft)
    issue = next(
        value
        for value in state.issues
        if value.kind == "conflict" and value.target_path is not None
    )

    assert issue.allowed_actions == ("correct", "cancel")
    isolated = builder.CompositionState(
        items=state.items,
        automatic_transfers=[],
        issues=[issue],
        preliminary_red_flags=[],
        unresolved_issue_ids={issue.issue_id},
        supply_boundary="set",
    )
    with pytest.raises(builder.WorkflowError, match="invalid action"):
        builder.apply_interactive_decisions(
            isolated,
            input_fn=answers(["accept"]),
            output_fn=lambda _value: None,
        )


def test_targetless_conflict_is_fail_closed(tmp_path: Path) -> None:
    def add_conflict(draft: dict[str, Any]) -> None:
        draft["items"][0]["components"][0]["conflicts"] = [
            {
                "conflict_id": "CONFLICT-OTHER",
                "type": "unknown_boundary",
                "field": "other",
                "message": "unsupported conflict",
                "sources": provenance(),
            }
        ]

    root, _draft = create_bundle(tmp_path, mutate_draft=add_conflict)
    snapshot = builder.load_snapshot(
        builder.resolve_case_paths("CASE-TEST-001", canonical_root=root)
    )
    issue = next(
        value
        for value in builder.classify_composition(snapshot.draft).issues
        if value.kind == "conflict" and value.target_path is None
    )

    assert issue.allowed_actions == ("cancel",)


def technical_details_state(tmp_path: Path) -> Any:
    def add_missing_detail(draft: dict[str, Any]) -> None:
        component = draft["items"][0]["components"][0]
        component["brand_guess"] = None
        component["missing_fields"] = ["brand_guess"]

    root, _draft = create_bundle(tmp_path, mutate_draft=add_missing_detail)
    snapshot = builder.load_snapshot(
        builder.resolve_case_paths("CASE-TEST-001", canonical_root=root)
    )
    state = builder.classify_composition(snapshot.draft)
    issue = next(value for value in state.issues if value.kind == "technical_details")
    return builder.CompositionState(
        items=state.items,
        automatic_transfers=[],
        issues=[issue],
        preliminary_red_flags=[],
        unresolved_issue_ids={issue.issue_id},
        supply_boundary="set",
    )


def test_technical_details_cannot_be_rejected(tmp_path: Path) -> None:
    state = technical_details_state(tmp_path)
    assert state.issues[0].allowed_actions == (
        "correct",
        "not_applicable",
        "cancel",
    )
    with pytest.raises(builder.WorkflowError, match="invalid action"):
        builder.apply_interactive_decisions(
            state,
            input_fn=answers(["reject"]),
            output_fn=lambda _value: None,
        )


def test_not_applicable_requires_reason(tmp_path: Path) -> None:
    state = technical_details_state(tmp_path)
    with pytest.raises(builder.WorkflowError, match="reason must be non-empty"):
        builder.apply_interactive_decisions(
            state,
            input_fn=answers(["not_applicable", ""]),
            output_fn=lambda _value: None,
        )


def test_not_applicable_records_reason_without_removing_component(
    tmp_path: Path,
) -> None:
    state = technical_details_state(tmp_path)
    original_components = len(state.items[0]["components"])
    builder.apply_interactive_decisions(
        state,
        input_fn=answers(["not_applicable", "unit is implicit in quantity"]),
        output_fn=lambda _value: None,
    )

    decision = state.not_applicable_technical_details[0]
    assert decision["action"] == "marked_not_applicable"
    assert decision["reason"] == "unit is implicit in quantity"
    assert len(state.items[0]["components"]) == original_components
    assert state.removed_values == []


def test_nontechnical_assumption_records_classification_and_reason(
    tmp_path: Path,
) -> None:
    def add_assumption(draft: dict[str, Any]) -> None:
        draft["assumptions"] = ["Nontechnical: retain source row ordering."]

    root, _draft = create_bundle(tmp_path, mutate_draft=add_assumption)
    snapshot = builder.load_snapshot(
        builder.resolve_case_paths("CASE-TEST-001", canonical_root=root)
    )
    state = builder.classify_composition(snapshot.draft)
    issue = next(value for value in state.issues if value.kind == "assumption")
    isolated = builder.CompositionState(
        items=state.items,
        automatic_transfers=[],
        issues=[issue],
        preliminary_red_flags=[],
        unresolved_issue_ids={issue.issue_id},
        supply_boundary="set",
    )
    builder.apply_interactive_decisions(
        isolated,
        input_fn=answers(["accept", "document presentation only"]),
        output_fn=lambda _value: None,
    )

    decision = isolated.accepted_nontechnical_assumptions[0]
    assert decision["action"] == "accepted_nontechnical_assumption"
    assert decision["classification"] == "nontechnical"
    assert decision["reason"] == "document presentation only"


def test_technical_assumption_cannot_be_accepted(tmp_path: Path) -> None:
    def add_assumption(draft: dict[str, Any]) -> None:
        draft["items"][0]["assumptions"] = ["Assume enclosure dimensions."]

    root, _draft = create_bundle(tmp_path, mutate_draft=add_assumption)
    snapshot = builder.load_snapshot(
        builder.resolve_case_paths("CASE-TEST-001", canonical_root=root)
    )
    issue = next(
        value
        for value in builder.classify_composition(snapshot.draft).issues
        if value.kind == "assumption"
    )

    assert issue.classification == "technical"
    assert issue.allowed_actions == ("cancel",)


def test_legacy_profile_does_not_auto_transfer_provenanced_values() -> None:
    draft = valid_draft("0" * 64)
    del draft["source"]["source_files"]
    state = builder.classify_composition(draft)
    targets = {value.target_path for value in state.automatic_transfers}

    assert "items[0].product_name" not in targets
    assert any(issue.kind == "required_value" for issue in state.issues)


def test_provenance_metadata_mismatch_blocks_before_questions(tmp_path: Path) -> None:
    def mismatch(draft: dict[str, Any]) -> None:
        component = draft["items"][0]["components"][0]
        component["provenance"][0]["source_file"] = "missing.xlsx"

    root, _draft = create_bundle(tmp_path, mutate_draft=mismatch)
    prompts: list[str] = []
    result = builder.run_builder(
        case_id="CASE-TEST-001",
        confirmation_id="CONFIRM-TEST-001",
        approval_channel="local_terminal",
        canonical_root=root,
        input_fn=recording_answers(prompts),
        output_fn=lambda _value: None,
        now_fn=fixed_now,
    )

    assert result.status == "FAIL"
    assert "has no source metadata" in result.red_flags[0]
    assert prompts == []


@pytest.mark.parametrize("kind", ["item", "component"])
def test_duplicate_ids_block_before_approval(tmp_path: Path, kind: str) -> None:
    def duplicate(draft: dict[str, Any]) -> None:
        if kind == "item":
            draft["items"].append(copy.deepcopy(draft["items"][0]))
        else:
            components = draft["items"][0]["components"]
            components.append(copy.deepcopy(components[0]))

    root, _draft = create_bundle(tmp_path, mutate_draft=duplicate)
    prompts: list[str] = []
    result = builder.run_builder(
        case_id="CASE-TEST-001",
        confirmation_id="CONFIRM-TEST-001",
        approval_channel="local_terminal",
        canonical_root=root,
        input_fn=recording_answers(prompts),
        output_fn=lambda _value: None,
        now_fn=fixed_now,
    )

    assert result.status == "FAIL"
    assert f"duplicate {kind}_id" in result.red_flags[0]
    assert prompts == []


def test_null_id_blocks_before_approval(tmp_path: Path) -> None:
    def null_id(draft: dict[str, Any]) -> None:
        draft["items"][0]["components"][0]["component_id"] = None

    root, _draft = create_bundle(tmp_path, mutate_draft=null_id)
    prompts: list[str] = []
    result = builder.run_builder(
        case_id="CASE-TEST-001",
        confirmation_id="CONFIRM-TEST-001",
        approval_channel="local_terminal",
        canonical_root=root,
        input_fn=recording_answers(prompts),
        output_fn=lambda _value: None,
        now_fn=fixed_now,
    )

    assert result.status == "FAIL"
    assert "preliminary validator failed" in result.red_flags[0]
    assert prompts == []


def test_corrected_payload_is_used_by_summary_and_decision_record(
    tmp_path: Path,
) -> None:
    def conflict(draft: dict[str, Any]) -> None:
        draft["items"][0]["components"][0]["conflicts"] = [
            {
                "conflict_id": "CONFLICT-QUANTITY",
                "type": "quantity_mismatch",
                "field": "quantity",
                "message": "2 versus 3",
                "sources": provenance(),
            }
        ]

    root, _draft = create_bundle(tmp_path, mutate_draft=conflict)
    output: list[str] = []
    result = builder.run_builder(
        case_id="CASE-TEST-001",
        confirmation_id="CONFIRM-TEST-001",
        approval_channel="local_terminal",
        canonical_root=root,
        input_fn=answers(
            [
                "correct",
                "CAB-24 | 24-module cabinet",
                "correct",
                "3",
                "correct",
                "Panel supply only",
                builder.APPROVAL_PHRASE,
            ]
        ),
        output_fn=output.append,
        now_fn=fixed_now,
    )

    assert result.status == "PASS"
    artifact, decisions, _receipt = read_outputs(tmp_path)
    assert artifact["items"][0]["components"][0]["quantity"] == 3
    assert decisions["resolved_conflicts"][0]["final_value"] == 3
    assert decisions["resolved_conflicts"][0]["action"] == "resolved_conflict"
    assert set(decisions["resolved_conflicts"][0]) >= {
        "issue_id",
        "issue_kind",
        "message",
        "source_path",
        "target_path",
        "action",
        "original_value",
        "final_value",
        "reason",
    }
    assert "qty=3" in "\n".join(output)


def representative_draft() -> dict[str, Any]:
    draft = valid_draft("0" * 64)
    template = draft["items"][0]
    items: list[dict[str, Any]] = []
    component_number = 0
    for item_number, component_count in enumerate((16, 15, 15), start=1):
        item = copy.deepcopy(template)
        item["item_id"] = f"ITEM-{item_number:03d}"
        item["product_name_guess"] = f"Panel {item_number}"
        item["components"] = []
        for _index in range(component_count):
            component_number += 1
            component = copy.deepcopy(template["components"][0])
            component["component_id"] = f"COMP-{component_number:03d}"
            component["component_code_guess"] = f"CODE-{component_number:03d}"
            component["component_label_guess"] = f"Device {component_number:03d}"
            component["install_type_guess"] = "manual_review_required"
            item["components"].append(component)
        items.append(item)
    draft["items"] = items
    return draft


def test_representative_three_item_46_component_classification() -> None:
    draft = representative_draft()
    builder.validate_identifier_integrity(draft)
    state = builder.classify_composition(draft)

    assert len(state.items) == 3
    assert sum(len(item["components"]) for item in state.items) == 46
    assert sum(issue.kind == "cabinet" for issue in state.issues) == 3
    assert sum(issue.kind == "manual_review_required" for issue in state.issues) == 46
    assert len(state.issues) == 50


def test_group_install_decision_does_not_cross_fingerprints() -> None:
    draft = valid_draft("0" * 64)
    first = draft["items"][0]["components"][0]
    second = copy.deepcopy(first)
    second["component_id"] = "COMP-002"
    for component, rating in ((first, "16A"), (second, "25A")):
        component.update(
            {
                "install_type_guess": "manual_review_required",
                "model_guess": "VA47",
                "brand_guess": "IEK",
                "rating_guess": rating,
                "unit_guess": "pcs",
                "note_guess": "DIN",
            }
        )
    draft["items"][0]["components"].append(second)
    state = builder.classify_composition(draft)
    issues = [issue for issue in state.issues if issue.kind == "manual_review_required"]
    isolated = builder.CompositionState(
        items=state.items,
        automatic_transfers=[],
        issues=issues,
        preliminary_red_flags=[],
        unresolved_issue_ids={issue.issue_id for issue in issues},
        supply_boundary="set",
    )
    builder.apply_interactive_decisions(
        isolated,
        input_fn=answers(["correct", "modular_1p", "correct", "mccb_up_to_100a"]),
        output_fn=lambda _value: None,
    )

    components = isolated.items[0]["components"]
    assert components[0]["install_type"] == "modular_1p"
    assert components[1]["install_type"] == "mccb_up_to_100a"


def test_homogeneous_install_group_expands_to_component_decisions() -> None:
    draft = valid_draft("0" * 64)
    first = draft["items"][0]["components"][0]
    second = copy.deepcopy(first)
    second["component_id"] = "COMP-002"
    for component in (first, second):
        component.update(
            {
                "install_type_guess": "manual_review_required",
                "model_guess": "VA47",
                "brand_guess": "IEK",
                "rating_guess": "16A",
                "unit_guess": "pcs",
                "note_guess": "DIN",
            }
        )
    draft["items"][0]["components"].append(second)
    state = builder.classify_composition(draft)
    issues = [issue for issue in state.issues if issue.kind == "manual_review_required"]
    isolated = builder.CompositionState(
        items=state.items,
        automatic_transfers=[],
        issues=issues,
        preliminary_red_flags=[],
        unresolved_issue_ids={issue.issue_id for issue in issues},
        supply_boundary="set",
    )
    output: list[str] = []
    builder.apply_interactive_decisions(
        isolated,
        input_fn=answers(["apply", "modular_1p"]),
        output_fn=output.append,
    )

    assert "COMP-001" in "\n".join(output)
    assert "COMP-002" in "\n".join(output)
    assert len(isolated.corrected_values) == 2
    assert all(
        value["reason"] == "explicit homogeneous group decision"
        for value in isolated.corrected_values
    )
    assert all(
        component["install_type"] == "modular_1p"
        for component in isolated.items[0]["components"]
    )


def test_late_cancellation_creates_no_outputs(tmp_path: Path) -> None:
    root, _draft = create_bundle(tmp_path)
    result = builder.run_builder(
        case_id="CASE-TEST-001",
        confirmation_id="CONFIRM-TEST-001",
        approval_channel="local_terminal",
        canonical_root=root,
        input_fn=answers(["correct", "CAB-24 | 24-module cabinet", "cancel"]),
        output_fn=lambda _value: None,
        now_fn=fixed_now,
    )

    assert result.status == "FAIL"
    assert not (root / "CASE-TEST-001" / builder.OUTPUT_DIR_NAME).exists()


def test_destination_race_preserves_canonical_and_cleans_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _draft = create_bundle(tmp_path)
    paths = builder.resolve_case_paths("CASE-TEST-001", canonical_root=root)
    artifact: dict[str, Any] = {"red_flags": []}
    passed = SimpleNamespace(status="PASS", red_flags=[])

    def race(_source: Path, destination: Path) -> None:
        destination.mkdir()
        (destination / "sentinel.txt").write_text("concurrent", encoding="utf-8")
        raise FileExistsError("synthetic race")

    monkeypatch.setattr(builder.os, "rename", race)
    with pytest.raises(builder.WorkflowError, match="manual inspection"):
        builder.publish_atomically(
            paths=paths,
            artifact=artifact,
            record_factory=lambda _hash: {},
            receipt_factory=lambda _record, _hash: "receipt",
            confirmed_validator=lambda _path: passed,
        )

    assert (paths.output_dir / "sentinel.txt").read_text("utf-8") == "concurrent"
    assert not list(paths.case_dir.glob(".confirmed-staging-*"))


def test_applied_v023_builds_confirmed_v02_with_separate_reserved_spaces(
    tmp_path: Path,
) -> None:
    applied_path = write_applied_bundle(tmp_path)
    applied_sha256 = hashlib.sha256(applied_path.read_bytes()).hexdigest()

    result = builder.run_applied_builder(
        applied_bundle_json=applied_path,
        confirmation_id="CONFIRM-SYNTHETIC-V023",
        approval_channel="synthetic_test",
        input_fn=answers([builder.APPROVAL_PHRASE]),
        output_fn=lambda _value: None,
        now_fn=fixed_now,
    )

    assert result.status == "PASS"
    assert result.output_created is True
    artifact, decisions = read_applied_outputs(applied_path)
    assert artifact["schema_version"] == "confirmed_composition_artifact.v0.2"
    assert artifact["source_lineage"]["applied_bundle_sha256"] == applied_sha256
    assert (
        artifact["source_lineage"]["applied_source_lineage"]
        == valid_applied_bundle()["source_lineage"]
    )
    assert len(artifact["installed_components"]) == 18
    assert len(artifact["reserved_meter_spaces"]) == 4
    assert all(
        value["installed_component"] is False
        for value in artifact["reserved_meter_spaces"]
    )
    assert {value["overlay_kind"] for value in artifact["installed_components"]} == {
        "COMPONENT_SIGNATURE_CORRECTION",
        "COMPONENT_RECONFIRMATION",
    }
    assert artifact["installed_components"][0]["quantity"]["quantity_per_cabinet"] == 1
    assert artifact["installed_components"][-1]["quantity"] == {
        "decision_id": "DEC-018",
        "decision_kind": "CABINET_LEVEL_AGGREGATE",
        "aggregate_quantity_per_cabinet": 3,
        "applies_once_per_cabinet": True,
        "multiply_by_member_count": False,
    }
    assert artifact["confirmed_composition_created"] is True
    assert artifact["pricing_started"] is False
    assert artifact["downstream_started"] is False
    assert decisions["final_approval_phrase"] == builder.APPROVAL_PHRASE
    assert decisions["approvals"]["technical_composition"] is True
    assert decisions["approvals"]["price"] is False


def test_preliminary_path_still_emits_semantically_unchanged_v01(
    tmp_path: Path,
) -> None:
    result = run_success(tmp_path)
    artifact, _decisions, _receipt = read_outputs(tmp_path)

    assert result.status == "PASS"
    assert artifact["schema_version"] == "confirmed_composition_artifact.v0.1"
    assert "installed_components" not in artifact
    assert artifact["safety"]["price_approved_by_igor"] is False


def test_builder_cli_sources_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit):
        builder.parse_args(
            [
                "--case-id",
                "CASE-TEST-001",
                "--applied-bundle-json",
                "applied.json",
                "--confirmation-id",
                "CONFIRM-001",
                "--approval-channel",
                "synthetic_test",
            ]
        )


def test_applied_path_requires_existing_exact_approval(
    tmp_path: Path,
) -> None:
    applied_path = write_applied_bundle(tmp_path)

    result = builder.run_applied_builder(
        applied_bundle_json=applied_path,
        confirmation_id="CONFIRM-SYNTHETIC-V023",
        approval_channel="synthetic_test",
        input_fn=answers(["WRONG APPROVAL"]),
        output_fn=lambda _value: None,
        now_fn=fixed_now,
    )

    assert result.status == "FAIL"
    assert not (applied_path.parent / builder.OUTPUT_DIR_NAME).exists()
    assert any(
        "exact technical composition approval phrase" in value
        for value in result.red_flags
    )


def test_applied_hash_drift_after_approval_blocks_publication(
    tmp_path: Path,
) -> None:
    applied_path = write_applied_bundle(tmp_path)

    def mutate_source() -> None:
        applied_path.write_bytes(applied_path.read_bytes() + b" ")

    result = builder.run_applied_builder(
        applied_bundle_json=applied_path,
        confirmation_id="CONFIRM-SYNTHETIC-V023",
        approval_channel="synthetic_test",
        input_fn=answers([builder.APPROVAL_PHRASE]),
        output_fn=lambda _value: None,
        now_fn=fixed_now,
        before_drift_check=mutate_source,
    )

    assert result.status == "FAIL"
    assert not (applied_path.parent / builder.OUTPUT_DIR_NAME).exists()
    assert any("hash drift" in value for value in result.red_flags)


@pytest.mark.parametrize("fault", ["duplicate", "unknown", "coverage"])
def test_applied_source_comp_and_coverage_faults_fail_closed(
    tmp_path: Path,
    fault: str,
) -> None:
    data = valid_applied_bundle()
    if fault == "duplicate":
        data["component_signature_overlays"][1]["component_evidence_id"] = data[
            "component_signature_overlays"
        ][0]["component_evidence_id"]
    elif fault == "unknown":
        data["component_signature_overlays"][0][
            "component_evidence_id"
        ] = "COMP-UNKNOWN"
    else:
        data["coverage"]["overlay_component_count"] = 21
    applied_path = write_applied_bundle(tmp_path, data)

    result = builder.run_applied_builder(
        applied_bundle_json=applied_path,
        confirmation_id="CONFIRM-SYNTHETIC-V023",
        approval_channel="synthetic_test",
        input_fn=answers([builder.APPROVAL_PHRASE]),
        output_fn=lambda _value: None,
        now_fn=fixed_now,
    )

    assert result.status == "FAIL"
    assert not (applied_path.parent / builder.OUTPUT_DIR_NAME).exists()
