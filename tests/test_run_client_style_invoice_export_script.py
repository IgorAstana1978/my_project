import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "run_client_style_invoice_export.ps1"
OLD_WORKFLOW_FILES = (
    PROJECT_ROOT / "scripts" / "make_quote_capacity100.ps1",
    PROJECT_ROOT / "scripts" / "make_quote_capacity100_checked.ps1",
    PROJECT_ROOT / "scripts" / "make_quote_capacity100_commercial_checked.ps1",
    PROJECT_ROOT / "scripts" / "run_invoice_quote_extended_from_csv_compact.py",
    PROJECT_ROOT / "scripts" / "run_invoice_quote_commercial_from_csv.py",
)
APPROVED_TEMPLATE = (
    r"C:\Users\IgorN\Downloads\client_style_template_phase_2_30e"
    r"\client_style_invoice_template_candidate.xlsx"
)
APPROVED_TEMPLATE_CONTRACT = (
    r"C:\Users\IgorN\Downloads\client_style_template_phase_2_30e"
    r"\client_style_invoice_template_contract.candidate.json"
)


def script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_launcher_file_exists() -> None:
    assert SCRIPT.is_file()


def test_launcher_resolves_repo_root_and_calls_client_style_exporter() -> None:
    text = script_text()

    assert "$ProjectRoot = Split-Path -Parent $PSScriptRoot" in text
    assert (
        "$Exporter = Join-Path $ProjectRoot "
        '"scripts\\export_client_style_invoice.py"'
    ) in text
    assert "& $Python $Exporter" in text


def test_launcher_passes_all_exporter_paths() -> None:
    text = script_text()

    expected_arguments = (
        "--commercial-csv $CommercialCsv",
        "--internal-draft-xlsx $InternalDraftXlsx",
        "--template-xlsx $TemplateXlsx",
        "--template-contract-json $TemplateContractJson",
        "--approval-json $ApprovalJson",
        "--output-xlsx $OutputXlsx",
    )
    for argument in expected_arguments:
        assert argument in text


def test_launcher_has_approved_template_defaults() -> None:
    text = script_text()

    assert APPROVED_TEMPLATE in text
    assert APPROVED_TEMPLATE_CONTRACT in text


def test_launcher_uses_repo_venv_python_by_default() -> None:
    text = script_text()

    assert '[string]$Python = ""' in text
    assert 'Join-Path $ProjectRoot ".venv\\Scripts\\python.exe"' in text


def test_launcher_prints_operator_safety_header() -> None:
    text = script_text()

    assert "client-style invoice export candidate only" in text
    assert "PASS is not sending approval" in text
    assert "Human Approval required before sending" in text


def test_launcher_preserves_exporter_exit_code_without_hiding_report() -> None:
    text = script_text()

    invocation = text.index("& $Python $Exporter")
    exit_code = text.index("$ExitCode = $LASTEXITCODE")
    exit_statement = text.index("exit $ExitCode")

    assert invocation < exit_code < exit_statement
    assert "2>&1" not in text


def test_launcher_contains_no_git_write_commands() -> None:
    text = script_text().casefold()

    for command in ("git add", "git commit", "git push"):
        assert command not in text


def test_launcher_contains_no_automatic_send_action() -> None:
    text = script_text().casefold()
    forbidden = (
        "send-mailmessage",
        "system.net.mail",
        "smtp",
        "outlook.application",
        "invoke-restmethod",
        "invoke-webrequest",
        "start-process",
    )

    for action in forbidden:
        assert action not in text


def test_launcher_does_not_reference_old_checked_launchers() -> None:
    text = script_text()

    assert "make_quote_capacity100_checked.ps1" not in text
    assert "make_quote_capacity100_commercial_checked.ps1" not in text


def test_existing_old_workflows_do_not_reference_this_launcher() -> None:
    for path in OLD_WORKFLOW_FILES:
        assert SCRIPT.name not in path.read_text(encoding="utf-8"), path


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
