import copy
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "validate_preliminary_composition_draft.py"
EXAMPLE = PROJECT_ROOT / "examples" / "preliminary_composition_draft.example.json"
OLD_WORKFLOWS = (
    PROJECT_ROOT / "scripts" / "calc_quote_price_draft.py",
    PROJECT_ROOT / "scripts" / "preflight_quote_commercial_input.py",
    PROJECT_ROOT / "scripts" / "run_invoice_quote_commercial_from_csv.py",
    PROJECT_ROOT / "scripts" / "make_quote_capacity100_commercial_checked.ps1",
    PROJECT_ROOT / "scripts" / "create_client_style_approval_draft.py",
    PROJECT_ROOT / "scripts" / "export_client_style_invoice.py",
    PROJECT_ROOT / "scripts" / "run_client_style_invoice_export.ps1",
    PROJECT_ROOT / "scripts" / "preflight_client_style_invoice_template_contract.py",
    PROJECT_ROOT / "scripts" / "make_quote_capacity100_checked.ps1",
    PROJECT_ROOT / "scripts" / "run_invoice_quote_extended_from_items.py",
)


def load_validator_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "validate_preliminary_composition_draft_for_test",
        SCRIPT,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


validator = cast(Any, load_validator_module())


def valid_data() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(EXAMPLE.read_text(encoding="utf-8")))


def valid_section_data() -> dict[str, Any]:
    data = valid_data()
    context = {
        "project_id": "2024/086",
        "section_id": "13",
        "discipline": "ЭОМ",
        "source_document_id": "section-13-eom",
        "source_role": "project_pdf",
    }
    data["schema_version"] = "preliminary_composition_draft.section_aware.v0.1"
    data["source"] = {
        "source_type": "other",
        "source_summary": "Synthetic section-aware validator fixture.",
        "raw_input_sha256": "a" * 64,
        "source_documents": [
            {
                "file_name": "section-13-eom.pdf",
                "source_type": "pdf",
                "sha256": "b" * 64,
                "status": "extracted",
                "pages": [{"page": 1, "status": "text_available"}],
                **context,
                "intake_path": "section-13-eom.pdf",
                "resolved_path": "C:/sources/section-13-eom.pdf",
            }
        ],
    }
    item = first_item(data)
    item.update(context)
    item["normalized_designation"] = "VRU-1"
    item["source_designation"] = "VRU-1"
    item["provenance"] = [
        {
            "source_file": "section-13-eom.pdf",
            "source_type": "pdf",
            "locator": "page=1; block=1",
            "raw_text": "VRU-1",
            "confidence": 0.9,
            "reason": "synthetic board evidence",
            "page": 1,
            **context,
            "item_id": item["item_id"],
        }
    ]
    for component in cast(list[dict[str, Any]], item["components"]):
        component.update(context)
        component["item_id"] = item["item_id"]
        component["provenance"] = [
            {
                "source_file": "section-13-eom.pdf",
                "source_type": "pdf",
                "locator": "page=1; block=2",
                "raw_text": component["component_label_guess"],
                "confidence": 0.8,
                "reason": "synthetic component evidence",
                "page": 1,
                **context,
                "item_id": item["item_id"],
                "component_id": component["component_id"],
            }
        ]
    return data


def renumber_section_item(item: dict[str, Any], item_id: str) -> None:
    item["item_id"] = item_id
    for provenance in cast(list[dict[str, Any]], item["provenance"]):
        provenance["item_id"] = item_id
    for index, component in enumerate(
        cast(list[dict[str, Any]], item["components"]), start=1
    ):
        component_id = f"{item_id}-COMP-{index:03d}"
        component["component_id"] = component_id
        component["item_id"] = item_id
        for provenance in cast(list[dict[str, Any]], component["provenance"]):
            provenance["item_id"] = item_id
            provenance["component_id"] = component_id


