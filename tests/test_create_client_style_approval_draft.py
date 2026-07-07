import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "create_client_style_approval_draft.py"
PREFLIGHT_SCRIPT = PROJECT_ROOT / "scripts" / "preflight_client_style_invoice_export.py"
OLD_WORKFLOWS = (
    PROJECT_ROOT / "scripts" / "run_invoice_quote_commercial_from_csv.py",
    PROJECT_ROOT / "scripts" / "make_quote_capacity100_commercial_checked.ps1",
    PROJECT_ROOT / "scripts" / "calc_quote_price_draft.py",
    PROJECT_ROOT / "scripts" / "make_quote_capacity100_checked.ps1",
    PROJECT_ROOT / "scripts" / "run_client_style_invoice_export.ps1",
)


def load_script_module(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


approval_draft = cast(
    Any,
    load_script_module("create_client_style_approval_draft_for_test", SCRIPT),
)
preflight_module = cast(
    Any,
    load_script_module(
        "preflight_client_style_invoice_export_for_draft_test",
        PREFLIGHT_SCRIPT,
    ),
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setattr(approval_draft, "PROJECT_ROOT", repo_root)

    commercial_csv = outside / "approved-commercial.csv"
    internal_draft_xlsx = outside / "internal-draft.xlsx"
    template_xlsx = outside / "client-style-template.xlsx"
    output_json = outside / "client-style-approval.draft.json"

    commercial_csv.write_bytes(b"commercial csv bytes\n")
    internal_draft_xlsx.write_bytes(b"internal draft xlsx bytes\n")
    template_xlsx.write_bytes(b"template xlsx bytes\n")

    return {
        "repo_root": repo_root,
        "outside": outside,
        "commercial_csv": commercial_csv,
        "internal_draft_xlsx": internal_draft_xlsx,
        "template_xlsx": template_xlsx,
        "output_json": output_json,
    }


def base_args(case: dict[str, Path]) -> list[str]:
    return [
        "--commercial-csv",
        str(case["commercial_csv"]),
        "--internal-draft-xlsx",
        str(case["internal_draft_xlsx"]),
        "--template-xlsx",
        str(case["template_xlsx"]),
        "--output-json",
        str(case["output_json"]),
        "--approval-id",
        "APPROVAL-EXAMPLE-001",
        "--approved-by",
        "Igor",
        "--approved-at",
        "2099-01-01T12:00:00+05:00",
        "--invoice-number",
        "TEST-001",
        "--invoice-date",
        "2099-01-01",
        "--payer-name",
        "SAFE-PAYER",
        "--vat-text-approved",
        "SECRET VAT TERM",
        "--payment-terms-approved",
        "SECRET PAYMENT TERM",
        "--delivery-terms-approved",
        "SECRET DELIVERY TERM",
        "--validity-terms-approved",
        "SECRET VALIDITY TERM",
        "--return-terms-approved",
        "SECRET RETURN TERM",
        "--signer-name",
        "SAFE-SIGNER",
        "--signer-title",
        "SAFE-TITLE",
        "--approval-note",
        "SECRET APPROVAL NOTE",
    ]


def read_payload(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def test_creates_valid_approval_json_outside_git(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = build_case(tmp_path, monkeypatch)

    assert approval_draft.main(base_args(case)) == 0

    payload = read_payload(case["output_json"])
    assert list(payload) == list(preflight_module.REQUIRED_FIELDS)
    assert payload["approval_id"] == "APPROVAL-EXAMPLE-001"
    assert payload["approved_by"] == "Igor"
    assert payload["invoice_number"] == "TEST-001"


def test_hashes_match_input_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = build_case(tmp_path, monkeypatch)

    assert approval_draft.main(base_args(case)) == 0

    payload = read_payload(case["output_json"])
    assert payload["commercial_csv_sha256"] == sha256(case["commercial_csv"])
    assert payload["internal_draft_xlsx_sha256"] == sha256(case["internal_draft_xlsx"])
    assert payload["template_sha256"] == sha256(case["template_xlsx"])


def test_object_name_is_null_when_not_supplied(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = build_case(tmp_path, monkeypatch)

    assert approval_draft.main(base_args(case)) == 0

    assert read_payload(case["output_json"])["object_name"] is None


def test_object_name_string_when_supplied(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = build_case(tmp_path, monkeypatch)

    assert approval_draft.main([*base_args(case), "--object-name", "SAFE-OBJECT"]) == 0

    assert read_payload(case["output_json"])["object_name"] == "SAFE-OBJECT"


def test_output_existing_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = build_case(tmp_path, monkeypatch)
    case["output_json"].write_text("existing", encoding="utf-8")

    assert approval_draft.main(base_args(case)) == 1

    assert case["output_json"].read_text(encoding="utf-8") == "existing"


def test_output_inside_git_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = build_case(tmp_path, monkeypatch)
    case["output_json"] = case["repo_root"] / "approval.draft.json"

    assert approval_draft.main(base_args(case)) == 1

    assert not case["output_json"].exists()


def test_missing_input_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = build_case(tmp_path, monkeypatch)
    case["commercial_csv"].unlink()

    assert approval_draft.main(base_args(case)) == 1

    assert not case["output_json"].exists()


def test_input_inside_git_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = build_case(tmp_path, monkeypatch)
    inside_csv = case["repo_root"] / "approved-commercial.csv"
    inside_csv.write_bytes(case["commercial_csv"].read_bytes())
    case["commercial_csv"] = inside_csv

    assert approval_draft.main(base_args(case)) == 1

    assert not case["output_json"].exists()


def test_no_xlsx_or_csv_generated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = build_case(tmp_path, monkeypatch)
    before = {path.name for path in case["outside"].iterdir()}

    assert approval_draft.main(base_args(case)) == 0

    after = {path.name for path in case["outside"].iterdir()}
    assert after - before == {case["output_json"].name}
    assert not any(name.endswith(".candidate.xlsx") for name in after - before)
    assert not any(name.endswith(".csv") for name in after - before)


def test_does_not_call_exporter_or_launcher() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "export_client_style_invoice.py" not in text
    assert "run_client_style_invoice_export.ps1" not in text


def test_no_git_commands_in_script() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "subprocess" not in text
    assert "os.system" not in text
    assert "check_call" not in text
    assert "check_output" not in text
    assert "Popen" not in text


def test_report_contains_safety_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    case = build_case(tmp_path, monkeypatch)

    assert approval_draft.main(base_args(case)) == 0
    report = capsys.readouterr().out

    assert report.startswith("CLIENT_STYLE_APPROVAL_DRAFT_REPORT_START")
    assert "Mode:\napproval JSON draft only" in report
    assert "Commercial status:\nnot commercial approval" in report
    assert "Sending status:\nnot sending approval" in report
    assert "Human review:\nmanual Igor review required" in report
    assert report.rstrip().endswith("CLIENT_STYLE_APPROVAL_DRAFT_REPORT_END")


def test_report_does_not_print_full_approved_terms(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    case = build_case(tmp_path, monkeypatch)

    assert approval_draft.main(base_args(case)) == 0
    report = capsys.readouterr().out

    for secret in (
        "SECRET VAT TERM",
        "SECRET PAYMENT TERM",
        "SECRET DELIVERY TERM",
        "SECRET VALIDITY TERM",
        "SECRET RETURN TERM",
        "SECRET APPROVAL NOTE",
    ):
        assert secret not in report


def test_json_schema_matches_approval_preflight_expectations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = build_case(tmp_path, monkeypatch)

    assert approval_draft.main(base_args(case)) == 0

    payload = read_payload(case["output_json"])
    assert tuple(payload) == tuple(preflight_module.REQUIRED_FIELDS)


def test_old_workflows_do_not_reference_this_helper() -> None:
    helper_name = "create_client_style_approval_draft"

    for path in OLD_WORKFLOWS:
        assert path.is_file(), path
        assert helper_name not in path.read_text(encoding="utf-8"), path
