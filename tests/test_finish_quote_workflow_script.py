from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "finish_quote_workflow.ps1"


def script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_script_exists() -> None:
    assert SCRIPT.is_file()


def test_runs_fast_finish_checks_with_quote_smoke() -> None:
    text = script_text()

    assert "run_codex_finish_checks.py" in text
    assert "--mode fast" in text
    assert "--include-quote-smoke" in text


def test_finds_project_root_relative_to_script_root() -> None:
    text = script_text()

    assert "$ProjectRoot = Split-Path -Parent $PSScriptRoot" in text
    assert "Push-Location $ProjectRoot" in text
    assert "Pop-Location" in text


def test_uses_default_venv_python_and_supports_override() -> None:
    text = script_text()

    assert '[string]$Python = ""' in text
    assert 'Join-Path $ProjectRoot ".venv\\Scripts\\python.exe"' in text
    assert "& $Python $FinishChecksScript" in text


def test_returns_child_exit_code() -> None:
    text = script_text()

    assert "$FinishExitCode = $LASTEXITCODE" in text
    assert "exit $FinishExitCode" in text


def test_does_not_invoke_quote_launchers_directly() -> None:
    text = script_text()

    assert "make_quote_capacity100.ps1" not in text
    assert "make_quote_capacity100_checked.ps1" not in text


def test_does_not_reference_inputs_outputs_or_client_paths() -> None:
    lowered = script_text().casefold()

    assert ".xls" not in lowered
    assert ".xlsx" not in lowered
    assert "generated .csv" not in lowered
    assert "downloads" not in lowered
    assert "desktop" not in lowered
    assert "client" not in lowered


def test_does_not_contain_git_write_commands() -> None:
    lowered = script_text().casefold()

    assert "git add" not in lowered
    assert "git commit" not in lowered
    assert "git push" not in lowered
