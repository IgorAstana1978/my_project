import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "make_quote_capacity100_commercial_checked.ps1"
TECHNICAL_CHECKED_SCRIPT = (
    PROJECT_ROOT / "scripts" / "make_quote_capacity100_checked.ps1"
)


def script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_launcher_script_exists() -> None:
    assert SCRIPT.is_file()


def test_launcher_declares_only_expected_runtime_parameters() -> None:
    text = script_text()

    for name in ("CommercialCsv", "Output", "Template", "Python"):
        assert f"${name}" in text
    assert "$ItemsCsv" not in text
    assert "$TemplateCapacity" not in text


def test_launcher_uses_canonical_userprofile_template_without_guessing() -> None:
    text = script_text()

    assert "$env:USERPROFILE" in text
    assert "Downloads" in text
    assert "capacity100_tuned_v3" in text
    assert "[regex]::Unescape" in text
    assert "\\u0424\\u0438\\u0440" in text
    assert "Get-ChildItem" not in text
    assert "C:\\Users\\IgorN" not in text


def test_launcher_calls_commercial_writer_with_fixed_capacity100() -> None:
    text = script_text()

    assert "run_invoice_quote_commercial_from_csv.py" in text
    assert "--commercial-csv $CommercialCsv" in text
    assert "--template $Template" in text
    assert "--template-capacity 100" in text
    assert "--output $Output" in text


def test_launcher_does_not_call_old_technical_writer() -> None:
    text = script_text()

    assert "run_invoice_quote_extended" not in text
    assert "make_quote_capacity100.ps1" not in text
    assert "--items-csv" not in text


def test_launcher_has_required_path_checks() -> None:
    text = script_text()

    assert "Commercial CSV does not exist" in text
    assert "Template does not exist" in text
    assert "Python executable does not exist" in text
    assert "Output already exists" in text
    assert "Output parent directory does not exist" in text
    assert "Test-Path -LiteralPath $CommercialCsv" in text
    assert "Test-Path -LiteralPath $Template" in text
    assert "Test-Path -LiteralPath $Python" in text
    assert "Test-Path -LiteralPath $Output" in text


def test_launcher_preserves_writer_exit_code() -> None:
    text = script_text()

    assert "$ExitCode = $LASTEXITCODE" in text
    assert "exit $ExitCode" in text
    assert "Created internal draft: $Output" in text


def test_launcher_contains_no_git_send_client_ready_or_commercial_values() -> None:
    text = script_text().casefold()
    forbidden = (
        "git add",
        "git commit",
        "git push",
        "send-mailmessage",
        "invoke-restmethod",
        "smtp",
        "outlook",
        "client-ready",
        "client ready",
        "unit_price",
        "grand_total",
        "line_total",
        "vat",
        "ндс",
        "цена",
        "сумм",
    )

    for value in forbidden:
        assert value not in text, value


def test_existing_checked_launcher_remains_technical_only() -> None:
    text = TECHNICAL_CHECKED_SCRIPT.read_text(encoding="utf-8")

    assert "preflight_quote_input.py" in text
    assert "make_quote_capacity100.ps1" in text
    assert "inspect_quote_draft.py" in text
    assert "run_invoice_quote_commercial_from_csv.py" not in text
    assert "make_quote_capacity100_commercial_checked.ps1" not in text
    assert "$CommercialCsv" not in text


def test_launcher_parses_with_available_powershell() -> None:
    executable = shutil.which("powershell") or shutil.which("pwsh")
    if executable is None:
        pytest.skip("PowerShell is not available")

    script_path = str(SCRIPT).replace("'", "''")
    command = (
        f"$path = '{script_path}'; "
        "$tokens = $null; "
        "$errors = $null; "
        "[System.Management.Automation.Language.Parser]::ParseFile("
        "$path, [ref]$tokens, [ref]$errors) | Out-Null; "
        "if ($errors.Count -gt 0) { "
        "$errors | ForEach-Object { Write-Error $_.Message }; "
        "exit 1 "
        "}"
    )
    result = subprocess.run(
        [executable, "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
