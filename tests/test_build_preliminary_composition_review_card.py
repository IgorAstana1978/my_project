import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "build_preliminary_composition_review_card.py"
EXAMPLE = PROJECT_ROOT / "examples" / "preliminary_composition_draft.example.json"
OLD_WORKFLOWS = (
    PROJECT_ROOT / "scripts" / "calc_quote_price_draft.py",
    PROJECT_ROOT / "scripts" / "preflight_quote_commercial_input.py",
    PROJECT_ROOT / "scripts" / "run_invoice_quote_commercial_from_csv.py",
    PROJECT_ROOT / "scripts" / "make_quote_capacity100_commercial_checked.ps1",
    PROJECT_ROOT / "scripts" / "create_client_style_approval_draft.py",
    PROJECT_ROOT / "scripts" / "export_client_style_invoice.py",
    PROJECT_ROOT / "scripts" / "run_client_style_invoice_export.ps1",
    PROJECT_ROOT / "scripts" / "preflight_client_style_invoice_template_contract.py",
    PROJECT_ROOT / "scripts" / "make_quote_capacity100_checked.ps1",
    PROJECT_ROOT / "scripts" / "run_invoice_quote_extended_from_items.py",
)
FORBIDDEN_MARKDOWN_TOKENS = (
    "price_confirmed_by_igor",
    "price_includes_vat",
    "unit_price_kzt",
    "line_total",
    "total_kzt",
    "final_price",
    "client_ready",
    "ready_to_send",
    "send_to_client",
    "commercial_approved",
    "production_approved",
    "confirmed_composition",
    "production_action_authorized",
    "token_execution_authorized",
)


def load_builder_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "build_preliminary_composition_review_card_for_test",
        SCRIPT,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


builder = cast(Any, load_builder_module())


def valid_data(raw_text: str = "Synthetic raw request text.\n") -> dict[str, Any]:
    data = cast(dict[str, Any], json.loads(EXAMPLE.read_text(encoding="utf-8")))
    cast(dict[str, Any], data["source"])["raw_input_sha256"] = hashlib.sha256(
        raw_text.encode("utf-8")
    ).hexdigest()
    return data


def write_raw_text(tmp_path: Path, text: str = "Synthetic raw request text.\n") -> Path:
    path = tmp_path / "raw-request.txt"
    path.write_bytes(text.encode("utf-8"))
    return path


def write_draft(tmp_path: Path, data: dict[str, Any]) -> Path:
    path = tmp_path / "draft.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def build_card(
    tmp_path: Path,
    raw_text: str = "Synthetic raw request text.\n",
    data: dict[str, Any] | None = None,
    output_name: str = "review-card.md",
) -> Any:
    raw_path = write_raw_text(tmp_path, raw_text)
    draft_path = write_draft(
        tmp_path,
        data if data is not None else valid_data(raw_text),
    )
    output_path = tmp_path / output_name
    return builder.build_review_card(raw_path, draft_path, output_path)


def test_valid_source_bound_draft_creates_review_card_outside_git(
    tmp_path: Path,
) -> None:
    result = build_card(tmp_path)

    assert result.status == "PASS"
    assert result.output_created is True
    assert result.output_md.is_file()
    assert all(status == "pass" for status in result.checks.values())


def test_source_bundle_verifier_fail_prevents_output(tmp_path: Path) -> None:
    data = valid_data()
    cast(dict[str, Any], data["source"])["raw_input_sha256"] = "0" * 64
    result = build_card(tmp_path, data=data)

    assert result.status == "FAIL"
    assert result.output_created is False
    assert not result.output_md.exists()
    assert result.checks["source bundle verification"] == "fail"


def test_output_already_exists_fails_without_overwrite(tmp_path: Path) -> None:
    output_path = tmp_path / "review-card.md"
    output_path.write_text("KEEP THIS", encoding="utf-8")
    result = build_card(tmp_path)

    assert result.status == "FAIL"
    assert result.output_created is False
    assert output_path.read_text(encoding="utf-8") == "KEEP THIS"
    assert "output Markdown already exists" in result.red_flags


def test_output_inside_git_fails(tmp_path: Path) -> None:
    raw_path = write_raw_text(tmp_path)
    draft_path = write_draft(tmp_path, valid_data())
    output_path = PROJECT_ROOT / "review-card-inside-git.md"

    result = builder.build_review_card(raw_path, draft_path, output_path)

    assert result.status == "FAIL"
    assert result.output_created is False
    assert "output Markdown must be outside the project" in result.red_flags


def test_output_parent_missing_fails(tmp_path: Path) -> None:
    raw_path = write_raw_text(tmp_path)
    draft_path = write_draft(tmp_path, valid_data())
    output_path = tmp_path / "missing-parent" / "review-card.md"

    result = builder.build_review_card(raw_path, draft_path, output_path)

    assert result.status == "FAIL"
    assert result.output_created is False
    assert "output parent directory does not exist" in result.red_flags


def test_malformed_draft_bundle_fail_prevents_output(tmp_path: Path) -> None:
    raw_path = write_raw_text(tmp_path)
    draft_path = tmp_path / "draft.json"
    draft_path.write_text("{not-json", encoding="utf-8")
    output_path = tmp_path / "review-card.md"

    result = builder.build_review_card(raw_path, draft_path, output_path)

    assert result.status == "FAIL"
    assert result.output_created is False
    assert not output_path.exists()
    assert any("malformed" in flag for flag in result.red_flags)


