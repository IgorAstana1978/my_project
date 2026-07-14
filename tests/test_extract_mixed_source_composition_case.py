import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, cast

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
WRAPPER_SCRIPT = SCRIPTS_DIR / "extract_mixed_source_composition_case.py"
sys.path.insert(0, str(SCRIPTS_DIR))


def load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


wrapper = cast(Any, load_module("mixed_source_case_wrapper_for_test", WRAPPER_SCRIPT))


@pytest.fixture
def canonical_root(tmp_path: Path) -> Path:
    root = tmp_path / "production_ai_cases"
    root.mkdir()
    return root


@pytest.fixture
def sources(tmp_path: Path) -> tuple[Path, Path]:
    pdf = tmp_path / "project.pdf"
    workbook = tmp_path / "spec.xlsx"
    pdf.write_bytes(b"synthetic pdf source")
    workbook.write_bytes(b"synthetic workbook source")
    return pdf, workbook


def passing_extractor(
    project_pdf: Path | None,
    spec_workbook: Path | None,
    output_dir: Path,
) -> SimpleNamespace:
    assert project_pdf is not None or spec_workbook is not None
    output_dir.mkdir()
    for name in wrapper.EXPECTED_FILES:
        (output_dir / name).write_text(f"synthetic {name}", encoding="utf-8")
    return SimpleNamespace(
        status="PASS",
        output_dir=output_dir,
        checks={name: "pass" for name in wrapper.REQUIRED_EXTRACTOR_CHECKS},
        red_flags=[],
    )


def run_success(
    canonical_root: Path,
    sources: tuple[Path, Path],
    **overrides: Any,
) -> Any:
    pdf, workbook = sources
    arguments: dict[str, Any] = {
        "case_id": "CASE-ALPHA-01",
        "project_pdf": pdf,
        "spec_workbook": workbook,
        "canonical_root": canonical_root,
        "extractor_fn": passing_extractor,
    }
    arguments.update(overrides)
    return wrapper.run_case_extraction(**arguments)


def fixed_uuid() -> SimpleNamespace:
    return SimpleNamespace(hex="fixed")


@pytest.mark.parametrize(
    "case_id",
    ["CASE-A", "CASE-123", "CASE-ALPHA-01", "CASE-A1-B2-C3"],
)
def test_case_id_grammar_accepts_canonical_values(case_id: str) -> None:
    assert wrapper.valid_case_id(case_id)


@pytest.mark.parametrize(
    "case_id",
    [
        "case-A",
        "CASE",
        "CASE-",
        "CASE--A",
        "CASE_A",
        "CASE-A/OTHER",
        "CASE-A\\OTHER",
        "../CASE-A",
        "CASE-Ä",
        " CASE-A",
    ],
)
def test_case_id_grammar_rejects_invalid_or_traversal_values(case_id: str) -> None:
    assert not wrapper.valid_case_id(case_id)


def test_case_id_length_is_bounded() -> None:
    assert not wrapper.valid_case_id("CASE-" + "A" * 124)


def test_requires_at_least_one_source(canonical_root: Path) -> None:
    result = wrapper.run_case_extraction(
        case_id="CASE-A",
        project_pdf=None,
        spec_workbook=None,
        canonical_root=canonical_root,
        extractor_fn=passing_extractor,
    )

    assert result.status == "FAIL"
    assert "at least one source" in result.red_flags[0]
    assert list(canonical_root.iterdir()) == []


@pytest.mark.parametrize(
    ("use_pdf", "use_workbook", "expected_mode"),
    [
        (True, False, "pdf_only"),
        (False, True, "workbook_only"),
        (True, True, "pdf_and_workbook"),
    ],
)
def test_supported_source_modes(
    canonical_root: Path,
    sources: tuple[Path, Path],
    use_pdf: bool,
    use_workbook: bool,
    expected_mode: str,
) -> None:
    pdf, workbook = sources
    result = wrapper.run_case_extraction(
        case_id=f"CASE-{expected_mode.upper().replace('_', '-')}",
        project_pdf=pdf if use_pdf else None,
        spec_workbook=workbook if use_workbook else None,
        canonical_root=canonical_root,
        extractor_fn=passing_extractor,
    )

    assert result.status == "PASS"
    assert result.source_mode == expected_mode


