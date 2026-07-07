import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "verify_preliminary_composition_source_bundle.py"
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


def load_bundle_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "verify_preliminary_composition_source_bundle_for_test",
        SCRIPT,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


verifier = cast(Any, load_bundle_module())


def valid_data(raw_text: str = "Synthetic raw request text.\n") -> dict[str, Any]:
    data = cast(dict[str, Any], json.loads(EXAMPLE.read_text(encoding="utf-8")))
    cast(dict[str, Any], data["source"])["raw_input_sha256"] = hashlib.sha256(
        raw_text.encode("utf-8")
    ).hexdigest()
    return data


def write_raw_text(tmp_path: Path, text: str = "Synthetic raw request text.\n") -> Path:
    path = tmp_path / "raw-request.txt"
    path.write_bytes(text.encode("utf-8"))
    return path


def write_draft(tmp_path: Path, data: dict[str, Any]) -> Path:
    path = tmp_path / "draft.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run_bundle(
    tmp_path: Path,
    raw_text: str = "Synthetic raw request text.\n",
    data: dict[str, Any] | None = None,
) -> Any:
    raw_path = write_raw_text(tmp_path, raw_text)
    draft_path = write_draft(
        tmp_path,
        data if data is not None else valid_data(raw_text),
    )
    return verifier.verify_source_bundle(raw_path, draft_path)


def test_valid_raw_input_and_matching_draft_passes(tmp_path: Path) -> None:
    result = run_bundle(tmp_path)

    assert result.status == "PASS"
    assert result.red_flags == []
    assert all(status == "pass" for status in result.checks.values())


def test_missing_raw_input_fails(tmp_path: Path) -> None:
    draft_path = write_draft(tmp_path, valid_data())
    missing_raw = tmp_path / "missing-raw.txt"

    result = verifier.verify_source_bundle(missing_raw, draft_path)

    assert result.status == "FAIL"
    assert result.checks["raw input readable"] == "fail"
    assert "raw input text does not exist" in result.red_flags


def test_non_utf8_raw_input_fails(tmp_path: Path) -> None:
    raw_path = tmp_path / "raw-request.txt"
    raw_path.write_bytes(b"\xff\xfe\x00")
    draft_path = write_draft(tmp_path, valid_data())

    result = verifier.verify_source_bundle(raw_path, draft_path)

    assert result.status == "FAIL"
    assert "raw input text must be valid UTF-8" in result.red_flags


def test_missing_draft_json_fails(tmp_path: Path) -> None:
    raw_path = write_raw_text(tmp_path)
    missing_draft = tmp_path / "missing-draft.json"

    result = verifier.verify_source_bundle(raw_path, missing_draft)

    assert result.status == "FAIL"
    assert result.checks["draft validation"] == "fail"
    assert "draft validation: input JSON does not exist" in result.red_flags


def test_malformed_draft_json_fails_through_validator(tmp_path: Path) -> None:
    raw_path = write_raw_text(tmp_path)
    draft_path = tmp_path / "draft.json"
    draft_path.write_text("{not-json", encoding="utf-8")

    result = verifier.verify_source_bundle(raw_path, draft_path)

    assert result.status == "FAIL"
    assert result.checks["draft validation"] == "fail"
    assert "draft validation: input JSON is malformed" in result.red_flags


def test_draft_validator_fail_causes_bundle_fail(tmp_path: Path) -> None:
    data = valid_data()
    cast(dict[str, Any], data["safety"])["price_execution_authorized"] = True

    result = run_bundle(tmp_path, data=data)

    assert result.status == "FAIL"
    assert result.checks["draft validation"] == "fail"
    assert any("price_execution_authorized" in flag for flag in result.red_flags)


def test_raw_input_sha256_mismatch_fails(tmp_path: Path) -> None:
    data = valid_data()
    cast(dict[str, Any], data["source"])["raw_input_sha256"] = "0" * 64

    result = run_bundle(tmp_path, data=data)

    assert result.status == "FAIL"
    assert result.checks["source hash match"] == "fail"
    assert "raw input SHA256 mismatch" in result.red_flags


def test_missing_source_raw_input_sha256_fails(tmp_path: Path) -> None:
    data = valid_data()
    del cast(dict[str, Any], data["source"])["raw_input_sha256"]

    result = run_bundle(tmp_path, data=data)

    assert result.status == "FAIL"
    assert result.checks["source hash match"] == "fail"
    assert "source.raw_input_sha256 is missing or invalid" in result.red_flags


def test_report_does_not_leak_raw_input_text(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw_text = "SECRET RAW REQUEST TEXT should never appear in the report.\n"
    raw_path = write_raw_text(tmp_path, raw_text)
    draft_path = write_draft(tmp_path, valid_data(raw_text))

    assert (
        verifier.main(
            ["--raw-input-text", str(raw_path), "--draft-json", str(draft_path)]
        )
        == 0
    )
    report = capsys.readouterr().out

    assert "SECRET RAW REQUEST TEXT" not in report
    assert raw_text not in report


def test_report_does_not_leak_long_evidence(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw_text = "Synthetic raw request text.\n"
    data = valid_data(raw_text)
    secret_long_evidence = "SECRET LONG EVIDENCE BLOCK " * 40
    cast(list[dict[str, Any]], data["items"])[0]["evidence"] = [secret_long_evidence]
    raw_path = write_raw_text(tmp_path, raw_text)
    draft_path = write_draft(tmp_path, data)

    assert (
        verifier.main(
            ["--raw-input-text", str(raw_path), "--draft-json", str(draft_path)]
        )
        == 0
    )
    report = capsys.readouterr().out

    assert secret_long_evidence not in report
    assert "SECRET LONG EVIDENCE BLOCK" not in report


def test_no_output_or_generated_files_created(tmp_path: Path) -> None:
    before = {path.relative_to(tmp_path) for path in tmp_path.rglob("*")}
    result = run_bundle(tmp_path)
    after = {path.relative_to(tmp_path) for path in tmp_path.rglob("*")}

    assert result.status == "PASS"
    assert after - before == {Path("raw-request.txt"), Path("draft.json")}


def test_script_does_not_reference_price_calculator() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "calc_quote_price_draft" not in source
    assert "price calculator" not in source.lower()


def test_script_does_not_reference_commercial_writer_or_launcher() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "run_invoice_quote_commercial_from_csv" not in source
    assert "make_quote_capacity100_commercial_checked" not in source
    assert "commercial writer" not in source.lower()


def test_script_does_not_reference_client_style_exporter_or_launcher() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "export_client_style_invoice" not in source
    assert "run_client_style_invoice_export" not in source
    assert "client-style exporter" not in source.lower()


def test_script_does_not_call_git() -> None:
    source = SCRIPT.read_text(encoding="utf-8").lower()

    assert "subprocess" not in source
    assert " git " not in source
    assert "git." not in source


def test_old_workflows_do_not_reference_this_verifier() -> None:
    verifier_name = "verify_preliminary_composition_source_bundle"

    for path in OLD_WORKFLOWS:
        assert path.is_file(), path
        assert verifier_name not in path.read_text(encoding="utf-8"), path
