import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest
from openpyxl import Workbook  # type: ignore[import-untyped]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    PROJECT_ROOT / "scripts" / "preflight_client_style_invoice_template_contract.py"
)
EXAMPLE_CONTRACT = (
    PROJECT_ROOT / "examples" / "client_style_invoice_template_contract.example.json"
)
EXISTING_PRODUCTION_ENTRY_POINTS = (
    PROJECT_ROOT / "scripts" / "run_invoice_quote_commercial_from_csv.py",
    PROJECT_ROOT / "scripts" / "make_quote_capacity100_commercial_checked.ps1",
    PROJECT_ROOT / "scripts" / "calc_quote_price_draft.py",
    PROJECT_ROOT / "scripts" / "make_quote_capacity100_checked.ps1",
    PROJECT_ROOT / "scripts" / "preflight_client_style_invoice_export.py",
)


def load_script_module(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


preflight_module = cast(
    Any,
    load_script_module(
        "preflight_client_style_invoice_template_contract_for_test",
        SCRIPT,
    ),
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create_template(
    path: Path,
    *,
    sheet_name: str = "Лист1",
    extra_sheets: tuple[str, ...] = (),
    fixed_label: str = "№ п/п",
    orientation: str | None = "portrait",
    paper_size: str | None = "9",
    print_area: str | None = "B1:I30",
) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = sheet_name
    worksheet["C9"] = "SYNTHETIC INVOICE"
    worksheet["E9"] = "SYNTHETIC DATE"
    worksheet["C10"] = "SYNTHETIC PAYER"
    worksheet["B15"] = fixed_label
    worksheet["C15"] = "Наименование"
    worksheet["D15"] = "Ед."
    worksheet["E15"] = "Кол-во"
    worksheet["F15"] = "Приборы"
    worksheet["G15"] = "Шкаф"
    worksheet["H15"] = "Цена"
    worksheet["I15"] = "Сумма"
    worksheet["C16"] = "SYNTHETIC ITEM"
    worksheet["C19"] = "SYNTHETIC AMOUNT WORDS"
    worksheet["C29"] = "SYNTHETIC SIGNER TITLE"
    worksheet["F29"] = "SYNTHETIC SIGNER NAME"
    worksheet.page_setup.orientation = orientation
    worksheet.page_setup.paperSize = paper_size
    if print_area is not None:
        worksheet.print_area = print_area
    for extra_sheet in extra_sheets:
        workbook.create_sheet(extra_sheet)
    workbook.save(path)
    workbook.close()


def contract_data(
    template: Path,
    *,
    expected_sheet_name: str = "Лист1",
    allowed_extra_sheets: list[str] | None = None,
    fixed_label_text: str = "№",
) -> dict[str, Any]:
    return {
        "contract_id": "SYNTHETIC-CONTRACT",
        "template_name": "SYNTHETIC-TEMPLATE",
        "template_version": "SYNTHETIC-VERSION",
        "expected_sheet_name": expected_sheet_name,
        "template_sha256": sha256(template),
        "allowed_extra_sheets": allowed_extra_sheets or [],
        "print": {
            "orientation": "portrait",
            "paper_size": "9",
            "print_area_required": True,
        },
        "layout": {
            "invoice_number_cell": "C9",
            "invoice_date_cell": "E9",
            "payer_cell": "C10",
            "object_cell": None,
            "table_header_row": 15,
            "first_item_row": 16,
            "item_columns": {
                "index": "B",
                "name": "C",
                "unit": "D",
                "quantity": "E",
                "instruments_and_devices": "F",
                "cabinet": "G",
                "unit_price": "H",
                "line_total": "I",
            },
            "amount_words_cell": "C19",
            "signer_name_cell": "F29",
            "signer_title_cell": "C29",
        },
        "required_fixed_labels": [
            {
                "cell": "B15",
                "expected_text_contains": fixed_label_text,
            },
            {
                "cell": "C15",
                "expected_text_contains": "Наименование",
            },
            {
                "cell": "I15",
                "expected_text_contains": "Сумма",
            },
        ],
    }


def write_contract(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def build_valid_case(tmp_path: Path, monkeypatch: Any) -> dict[str, Any]:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setattr(preflight_module, "PROJECT_ROOT", repo_root)

    template = outside / "client-template.xlsx"
    contract = outside / "template-contract.json"
    create_template(template)
    data = contract_data(template)
    write_contract(contract, data)
    return {
        "repo_root": repo_root,
        "outside": outside,
        "template": template,
        "contract": contract,
        "data": data,
    }


def refresh_template_hash(case: dict[str, Any]) -> None:
    case["data"]["template_sha256"] = sha256(case["template"])
    write_contract(case["contract"], case["data"])


def run_preflight(case: dict[str, Any]) -> Any:
    return preflight_module.preflight(case["template"], case["contract"])


def report_for(case: dict[str, Any]) -> str:
    return cast(str, preflight_module.format_report(run_preflight(case)))


def assert_status(case: dict[str, Any], expected: str) -> str:
    report = report_for(case)
    assert f"Status:\n{expected}" in report
    return report


def test_valid_synthetic_template_with_matching_contract_passes(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    case = build_valid_case(tmp_path, monkeypatch)

    report = assert_status(case, "PASS")

    assert "input paths: pass" in report
    assert "contract schema: pass" in report
    assert "template hash: pass" in report
    assert "workbook layout: pass" in report
    assert "fixed labels: pass" in report
    assert "print setup: pass" in report
    assert "safety boundaries: pass" in report
    assert "Red flags:\nnone" in report


def test_missing_template_file_fails(tmp_path: Path, monkeypatch: Any) -> None:
    case = build_valid_case(tmp_path, monkeypatch)
    case["template"].unlink()

    report = assert_status(case, "FAIL")

    assert "template XLSX does not exist" in report


def test_template_inside_git_fails(tmp_path: Path, monkeypatch: Any) -> None:
    case = build_valid_case(tmp_path, monkeypatch)
    inside_template = case["repo_root"] / "client-template.xlsx"
    create_template(inside_template)
    case["template"] = inside_template
    refresh_template_hash(case)

    report = assert_status(case, "FAIL")

    assert "template XLSX must be outside the Git project" in report


def test_invalid_template_suffix_fails(tmp_path: Path, monkeypatch: Any) -> None:
    case = build_valid_case(tmp_path, monkeypatch)
    renamed = case["template"].with_suffix(".xls")
    case["template"].replace(renamed)
    case["template"] = renamed
    refresh_template_hash(case)

    report = assert_status(case, "FAIL")

    assert "template suffix must be .xlsx" in report


def test_missing_contract_file_fails(tmp_path: Path, monkeypatch: Any) -> None:
    case = build_valid_case(tmp_path, monkeypatch)
    case["contract"].unlink()

    report = assert_status(case, "FAIL")

    assert "contract JSON does not exist" in report


def test_invalid_json_fails(tmp_path: Path, monkeypatch: Any) -> None:
    case = build_valid_case(tmp_path, monkeypatch)
    case["contract"].write_text("{invalid", encoding="utf-8")

    report = assert_status(case, "FAIL")

    assert "contract JSON is invalid" in report


def test_missing_required_field_fails(tmp_path: Path, monkeypatch: Any) -> None:
    case = build_valid_case(tmp_path, monkeypatch)
    del case["data"]["template_version"]
    write_contract(case["contract"], case["data"])

    report = assert_status(case, "FAIL")

    assert "contract field is missing: template_version" in report


@pytest.mark.parametrize(
    "invalid_hash",
    ["", "a" * 63, "a" * 65, "A" * 64, "g" * 64],
)
def test_invalid_template_sha256_format_fails(
    invalid_hash: str,
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    case = build_valid_case(tmp_path, monkeypatch)
    case["data"]["template_sha256"] = invalid_hash
    write_contract(case["contract"], case["data"])

    report = assert_status(case, "FAIL")

    assert "template_sha256 must be exactly 64 lowercase hex characters" in report


def test_template_hash_mismatch_fails(tmp_path: Path, monkeypatch: Any) -> None:
    case = build_valid_case(tmp_path, monkeypatch)
    case["data"]["template_sha256"] = "0" * 64
    write_contract(case["contract"], case["data"])

    report = assert_status(case, "FAIL")

    assert "template SHA256 does not match contract" in report
    assert "template hash: fail" in report


def test_expected_sheet_missing_fails(tmp_path: Path, monkeypatch: Any) -> None:
    case = build_valid_case(tmp_path, monkeypatch)
    case["data"]["expected_sheet_name"] = "Missing"
    write_contract(case["contract"], case["data"])

    report = assert_status(case, "FAIL")

    assert "expected worksheet is missing" in report


def test_unexpected_extra_sheet_fails(tmp_path: Path, monkeypatch: Any) -> None:
    case = build_valid_case(tmp_path, monkeypatch)
    create_template(case["template"], extra_sheets=("Extra",))
    refresh_template_hash(case)

    report = assert_status(case, "FAIL")

    assert "workbook contains an unexpected extra worksheet" in report


def test_allowed_extra_sheet_is_accepted(tmp_path: Path, monkeypatch: Any) -> None:
    case = build_valid_case(tmp_path, monkeypatch)
    create_template(case["template"], extra_sheets=("Extra",))
    case["data"]["allowed_extra_sheets"] = ["Extra"]
    refresh_template_hash(case)

    assert_status(case, "PASS")


def test_invalid_cell_coordinate_fails(tmp_path: Path, monkeypatch: Any) -> None:
    case = build_valid_case(tmp_path, monkeypatch)
    case["data"]["layout"]["payer_cell"] = "A0"
    write_contract(case["contract"], case["data"])

    report = assert_status(case, "FAIL")

    assert "contract field must be a valid Excel cell: layout.payer_cell" in report


def test_invalid_item_column_fails(tmp_path: Path, monkeypatch: Any) -> None:
    case = build_valid_case(tmp_path, monkeypatch)
    case["data"]["layout"]["item_columns"]["line_total"] = "XFE"
    write_contract(case["contract"], case["data"])

    report = assert_status(case, "FAIL")

    assert (
        "contract field must be a valid Excel column: " "layout.item_columns.line_total"
    ) in report


def test_layout_cell_outside_used_range_fails(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    case = build_valid_case(tmp_path, monkeypatch)
    case["data"]["layout"]["payer_cell"] = "Z100"
    write_contract(case["contract"], case["data"])

    report = assert_status(case, "FAIL")

    assert "layout cell is outside worksheet used range: payer_cell" in report


def test_first_item_row_must_follow_header(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    case = build_valid_case(tmp_path, monkeypatch)
    case["data"]["layout"]["first_item_row"] = 15
    write_contract(case["contract"], case["data"])

    report = assert_status(case, "FAIL")

    assert (
        "layout.first_item_row must be greater than layout.table_header_row" in report
    )


def test_fixed_label_missing_fails(tmp_path: Path, monkeypatch: Any) -> None:
    case = build_valid_case(tmp_path, monkeypatch)
    create_template(case["template"], fixed_label="SYNTHETIC OTHER LABEL")
    refresh_template_hash(case)

    report = assert_status(case, "FAIL")

    assert "required fixed label mismatch at item 1" in report


def test_print_area_required_but_absent_fails(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    case = build_valid_case(tmp_path, monkeypatch)
    create_template(case["template"], print_area=None)
    refresh_template_hash(case)

    report = assert_status(case, "FAIL")

    assert "print area is required but missing" in report


def test_orientation_mismatch_fails(tmp_path: Path, monkeypatch: Any) -> None:
    case = build_valid_case(tmp_path, monkeypatch)
    create_template(case["template"], orientation="landscape")
    refresh_template_hash(case)

    report = assert_status(case, "FAIL")

    assert "print orientation does not match contract" in report


def test_paper_size_mismatch_fails(tmp_path: Path, monkeypatch: Any) -> None:
    case = build_valid_case(tmp_path, monkeypatch)
    create_template(case["template"], paper_size="1")
    refresh_template_hash(case)

    report = assert_status(case, "FAIL")

    assert "print paper size does not match contract" in report


def test_script_does_not_modify_template_hash(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    case = build_valid_case(tmp_path, monkeypatch)
    before = sha256(case["template"])

    assert_status(case, "PASS")

    assert sha256(case["template"]) == before


def test_report_contains_safety_boundaries(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    case = build_valid_case(tmp_path, monkeypatch)

    report = assert_status(case, "PASS")

    assert "Mode:\nread-only client-style invoice template contract preflight" in report
    assert "safety boundaries: pass" in report
    assert (
        "Commercial status:\n"
        "template preflight only; PASS is not client export approval"
    ) in report
    assert (
        "Human Approval:\n" "required before generating or sending client-style invoice"
    ) in report
    assert "production contract must be outside Git" in report
    assert report.startswith("CLIENT_STYLE_TEMPLATE_CONTRACT_PREFLIGHT_REPORT_START")
    assert report.endswith("CLIENT_STYLE_TEMPLATE_CONTRACT_PREFLIGHT_REPORT_END")


def test_report_does_not_leak_long_fixed_label(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    case = build_valid_case(tmp_path, monkeypatch)
    secret_label = "FULL-SECRET-SYNTHETIC-FIXED-LABEL-" + "X" * 120
    case["data"]["required_fixed_labels"][0]["expected_text_contains"] = secret_label
    write_contract(case["contract"], case["data"])

    report = assert_status(case, "FAIL")

    assert secret_label not in report
    assert "required fixed label mismatch at item 1" in report


def test_real_contract_inside_git_fails(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    case = build_valid_case(tmp_path, monkeypatch)
    inside_contract = case["repo_root"] / "real-contract.json"
    write_contract(inside_contract, case["data"])
    case["contract"] = inside_contract

    report = assert_status(case, "FAIL")

    assert "production contract JSON must be outside the Git project" in report


def test_documented_example_contract_path_inside_git_is_allowed(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    case = build_valid_case(tmp_path, monkeypatch)
    examples = case["repo_root"] / "examples"
    examples.mkdir()
    example_contract = examples / "client_style_invoice_template_contract.example.json"
    write_contract(example_contract, case["data"])
    case["contract"] = example_contract

    assert_status(case, "PASS")


def test_example_contract_is_safe_placeholder() -> None:
    text = EXAMPLE_CONTRACT.read_text(encoding="utf-8")
    data = json.loads(text)

    assert data["expected_sheet_name"] == "Лист1"
    assert data["layout"]["table_header_row"] == 15
    assert data["layout"]["first_item_row"] == 16
    assert data["layout"]["item_columns"] == {
        "index": "B",
        "name": "C",
        "unit": "D",
        "quantity": "E",
        "instruments_and_devices": "F",
        "cabinet": "G",
        "unit_price": "H",
        "line_total": "I",
    }
    assert preflight_module.HASH_RE.fullmatch(data["template_sha256"])
    assert "TDK Energy" not in text
    assert "551" not in text
    assert "IBAN" not in text


def test_old_workflows_remain_isolated() -> None:
    reference = "preflight_client_style_invoice_template_contract"
    for path in EXISTING_PRODUCTION_ENTRY_POINTS:
        assert path.is_file(), path
        assert reference not in path.read_text(encoding="utf-8"), path


def test_cli_exit_codes_match_status(tmp_path: Path) -> None:
    template = tmp_path / "client-template.xlsx"
    contract = tmp_path / "template-contract.json"
    create_template(template)
    data = contract_data(template)
    write_contract(contract, data)
    command = [
        sys.executable,
        str(SCRIPT),
        "--template-xlsx",
        str(template),
        "--contract-json",
        str(contract),
    ]

    pass_result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    data["template_sha256"] = "0" * 64
    write_contract(contract, data)
    fail_result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )

    assert pass_result.returncode == 0
    assert "Status:\nPASS" in pass_result.stdout
    assert fail_result.returncode == 1
    assert "Status:\nFAIL" in fail_result.stdout
