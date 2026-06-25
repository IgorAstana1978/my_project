from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CARD_PATH = (
    PROJECT_ROOT / "docs" / "invoice_quote_filler_v0_2_1_codex_compact_prompt_card.md"
)
OPERATOR_RUN_CARD_PATH = (
    PROJECT_ROOT / "docs" / "invoice_quote_filler_v0_2_1_operator_run_card.md"
)
FINISH_RUNBOOK_PATH = (
    PROJECT_ROOT / "docs" / "invoice_quote_filler_v0_2_1_codex_finish_checks_runbook.md"
)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def normalized(text: str) -> str:
    return " ".join(text.casefold().split())


def test_compact_prompt_card_exists() -> None:
    assert CARD_PATH.is_file()


def test_card_contains_required_prompt_sections() -> None:
    text = read_text(CARD_PATH)

    for heading in (
        "Repo:",
        "HEAD:",
        "Task:",
        "Scope only:",
        "Guardrails:",
        "Checks:",
        "Final report:",
    ):
        assert heading in text


def test_card_contains_required_git_and_approval_guardrails() -> None:
    text = normalized(read_text(CARD_PATH))

    assert "use current repo guardrails" in text
    assert "exact-file staging only" in text
    assert "do not use git add ." in text
    assert "no client files or generated files in git" in text
    assert "no commit or push without separate human approval" in text


def test_card_contains_checks_and_final_report_contract() -> None:
    text = read_text(CARD_PATH)

    assert "git diff --check" in text
    assert r".\scripts\finish_quote_workflow.ps1" in text
    assert "CODEX_FINISH_REPORT" in text
    assert "git status --short --untracked-files=all" in text


def test_card_requires_extended_prompts_for_dangerous_areas() -> None:
    text = normalized(read_text(CARD_PATH))

    for area in (
        "quote generation",
        "excel templates",
        "dependencies",
        "real client files",
        "excel runtime",
        "commercial data",
    ):
        assert area in text


def test_card_forbids_generated_and_client_files_in_git() -> None:
    text = read_text(CARD_PATH)

    assert ".xls" in text
    assert ".xlsx" in text
    assert "generated `.csv`" in text
    assert "client" in text.casefold()
    assert "in Git" in text


def test_operator_and_finish_docs_link_to_compact_prompt_card() -> None:
    card_name = CARD_PATH.name

    assert card_name in read_text(OPERATOR_RUN_CARD_PATH)
    assert card_name in read_text(FINISH_RUNBOOK_PATH)