def test_canonical_root_must_already_exist(
    tmp_path: Path, sources: tuple[Path, Path]
) -> None:
    result = run_success(tmp_path / "missing", sources)

    assert result.status == "FAIL"
    assert "canonical root does not exist" in result.red_flags[0]


def test_existing_final_directory_is_preserved(
    canonical_root: Path, sources: tuple[Path, Path]
) -> None:
    final = canonical_root / "CASE-ALPHA-01"
    final.mkdir()
    sentinel = final / "existing.txt"
    sentinel.write_text("preserve", encoding="utf-8")

    result = run_success(canonical_root, sources)

    assert result.status == "FAIL"
    assert sentinel.read_text(encoding="utf-8") == "preserve"
    assert set(final.iterdir()) == {sentinel}


def test_existing_empty_final_directory_blocks_run(
    canonical_root: Path, sources: tuple[Path, Path]
) -> None:
    final = canonical_root / "CASE-ALPHA-01"
    final.mkdir()

    result = run_success(canonical_root, sources)

    assert result.status == "FAIL"
    assert final.is_dir()
    assert list(final.iterdir()) == []


def test_existing_path_entry_policy_uses_lexists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[Path] = []

    def fake_lexists(path: Path) -> bool:
        observed.append(path)
        return True

    monkeypatch.setattr(wrapper.os.path, "lexists", fake_lexists)

    assert wrapper.path_entry_exists(Path("dangling-entry")) is True
    assert observed == [Path("dangling-entry")]


def test_preexisting_selected_owner_is_preserved_without_extractor_or_cleanup(
    canonical_root: Path, sources: tuple[Path, Path]
) -> None:
    owner = canonical_root / ".CASE-ALPHA-01-wrapper-fixed"
    owner.mkdir()
    sentinel = owner / "sentinel.bin"
    sentinel.write_bytes(b"preserve exact bytes")
    extractor_calls: list[Path] = []
    cleanup_calls: list[Path] = []

    def forbidden_extractor(
        project: Path | None, spec: Path | None, output: Path
    ) -> Any:
        extractor_calls.append(output)
        raise AssertionError("extractor must not run")

    def cleanup_spy(path: Path) -> str | None:
        cleanup_calls.append(path)
        return None

    result = run_success(
        canonical_root,
        sources,
        uuid_fn=fixed_uuid,
        extractor_fn=forbidden_extractor,
        cleanup_fn=cleanup_spy,
    )

    assert result.status == "FAIL"
    assert extractor_calls == []
    assert cleanup_calls == []
    assert sentinel.read_bytes() == b"preserve exact bytes"
    assert not (canonical_root / "CASE-ALPHA-01").exists()
    assert any(str(owner.resolve()) in flag for flag in result.red_flags)
    assert any("manual inspection" in flag for flag in result.red_flags)


def test_owner_creation_race_is_preserved_without_cleanup(
    canonical_root: Path, sources: tuple[Path, Path]
) -> None:
    owner = canonical_root / ".CASE-ALPHA-01-wrapper-fixed"
    sentinel = owner / "competing.bin"
    cleanup_calls: list[Path] = []

    def racing_mkdir(path: Path) -> None:
        path.mkdir()
        sentinel.write_bytes(b"competing exact bytes")
        raise FileExistsError("synthetic owner race")

    def cleanup_spy(path: Path) -> str | None:
        cleanup_calls.append(path)
        return None

    result = run_success(
        canonical_root,
        sources,
        uuid_fn=fixed_uuid,
        owner_mkdir_fn=racing_mkdir,
        cleanup_fn=cleanup_spy,
    )

    assert result.status == "FAIL"
    assert cleanup_calls == []
    assert sentinel.read_bytes() == b"competing exact bytes"
    assert not (canonical_root / "CASE-ALPHA-01").exists()
    assert any(str(owner.resolve()) in flag for flag in result.red_flags)
    assert any("manual inspection" in flag for flag in result.red_flags)


def test_cli_does_not_accept_arbitrary_output_directory() -> None:
    with pytest.raises(SystemExit):
        wrapper.parse_args(["--case-id", "CASE-A", "--output-dir", "elsewhere"])


