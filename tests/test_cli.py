import builtins
import subprocess
import sys

import pytest

import src.main as main_module


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "src.main", *args],
        capture_output=True,
        text=True,
    )


def test_cli_without_args() -> None:
    result = run_cli()

    assert result.returncode == 0
    assert "usage:" in result.stdout
    assert "interactive" in result.stdout
    assert result.stderr == ""


def test_cli_help() -> None:
    result = run_cli("--help")

    assert result.returncode == 0
    assert "Simple calculator CLI with subcommands." in result.stdout
    assert "interactive" in result.stdout
    assert "add" in result.stdout
    assert result.stderr == ""


def test_cli_add() -> None:
    result = run_cli("add", "2", "3")

    assert result.returncode == 0
    assert result.stdout.strip() == "5"
    assert result.stderr == ""


def test_cli_subtract_alias() -> None:
    result = run_cli("sub", "10", "4")

    assert result.returncode == 0
    assert result.stdout.strip() == "6"
    assert result.stderr == ""


def test_cli_multiply_alias() -> None:
    result = run_cli("mul", "6", "7")

    assert result.returncode == 0
    assert result.stdout.strip() == "42"
    assert result.stderr == ""


def test_cli_divide_alias() -> None:
    result = run_cli("div", "5", "2")

    assert result.returncode == 0
    assert result.stdout.strip() == "2.5"
    assert result.stderr == ""


def test_cli_power_alias() -> None:
    result = run_cli("pow", "2", "8")

    assert result.returncode == 0
    assert result.stdout.strip() == "256"
    assert result.stderr == ""


def test_cli_modulo_alias() -> None:
    result = run_cli("mod", "10", "3")

    assert result.returncode == 0
    assert result.stdout.strip() == "1"
    assert result.stderr == ""


def test_cli_divide_by_zero() -> None:
    result = run_cli("divide", "1", "0")

    assert result.returncode != 0
    assert result.stdout == ""
    assert "Cannot divide by zero" in result.stderr


def test_cli_unknown_operation() -> None:
    result = run_cli("oops", "2", "3")

    assert result.returncode != 0
    assert result.stdout == ""
    assert "invalid choice" in result.stderr


def test_cli_missing_argument() -> None:
    result = run_cli("add", "2")

    assert result.returncode != 0
    assert "the following arguments are required: b" in result.stderr


def test_main_interactive_mode(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    original_argv = sys.argv[:]

    try:
        sys.argv = ["prog", "interactive"]
        inputs = iter(["exit"])
        monkeypatch.setattr(
            builtins,
            "input",
            lambda _: next(inputs),
        )

        main_module.main()

        captured = capsys.readouterr()
        assert "Interactive calculator mode" in captured.out
        assert "Bye!" in captured.out
    finally:
        sys.argv = original_argv


def test_run_interactive_help_and_calculation(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inputs = iter(["help", "add", "2", "3", "history", "exit"])
    monkeypatch.setattr(
        builtins,
        "input",
        lambda _: next(inputs),
    )

    main_module.run_interactive()

    captured = capsys.readouterr()
    assert "Interactive calculator mode" in captured.out
    assert (
        "Commands: add, sub, mul, div, pow, mod, history, clear, help, exit"
        in captured.out
    )
    assert "add 2 3 = 5" in captured.out
    assert "History:" in captured.out
    assert "Bye!" in captured.out


def test_run_interactive_clear_history(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inputs = iter(["add", "2", "3", "clear", "history", "exit"])
    monkeypatch.setattr(
        builtins,
        "input",
        lambda _: next(inputs),
    )

    main_module.run_interactive()

    captured = capsys.readouterr()
    assert "add 2 3 = 5" in captured.out
    assert "History cleared." in captured.out
    assert "History is empty." in captured.out


def test_run_interactive_unknown_operation(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inputs = iter(["oops", "exit"])
    monkeypatch.setattr(
        builtins,
        "input",
        lambda _: next(inputs),
    )

    main_module.run_interactive()

    captured = capsys.readouterr()
    assert "Unknown operation: oops" in captured.out
    assert "Bye!" in captured.out
