"""Run read-only finish checks and print a compact Codex report."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(sys.executable)
HANDOFF_SCRIPT = PROJECT_ROOT / "scripts" / "build_repo_handoff.py"
EXCERPT_LINES = 40
VALID_MODES = {"fast", "full"}

CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    command: tuple[str, ...]
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class FinishReport:
    mode: str
    checks: tuple[CheckResult, ...]
    handoff_output: str


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run read-only Codex finish checks and print a report."
    )
    parser.add_argument(
        "--mode",
        required=True,
        help="Check mode: fast or full",
    )
    return parser.parse_args(argv)


def run_command(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
        shell=False,
    )


def command_for_check(name: str) -> tuple[str, ...]:
    if name == "pytest":
        return (str(PYTHON), "-m", "pytest")
    if name == "mypy":
        return (str(PYTHON), "-m", "mypy")
    if name == "ruff":
        return (str(PYTHON), "-m", "ruff", "check")
    if name == "black":
        return (str(PYTHON), "-m", "black", "--check", ".")
    if name == "git diff --check":
        return ("git", "diff", "--check")
    if name == "repo handoff":
        return (str(PYTHON), str(HANDOFF_SCRIPT))
    raise ValueError(f"unknown check: {name}")


def check_names_for_mode(mode: str) -> tuple[str, ...]:
    if mode == "fast":
        return (
            "mypy",
            "ruff",
            "black",
            "git diff --check",
            "repo handoff",
        )
    if mode == "full":
        return (
            "pytest",
            "mypy",
            "ruff",
            "black",
            "git diff --check",
            "repo handoff",
        )
    raise ValueError(f"invalid mode: {mode}")


def run_single_check(name: str, runner: CommandRunner) -> CheckResult:
    command = command_for_check(name)
    result = runner(command)
    status = "pass" if result.returncode == 0 else "fail"
    return CheckResult(
        name=name,
        status=status,
        command=command,
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def skipped_pytest() -> CheckResult:
    return CheckResult(
        name="pytest",
        status="skip",
        command=(),
        returncode=0,
    )


def run_checks(
    mode: str,
    runner: CommandRunner = run_command,
) -> FinishReport:
    if mode not in VALID_MODES:
        raise ValueError(f"invalid mode: {mode}")

    results: list[CheckResult] = []
    if mode == "fast":
        results.append(skipped_pytest())

    for name in check_names_for_mode(mode):
        results.append(run_single_check(name, runner))

    handoff = next(result for result in results if result.name == "repo handoff")
    handoff_output = handoff.stdout.strip()
    return FinishReport(
        mode=mode,
        checks=tuple(results),
        handoff_output=handoff_output,
    )


def status_for(report: FinishReport, name: str) -> str:
    for check in report.checks:
        if check.name == name:
            return check.status
    return "skip"


def combined_output(check: CheckResult) -> str:
    parts = []
    if check.stdout:
        parts.append(check.stdout.strip())
    if check.stderr:
        parts.append(check.stderr.strip())
    return "\n".join(part for part in parts if part)


def short_excerpt(text: str, line_limit: int = EXCERPT_LINES) -> str:
    lines = text.splitlines()
    if not lines:
        return "(no output)"
    return "\n".join(lines[-line_limit:])


def failure_excerpts(report: FinishReport) -> list[str]:
    excerpts: list[str] = []
    for check in report.checks:
        if check.status != "fail":
            continue
        command = " ".join(check.command) if check.command else check.name
        excerpts.append(
            f"{check.name} failed: {command}\n"
            f"{short_excerpt(combined_output(check))}"
        )
    return excerpts


def fallback_handoff_block() -> str:
    return "\n".join(
        [
            "CHATGPT_HANDOFF_START",
            "not available",
            "CHATGPT_HANDOFF_END",
        ]
    )


def format_report(report: FinishReport) -> str:
    failures = failure_excerpts(report)
    handoff_output = report.handoff_output or fallback_handoff_block()
    lines = [
        "CODEX_FINISH_REPORT_START",
        "",
        "Mode:",
        report.mode,
        "",
        "Checks:",
        f"pytest: {status_for(report, 'pytest')}",
        f"mypy: {status_for(report, 'mypy')}",
        f"ruff: {status_for(report, 'ruff')}",
        f"black: {status_for(report, 'black')}",
        f"git diff --check: {status_for(report, 'git diff --check')}",
        f"repo handoff: {status_for(report, 'repo handoff')}",
        "",
        "Failures:",
    ]
    if failures:
        lines.append("\n\n".join(failures))
    else:
        lines.append("none")
    lines.extend(["", handoff_output, "", "CODEX_FINISH_REPORT_END"])
    return "\n".join(lines)


def report_exit_code(report: FinishReport) -> int:
    return 1 if any(check.status == "fail" for check in report.checks) else 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    mode = str(args.mode)
    if mode not in VALID_MODES:
        print(
            "ERROR: invalid mode. Use --mode fast or --mode full.",
            file=sys.stderr,
        )
        return 2

    report = run_checks(mode)
    print(format_report(report))
    return report_exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