@pytest.mark.parametrize(
    ("source_name", "argument", "message"),
    [
        ("missing.pdf", "project_pdf", "does not exist"),
        ("source.txt", "project_pdf", "extension must be"),
        ("source.csv", "spec_workbook", "extension must be"),
    ],
)
def test_invalid_source_is_rejected(
    canonical_root: Path,
    tmp_path: Path,
    source_name: str,
    argument: str,
    message: str,
) -> None:
    source = tmp_path / source_name
    if not source_name.startswith("missing"):
        source.write_text("synthetic", encoding="utf-8")
    kwargs = {"project_pdf": None, "spec_workbook": None, argument: source}

    result = wrapper.run_case_extraction(
        case_id="CASE-A",
        canonical_root=canonical_root,
        extractor_fn=passing_extractor,
        **kwargs,
    )

    assert result.status == "FAIL"
    assert message in result.red_flags[0]


def test_source_directory_is_rejected(canonical_root: Path, tmp_path: Path) -> None:
    directory = tmp_path / "source.pdf"
    directory.mkdir()

    result = wrapper.run_case_extraction(
        case_id="CASE-A",
        project_pdf=directory,
        spec_workbook=None,
        canonical_root=canonical_root,
        extractor_fn=passing_extractor,
    )

    assert result.status == "FAIL"
    assert "regular file" in result.red_flags[0]


def test_identical_source_paths_are_rejected_before_suffix_checks(
    canonical_root: Path, sources: tuple[Path, Path]
) -> None:
    pdf, _ = sources

    result = wrapper.run_case_extraction(
        case_id="CASE-A",
        project_pdf=pdf,
        spec_workbook=pdf,
        canonical_root=canonical_root,
        extractor_fn=passing_extractor,
    )

    assert result.status == "FAIL"
    assert "different source paths" in result.red_flags[0]


def test_source_inside_future_case_directory_is_rejected(
    canonical_root: Path,
) -> None:
    final = canonical_root / "CASE-A"
    final.mkdir()
    source = final / "project.pdf"
    source.write_bytes(b"synthetic")

    result = wrapper.run_case_extraction(
        case_id="CASE-A",
        project_pdf=source,
        spec_workbook=None,
        canonical_root=canonical_root,
        extractor_fn=passing_extractor,
    )

    assert result.status == "FAIL"
    assert "outside the future Case directory" in result.red_flags[0]
    assert source.exists()


def test_existing_extractor_is_called_directly_with_staging_directory(
    canonical_root: Path, sources: tuple[Path, Path]
) -> None:
    pdf, workbook = sources
    calls: list[tuple[Path | None, Path | None, Path]] = []

    def spy(project: Path | None, spec: Path | None, output: Path) -> Any:
        calls.append((project, spec, output))
        assert not (canonical_root / "CASE-ALPHA-01").exists()
        assert output.name == "bundle"
        assert output.parent.is_dir()
        assert not output.exists()
        return passing_extractor(project, spec, output)

    result = run_success(canonical_root, sources, extractor_fn=spy)

    assert result.status == "PASS"
    assert len(calls) == 1
    assert calls[0][0:2] == (pdf.resolve(), workbook.resolve())
    assert calls[0][2].parent.parent == canonical_root.resolve()
    assert calls[0][2].parent.name.startswith(".CASE-ALPHA-01-wrapper-")


def test_extractor_failure_blocks_publication_and_cleans_staging(
    canonical_root: Path, sources: tuple[Path, Path]
) -> None:
    def failing(project: Path | None, spec: Path | None, output: Path) -> Any:
        output.mkdir()
        return SimpleNamespace(
            status="FAIL", output_dir=output, checks={}, red_flags=["synthetic failure"]
        )

    result = run_success(canonical_root, sources, extractor_fn=failing)

    assert result.status == "FAIL"
    assert "existing extractor failed: synthetic failure" in result.red_flags
    assert list(canonical_root.iterdir()) == []


def test_partial_bundle_from_failed_extractor_is_owned_and_cleaned(
    canonical_root: Path, sources: tuple[Path, Path]
) -> None:
    def partial(project: Path | None, spec: Path | None, output: Path) -> Any:
        output.mkdir()
        (output / "partial.bin").write_bytes(b"owned partial")
        return SimpleNamespace(
            status="FAIL", output_dir=output, checks={}, red_flags=["partial"]
        )

    result = run_success(
        canonical_root,
        sources,
        uuid_fn=fixed_uuid,
        extractor_fn=partial,
    )

    assert result.status == "FAIL"
    assert not (canonical_root / ".CASE-ALPHA-01-wrapper-fixed").exists()
    assert not (canonical_root / "CASE-ALPHA-01").exists()