def test_markdown_contains_preliminary_only_status(tmp_path: Path) -> None:
    result = build_card(tmp_path)
    markdown = result.output_md.read_text(encoding="utf-8")

    assert "PRELIMINARY ONLY - NOT CONFIRMED" in markdown


def test_markdown_contains_item_summary(tmp_path: Path) -> None:
    result = build_card(tmp_path)
    markdown = result.output_md.read_text(encoding="utf-8")

    assert "## Item 1 - РУ-АВР / ЩРН-24" in markdown
    assert "- item_id: ITEM-001" in markdown
    assert "- quantity_guess: 1" in markdown


def test_markdown_contains_cabinet_guess(tmp_path: Path) -> None:
    result = build_card(tmp_path)
    markdown = result.output_md.read_text(encoding="utf-8")

    assert "cabinet_guess: code=CAB-KRN-24; label=КРН-24" in markdown


def test_markdown_contains_components_table(tmp_path: Path) -> None:
    result = build_card(tmp_path)
    markdown = result.output_md.read_text(encoding="utf-8")

    assert "component_id | component_code_guess | component_label_guess" in markdown
    assert "COMP-001 | EKF-VA47-29-1P" in markdown


def test_markdown_contains_human_confirmation_checklist(tmp_path: Path) -> None:
    result = build_card(tmp_path)
    markdown = result.output_md.read_text(encoding="utf-8")

    assert "Human Confirmation Checklist:" in markdown
    assert "- [ ] Confirm item ITEM-001 product name/type." in markdown
    assert (
        "- [ ] Confirm component COMP-001 code/label/quantity/install type." in markdown
    )
    assert (
        "- [ ] Confirm whether this draft may proceed to price calculation." in markdown
    )


def test_markdown_contains_final_safety_footer(tmp_path: Path) -> None:
    result = build_card(tmp_path)
    markdown = result.output_md.read_text(encoding="utf-8")

    assert "Final safety footer:" in markdown
    assert "does not approve composition, price, commercial CSV" in markdown
    assert "Igor confirmation is required before any price calculation" in markdown


def test_markdown_does_not_contain_raw_input_text(tmp_path: Path) -> None:
    raw_text = "SECRET RAW REQUEST TEXT should not enter Markdown.\n"
    result = build_card(tmp_path, raw_text=raw_text, data=valid_data(raw_text))
    markdown = result.output_md.read_text(encoding="utf-8")

    assert "SECRET RAW REQUEST TEXT" not in markdown
    assert raw_text not in markdown


def test_markdown_truncates_long_evidence(tmp_path: Path) -> None:
    data = valid_data()
    long_evidence = "LONG-EVIDENCE-" * 40
    cast(list[dict[str, Any]], data["items"])[0]["evidence"] = [long_evidence]

    result = build_card(tmp_path, data=data)
    markdown = result.output_md.read_text(encoding="utf-8")

    assert long_evidence not in markdown
    assert "LONG-EVIDENCE-" in markdown
    assert "..." in markdown


def test_markdown_contains_no_forbidden_price_or_approval_fields(
    tmp_path: Path,
) -> None:
    result = build_card(tmp_path)
    markdown = result.output_md.read_text(encoding="utf-8").lower()

    for token in FORBIDDEN_MARKDOWN_TOKENS:
        assert token not in markdown


def test_script_does_not_reference_price_calculator() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "calc_quote_price_draft" not in source
    assert "price calculator" not in source.lower()


def test_script_does_not_reference_commercial_writer_or_launcher() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "run_invoice_quote_commercial_from_csv" not in source
    assert "make_quote_capacity100_commercial_checked" not in source
    assert "commercial writer" not in source.lower()


def test_script_does_not_reference_client_style_exporter_or_launcher() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "export_client_style_invoice" not in source
    assert "run_client_style_invoice_export" not in source
    assert "client-style exporter" not in source.lower()


def test_script_does_not_call_git() -> None:
    source = SCRIPT.read_text(encoding="utf-8").lower()

    assert "subprocess" not in source
    assert " git " not in source
    assert "git." not in source


def test_old_workflows_do_not_reference_this_review_card_builder() -> None:
    builder_name = "build_preliminary_composition_review_card"

    for path in OLD_WORKFLOWS:
        assert path.is_file(), path
        assert builder_name not in path.read_text(encoding="utf-8"), path


def test_report_has_required_markers_and_output_status(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw_path = write_raw_text(tmp_path)
    draft_path = write_draft(tmp_path, valid_data())
    output_path = tmp_path / "review-card.md"

    assert (
        builder.main(
            [
                "--raw-input-text",
                str(raw_path),
                "--draft-json",
                str(draft_path),
                "--output-md",
                str(output_path),
            ]
        )
        == 0
    )
    report = capsys.readouterr().out

    assert report.startswith("PRELIMINARY_COMPOSITION_REVIEW_CARD_REPORT_START")
    assert "Mode:\npreliminary composition Igor review card only" in report
    assert "Output:\n" in report
    assert str(output_path) in report
    assert report.rstrip().endswith("PRELIMINARY_COMPOSITION_REVIEW_CARD_REPORT_END")