def append_section_item_variant(
    data: dict[str, Any],
    *,
    section_id: str = "13",
    discipline: str = "ЭОМ",
) -> dict[str, Any]:
    source = cast(dict[str, Any], data["source"])
    documents = cast(list[dict[str, Any]], source["source_documents"])
    document = copy.deepcopy(documents[0])
    document_id = f"variant-{len(documents) + 1}"
    file_name = f"{document_id}.pdf"
    document.update(
        {
            "file_name": file_name,
            "source_document_id": document_id,
            "section_id": section_id,
            "discipline": discipline,
            "intake_path": file_name,
            "resolved_path": f"C:/sources/{file_name}",
        }
    )
    documents.append(document)

    items = cast(list[dict[str, Any]], data["items"])
    item = copy.deepcopy(items[0])
    renumber_section_item(item, f"ITEM-{len(items) + 1:03d}")
    context = {
        "project_id": document["project_id"],
        "section_id": section_id,
        "discipline": discipline,
        "source_document_id": document_id,
        "source_role": document["source_role"],
    }
    item.update(context)
    for provenance in cast(list[dict[str, Any]], item["provenance"]):
        provenance.update(context)
        provenance["source_file"] = file_name
    for component in cast(list[dict[str, Any]], item["components"]):
        component.update(context)
        for provenance in cast(list[dict[str, Any]], component["provenance"]):
            provenance.update(context)
            provenance["source_file"] = file_name
    items.append(item)
    return item


def write_json(tmp_path: Path, data: dict[str, Any]) -> Path:
    path = tmp_path / "draft.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run_validation(data: dict[str, Any], tmp_path: Path) -> Any:
    return validator.validate_preliminary_composition_draft(write_json(tmp_path, data))


def first_item(data: dict[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], data["items"][0])


def first_component(data: dict[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], first_item(data)["components"][0])


def assert_fails_with(
    data: dict[str, Any],
    tmp_path: Path,
    expected: str,
) -> None:
    result = run_validation(data, tmp_path)

    assert result.status == "FAIL"
    assert any(expected in red_flag for red_flag in result.red_flags), result.red_flags


def test_valid_example_passes(tmp_path: Path) -> None:
    result = run_validation(valid_data(), tmp_path)

    assert result.status == "PASS"
    assert result.red_flags == []
    assert all(status == "pass" for status in result.checks.values())


def applicability_entry(
    *,
    status: str = "NOT_APPLICABLE_WITH_REASON",
    source: str = "contract",
) -> dict[str, str]:
    return {
        "field": "rating_guess",
        "status": status,
        "reason": "Bounded synthetic applicability reason.",
        "source": source,
    }


def test_legacy_component_without_field_applicability_passes(tmp_path: Path) -> None:
    data = valid_data()
    assert "field_applicability" not in first_component(data)

    result = run_validation(data, tmp_path)

    assert result.status == "PASS", result.red_flags


def test_valid_field_applicability_passes(tmp_path: Path) -> None:
    data = valid_data()
    first_component(data)["field_applicability"] = [applicability_entry()]

    result = run_validation(data, tmp_path)

    assert result.status == "PASS", result.red_flags


def test_required_applicability_reason_may_be_absent(tmp_path: Path) -> None:
    data = valid_data()
    entry = applicability_entry(status="REQUIRED")
    entry.pop("reason")
    first_component(data)["field_applicability"] = [entry]

    result = run_validation(data, tmp_path)

    assert result.status == "PASS", result.red_flags


def test_field_applicability_unknown_key_fails(tmp_path: Path) -> None:
    data = valid_data()
    entry = applicability_entry()
    entry["approval"] = "forbidden"
    first_component(data)["field_applicability"] = [entry]

    assert_fails_with(data, tmp_path, "unknown field is not allowed")


def test_field_applicability_unknown_field_fails(tmp_path: Path) -> None:
    data = valid_data()
    entry = applicability_entry()
    entry["field"] = "model_guess"
    first_component(data)["field_applicability"] = [entry]

    assert_fails_with(data, tmp_path, "field_applicability field is not allowed")


def test_field_applicability_unknown_status_fails(tmp_path: Path) -> None:
    data = valid_data()
    first_component(data)["field_applicability"] = [
        applicability_entry(status="SOMETIMES_REQUIRED")
    ]

    assert_fails_with(data, tmp_path, "field_applicability status is not allowed")


def test_field_applicability_unknown_source_fails(tmp_path: Path) -> None:
    data = valid_data()
    first_component(data)["field_applicability"] = [
        applicability_entry(source="inferred")
    ]

    assert_fails_with(data, tmp_path, "field_applicability source is not allowed")


