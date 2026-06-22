from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "make_quote_capacity100_checked.ps1"


def script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_script_exists() -> None:
    assert SCRIPT.is_file()


def test_references_preflight_and_existing_launcher() -> None:
    text = script_text()

    assert "preflight_quote_input.py" in text
    assert "make_quote_capacity100.ps1" in text
    assert "inspect_quote_draft.py" in text


def test_contains_allow_warn_and_blocks_warn_without_switch() -> None:
    text = script_text()

    assert "AllowWarn" in text
    assert '$PreflightStatus -eq "WARN" -and -not $AllowWarn' in text
    assert "WARN requires manual Igor check and rerun with -AllowWarn" in text
    assert "exit $FinalExitCode" in text


def test_blocks_fail_status_and_nonzero_preflight() -> None:
    text = script_text()

    assert "$PreflightExitCode -ne 0" in text
    assert '$PreflightStatus -eq "FAIL"' in text
    assert '$GenerationStatus = "skipped"' in text


def test_prints_checked_quote_run_report_markers() -> None:
    text = script_text()

    assert "CHECKED_QUOTE_RUN_REPORT_START" in text
    assert "CHECKED_QUOTE_RUN_REPORT_END" in text
    assert '"Inspection:"' in text


def test_supports_pass_through_parameters() -> None:
    text = script_text()

    assert "[string]$Template" in text
    assert "[int]$TemplateCapacity" in text
    assert "[string]$Python" in text
    assert "TemplateCapacity = $TemplateCapacity" in text
    assert "Python = $Python" in text
    assert '$LauncherParams["Template"] = $Template' in text


def test_launcher_uses_hashtable_splatting_not_array_args() -> None:
    text = script_text()

    assert "$LauncherParams = @{" in text
    assert "ItemsCsv = $ItemsCsv" in text
    assert "Output = $Output" in text
    assert "TemplateCapacity = $TemplateCapacity" in text
    assert "Python = $Python" in text
    assert '$LauncherParams["Template"] = $Template' in text
    assert "& $LauncherScript @LauncherParams" in text
    assert "$LauncherArgs = @(" not in text


def test_uses_python_for_preflight() -> None:
    text = script_text()

    assert "$PreflightOutput = & $Python $PreflightScript" in text
    assert "--input $ItemsCsv --draft-output $Output" in text


def test_uses_python_for_draft_inspection() -> None:
    text = script_text()

    assert "$InspectionScript = Join-Path $ProjectRoot" in text
    assert "inspect_quote_draft.py" in text
    assert "$InspectionOutput = & $Python $InspectionScript --input $Output" in text
    assert "$InspectionLines | ForEach-Object { Write-Host $_ }" in text


def test_inspection_runs_only_after_generation_pass_and_output_exists() -> None:
    text = script_text()
    generation_gate = (
        "$GeneratorExitCode -eq 0 -and "
        "(Test-Path -LiteralPath $Output -PathType Leaf)"
    )

    assert generation_gate in text
    assert text.index(generation_gate) < text.index("$InspectionOutput = & $Python")
    assert '$GenerationStatus = "pass"' in text


def test_inspection_status_supports_pass_fail_and_skipped() -> None:
    text = script_text()

    assert '$InspectionStatus = "skipped"' in text
    assert '$InspectionStatus = "pass"' in text
    assert '$InspectionStatus = "fail"' in text


def test_inspection_failure_sets_nonzero_exit_and_next_message() -> None:
    text = script_text()

    assert "$InspectionExitCode -ne 0" in text
    assert (
        "$FinalExitCode = if ($InspectionExitCode -ne 0) "
        "{ $InspectionExitCode } else { 1 }"
    ) in text
    assert "draft inspection failed; do not use draft" in text


def test_does_not_contain_git_write_commands() -> None:
    text = script_text().casefold()

    assert "git commit" not in text
    assert "git push" not in text
    assert "git add ." not in text


def test_does_not_reference_xls_extraction_or_template_file_directly() -> None:
    text = script_text()

    assert "extract_legacy_xls" not in text
    assert "xlrd" not in text
    assert "Фирменный_шаблон" not in text
    assert "capacity100_tuned" not in text
