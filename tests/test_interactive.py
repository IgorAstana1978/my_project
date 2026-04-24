"""Tests for interactive mode history export."""

from pathlib import Path
from unittest.mock import patch


def test_history_export_empty(tmp_path: Path) -> None:
    """Test exporting when history is empty."""
    from src.main import run_interactive

    export_path = tmp_path / "history.txt"

    inputs = iter(
        [
            "history export " + str(export_path),
            "exit",
        ]
    )

    with patch("builtins.input", side_effect=lambda prompt: next(inputs)):
        with patch("src.main.print") as mock_print:
            run_interactive()
            output = " ".join(call.args[0] for call in mock_print.call_args_list)
            assert "History is empty" in output


def test_history_export_success(tmp_path: Path) -> None:
    """Test successful history export."""
    from src.main import run_interactive

    export_path = tmp_path / "history.txt"

    inputs = iter(
        [
            "add",
            "2",
            "3",  # Result: 5
            "add",
            "4",
            "5",  # Result: 9
            "history export " + str(export_path),
            "exit",
        ]
    )

    with patch("builtins.input", side_effect=lambda prompt: next(inputs)):
        run_interactive()

    content = export_path.read_text()
    assert "add 2 3 = 5" in content
    assert "add 4 5 = 9" in content


def test_history_export_invalid_path() -> None:
    """Test export with invalid path."""
    from src.main import run_interactive

    inputs = iter(
        [
            "add",
            "2",
            "3",
            "history export /invalid/path/file.txt",
            "exit",
        ]
    )

    with patch("builtins.input", side_effect=lambda prompt: next(inputs)):
        with patch("src.main.print") as mock_print:
            run_interactive()
            output = " ".join(call.args[0] for call in mock_print.call_args_list)
            assert "Failed to export" in output


def test_history_export_no_path() -> None:
    """Test export with missing path argument."""
    from src.main import run_interactive

    inputs = iter(
        [
            "add",
            "2",
            "3",
            "history export",
            "exit",
        ]
    )

    with patch("builtins.input", side_effect=lambda prompt: next(inputs)):
        with patch("src.main.print") as mock_print:
            run_interactive()
            output_lines = []
            for call in mock_print.call_args_list:
                if call.args:
                    output_lines.append(str(call.args[0]))
            output = " ".join(output_lines)
            assert "Usage" in output
