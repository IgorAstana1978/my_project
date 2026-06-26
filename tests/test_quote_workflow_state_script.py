from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "quote_workflow_state.ps1"


def script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_script_exists() -> None:
    assert SCRIPT.is_file()


def test_contains_state_card_markers() -> None:
    text = script_text()

    assert "QUOTE_WORKFLOW_STATE_START" in text
    assert "QUOTE_WORKFLOW_STATE_END" in text


def test_references_canonical_workflow_commands() -> None:
    text = script_text()

    assert r".\scripts\create_quote_items_csv_template.ps1" in text
    assert r"C:\Users\IgorN\Downloads\items.csv" in text
    assert r".\scripts\make_quote_capacity100_checked.ps1" in text
    assert r".\scripts\finish_quote_workflow.ps1" in text
    assert r".\scripts\finish_quote_workflow.ps1 -CopyToClipboard" in text
    assert r".\scripts\quote_workflow_state.ps1 -CopyToClipboard" in text


def test_contains_input_output_and_stop_safety() -> None:
    text = script_text()

    assert "strict 5-column CSV outside Git only" in text
    assert "generated .xlsx is internal draft only and must stay outside Git" in text
    assert "manual Igor check" in text
    assert "Human Approval" in text
    assert "technical PASS / smoke PASS is not commercial approval" in text


def test_supports_explicit_clipboard_switch() -> None:
    text = script_text()

    assert "[switch]$CopyToClipboard" in text
    assert "Set-Clipboard -Value $StateCard" in text


def test_clipboard_copy_is_explicitly_guarded() -> None:
    text = script_text()

    condition = text.index("if ($CopyToClipboard)")
    clipboard_command = text.index("Set-Clipboard -Value $StateCard")

    assert condition < clipboard_command
    assert text.count("Set-Clipboard") == 1


def test_prints_state_card_before_optional_clipboard_copy() -> None:
    text = script_text()

    print_command = text.index("Write-Output $StateCard")
    clipboard_condition = text.index("if ($CopyToClipboard)")

    assert print_command < clipboard_condition


def test_does_not_invoke_workflow_commands() -> None:
    lowered = script_text().casefold()
    forbidden_invocations = (
        "& $",
        "& .\\scripts\\make_quote",
        "powershell -file",
        "run_codex_finish_checks.py",
        "smoke_checked_quote_launcher.ps1",
        "make_quote_capacity100.ps1",
    )

    for value in forbidden_invocations:
        assert value not in lowered, value


def test_does_not_contain_git_write_commands_or_real_paths() -> None:
    lowered = script_text().casefold()

    assert "git add" not in lowered
    assert "git commit" not in lowered
    assert "git push" not in lowered
    assert "desktop" not in lowered
    assert "client files" not in lowered


def test_does_not_contain_commercial_details() -> None:
    lowered = script_text().casefold()
    allowed_safety_phrase = "commercial approval"
    text_without_safety_phrase = lowered.replace(allowed_safety_phrase, "")

    for value in ("price", "sum", "vat", "currency", "payment terms"):
        assert value not in text_without_safety_phrase, value