@pytest.mark.parametrize("defect", ["missing", "extra", "subdirectory", "empty"])
def test_invalid_staging_outputs_block_publication(
    canonical_root: Path,
    sources: tuple[Path, Path],
    defect: str,
) -> None:
    def invalid(project: Path | None, spec: Path | None, output: Path) -> Any:
        result = passing_extractor(project, spec, output)
        if defect == "missing":
            (output / wrapper.DRAFT_NAME).unlink()
        elif defect == "extra":
            (output / "extra.txt").write_text("extra", encoding="utf-8")
        elif defect == "subdirectory":
            (output / wrapper.DRAFT_NAME).unlink()
            (output / wrapper.DRAFT_NAME).mkdir()
        else:
            (output / wrapper.DRAFT_NAME).write_bytes(b"")
        return result

    result = run_success(canonical_root, sources, extractor_fn=invalid)

    assert result.status == "FAIL"
    assert list(canonical_root.iterdir()) == []


def test_structured_extractor_checks_must_pass(
    canonical_root: Path, sources: tuple[Path, Path]
) -> None:
    def incomplete(project: Path | None, spec: Path | None, output: Path) -> Any:
        result = passing_extractor(project, spec, output)
        result.checks["safety boundary"] = "fail"
        return result

    result = run_success(canonical_root, sources, extractor_fn=incomplete)

    assert result.status == "FAIL"
    assert "required validation checks" in result.red_flags[0]
    assert list(canonical_root.iterdir()) == []


def test_success_publishes_exact_files_with_one_directory_rename(
    canonical_root: Path, sources: tuple[Path, Path]
) -> None:
    observations: list[tuple[Path, Path]] = []

    def checked_rename(source: Path, destination: Path) -> None:
        assert source.is_dir()
        assert not destination.exists()
        observations.append((source, destination))
        os.rename(source, destination)

    result = run_success(canonical_root, sources, rename_fn=checked_rename)
    final = canonical_root / "CASE-ALPHA-01"

    assert result.status == "PASS"
    assert result.output_created is True
    assert result.output_dir == final.resolve()
    assert result.created_files == sorted(wrapper.EXPECTED_FILES)
    assert {path.name for path in final.iterdir()} == wrapper.EXPECTED_FILES
    assert len(observations) == 1
    assert not observations[0][0].exists()
    assert not observations[0][0].parent.exists()


def test_rename_race_preserves_competing_final_and_cleans_staging(
    canonical_root: Path, sources: tuple[Path, Path]
) -> None:
    sentinel = canonical_root / "CASE-ALPHA-01" / "competing.txt"

    def racing_rename(source: Path, destination: Path) -> None:
        destination.mkdir()
        sentinel.write_text("preserve", encoding="utf-8")
        raise FileExistsError("synthetic publish race")

    result = run_success(canonical_root, sources, rename_fn=racing_rename)

    assert result.status == "FAIL"
    assert sentinel.read_text(encoding="utf-8") == "preserve"
    assert set(canonical_root.iterdir()) == {sentinel.parent}
    assert any("manual inspection" in flag for flag in result.red_flags)


def test_cleanup_failure_is_reported_for_manual_inspection(
    canonical_root: Path,
    sources: tuple[Path, Path],
) -> None:
    owner = canonical_root / ".CASE-ALPHA-01-wrapper-fixed"

    def failing(project: Path | None, spec: Path | None, output: Path) -> Any:
        output.mkdir()
        return SimpleNamespace(status="FAIL", red_flags=["blocked"])

    result = run_success(
        canonical_root,
        sources,
        uuid_fn=fixed_uuid,
        extractor_fn=failing,
        cleanup_fn=lambda path: "synthetic denial",
    )

    assert result.status == "FAIL"
    assert any("cleanup failed" in flag for flag in result.red_flags)
    assert any("manual inspection" in flag for flag in result.red_flags)
    assert any(str(owner.resolve()) in flag for flag in result.red_flags)
    assert owner.exists()


