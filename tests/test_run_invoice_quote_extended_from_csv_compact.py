import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPACT_RUNNER_SCRIPT = (
    PROJECT_ROOT / "scripts" / "run_invoice_quote_extended_from_csv_compact.py"
)
ITEMS_BRIDGE_TESTS = (
    PROJECT_ROOT / "tests" / "test_run_invoice_quote_extended_from_items.py"
)


def load_script_module(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


compact_runner = cast(
    Any,
    load_script_module(
        "run_invoice_quote_extended_from_csv_compact_for_test",
        COMPACT_RUNNER_SCRIPT,
    ),
)
items_bridge_tests = cast(
    Any,
    load_script_module(
        "run_invoice_quote_extended_from_items_helpers_for_compact_csv_test",
        ITEMS_BRIDGE_TESTS,
    ),
)
workbook_value = items_bridge_tests.workbook_value
write_extended_template = items_bridge_tests.write_extended_template


def csv_header() -> str:
    return (
        "name;unit;quantity;instruments_and_devices;"
        "cabinet_type_dimensions_material\n"
    )


def write_items_csv(path: Path, rows: list[str]) -> None:
    path.write_text(csv_header() + "".join(rows), encoding="utf-8", newline="")


def output_path(tmp_path: Path) -> Path:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    return output_dir / "draft.xlsx"


def compact_args(
    items_csv: Path,
    template: Path,
    capacity: int,
    output: Path,
) -> list[str]:
    return [
        "--items-csv",
        str(items_csv),
        "--template",
        str(template),
        "--template-capacity",
        str(capacity),
        "--output",
        str(output),
    ]


def run_compact_runner(
    items_csv: Path,
    template: Path,
    capacity: int,
    output: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(COMPACT_RUNNER_SCRIPT)]
        + compact_args(items_csv, template, capacity, output),
        capture_output=True,
        text=True,
        check=False,
    )


def test_compact_runner_cli_compacts_then_runs_csv_runtime(tmp_path: Path) -> None:
    template = tmp_path / "extended_template.xlsx"
    items_csv = tmp_path / "items.csv"
    output = output_path(tmp_path)
    write_extended_template(template)
    write_items_csv(
        items_csv,
        [
            (
                '"Щит\n\nуправления";шт;1;'
                '"Контроллер\n  датчики\nклеммы";"Шкаф\nметалл"\n'
            )
        ],
    )

    result = run_compact_runner(items_csv, template, 8, output)

    assert result.returncode == 0
    assert "CREATED:" in result.stdout
    assert result.stderr == ""
    assert output.is_file()
    assert workbook_value(output, "C17") == "Щит управления"
    assert workbook_value(output, "F17") == "Контроллер датчики клеммы"
    assert workbook_value(output, "G17") == "Шкаф металл"


def test_compact_runner_cleans_temp_compact_csv_after_success(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    template = tmp_path / "extended_template.xlsx"
    items_csv = tmp_path / "items.csv"
    output = output_path(tmp_path)
    temp_parent = tmp_path / "compact-temp"
    temp_parent.mkdir()
    created_dirs: list[Path] = []
    captured: dict[str, Any] = {}
    write_items_csv(items_csv, ['ВРУ;шт;1;"прибор\nшкаф";"корпус\nметалл"\n'])

    def temporary_directory(*args: Any, **kwargs: Any) -> Any:
        kwargs["dir"] = temp_parent
        manager = tempfile.TemporaryDirectory(*args, **kwargs)
        created_dirs.append(Path(manager.name))
        return manager

    def fake_csv_bridge_main(argv: list[str]) -> int:
        compact_csv = Path(argv[argv.index("--items-csv") + 1])
        captured["compact_csv"] = compact_csv
        captured["text"] = compact_csv.read_text(encoding="utf-8")
        captured["argv"] = argv
        return 0

    monkeypatch.setattr(compact_runner, "TEMPORARY_DIRECTORY", temporary_directory)
    monkeypatch.setattr(compact_runner.csv_bridge, "main", fake_csv_bridge_main)

    exit_code = compact_runner.main(compact_args(items_csv, template, 8, output))

    assert exit_code == 0
    assert created_dirs
    assert "прибор шкаф" in captured["text"]
    assert captured["compact_csv"].name == "items_compact.csv"
    assert all(not path.exists() for path in created_dirs)
    assert list(temp_parent.iterdir()) == []


def test_compact_runner_cleans_temp_compact_csv_after_downstream_error(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    template = tmp_path / "extended_template.xlsx"
    items_csv = tmp_path / "items.csv"
    output = output_path(tmp_path)
    temp_parent = tmp_path / "compact-temp"
    temp_parent.mkdir()
    created_dirs: list[Path] = []
    write_items_csv(items_csv, ['ВРУ;шт;1;"прибор\nшкаф";корпус\n'])

    def temporary_directory(*args: Any, **kwargs: Any) -> Any:
        kwargs["dir"] = temp_parent
        manager = tempfile.TemporaryDirectory(*args, **kwargs)
        created_dirs.append(Path(manager.name))
        return manager

    def fake_csv_bridge_main(argv: list[str]) -> int:
        compact_csv = Path(argv[argv.index("--items-csv") + 1])
        assert compact_csv.is_file()
        return 1

    monkeypatch.setattr(compact_runner, "TEMPORARY_DIRECTORY", temporary_directory)
    monkeypatch.setattr(compact_runner.csv_bridge, "main", fake_csv_bridge_main)

    exit_code = compact_runner.main(compact_args(items_csv, template, 8, output))

    assert exit_code == 1
    assert created_dirs
    assert all(not path.exists() for path in created_dirs)
    assert list(temp_parent.iterdir()) == []
    assert not output.exists()


def test_compact_runner_returns_one_when_compaction_fails(
    tmp_path: Path,
    monkeypatch: Any,
    capsys: Any,
) -> None:
    template = tmp_path / "extended_template.xlsx"
    items_csv = tmp_path / "items.csv"
    output = output_path(tmp_path)
    called = False
    write_items_csv(items_csv, ["ВРУ;шт;bad;приборы;шкаф\n"])

    def fake_csv_bridge_main(argv: list[str]) -> int:
        nonlocal called
        called = True
        return 0

    monkeypatch.setattr(compact_runner.csv_bridge, "main", fake_csv_bridge_main)

    exit_code = compact_runner.main(compact_args(items_csv, template, 8, output))

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "quantity must be an integer" in captured.err
    assert called is False
    assert not output.exists()


def test_compact_runner_preserves_downstream_existing_output_failure(
    tmp_path: Path,
) -> None:
    template = tmp_path / "extended_template.xlsx"
    items_csv = tmp_path / "items.csv"
    output = output_path(tmp_path)
    output.write_bytes(b"existing")
    write_extended_template(template)
    write_items_csv(items_csv, ["ВРУ;шт;1;приборы;шкаф\n"])

    result = run_compact_runner(items_csv, template, 8, output)

    assert result.returncode == 1
    assert "output already exists" in result.stderr
    assert output.read_bytes() == b"existing"


def test_compact_runner_preserves_downstream_output_inside_git_failure(
    tmp_path: Path,
) -> None:
    template = tmp_path / "extended_template.xlsx"
    items_csv = tmp_path / "items.csv"
    output = PROJECT_ROOT / "compact_runner_should_not_write.xlsx"
    write_extended_template(template)
    write_items_csv(items_csv, ["ВРУ;шт;1;приборы;шкаф\n"])

    result = run_compact_runner(items_csv, template, 8, output)

    assert result.returncode == 1
    assert "output is inside the Git project" in result.stderr
    assert not output.exists()
