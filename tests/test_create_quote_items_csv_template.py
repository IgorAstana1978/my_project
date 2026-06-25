import csv
import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "create_quote_items_csv_template.py"
WRAPPER = PROJECT_ROOT / "scripts" / "create_quote_items_csv_template.ps1"
EXPECTED_HEADER = (
    "name",
    "unit",
    "quantity",
    "instruments_and_devices",
    "cabinet_type_dimensions_material",
)


def load_script_module(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


template = cast(
    Any,
    load_script_module("create_quote_items_csv_template_for_test", SCRIPT),
)


def test_creates_header_only_strict_semicolon_csv(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(template, "PROJECT_ROOT", tmp_path / "repo")
    output = tmp_path / "items.csv"

    result = template.create_template(output)

    assert result.result == "pass"
    assert output.read_text(encoding="utf-8") == ";".join(EXPECTED_HEADER) + "\n"
    with output.open("r", encoding="utf-8", newline="") as csv_file:
        rows = list(csv.reader(csv_file, delimiter=";"))
    assert rows == [list(EXPECTED_HEADER)]


def test_report_contains_required_template_metadata(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(template, "PROJECT_ROOT", tmp_path / "repo")
    output = tmp_path / "items.csv"

    report = template.format_report(template.create_template(output))

    assert "QUOTE_ITEMS_CSV_TEMPLATE_REPORT" in report
    assert "Result: pass" in report
    assert f"Output: {output.resolve()}" in report
    assert "Rows: 0" in report
    assert "Columns: 5" in report
    assert "Delimiter: ;" in report
    assert "Status: template created" in report


def test_wrong_suffix_fails_without_creating_file(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(template, "PROJECT_ROOT", tmp_path / "repo")
    output = tmp_path / "items.txt"

    result = template.create_template(output)

    assert result.result == "fail"
    assert result.status == "output suffix must be .csv"
    assert not output.exists()


def test_output_inside_project_fails(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(template, "PROJECT_ROOT", repo_root)
    output = repo_root / "items.csv"

    result = template.create_template(output)

    assert result.result == "fail"
    assert result.status == "output CSV must be outside the Git project"
    assert not output.exists()


def test_missing_parent_fails(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(template, "PROJECT_ROOT", tmp_path / "repo")
    output = tmp_path / "missing" / "items.csv"

    result = template.create_template(output)

    assert result.result == "fail"
    assert result.status == "output parent directory does not exist"
    assert not output.exists()


def test_existing_file_fails_without_overwrite(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(template, "PROJECT_ROOT", tmp_path / "repo")
    output = tmp_path / "items.csv"
    original = "synthetic existing content\n"
    output.write_text(original, encoding="utf-8")

    result = template.create_template(output)

    assert result.result == "fail"
    assert result.status == "output file already exists"
    assert output.read_text(encoding="utf-8") == original


def test_cli_exit_codes_match_result(tmp_path: Path) -> None:
    output = tmp_path / "items.csv"

    success = subprocess.run(
        [sys.executable, str(SCRIPT), "--output", str(output)],
        capture_output=True,
        text=True,
        check=False,
    )
    failure = subprocess.run(
        [sys.executable, str(SCRIPT), "--output", str(output)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert success.returncode == 0
    assert "Result: pass" in success.stdout
    assert failure.returncode == 1
    assert "Result: fail" in failure.stdout
    assert "Status: output file already exists" in failure.stdout


def test_header_has_no_commercial_columns() -> None:
    header = tuple(column.casefold() for column in template.STRICT_COLUMNS)

    assert header == EXPECTED_HEADER
    for forbidden in ("price", "sum", "vat", "currency", "term"):
        assert forbidden not in header


def test_powershell_wrapper_invokes_python_helper_and_returns_exit_code() -> None:
    text = WRAPPER.read_text(encoding="utf-8")

    assert "[string]$Output" in text
    assert 'Join-Path $ProjectRoot ".venv\\Scripts\\python.exe"' in text
    assert "create_quote_items_csv_template.py" in text
    assert "& $Python $TemplateScript --output $Output" in text
    assert "exit $LASTEXITCODE" in text


def test_powershell_wrapper_has_no_git_or_quote_generation_commands() -> None:
    lowered = WRAPPER.read_text(encoding="utf-8").casefold()

    for forbidden in (
        "git add",
        "git commit",
        "git push",
        "make_quote_capacity100",
        "run_codex_finish_checks",
        ".xlsx",
        ".xls",
    ):
        assert forbidden not in lowered
