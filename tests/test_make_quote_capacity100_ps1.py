from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "make_quote_capacity100.ps1"


def script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_launcher_script_exists() -> None:
    assert SCRIPT.is_file()


def test_launcher_declares_expected_parameters() -> None:
    text = script_text()

    assert "param(" in text
    for name in ("ItemsCsv", "Output", "Template", "TemplateCapacity", "Python"):
        assert f"${name}" in text


def test_launcher_uses_userprofile_for_default_template() -> None:
    text = script_text()

    assert "$env:USERPROFILE" in text
    assert "Фирменный_шаблон_счёта-КП_v0.3_capacity100_tuned_v3_ДиН_ВА-КЭС.xlsx" in text
    assert "C:\\Users\\IgorN" not in text


def test_launcher_defaults_capacity_and_python_path() -> None:
    text = script_text()

    assert "[int]$TemplateCapacity = 100" in text
    assert ".venv\\Scripts\\python.exe" in text
    assert "$ProjectRoot = Split-Path -Parent $PSScriptRoot" in text


def test_launcher_calls_compact_csv_runner_with_runtime_arguments() -> None:
    text = script_text()

    assert "run_invoice_quote_extended_from_csv_compact.py" in text
    assert "--items-csv $ItemsCsv" in text
    assert "--template $Template" in text
    assert "--template-capacity $TemplateCapacity" in text
    assert "--output $Output" in text


def test_launcher_has_required_preflight_checks() -> None:
    text = script_text()

    assert "Input CSV does not exist" in text
    assert "Template does not exist" in text
    assert "Python executable does not exist" in text
    assert "Output already exists" in text
    assert "Output parent directory does not exist" in text
    assert "Test-Path -LiteralPath $ItemsCsv" in text
    assert "Test-Path -LiteralPath $Template" in text
    assert "Test-Path -LiteralPath $Python" in text
    assert "Test-Path -LiteralPath $Output" in text


def test_launcher_preserves_downstream_exit_code_and_reports_output() -> None:
    text = script_text()

    assert "$ExitCode = $LASTEXITCODE" in text
    assert "exit $ExitCode" in text
    assert "Created output: $Output" in text


def test_launcher_has_no_git_or_commercial_content() -> None:
    text = script_text().casefold()

    assert "git add" not in text
    for forbidden in ("price", "sum", "vat", "term", "цена", "сумм", "ндс", "срок"):
        assert forbidden not in text