def test_successful_final_is_never_removed_by_cleanup(
    canonical_root: Path, sources: tuple[Path, Path]
) -> None:
    prepublication_cleanup_calls: list[Path] = []
    postpublication_cleanup_calls: list[Path] = []

    def cleanup_spy(path: Path) -> str | None:
        prepublication_cleanup_calls.append(path)
        return cast(str | None, wrapper.cleanup_owned_container(path))

    def post_cleanup_spy(path: Path) -> str | None:
        postpublication_cleanup_calls.append(path)
        return cast(str | None, wrapper.remove_empty_owner_after_publication(path))

    result = run_success(
        canonical_root,
        sources,
        cleanup_fn=cleanup_spy,
        post_publish_cleanup_fn=post_cleanup_spy,
    )
    final = result.output_dir

    assert result.status == "PASS"
    assert prepublication_cleanup_calls == []
    assert len(postpublication_cleanup_calls) == 1
    assert postpublication_cleanup_calls[0] != final
    assert final.is_dir()
    assert {path.name for path in final.iterdir()} == wrapper.EXPECTED_FILES


def test_post_publication_owner_cleanup_failure_preserves_final_and_state(
    canonical_root: Path, sources: tuple[Path, Path]
) -> None:
    owner = canonical_root / ".CASE-ALPHA-01-wrapper-fixed"

    result = run_success(
        canonical_root,
        sources,
        uuid_fn=fixed_uuid,
        post_publish_cleanup_fn=lambda path: "synthetic post-publish denial",
    )

    assert result.status == "FAIL"
    assert result.output_created is True
    assert result.output_dir.is_dir()
    assert owner.is_dir()
    assert list(owner.iterdir()) == []
    assert any(str(owner.resolve()) in flag for flag in result.red_flags)
    assert any(
        "published final Case was preserved" in flag for flag in result.red_flags
    )


def test_post_publication_cleanup_exception_reports_exact_owner(
    canonical_root: Path, sources: tuple[Path, Path]
) -> None:
    owner = canonical_root / ".CASE-ALPHA-01-wrapper-fixed"

    def raising_cleanup(path: Path) -> str | None:
        raise OSError("synthetic cleanup exception")

    result = run_success(
        canonical_root,
        sources,
        uuid_fn=fixed_uuid,
        post_publish_cleanup_fn=raising_cleanup,
    )

    assert result.status == "FAIL"
    assert result.output_created is True
    assert result.output_dir.is_dir()
    assert owner.is_dir()
    assert any(str(owner.resolve()) in flag for flag in result.red_flags)
    assert any("manual inspection" in flag for flag in result.red_flags)


def test_report_is_bounded_and_states_safety_boundary(
    canonical_root: Path, sources: tuple[Path, Path]
) -> None:
    result = run_success(canonical_root, sources)
    report = wrapper.format_report(result)

    assert report.startswith(wrapper.REPORT_START)
    assert report.endswith(wrapper.REPORT_END)
    assert "Status:\nPASS" in report
    assert "Case ID:\nCASE-ALPHA-01" in report
    assert f"Output:\n{result.output_dir}" in report
    assert "Output created:\nyes" in report
    assert "Igor review is required" in report
    for forbidden_approval in ("calculator", "price", "client send", "production"):
        assert forbidden_approval in report


def test_main_exit_codes_and_prints_report(monkeypatch: pytest.MonkeyPatch) -> None:
    success = wrapper.CaseExtractionResult(
        case_id="CASE-A", output_dir=Path("CASE-A"), status="PASS"
    )
    failure = wrapper.CaseExtractionResult(
        case_id="CASE-A", output_dir=Path("CASE-A"), red_flags=["blocked"]
    )
    monkeypatch.setattr(wrapper, "run_case_extraction", lambda **kwargs: success)
    assert wrapper.main(["--case-id", "CASE-A", "--project-pdf", "source.pdf"]) == 0
    monkeypatch.setattr(wrapper, "run_case_extraction", lambda **kwargs: failure)
    assert wrapper.main(["--case-id", "CASE-A", "--project-pdf", "source.pdf"]) == 1


def test_wrapper_has_no_forbidden_execution_or_copy_paths() -> None:
    source = WRAPPER_SCRIPT.read_text(encoding="utf-8").casefold()

    for forbidden in (
        "subprocess",
        "copy2",
        "copyfile",
        "clipboard",
        "openai",
        "requests",
        "build_confirmed_composition",
        "build_production_envelope",
    ):
        assert forbidden not in source