@pytest.mark.parametrize(
    "status",
    [
        "NOT_APPLICABLE_WITH_REASON",
        "MODEL_OR_TYPE_SEMANTICS",
        "UNRESOLVED_TECHNICAL_DETAIL",
    ],
)
@pytest.mark.parametrize("reason", [None, ""])
def test_non_required_applicability_requires_non_empty_reason(
    tmp_path: Path,
    status: str,
    reason: str | None,
) -> None:
    data = valid_data()
    entry: dict[str, Any] = applicability_entry(status=status)
    if reason is None:
        entry.pop("reason")
    else:
        entry["reason"] = reason
    first_component(data)["field_applicability"] = [entry]

    assert_fails_with(data, tmp_path, "field_applicability[0].reason")


def test_duplicate_rating_applicability_fails(tmp_path: Path) -> None:
    data = valid_data()
    first_component(data)["field_applicability"] = [
        applicability_entry(),
        applicability_entry(status="MODEL_OR_TYPE_SEMANTICS"),
    ]

    assert_fails_with(data, tmp_path, "duplicate field_applicability field")


def test_field_applicability_does_not_replace_missing_quantity(
    tmp_path: Path,
) -> None:
    data = valid_data()
    component = first_component(data)
    component["quantity_guess"] = None
    component["field_applicability"] = [applicability_entry()]

    assert_fails_with(data, tmp_path, "quantity_guess")


def test_valid_section_aware_contract_passes(tmp_path: Path) -> None:
    result = run_validation(valid_section_data(), tmp_path)

    assert result.status == "PASS", result.red_flags
    assert result.red_flags == []


def test_v01_contract_rejects_section_aware_fields(tmp_path: Path) -> None:
    data = valid_data()
    first_item(data)["section_id"] = "13"

    assert_fails_with(data, tmp_path, "unknown field is not allowed")


@pytest.mark.parametrize("field_name", ["project_id", "section_id", "discipline"])
def test_section_contract_rejects_missing_context(
    tmp_path: Path, field_name: str
) -> None:
    data = valid_section_data()
    del first_item(data)[field_name]

    assert_fails_with(data, tmp_path, f"items[0].{field_name}")


def test_section_contract_rejects_cross_boundary_provenance(tmp_path: Path) -> None:
    data = valid_section_data()
    item = first_item(data)
    provenance = cast(list[dict[str, Any]], item["provenance"])[0]
    provenance["section_id"] = "12"

    assert_fails_with(data, tmp_path, "cross-boundary provenance is not allowed")


def test_section_contract_rejects_unknown_source_document_reference(
    tmp_path: Path,
) -> None:
    data = valid_section_data()
    item = first_item(data)
    item["source_document_id"] = "unknown-document"
    for provenance in cast(list[dict[str, Any]], item["provenance"]):
        provenance["source_document_id"] = "unknown-document"

    assert_fails_with(data, tmp_path, "canonical source record")


def test_section_contract_rejects_mixed_v01_source_structure(tmp_path: Path) -> None:
    data = valid_section_data()
    source = cast(dict[str, Any], data["source"])
    source["source_files"] = source["source_documents"]

    assert_fails_with(data, tmp_path, "source_files")


def test_section_contract_rejects_duplicate_merge_identity(tmp_path: Path) -> None:
    data = valid_section_data()
    duplicate = copy.deepcopy(first_item(data))
    renumber_section_item(duplicate, "ITEM-002")
    cast(list[dict[str, Any]], data["items"]).append(duplicate)

    assert_fails_with(data, tmp_path, "duplicate section-aware item identity")


@pytest.mark.parametrize(
    ("section_id", "discipline"),
    [("12", "ЭОМ"), ("13", "ЭОФ")],
)
def test_same_designation_across_section_boundary_remains_valid(
    tmp_path: Path, section_id: str, discipline: str
) -> None:
    data = valid_section_data()
    variant = append_section_item_variant(
        data, section_id=section_id, discipline=discipline
    )

    assert (
        variant["normalized_designation"] == first_item(data)["normalized_designation"]
    )
    result = run_validation(data, tmp_path)
    assert result.status == "PASS", result.red_flags


