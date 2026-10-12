"""Governed intake, immutable rerun, and version binding safety checks."""

# ruff: noqa: E402

import copy
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import build_confirmed_composition_from_preliminary_bundle as builder  # type: ignore[import-not-found]
import extract_mixed_source_composition_case as wrapper  # type: ignore[import-not-found]
import governed_case_intake as intake_module  # type: ignore[import-not-found]
from governed_case_intake import (  # type: ignore[import-not-found]
    GovernedIntake,
    IntakeError,
    load_governed_intake,
    verify_versioned_extraction,
)
from test_build_confirmed_composition_from_preliminary_bundle import valid_draft


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def evidence(body: str) -> dict[str, str]:
    return {
        "text": body,
        "source_locator": "synthetic user instruction",
        "text_sha256": sha(body.encode("utf-8")),
    }


def setup_case(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    root = tmp_path / "production_ai_cases"
    case = root / "CASE-TEST-001"
    case.mkdir(parents=True)
    for name in wrapper.EXPECTED_FILES:
        (case / name).write_text(f"original {name}\n", encoding="utf-8")
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"synthetic immutable PDF")
    intake = tmp_path / "intake.json"
    request = "One VRU-1 and one AVR"
    data = {
        "schema_version": "governed_case_extraction_intake.v0.1",
        "case_id": case.name,
        "extraction_version": "V001",
        "project_pdf_path": str(pdf.resolve()),
        "project_pdf_sha256": sha(pdf.read_bytes()),
        "base_manifest_sha256": sha((case / wrapper.MANIFEST_NAME).read_bytes()),
        "client_request": evidence(request),
        "human_decisions": [evidence("Exclude METER-X from commercial supply")],
        "requested_supply": [
            {"designation": "VRU-1", "quantity": 1},
            {"designation": "AVR", "quantity": 1},
        ],
        "excluded_components": [{"designation": "METER-X", "quantity": 2}],
    }
    intake.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return root, case, pdf, intake


