from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOC_PATHS = (
    PROJECT_ROOT
    / "docs"
    / "invoice_quote_filler_v0_2_1_capacity100_runtime_handoff.md",
    PROJECT_ROOT
    / "docs"
    / "invoice_quote_filler_v0_2_1_checked_quote_launcher_runbook.md",
    PROJECT_ROOT
    / "docs"
    / "invoice_quote_filler_v0_2_1_legacy_xls_extractor_runbook.md",
    PROJECT_ROOT / "docs" / "invoice_quote_filler_v0_2_1_legacy_xls_to_csv_plan.md",
    PROJECT_ROOT
    / "docs"
    / "invoice_quote_filler_v0_2_1_quote_input_preflight_runbook.md",
    PROJECT_ROOT / "docs" / "invoice_quote_filler_v0_2_1_user_csv_runbook.md",
)
LEGACY_XLS_DOCS = (
    PROJECT_ROOT
    / "docs"
    / "invoice_quote_filler_v0_2_1_legacy_xls_extractor_runbook.md",
    PROJECT_ROOT / "docs" / "invoice_quote_filler_v0_2_1_legacy_xls_to_csv_plan.md",
)
CANONICAL_LAUNCHER = "make_quote_capacity100_checked.ps1"
LOW_LEVEL_LAUNCHER = "make_quote_capacity100.ps1"
WORKFLOW = "preflight -> generation -> draft inspection -> checked quote run report"
STALE_PHRASES = (
    "current stable commit: 55cd055",
    "helper is not implemented yet",
    "not implemented yet",
    "future safe helper",
    "ci is green at the stable commit",
)


def read_doc(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def normalized(text: str) -> str:
    return " ".join(text.casefold().split())


def assert_contains_any(text: str, options: tuple[str, ...]) -> None:
    compact = normalized(text)
    assert any(option.casefold() in compact for option in options)


def test_canonical_workflow_docs_exist() -> None:
    for path in DOC_PATHS:
        assert path.is_file(), path


def test_user_facing_docs_reference_checked_launcher_and_workflow() -> None:
    for path in DOC_PATHS:
        text = read_doc(path)
        compact = normalized(text)

        assert CANONICAL_LAUNCHER in text, path
        assert WORKFLOW in compact, path


def test_direct_launcher_mentions_are_marked_low_level_internal() -> None:
    for path in DOC_PATHS:
        text = read_doc(path)
        if LOW_LEVEL_LAUNCHER in text:
            assert "low-level/internal" in normalized(text), path


def test_docs_preserve_quote_safety_requirements() -> None:
    internal_draft_phrases = (
        "internal draft",
        "внутренним draft",
        "внутренним черновиком",
    )
    technical_pass_phrases = (
        "technical pass",
        "inspection: pass",
        "smoke pass",
    )
    commercial_approval_phrases = (
        "not commercial approval",
        "не являются commercial approval",
    )
    manual_check_phrases = (
        "manual igor check",
        "manually checked by igor",
        "ручной проверки игоря",
        "игорь вручную проверяет",
    )
    human_approval_phrases = (
        "human approval",
        "отдельное human approval",
    )

    for path in DOC_PATHS:
        text = read_doc(path)

        assert_contains_any(text, internal_draft_phrases)
        assert_contains_any(text, technical_pass_phrases)
        assert_contains_any(text, commercial_approval_phrases)
        assert_contains_any(text, manual_check_phrases)
        assert_contains_any(text, human_approval_phrases)


def test_stale_canonical_workflow_phrases_are_absent() -> None:
    for path in DOC_PATHS:
        compact = normalized(read_doc(path))

        for phrase in STALE_PHRASES:
            assert phrase not in compact, f"{path}: {phrase}"


def test_legacy_xls_docs_do_not_say_extractor_is_unimplemented() -> None:
    forbidden = (
        "extractor is not implemented",
        "helper is not implemented yet",
        "not implemented yet",
        "future safe helper",
    )

    for path in LEGACY_XLS_DOCS:
        compact = normalized(read_doc(path))

        for phrase in forbidden:
            assert phrase not in compact, f"{path}: {phrase}"