def test_section_contract_rejects_duplicate_component_id(tmp_path: Path) -> None:
    data = valid_section_data()
    components = cast(list[dict[str, Any]], first_item(data)["components"])
    duplicate_id = components[0]["component_id"]
    components[1]["component_id"] = duplicate_id
    for provenance in cast(list[dict[str, Any]], components[1]["provenance"]):
        provenance["component_id"] = duplicate_id

    assert_fails_with(data, tmp_path, "duplicate component_id")


@pytest.mark.parametrize("provenance_owner", ["item", "component", "conflict"])
def test_section_contract_rejects_page_absent_from_source_record(
    tmp_path: Path, provenance_owner: str
) -> None:
    data = valid_section_data()
    item = first_item(data)
    if provenance_owner == "item":
        provenance = cast(list[dict[str, Any]], item["provenance"])[0]
    elif provenance_owner == "component":
        provenance = cast(list[dict[str, Any]], first_component(data)["provenance"])[0]
    else:
        conflict_provenance = copy.deepcopy(
            cast(list[dict[str, Any]], item["provenance"])[0]
        )
        item["conflicts"] = [
            {
                "conflict_id": "CONFLICT-001",
                "type": "synthetic_conflict",
                "field": "source_presence",
                "message": "Synthetic conflict for provenance validation.",
                "sources": [conflict_provenance],
            }
        ]
        provenance = conflict_provenance
    provenance["page"] = 999

    assert_fails_with(
        data,
        tmp_path,
        "provenance page is not present in canonical source document",
    )


def test_section_contract_accepts_multiple_canonical_pages(tmp_path: Path) -> None:
    data = valid_section_data()
    source = cast(dict[str, Any], data["source"])
    document = cast(list[dict[str, Any]], source["source_documents"])[0]
    cast(list[dict[str, Any]], document["pages"]).append(
        {"page": 2, "status": "text_available"}
    )
    item = first_item(data)
    second_page = copy.deepcopy(cast(list[dict[str, Any]], item["provenance"])[0])
    second_page["page"] = 2
    second_page["locator"] = "page=2; block=1"
    cast(list[dict[str, Any]], item["provenance"]).append(second_page)

    result = run_validation(data, tmp_path)
    assert result.status == "PASS", result.red_flags


def test_malformed_json_fails(tmp_path: Path) -> None:
    path = tmp_path / "malformed.json"
    path.write_text("{not-json", encoding="utf-8")

    result = validator.validate_preliminary_composition_draft(path)

    assert result.status == "FAIL"
    assert "input JSON is malformed" in result.red_flags


def test_missing_required_root_field_fails(tmp_path: Path) -> None:
    data = valid_data()
    del data["draft_id"]

    assert_fails_with(data, tmp_path, "required field is missing: draft_id")


def test_wrong_schema_version_fails(tmp_path: Path) -> None:
    data = valid_data()
    data["schema_version"] = "preliminary_composition_draft.v9"

    assert_fails_with(data, tmp_path, "schema_version must be")


def test_confirmed_by_igor_true_fails(tmp_path: Path) -> None:
    data = valid_data()
    cast(dict[str, Any], data["safety"])["confirmed_by_igor"] = True

    assert_fails_with(data, tmp_path, "safety.confirmed_by_igor must be false")


def test_price_execution_authorized_true_fails(tmp_path: Path) -> None:
    data = valid_data()
    cast(dict[str, Any], data["safety"])["price_execution_authorized"] = True

    assert_fails_with(data, tmp_path, "safety.price_execution_authorized must be false")


def test_commercial_csv_authorized_true_fails(tmp_path: Path) -> None:
    data = valid_data()
    cast(dict[str, Any], data["safety"])["commercial_csv_authorized"] = True

    assert_fails_with(data, tmp_path, "safety.commercial_csv_authorized must be false")


def test_sending_authorized_true_fails(tmp_path: Path) -> None:
    data = valid_data()
    cast(dict[str, Any], data["safety"])["sending_authorized"] = True

    assert_fails_with(data, tmp_path, "safety.sending_authorized must be false")


