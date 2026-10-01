"""Governed intake, immutable rerun, and version binding safety checks."""

# ruff: noqa: E402

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import build_confirmed_composition_from_preliminary_bundle as builder  # type: ignore[import-not-found]
import extract_mixed_source_composition_case as wrapper  # type: ignore[import-not-found]
from governed_case_intake import (  # type: ignore[import-not-found]
    GovernedIntake,
    IntakeError,
    load_governed_intake,
    verify_versioned_extraction,
)


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
