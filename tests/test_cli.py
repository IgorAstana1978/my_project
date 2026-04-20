import subprocess
import sys


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "src.main", *args],
        capture_output=True,
        text=True,
    )


def test_cli_without_args() -> None:
    result = run_cli()

    assert result.returncode == 0
    assert "Simple calculator CLI" in result.stdout
    assert "python -m src.main add 2 3" in result.stdout
    assert result.stderr == ""


def test_cli_add() -> None:
    result = run_cli("add", "2", "3")

    assert result.returncode == 0
    assert result.stdout.strip() == "5"
    assert result.stderr == ""


def test_cli_subtract() -> None:
    result = run_cli("subtract", "10", "4")

    assert result.returncode == 0
    assert result.stdout.strip() == "6"
    assert result.stderr == ""


def test_cli_multiply() -> None:
    result = run_cli("multiply", "6", "7")

    assert result.returncode == 0
    assert result.stdout.strip() == "42"
    assert result.stderr == ""


def test_cli_divide() -> None:
    result = run_cli("divide", "5", "2")

    assert result.returncode == 0
    assert result.stdout.strip() == "2.5"
    assert result.stderr == ""


def test_cli_divide_by_zero() -> None:
    result = run_cli("divide", "1", "0")

    assert result.returncode != 0
    assert result.stdout == ""
    assert "Cannot divide by zero" in result.stderr