def test_forbidden_key_unit_price_kzt_anywhere_fails(tmp_path: Path) -> None:
    data = valid_data()
    first_component(data)["unit_price_kzt"] = 1000

    assert_fails_with(data, tmp_path, "forbidden key present")


def test_forbidden_key_price_confirmed_by_igor_anywhere_fails(
    tmp_path: Path,
) -> None:
    data = valid_data()
    first_item(data)["price_confirmed_by_igor"] = False

    assert_fails_with(data, tmp_path, "price_confirmed_by_igor")


def test_empty_items_fails(tmp_path: Path) -> None:
    data = valid_data()
    data["items"] = []

    assert_fails_with(data, tmp_path, "items must be a non-empty list")


def test_item_requires_igor_confirmation_false_fails(tmp_path: Path) -> None:
    data = valid_data()
    first_item(data)["requires_igor_confirmation"] = False

    assert_fails_with(data, tmp_path, "requires_igor_confirmation must be true")


def test_component_requires_igor_confirmation_false_fails(tmp_path: Path) -> None:
    data = valid_data()
    first_component(data)["requires_igor_confirmation"] = False

    assert_fails_with(data, tmp_path, "requires_igor_confirmation must be true")


def test_invalid_confidence_below_zero_fails(tmp_path: Path) -> None:
    data = valid_data()
    first_item(data)["confidence"] = -0.01

    assert_fails_with(data, tmp_path, "confidence must be a number from 0 to 1")


def test_invalid_confidence_above_one_fails(tmp_path: Path) -> None:
    data = valid_data()
    first_component(data)["confidence"] = 1.01

    assert_fails_with(data, tmp_path, "confidence must be a number from 0 to 1")


def test_missing_evidence_fails(tmp_path: Path) -> None:
    data = valid_data()
    del first_item(data)["evidence"]

    assert_fails_with(data, tmp_path, "required field is missing: items[0].evidence")


def test_invalid_raw_input_sha256_fails(tmp_path: Path) -> None:
    data = valid_data()
    cast(dict[str, Any], data["source"])["raw_input_sha256"] = "ABC"

    assert_fails_with(data, tmp_path, "raw_input_sha256 must be 64 lowercase hex")


def test_quantity_zero_fails(tmp_path: Path) -> None:
    data = valid_data()
    first_item(data)["quantity_guess"] = 0

    assert_fails_with(data, tmp_path, "field must be a positive integer")


def test_component_quantity_zero_fails(tmp_path: Path) -> None:
    data = valid_data()
    first_component(data)["quantity_guess"] = 0

    assert_fails_with(data, tmp_path, "field must be a positive number")


def test_invalid_install_type_fails(tmp_path: Path) -> None:
    data = valid_data()
    first_component(data)["install_type_guess"] = "panel_magic"

    assert_fails_with(data, tmp_path, "install_type_guess is not allowed")


def test_report_has_safety_boundaries(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = write_json(tmp_path, valid_data())

    assert validator.main(["--input-json", str(path)]) == 0
    report = capsys.readouterr().out

    assert report.startswith("PRELIMINARY_COMPOSITION_DRAFT_VALIDATION_REPORT_START")
    assert "Mode:\npreliminary composition draft validation only" in report
    assert "Commercial status:\nnot confirmed composition" in report
    assert "not price approval" in report
    assert "not client-ready КП" in report
    assert "Human Approval:\nIgor confirmation required" in report
    assert report.rstrip().endswith(
        "PRELIMINARY_COMPOSITION_DRAFT_VALIDATION_REPORT_END"
    )


def test_report_does_not_leak_long_evidence(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data = valid_data()
    secret_long_evidence = "SECRET RAW PROJECT TEXT " * 40
    first_item(data)["evidence"] = [secret_long_evidence]
    path = write_json(tmp_path, data)

    assert validator.main(["--input-json", str(path)]) == 0
    report = capsys.readouterr().out

    assert secret_long_evidence not in report
    assert "SECRET RAW PROJECT TEXT" not in report


def test_old_workflows_do_not_reference_this_validator() -> None:
    validator_name = "validate_preliminary_composition_draft"

    for path in OLD_WORKFLOWS:
        assert path.is_file(), path
        assert validator_name not in path.read_text(encoding="utf-8"), path
