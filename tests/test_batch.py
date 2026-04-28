import os
import subprocess
import sys
import tempfile
from subprocess import CompletedProcess

BATCH_CMD = [sys.executable, "-m", "src.main", "batch"]


def run_batch_file(lines: list[str]) -> CompletedProcess[str]:
    with tempfile.NamedTemporaryFile("w+", delete=False, encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
        f.flush()
        path = f.name
    try:
        result = subprocess.run(BATCH_CMD + [path], capture_output=True, text=True)
        return result
    finally:
        os.remove(path)


def test_batch_success() -> None:
    lines = ["add 2 3", "mul 4 5", "div 10 2"]
    result = run_batch_file(lines)
    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout.strip().split("\n") == [
        "add 2 3 = 5",
        "multiply 4 5 = 20",
        "divide 10 2 = 5",
    ]


def test_batch_comments_and_blanks() -> None:
    lines = ["# comment", "", "add 1 2", "   ", "# another"]
    result = run_batch_file(lines)
    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout.strip() == "add 1 2 = 3"


def test_batch_aliases() -> None:
    lines = ["sum 1 2", "sub 5 3", "pow 2 3"]
    result = run_batch_file(lines)
    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout.strip().split("\n") == [
        "add 1 2 = 3",
        "subtract 5 3 = 2",
        "power 2 3 = 8",
    ]


def test_batch_file_not_found() -> None:
    result = subprocess.run(
        BATCH_CMD + ["no_such_file.txt"], capture_output=True, text=True
    )
    assert result.returncode == 1
    assert "cannot open file" in result.stderr


def test_batch_invalid_operation() -> None:
    lines = ["add 1 2", "badop 3 4", "mul 2 2"]
    result = run_batch_file(lines)
    assert result.returncode == 1
    assert "Unknown operation" in result.stderr
    assert "line 2" in result.stderr
    assert "add 1 2 = 3" in result.stdout
    assert "mul 2 2" not in result.stdout


def test_batch_invalid_number() -> None:
    lines = ["add 1 2", "add x 3"]
    result = run_batch_file(lines)
    assert result.returncode == 1
    assert "valid number" in result.stderr
    assert "line 2" in result.stderr
    assert "add 1 2 = 3" in result.stdout


def test_batch_division_by_zero() -> None:
    lines = ["div 1 0"]
    result = run_batch_file(lines)
    assert result.returncode == 1
    assert "line 1" in result.stderr
    assert "divide by zero" in result.stderr.lower()


def test_batch_malformed_line() -> None:
    lines = ["add 1", "mul 2 2 2"]
    result = run_batch_file(lines)
    assert result.returncode == 1
    assert "malformed line" in result.stderr


def test_batch_missing_file_arg() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "src.main", "batch"], capture_output=True, text=True
    )
    assert result.returncode == 2  # argparse error
    usage_in_stderr = "usage:" in result.stderr.lower()
    usage_in_stdout = "usage:" in result.stdout.lower()
    assert usage_in_stderr or usage_in_stdout
