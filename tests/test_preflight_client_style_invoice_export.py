import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "preflight_client_style_invoice_export.py"
EXAMPLE_APPROVAL = (
    PROJECT_ROOT / "examples" / "client_style_invoice_approval.example.json"
)
EXISTING_PRODUCTION_ENTRY_POINTS = (
    PROJECT_ROOT / "scripts" / "run_invoice_quote_commercial_from_csv.py",
    PROJECT_ROOT / "scripts" / "make_quote_capacity100_commercial_checked.ps1",
    PROJECT_ROOT / "scripts" / "calc_quote_price_draft.py",
    PROJECT_ROOT / "scripts" / "make_quote_capacity100_checked.ps1",
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
    load_script_module("preflight_client_style_invoice_export_for_test", SCRIPT),
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def approval_data(
    commercial_csv: Path,
    internal_draft_xlsx: Path,
    template_xlsx: Path,
    *,
    object_name: str | None = None,
) -> dict[str, Any]:
    return {
        "approval_id": "SYNTHETIC-APPROVAL-ID",
        "approved_by": "SYNTHETIC-APPROVER",
        "approved_at": "2099-01-01T12:30:00+00:00",
        "commercial_csv_sha256": sha256(commercial_csv),
        "internal_draft_xlsx_sha256": sha256(internal_draft_xlsx),
        "template_sha256": sha256(template_xlsx),
        "invoice_number": "SYNTHETIC-INVOICE",
        "invoice_date": "2099-01-01",
        "payer_name": "SYNTHETIC-PAYER",
        "object_name": object_name,
        "vat_text_approved": "SYNTHETIC VAT APPROVED TEXT",
        "payment_terms_approved": "SYNTHETIC PAYMENT APPROVED TEXT",
        "delivery_terms_approved": "SYNTHETIC DELIVERY APPROVED TEXT",
        "validity_terms_approved": "SYNTHETIC VALIDITY APPROVED TEXT",
        "return_terms_approved": "SYNTHETIC RETURN APPROVED TEXT",
        "signer_name": "SYNTHETIC-SIGNER",
        "signer_title": "SYNTHETIC-SIGNER-TITLE",
        "approval_note": "SYNTHETIC APPROVAL NOTE",
    }


def write_approval(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def build_valid_case(
    tmp_path: Path,
    monkeypatch: Any,
    *,
    object_name: str | None = None,
) -> dict[str, Any]:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setattr(preflight_module, "PROJECT_ROOT", repo_root)

    commercial_csv = outside / "commercial.csv"
    internal_draft_xlsx = outside / "internal-draft.xlsx"
    template_xlsx = outside / "client-template.xlsx"
    approval_json = outside / "approval.json"
    output_xlsx = outside / "client-output.xlsx"

    commercial_csv.write_bytes(b"synthetic commercial csv\n")
    internal_draft_xlsx.write_bytes(b"synthetic internal draft xlsx\n")
    template_xlsx.write_bytes(b"synthetic client template xlsx\n")
    artifact = approval_data(
        commercial_csv,
        internal_draft_xlsx,
        template_xlsx,
        object_name=object_name,
    )
    write_approval(approval_json, artifact)

    return {
        "repo_root": repo_root,
        "commercial_csv": commercial_csv,
        "internal_draft_xlsx": internal_draft_xlsx,
        "template_xlsx": template_xlsx,
        "approval_json": approval_json,
        "output_xlsx": output_xlsx,
        "artifact": artifact,
    }


def run_preflight(case: dict[str, Any]) -> Any:
    return preflight_module.preflight(
        case["commercial_csv"],
        case["internal_draft_xlsx"],
        case["template_xlsx"],
        case["approval_json"],
        case["output_xlsx"],
    )


def report_for(case: dict[str, Any]) -> str:
    return cast(str, preflight_module.format_report(run_preflight(case)))


def assert_status(case: dict[str, Any], expected: str) -> str:
    report = report_for(case)
    assert f"Status:\n{expected}" in report
    return report


def test_valid_artifact_with_matching_hashes_passes(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    case = build_valid_case(tmp_path, monkeypatch)

    report = assert_status(case, "PASS")

    assert "input paths: pass" in report
    assert "output policy: pass" in report
    assert "approval artifact schema: pass" in report
    assert "hash verification: pass" in report
    assert "Red flags:\nnone" in report


def test_missing_required_field_fails(tmp_path: Path, monkeypatch: Any) -> None:
    case = build_valid_case(tmp_path, monkeypatch)
    del case["artifact"]["approval_note"]
    write_approval(case["approval_json"], case["artifact"])

    report = assert_status(case, "FAIL")

    assert "approval field is missing: approval_note" in report
    assert "approval artifact schema: fail" in report


@pytest.mark.parametrize("invalid_value", ["", "   ", 551])
def test_required_non_object_field_must_be_nonempty_string(
    invalid_value: Any,
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    case = build_valid_case(tmp_path, monkeypatch)
    case["artifact"]["invoice_number"] = invalid_value
    write_approval(case["approval_json"], case["artifact"])

    report = assert_status(case, "FAIL")

    assert "approval field must be a non-empty string: invoice_number" in report


def test_object_name_null_is_accepted(tmp_path: Path, monkeypatch: Any) -> None:
    case = build_valid_case(tmp_path, monkeypatch, object_name=None)

    assert_status(case, "PASS")


def test_object_name_string_is_accepted(tmp_path: Path, monkeypatch: Any) -> None:
    case = build_valid_case(
        tmp_path,
        monkeypatch,
        object_name="SYNTHETIC-OBJECT",
    )

    assert_status(case, "PASS")


@pytest.mark.parametrize(
    "invalid_hash",
    [
        "",
        "a" * 63,
        "a" * 65,
        "A" * 64,
        "g" * 64,
    ],
)
def test_invalid_hash_format_fails(
    invalid_hash: str,
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    case = build_valid_case(tmp_path, monkeypatch)
    case["artifact"]["commercial_csv_sha256"] = invalid_hash
    write_approval(case["approval_json"], case["artifact"])

    report = assert_status(case, "FAIL")

    assert (
        "approval hash must be 64 lowercase hex characters: " "commercial_csv_sha256"
    ) in report


def test_hash_mismatch_fails(tmp_path: Path, monkeypatch: Any) -> None:
    case = build_valid_case(tmp_path, monkeypatch)
    case["artifact"]["template_sha256"] = "0" * 64
    write_approval(case["approval_json"], case["artifact"])

    report = assert_status(case, "FAIL")

    assert "client-style template SHA256 does not match approval" in report
    assert "hash verification: fail" in report


def test_approved_at_without_timezone_fails(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    case = build_valid_case(tmp_path, monkeypatch)
    case["artifact"]["approved_at"] = "2099-01-01T12:30:00"
    write_approval(case["approval_json"], case["artifact"])

    report = assert_status(case, "FAIL")

    assert "approved_at must be an ISO 8601 timestamp with timezone" in report


def test_output_inside_git_fails(tmp_path: Path, monkeypatch: Any) -> None:
    case = build_valid_case(tmp_path, monkeypatch)
    case["output_xlsx"] = case["repo_root"] / "client-output.xlsx"

    report = assert_status(case, "FAIL")

    assert "output XLSX must be outside the Git project" in report
    assert "output policy: fail" in report


def test_output_already_exists_fails(tmp_path: Path, monkeypatch: Any) -> None:
    case = build_valid_case(tmp_path, monkeypatch)
    case["output_xlsx"].write_bytes(b"existing output")

    report = assert_status(case, "FAIL")

    assert "output XLSX already exists" in report


def test_template_inside_git_fails(tmp_path: Path, monkeypatch: Any) -> None:
    case = build_valid_case(tmp_path, monkeypatch)
    inside_template = case["repo_root"] / "client-template.xlsx"
    inside_template.write_bytes(b"synthetic inside git template")
    case["template_xlsx"] = inside_template
    case["artifact"]["template_sha256"] = sha256(inside_template)
    write_approval(case["approval_json"], case["artifact"])

    report = assert_status(case, "FAIL")

    assert "client-style template must be outside the Git project" in report


def test_approval_json_inside_git_fails(tmp_path: Path, monkeypatch: Any) -> None:
    case = build_valid_case(tmp_path, monkeypatch)
    inside_approval = case["repo_root"] / "approval.json"
    write_approval(inside_approval, case["artifact"])
    case["approval_json"] = inside_approval

    report = assert_status(case, "FAIL")

    assert "approval JSON must be outside the Git project" in report


def test_report_contains_safety_boundaries(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    case = build_valid_case(tmp_path, monkeypatch)

    report = assert_status(case, "PASS")

    assert "Mode:\nread-only client-style invoice export preflight" in report
    assert "safety boundaries: pass" in report
    assert (
        "Commercial status:\npreflight only; PASS is not commercial approval" in report
    )
    assert "Human Approval:\nrequired before sending to client" in report
    assert report.startswith("CLIENT_STYLE_INVOICE_PREFLIGHT_REPORT_START")
    assert report.endswith("CLIENT_STYLE_INVOICE_PREFLIGHT_REPORT_END")


def test_report_does_not_leak_full_approved_terms(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    case = build_valid_case(tmp_path, monkeypatch)
    secret_terms = (
        "FULL-SECRET-VAT-TERM",
        "FULL-SECRET-PAYMENT-TERM",
        "FULL-SECRET-DELIVERY-TERM",
        "FULL-SECRET-VALIDITY-TERM",
        "FULL-SECRET-RETURN-TERM",
    )
    for field_name, value in zip(
        (
            "vat_text_approved",
            "payment_terms_approved",
            "delivery_terms_approved",
            "validity_terms_approved",
            "return_terms_approved",
        ),
        secret_terms,
        strict=True,
    ):
        case["artifact"][field_name] = value
    write_approval(case["approval_json"], case["artifact"])

    report = assert_status(case, "PASS")

    for secret in secret_terms:
        assert secret not in report
    assert "approved text present" not in report.casefold()


def test_script_does_not_create_output_file(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    case = build_valid_case(tmp_path, monkeypatch)

    assert_status(case, "PASS")

    assert not case["output_xlsx"].exists()


def test_old_workflows_remain_isolated() -> None:
    reference = "preflight_client_style_invoice_export"
    for path in EXISTING_PRODUCTION_ENTRY_POINTS:
        assert path.is_file(), path
        assert reference not in path.read_text(encoding="utf-8"), path


def test_example_approval_is_placeholder_only_and_schema_complete() -> None:
    text = EXAMPLE_APPROVAL.read_text(encoding="utf-8")
    artifact = json.loads(text)

    assert set(preflight_module.REQUIRED_FIELDS).issubset(artifact)
    for field_name in preflight_module.HASH_FIELDS:
        assert preflight_module.HASH_RE.fullmatch(artifact[field_name])
    assert artifact["invoice_number"] == "PLACEHOLDER-INVOICE-NUMBER"
    assert artifact["payer_name"] == "PLACEHOLDER-PAYER-NAME"
    assert artifact["object_name"] is None
    assert "TDK Energy" not in text
    assert "551" not in text


def test_missing_input_file_fails(tmp_path: Path, monkeypatch: Any) -> None:
    case = build_valid_case(tmp_path, monkeypatch)
    case["commercial_csv"].unlink()

    report = assert_status(case, "FAIL")

    assert "commercial CSV does not exist" in report
    assert "hash verification could not run safely" in report


@pytest.mark.parametrize(
    ("case_key", "bad_name", "expected_message"),
    [
        ("commercial_csv", "commercial.txt", "commercial CSV suffix must be .csv"),
        (
            "internal_draft_xlsx",
            "internal-draft.xls",
            "internal draft XLSX suffix must be .xlsx",
        ),
        (
            "template_xlsx",
            "client-template.xls",
            "client-style template suffix must be .xlsx",
        ),
        ("approval_json", "approval.txt", "approval JSON suffix must be .json"),
    ],
)
def test_input_suffix_must_match_contract(
    case_key: str,
    bad_name: str,
    expected_message: str,
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    case = build_valid_case(tmp_path, monkeypatch)
    old_path = case[case_key]
    new_path = old_path.with_name(bad_name)
    old_path.replace(new_path)
    case[case_key] = new_path

    report = assert_status(case, "FAIL")

    assert expected_message in report


def test_output_suffix_parent_and_input_identity_are_checked(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    case = build_valid_case(tmp_path, monkeypatch)
    case["output_xlsx"] = case["internal_draft_xlsx"]

    report = assert_status(case, "FAIL")

    assert "output XLSX already exists" in report
    assert "output XLSX must not match any input path" in report

    case["output_xlsx"] = tmp_path / "missing-parent" / "output.txt"
    report = assert_status(case, "FAIL")
    assert "output suffix must be .xlsx" in report
    assert "output parent directory does not exist" in report


@pytest.mark.parametrize("case_key", ["commercial_csv", "internal_draft_xlsx"])
def test_commercial_and_internal_inputs_must_be_outside_git(
    case_key: str,
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    case = build_valid_case(tmp_path, monkeypatch)
    source = case[case_key]
    inside_path = case["repo_root"] / source.name
    inside_path.write_bytes(source.read_bytes())
    case[case_key] = inside_path

    report = assert_status(case, "FAIL")

    label = "commercial CSV" if case_key == "commercial_csv" else "internal draft XLSX"
    assert f"{label} must be outside the Git project" in report


def test_cli_exit_codes_match_status(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    commercial_csv = outside / "commercial.csv"
    internal_draft_xlsx = outside / "internal-draft.xlsx"
    template_xlsx = outside / "template.xlsx"
    approval_json = outside / "approval.json"
    output_xlsx = outside / "output.xlsx"
    commercial_csv.write_bytes(b"commercial")
    internal_draft_xlsx.write_bytes(b"draft")
    template_xlsx.write_bytes(b"template")
    artifact = approval_data(
        commercial_csv,
        internal_draft_xlsx,
        template_xlsx,
    )
    write_approval(approval_json, artifact)
    command = [
        sys.executable,
        str(SCRIPT),
        "--commercial-csv",
        str(commercial_csv),
        "--internal-draft-xlsx",
        str(internal_draft_xlsx),
        "--template-xlsx",
        str(template_xlsx),
        "--approval-json",
        str(approval_json),
        "--output-xlsx",
        str(output_xlsx),
    ]

    pass_result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    artifact["template_sha256"] = "0" * 64
    write_approval(approval_json, artifact)
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
