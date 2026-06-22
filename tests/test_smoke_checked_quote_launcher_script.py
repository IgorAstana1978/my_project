from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "smoke_checked_quote_launcher.ps1"


def script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_script_exists() -> None:
    assert SCRIPT.is_file()


def test_references_checked_launcher() -> None:
    text = script_text()

    assert "make_quote_capacity100_checked.ps1" in text


def test_creates_temp_csv_and_xlsx_under_env_temp() -> None:
    text = script_text()

    assert "$env:TEMP" in text
    assert "$TempRoot" in text
    assert "codex_checked_quote_smoke_" in text
    assert 'Join-Path $TempRoot "codex_checked_quote_smoke_$SmokeId.csv"' in text
    assert 'Join-Path $TempRoot "codex_checked_quote_smoke_$SmokeId.xlsx"' in text
    assert "StartsWith($TempRoot" in text


def test_uses_synthetic_rows_only() -> None:
    text = script_text()

    assert "ВРУ-SMOKE-1" in text
    assert "ВРУ-SMOKE-2" in text
    assert "synthetic devices" in text
    assert "synthetic cabinet" in text
    assert "client" not in text.casefold()


def test_checks_checked_quote_run_report_and_pass_statuses() -> None:
    text = script_text()

    assert "CHECKED_QUOTE_RUN_REPORT_START" in text
    assert '"Preflight:"' in text
    assert '"PASS"' in text
    assert '"Generation:"' in text
    assert '"pass"' in text
    assert '"Output exists:"' in text
    assert '"yes"' in text


def test_deletes_temp_csv_and_xlsx() -> None:
    text = script_text()

    assert "Remove-Item -LiteralPath $TempCsv -Force" in text
    assert "Remove-Item -LiteralPath $TempXlsx -Force" in text
    assert "$TempCsvDeleted" in text
    assert "$TempXlsxDeleted" in text


def test_prints_smoke_report_markers() -> None:
    text = script_text()

    assert "CHECKED_QUOTE_SMOKE_REPORT_START" in text
    assert "CHECKED_QUOTE_SMOKE_REPORT_END" in text


def test_does_not_contain_git_write_commands() -> None:
    text = script_text().casefold()

    assert "git commit" not in text
    assert "git push" not in text
    assert "git add ." not in text


def test_does_not_reference_xls_extraction_or_real_client_paths() -> None:
    text = script_text()
    lowered = text.casefold()

    assert "extract_legacy_xls" not in text
    assert "xlrd" not in text
    assert '.xls"' not in lowered
    assert ".xls'" not in lowered
    assert "downloads" not in lowered
    assert "desktop" not in lowered
