import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

from openpyxl import Workbook  # type: ignore[import-untyped]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "inspect_quote_draft.py"


def load_script_module(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


inspector = cast(
    Any,
    load_script_module("inspect_quote_draft_for_test", SCRIPT),
)


def write_workbook(path: Path, value: str = "SYNTHETIC_CELL_VALUE") -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet["A1"] = value
    workbook.save(path)
    workbook.close()


def report_for(path: Path) -> str:
    result = inspector.inspect_draft(path)
    return cast(str, inspector.format_report(result))


def assert_status(path: Path, expected: str) -> str:
    report = report_for(path)
    assert f"Status:\n{expected}" in report
    return report


def test_valid_synthetic_xlsx_outside_git_passes(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(inspector, "PROJECT_ROOT", tmp_path / "repo")
    draft_path = tmp_path / "draft.xlsx"
    write_workbook(draft_path)

    report = assert_status(draft_path, "PASS")

    assert "input path: pass" in report
    assert "outside Git: pass" in report
    assert "suffix: pass" in report
    assert "file size: pass" in report
    assert "workbook opens: pass" in report
    assert "worksheets present: pass" in report


def test_missing_file_fails(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(inspector, "PROJECT_ROOT", tmp_path / "repo")
    draft_path = tmp_path / "missing.xlsx"

    report = assert_status(draft_path, "FAIL")

    assert "input path: fail" in report
    assert "input path does not exist" in report


def test_wrong_suffix_fails(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(inspector, "PROJECT_ROOT", tmp_path / "repo")
    draft_path = tmp_path / "draft.xlsm"
    write_workbook(draft_path)

    report = assert_status(draft_path, "FAIL")

    assert "suffix: fail" in report
    assert "input suffix must be .xlsx" in report


def test_input_inside_repo_fails(tmp_path: Path, monkeypatch: Any) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(inspector, "PROJECT_ROOT", repo_root)
    draft_path = repo_root / "draft.xlsx"
    write_workbook(draft_path)

    report = assert_status(draft_path, "FAIL")

    assert "outside Git: fail" in report
    assert "input draft must be outside the Git project" in report


def test_zero_byte_xlsx_fails(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(inspector, "PROJECT_ROOT", tmp_path / "repo")
    draft_path = tmp_path / "draft.xlsx"
    draft_path.write_bytes(b"")

    report = assert_status(draft_path, "FAIL")

    assert "file size: fail" in report
    assert "input draft file is empty" in report


def test_corrupt_xlsx_fails(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(inspector, "PROJECT_ROOT", tmp_path / "repo")
    draft_path = tmp_path / "draft.xlsx"
    draft_path.write_text("not a workbook", encoding="utf-8")

    report = assert_status(draft_path, "FAIL")

    assert "workbook opens: fail" in report
    assert "workbook could not be opened" in report


def test_workbook_with_worksheet_prints_count(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(inspector, "PROJECT_ROOT", tmp_path / "repo")
    draft_path = tmp_path / "draft.xlsx"
    write_workbook(draft_path)

    report = assert_status(draft_path, "PASS")

    assert "worksheet count: 1" in report


def test_report_markers_present(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(inspector, "PROJECT_ROOT", tmp_path / "repo")
    draft_path = tmp_path / "draft.xlsx"
    write_workbook(draft_path)

    report = report_for(draft_path)

    assert report.startswith("QUOTE_DRAFT_INSPECTION_REPORT_START")
    assert report.endswith("QUOTE_DRAFT_INSPECTION_REPORT_END")


def test_report_does_not_include_cell_values(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(inspector, "PROJECT_ROOT", tmp_path / "repo")
    draft_path = tmp_path / "draft.xlsx"
    write_workbook(draft_path, value="SECRET_SYNTHETIC_CELL_VALUE")

    report = assert_status(draft_path, "PASS")

    assert "SECRET_SYNTHETIC_CELL_VALUE" not in report


def test_cli_exit_code_matches_status(tmp_path: Path) -> None:
    draft_path = tmp_path / "draft.xlsx"
    write_workbook(draft_path)

    pass_result = subprocess.run(
        [sys.executable, str(SCRIPT), "--input", str(draft_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    fail_result = subprocess.run(
        [sys.executable, str(SCRIPT), "--input", str(tmp_path / "missing.xlsx")],
        capture_output=True,
        text=True,
        check=False,
    )

    assert pass_result.returncode == 0
    assert "Status:\nPASS" in pass_result.stdout
    assert fail_result.returncode == 1
    assert "Status:\nFAIL" in fail_result.stdout
