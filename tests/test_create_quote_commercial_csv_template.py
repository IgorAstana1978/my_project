import csv
import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "create_quote_commercial_csv_template.py"
WRAPPER = PROJECT_ROOT / "scripts" / "create_quote_commercial_csv_template.ps1"
EXPECTED_HEADER = (
    "name",
    "unit",
    "quantity",
    "instruments_and_devices",
    "cabinet_type_dimensions_material",
    "unit_price_kzt",
    "price_includes_vat",
    "price_confirmed_by_igor",
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
    load_script_module(
        "create_quote_commercial_csv_template_for_test",
        SCRIPT,
    ),
)


def test_creates_exact_header_only_commercial_csv(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(template, "PROJECT_ROOT", tmp_path / "repo")
    output = tmp_path / "commercial_items.csv"

    result = template.create_template(output)

    assert result.result == "pass"
    assert output.read_text(encoding="utf-8") == ";".join(EXPECTED_HEADER) + "\n"
    with output.open("r", encoding="utf-8", newline="") as csv_file:
        rows = list(csv.reader(csv_file, delimiter=";"))
    assert rows == [list(EXPECTED_HEADER)]


def test_report_contains_safe_template_metadata(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(template, "PROJECT_ROOT", tmp_path / "repo")
    output = tmp_path / "commercial_items.csv"

    report = template.format_report(template.create_template(output))

    assert report.startswith("COMMERCIAL_QUOTE_CSV_TEMPLATE_REPORT_START")
    assert report.endswith("COMMERCIAL_QUOTE_CSV_TEMPLATE_REPORT_END")
    assert "Result: pass" in report
    assert "Rows: 0" in report
    assert "Columns: 8" in report
    assert "Delimiter: ;" in report


def test_wrong_suffix_fails_without_creating_file(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(template, "PROJECT_ROOT", tmp_path / "repo")
    output = tmp_path / "commercial_items.txt"

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
    output = repo_root / "commercial_items.csv"

    result = template.create_template(output)

    assert result.result == "fail"
    assert result.status == "output CSV must be outside the Git project"
    assert not output.exists()


def test_missing_parent_fails(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(template, "PROJECT_ROOT", tmp_path / "repo")
    output = tmp_path / "missing" / "commercial_items.csv"

    result = template.create_template(output)

    assert result.result == "fail"
    assert result.status == "output parent directory does not exist"
    assert not output.exists()


def test_existing_file_is_not_overwritten(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(template, "PROJECT_ROOT", tmp_path / "repo")
    output = tmp_path / "commercial_items.csv"
    original = "existing synthetic content\n"
    output.write_text(original, encoding="utf-8")

    result = template.create_template(output)

    assert result.result == "fail"
    assert result.status == "output file already exists"
    assert output.read_text(encoding="utf-8") == original


def test_cli_exit_codes_match_result(tmp_path: Path) -> None:
    output = tmp_path / "commercial_items.csv"

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
    assert "Status: output file already exists" in failure.stdout


def test_powershell_wrapper_only_invokes_template_helper() -> None:
    text = WRAPPER.read_text(encoding="utf-8")
    lowered = text.casefold()

    assert "[string]$Output" in text
    assert "create_quote_commercial_csv_template.py" in text
    assert "& $Python $TemplateScript --output $Output" in text
    assert "exit $LASTEXITCODE" in text
    for forbidden in (
        "git add",
        "git commit",
        "git push",
        "make_quote",
        "preflight_quote",
        ".xlsx",
    ):
        assert forbidden not in lowered
