from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUN_CARD_PATH = (
    PROJECT_ROOT / "docs" / "invoice_quote_filler_v0_2_1_operator_run_card.md"
)
USER_CSV_RUNBOOK_PATH = (
    PROJECT_ROOT / "docs" / "invoice_quote_filler_v0_2_1_user_csv_runbook.md"
)
STRICT_COLUMNS = (
    "name",
    "unit",
    "quantity",
    "instruments_and_devices",
    "cabinet_type_dimensions_material",
)
STALE_PHRASES = (
    "not implemented yet",
    "future safe helper",
    "Current stable commit: 55cd055",
    "CI is green at the stable commit",
)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def normalized(text: str) -> str:
    return " ".join(text.casefold().split())


def test_operator_run_card_exists() -> None:
    assert RUN_CARD_PATH.is_file()


def test_operator_run_card_contains_canonical_launcher_and_columns() -> None:
    text = read_text(RUN_CARD_PATH)

    assert "make_quote_capacity100_checked.ps1" in text
    for column in STRICT_COLUMNS:
        assert column in text


def test_operator_run_card_contains_pass_criteria() -> None:
    text = read_text(RUN_CARD_PATH)

    assert "Preflight: PASS" in text
    assert "Generation: pass" in text
    assert "Inspection: pass" in text
    assert "Output exists: yes" in text


def test_operator_run_card_contains_stop_and_approval_rules() -> None:
    text = read_text(RUN_CARD_PATH)

    assert "Technical PASS" in text
    assert "not commercial approval" in text
    assert "Manual Igor check" in text
    assert "Human Approval" in text


def test_operator_run_card_marks_low_level_launcher_as_internal() -> None:
    text = normalized(read_text(RUN_CARD_PATH))

    assert "make_quote_capacity100.ps1" in text
    assert "low-level/internal" in text


def test_operator_run_card_forbids_generated_files_in_git() -> None:
    text = read_text(RUN_CARD_PATH)
    compact = normalized(text)

    assert ".xls" in text
    assert ".xlsx" in text
    assert "generated `.csv`" in text
    assert "в git" in compact


def test_user_csv_runbook_links_to_operator_run_card() -> None:
    text = read_text(USER_CSV_RUNBOOK_PATH)

    assert "invoice_quote_filler_v0_2_1_operator_run_card.md" in text


def test_stale_phrases_are_absent_from_operator_docs() -> None:
    for path in (RUN_CARD_PATH, USER_CSV_RUNBOOK_PATH):
        text = read_text(path)
        compact = normalized(text)

        for phrase in STALE_PHRASES:
            assert phrase.casefold() not in compact, f"{path}: {phrase}"