def passing_operator(
    pdf: Path,
    _workbook: None,
    output: Path,
    *,
    governed_intake: GovernedIntake,
) -> SimpleNamespace:
    output.mkdir()
    intake = governed_intake
    classifications = [
        {
            "classification": "requested_supply",
            "designation": name,
            "quantity": quantity,
        }
        for name, quantity in intake.requested_supply
    ] + [
        {
            "classification": "excluded_component",
            "designation": name,
            "quantity": quantity,
        }
        for name, quantity in intake.excluded_components
    ]
    (output / wrapper.MANIFEST_NAME).write_text(
        json.dumps(
            {
                "governed_intake_sha256": intake.sha256,
                "scope_classification": classifications,
                "sources": [
                    {
                        "source_type": "pdf",
                        "sha256": sha(pdf.read_bytes()),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (output / wrapper.DRAFT_NAME).write_text(
        json.dumps(
            {
                "items": [
                    {"product_name_guess": name, "quantity_guess": quantity}
                    for name, quantity in intake.requested_supply
                ]
            }
        ),
        encoding="utf-8",
    )
    (output / wrapper.REVIEW_NAME).write_text("synthetic review", encoding="utf-8")
    return SimpleNamespace(
        status="PASS",
        output_dir=output,
        checks={name: "pass" for name in wrapper.REQUIRED_EXTRACTOR_CHECKS},
    )


def test_versioned_rerun_preserves_base_and_rejects_overwrite(tmp_path: Path) -> None:
    root, case, pdf, intake = setup_case(tmp_path)
    original = {
        name: sha((case / name).read_bytes()) for name in wrapper.EXPECTED_FILES
    }

    result = wrapper.run_versioned_case_extraction(
        case_id=case.name,
        project_pdf=pdf,
        extraction_version="V001",
        intake_json=intake,
        canonical_root=root,
        operator_fn=passing_operator,
    )

    assert result.status == "PASS", result.red_flags
    assert result.output_dir == case / "extraction-V001"
    assert {name: sha((case / name).read_bytes()) for name in original} == original
    assert verify_versioned_extraction(
        result.output_dir,
        case_id=case.name,
        version="V001",
        base_manifest=case / wrapper.MANIFEST_NAME,
    )
    retry = wrapper.run_versioned_case_extraction(
        case_id=case.name,
        project_pdf=pdf,
        extraction_version="V001",
        intake_json=intake,
        canonical_root=root,
        operator_fn=passing_operator,
    )
    assert retry.status == "FAIL"
    assert "overwrite is forbidden" in retry.red_flags[0]


def test_version_binding_detects_tampered_draft(tmp_path: Path) -> None:
    root, case, pdf, intake = setup_case(tmp_path)
    result = wrapper.run_versioned_case_extraction(
        case_id=case.name,
        project_pdf=pdf,
        extraction_version="V001",
        intake_json=intake,
        canonical_root=root,
        operator_fn=passing_operator,
    )
    assert result.status == "PASS"
    (result.output_dir / wrapper.DRAFT_NAME).write_text("tampered", encoding="utf-8")

    with pytest.raises(IntakeError, match="SHA-256 mismatch"):
        verify_versioned_extraction(
            result.output_dir,
            case_id=case.name,
            version="V001",
            base_manifest=case / wrapper.MANIFEST_NAME,
        )
    paths = builder.resolve_case_paths(
        case.name, canonical_root=root, extraction_version="V001"
    )
    with pytest.raises(
        builder.WorkflowError, match="versioned extraction binding failed"
    ):
        builder.validate_case_directory(paths)


def test_confirmation_builder_requires_explicit_version(tmp_path: Path) -> None:
    root, case, pdf, intake = setup_case(tmp_path)
    result = wrapper.run_versioned_case_extraction(
        case_id=case.name,
        project_pdf=pdf,
        extraction_version="V001",
        intake_json=intake,
        canonical_root=root,
        operator_fn=passing_operator,
    )
    assert result.status == "PASS"
    original = builder.resolve_case_paths(case.name, canonical_root=root)
    selected = builder.resolve_case_paths(
        case.name, canonical_root=root, extraction_version="V001"
    )
    assert original.draft == case / wrapper.DRAFT_NAME
    assert selected.draft == result.output_dir / wrapper.DRAFT_NAME
    assert selected.output_dir == result.output_dir / "confirmed"
    builder.validate_case_directory(selected)


def test_unexpected_extractor_error_cleans_only_owned_staging(tmp_path: Path) -> None:
    root, case, pdf, intake = setup_case(tmp_path)

    def fail_operator(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("synthetic extractor error")

    result = wrapper.run_versioned_case_extraction(
        case_id=case.name,
        project_pdf=pdf,
        extraction_version="V001",
        intake_json=intake,
        canonical_root=root,
        operator_fn=fail_operator,
    )

    assert result.status == "FAIL"
    assert "synthetic extractor error" in result.red_flags[0]
    assert not (case / "extraction-V001").exists()
    assert {path.name for path in case.iterdir()} == wrapper.EXPECTED_FILES


def test_intake_rejects_pdf_drift_and_duplicate_keys(tmp_path: Path) -> None:
    _root, case, pdf, intake = setup_case(tmp_path)
    pdf.write_bytes(b"drift")
    with pytest.raises(IntakeError, match="PDF SHA-256 mismatch"):
        load_governed_intake(
            intake,
            case_id=case.name,
            version="V001",
            project_pdf=pdf,
            base_manifest=case / wrapper.MANIFEST_NAME,
        )
    pdf.write_bytes(b"synthetic immutable PDF")
    intake.write_text(
        intake.read_text(encoding="utf-8").replace(
            '"case_id":', '"case_id": "CASE-EXTRA", "case_id":', 1
        ),
        encoding="utf-8",
    )
    with pytest.raises(IntakeError, match="duplicate intake field"):
        load_governed_intake(
            intake,
            case_id=case.name,
            version="V001",
            project_pdf=pdf,
            base_manifest=case / wrapper.MANIFEST_NAME,
        )


def test_intake_rejects_scope_without_request_or_decision_evidence(
    tmp_path: Path,
) -> None:
    _root, case, pdf, intake = setup_case(tmp_path)
    data = json.loads(intake.read_text(encoding="utf-8"))
    data["requested_supply"][0]["designation"] = "UNREQUESTED-BOARD"
    intake.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(IntakeError, match="no request/decision evidence"):
        load_governed_intake(
            intake,
            case_id=case.name,
            version="V001",
            project_pdf=pdf,
            base_manifest=case / wrapper.MANIFEST_NAME,
        )


@pytest.mark.parametrize("excluded", [None, [], "", {}])
def test_intake_no_exclusions_must_be_explicit_list(
    tmp_path: Path, excluded: object
) -> None:
    _root, case, pdf, intake = setup_case(tmp_path)
    data = json.loads(intake.read_text(encoding="utf-8"))
    data["excluded_components"] = excluded
    intake.write_text(json.dumps(data), encoding="utf-8")
    if excluded == []:
        loaded = load_governed_intake(
            intake,
            case_id=case.name,
            version="V001",
            project_pdf=pdf,
            base_manifest=case / wrapper.MANIFEST_NAME,
        )
        assert loaded.excluded_components == ()
    else:
        with pytest.raises(IntakeError, match="scope list"):
            load_governed_intake(
                intake,
                case_id=case.name,
                version="V001",
                project_pdf=pdf,
                base_manifest=case / wrapper.MANIFEST_NAME,
            )


def test_intake_empty_requested_supply_still_holds(tmp_path: Path) -> None:
    _root, case, pdf, intake = setup_case(tmp_path)
    data = json.loads(intake.read_text(encoding="utf-8"))
    data["requested_supply"] = []
    intake.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(IntakeError, match="scope list"):
        load_governed_intake(
            intake,
            case_id=case.name,
            version="V001",
            project_pdf=pdf,
            base_manifest=case / wrapper.MANIFEST_NAME,
        )


def post_confirmation_case(
    tmp_path: Path, *, future: bool = False
) -> tuple[Path, Path, dict[str, str]]:
    """Run the existing extractor wrapper and confirmed producer on synthetic inputs."""
    root, case, pdf, intake = setup_case(tmp_path)

    def operator(*args: Any, **kwargs: Any) -> SimpleNamespace:
        result = passing_operator(*args, **kwargs)
        output = result.output_dir
        draft = valid_draft(sha((output / wrapper.MANIFEST_NAME).read_bytes()))
        first = draft["items"][0]
        first["product_name_guess"] = "VRU-1"
        second = copy.deepcopy(first)
        second["item_id"] = "ITEM-002"
        second["product_name_guess"] = "AVR"
        second["components"][0]["component_id"] = "COMP-002"
        draft["items"].append(second)
        if future:
            for item in draft["items"]:
                component = item["components"][0]
                component.update(
                    component_code_guess="ВА47-29",
                    rating_guess="D25A",
                    component_label_guess="ВА47-29 3P D25A",
                    install_type_guess="modular_3p",
                )
        (output / wrapper.DRAFT_NAME).write_text(json.dumps(draft), encoding="utf-8")
        (output / wrapper.REVIEW_NAME).write_text(
            "# Igor review\n\n"
            f"- raw_input_sha256: {draft['source']['raw_input_sha256']}"
            f"\n- draft_id: {draft['draft_id']}\n",
            encoding="utf-8",
        )
        return result

    extracted = wrapper.run_versioned_case_extraction(
        case_id=case.name,
        project_pdf=pdf,
        extraction_version="V001",
        intake_json=intake,
        canonical_root=root,
        operator_fn=operator,
    )
    assert extracted.status == "PASS", extracted.red_flags
    directory = case / "extraction-V001"
    before = {p.name: sha(p.read_bytes()) for p in directory.iterdir()}
    draft = json.loads((directory / wrapper.DRAFT_NAME).read_bytes())
    decisions = {
        "schema_version": builder.DECISIONS_INPUT_SCHEMA,
        "case_id": case.name,
        "draft_id": draft["draft_id"],
        "input_sha256": dict(
            zip(
                [
                    "source_bundle_manifest",
                    "preliminary_composition_draft",
                    "igor_review_card",
                ],
                [
                    before[wrapper.MANIFEST_NAME],
                    before[wrapper.DRAFT_NAME],
                    before[wrapper.REVIEW_NAME],
                ],
                strict=True,
            )
        ),
        "items": [
            {
                "item_id": item["item_id"],
                "product_name": item["product_name_guess"],
                "quantity": 1,
                "manufacturer": "EKF" if future else "IEK",
                "acknowledged_red_flags": [],
                "cabinet": {
                    "code": "CAB-24",
                    "label": "24-module cabinet",
                    "acknowledged_red_flags": [],
                },
                "component_groups": [
                    {
                        "component_ids": [c["component_id"]],
                        "total_quantity": c["quantity_guess"],
                        "final_description": (
                            "ВА47-29 EKF 3P D25A" if future else "Breaker VA47 IEK"
                        ),
                        "install_type": "modular_3p" if future else "modular_1p",
                        "substitution": None,
                        "acknowledged_red_flags": [],
                    }
                    for c in item["components"]
                ],
            }
            for item in draft["items"]
        ],
        "source_quality_acknowledgements": [],
        "technical_assumption_resolutions": [],
        "supply_boundary": "Synthetic approved composition only",
    }
    decisions_path = tmp_path / "decisions.json"
    decisions_path.write_text(json.dumps(decisions), encoding="utf-8")
    review_path = None
    if future:
        review_path = tmp_path / "future-review.json"
        review = {
            "schema_version": "future_composition_review.v0.1",
            "case_id": case.name,
            "draft_id": draft["draft_id"],
            "input_sha256": decisions["input_sha256"],
            "future_context": {
                "case_id": case.name,
                "case_state": "NEW_FUTURE",
                "future_cases_only": True,
                "historical_repricing_authorized": False,
            },
            "items": [
                {
                    "item_id": item["item_id"],
                    "technical_classification": {
                        "family": "ЩР",
                        "execution": "STANDARD",
                        "circuits": [
                            {
                                "circuit_id": "INPUT",
                                "conductor_mm2": 10,
                                "protection_component_ids": [
                                    item["components"][0]["component_id"]
                                ],
                            }
                        ],
                        "roles": {
                            item["components"][0]["component_id"]: "POWER_BREAKER"
                        },
                        "categories": {
                            item["components"][0]["component_id"]: "MCB 3P D 10-63A"
                        },
                        "fuses": {},
                        "interlocks": {"mechanical": False, "electrical": False},
                        "overrides": {},
                    },
                }
                for item in draft["items"]
            ],
        }
        review_path.write_text(json.dumps(review), encoding="utf-8")
    confirmed = builder.run_builder(
        case_id=case.name,
        confirmation_id="IGOR-SYNTHETIC-V001",
        approval_channel="synthetic_test",
        canonical_root=root,
        extraction_version="V001",
        decisions_json=decisions_path,
        future_review_json=review_path,
        future_review_sha256=sha(review_path.read_bytes()) if review_path else None,
        input_fn=lambda _: builder.APPROVAL_PHRASE,
        output_fn=lambda _: None,
    )
    assert confirmed.status == "PASS", confirmed.red_flags
    return case, directory, before


def check_post_confirmation(case: Path, directory: Path) -> str:
    return str(
        verify_versioned_extraction(
            directory,
            case_id=case.name,
            version="V001",
            base_manifest=case / wrapper.MANIFEST_NAME,
        )
    )


@pytest.mark.parametrize("future", [False, True])
def test_canonical_post_confirmation_flow_passes_without_source_changes(
    tmp_path: Path,
    future: bool,
) -> None:
    case, directory, before = post_confirmation_case(tmp_path, future=future)
    assert check_post_confirmation(case, directory) == before["version-binding.json"]
    assert {
        p.name: sha(p.read_bytes()) for p in directory.iterdir() if p.is_file()
    } == before
    retry = builder.run_builder(
        case_id=case.name,
        confirmation_id="RETRY",
        approval_channel="synthetic_test",
        canonical_root=case.parent,
        extraction_version="V001",
    )
    assert retry.status == "FAIL" and "overwrite is forbidden" in retry.red_flags[0]


@pytest.mark.parametrize(
    "where,kind",
    [
        ("root", "file"),
        ("root", "directory"),
        ("confirmed", "file"),
        ("confirmed", "directory"),
    ],
)
def test_post_confirmation_foreign_entries_fail(
    tmp_path: Path, where: str, kind: str
) -> None:
    case, directory, _ = post_confirmation_case(tmp_path)
    target = directory if where == "root" else directory / "confirmed"
    path = target / "foreign"
    if kind == "file":
        path.write_bytes(b"foreign")
    else:
        path.mkdir()
    with pytest.raises(IntakeError, match="file set mismatch"):
        check_post_confirmation(case, directory)


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "artifact_directory",
        "artifact_sha",
        "source_link",
        "case",
        "relative_path",
        "commercial_approval",
        "receipt",
        "duplicate_key",
    ],
)
def test_confirmed_contents_fail_closed(tmp_path: Path, fault: str) -> None:
    case, directory, _ = post_confirmation_case(tmp_path)
    folder = directory / "confirmed"
    artifact_path = folder / builder.ARTIFACT_NAME
    audit_path = folder / builder.DECISIONS_NAME
    audit = json.loads(audit_path.read_bytes())
    if fault == "missing":
        (folder / builder.RECEIPT_NAME).unlink()
    elif fault == "artifact_directory":
        artifact_path.unlink()
        artifact_path.mkdir()
    elif fault == "source_link":
        artifact = json.loads(artifact_path.read_bytes())
        artifact["source_links"]["raw_input_sha256"] = "0" * 64
        artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    elif fault == "receipt":
        (folder / builder.RECEIPT_NAME).write_text("foreign receipt", encoding="utf-8")
    elif fault == "duplicate_key":
        audit_path.write_text(
            audit_path.read_text(encoding="utf-8").replace(
                '"case_id":', '"case_id": "OTHER", "case_id":', 1
            ),
            encoding="utf-8",
        )
    else:
        if fault == "artifact_sha":
            audit["confirmed_artifact"]["sha256"] = "0" * 64
        elif fault == "case":
            audit["case_id"] = "CASE-OTHER-001"
        elif fault == "relative_path":
            audit["inputs"][wrapper.DRAFT_NAME][
                "relative_path"
            ] = "../preliminary-composition-draft.json"
        elif fault == "commercial_approval":
            audit["approvals"]["price"] = True
        audit_path.write_text(json.dumps(audit), encoding="utf-8")
    with pytest.raises(IntakeError):
        check_post_confirmation(case, directory)


@pytest.mark.parametrize(
    "target",
    [
        "confirmed",
        "confirmed-composition-artifact.json",
        "igor-composition-decisions.json",
        "igor-composition-decisions.md",
        "preliminary-composition-draft.json",
        "CASE-TEST-001",
        "source-bundle-manifest.txt",
    ],
)
def test_post_confirmation_reparse_paths_fail(
    tmp_path: Path, monkeypatch: Any, target: str
) -> None:
    case, directory, _ = post_confirmation_case(tmp_path)
    original = intake_module._unsafe_reparse
    monkeypatch.setattr(
        intake_module, "_unsafe_reparse", lambda p: p.name == target or original(p)
    )
    with pytest.raises(IntakeError, match="unsafe"):
        check_post_confirmation(case, directory)


@pytest.mark.parametrize(
    "name",
    [
        "governed-intake.json",
        "source-bundle-manifest.txt",
        "preliminary-composition-draft.json",
        "igor-review-card.md",
        "version-binding.json",
    ],
)
def test_source_drift_still_fails_after_confirmation(tmp_path: Path, name: str) -> None:
    case, directory, _ = post_confirmation_case(tmp_path)
    path = directory / name
    path.write_bytes(path.read_bytes() + b"drift")
    with pytest.raises(IntakeError):
        check_post_confirmation(case, directory)


@pytest.mark.parametrize("fault", ["source_sha", "classification"])
def test_confirmed_future_review_stays_bound(tmp_path: Path, fault: str) -> None:
    case, directory, _ = post_confirmation_case(tmp_path, future=True)
    if fault == "source_sha":
        path = tmp_path / "future-review.json"
        path.write_bytes(path.read_bytes() + b" ")
        message = "future review source drift"
    else:
        path = directory / "confirmed" / builder.ARTIFACT_NAME
        artifact = json.loads(path.read_bytes())
        artifact["items"][0]["technical_classification"]["circuits"][0][
            "conductor_mm2"
        ] = 11
        path.write_text(json.dumps(artifact), encoding="utf-8")
        message = "reviewed classification mismatch"
    with pytest.raises(IntakeError, match=message):
        check_post_confirmation(case, directory)


@pytest.mark.parametrize("target", ["bound_file", "confirmed_file", "root_inventory"])
def test_post_confirmation_rechecks_drift_during_validation(
    tmp_path: Path, monkeypatch: Any, target: str
) -> None:
    case, directory, _ = post_confirmation_case(tmp_path)
    original = builder.build_receipt

    def drift(**kwargs: Any) -> str:
        receipt = str(original(**kwargs))
        if target == "root_inventory":
            (directory / "foreign").write_bytes(b"foreign")
        else:
            path = (
                directory / wrapper.REVIEW_NAME
                if target == "bound_file"
                else directory / "confirmed" / builder.DECISIONS_NAME
            )
            path.write_bytes(path.read_bytes() + b" ")
        return receipt

    monkeypatch.setattr(builder, "build_receipt", drift)
    with pytest.raises(IntakeError, match="changed during verification"):
        check_post_confirmation(case, directory)


def test_confirmed_is_not_accepted_inside_owned_extraction_staging(
    tmp_path: Path,
) -> None:
    case, directory, _ = post_confirmation_case(tmp_path)
    staging = case / ".extraction-V001-wrapper-synthetic"
    staged = staging / "bundle"
    import shutil

    shutil.copytree(directory, staged)
    with pytest.raises(IntakeError, match="file set mismatch"):
        verify_versioned_extraction(
            staged,
            case_id=case.name,
            version="V001",
            base_manifest=case / wrapper.MANIFEST_NAME,
            owned_staging=staging,
        )
