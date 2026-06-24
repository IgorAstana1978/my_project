import importlib.util
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType
from typing import Any, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "run_codex_finish_checks.py"


def load_script_module(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


finish = cast(
    Any,
    load_script_module("run_codex_finish_checks_for_test", SCRIPT),
)


def completed(
    stdout: str = "",
    stderr: str = "",
    returncode: int = 0,
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def handoff_block() -> str:
    return "\n".join(
        [
            "CHATGPT_HANDOFF_START",
            "",
            "Repo:",
            "C:/repo",
            "",
            "Branch:",
            "main",
            "",
            "HEAD:",
            "abc1234 feat: demo",
            "",
            "Git status:",
            "clean",
            "",
            "Changed files:",
            "none",
            "",
            "Remote:",
            "origin/main",
            "",
            "CI:",
            "success",
            "",
            "GitHub Actions:",
            "https://github.example/actions/1",
            "",
            "Notes:",
            "none",
            "",
            "CHATGPT_HANDOFF_END",
        ]
    )


class FakeRunner:
    def __init__(
        self,
        fail_command_part: str | None = None,
        handoff_returncode: int = 0,
        noisy_failure: bool = False,
        smoke_stdout: str | None = None,
        smoke_returncode: int = 0,
    ) -> None:
        self.fail_command_part = fail_command_part
        self.handoff_returncode = handoff_returncode
        self.noisy_failure = noisy_failure
        self.smoke_stdout = smoke_stdout
        self.smoke_returncode = smoke_returncode
        self.commands: list[tuple[str, ...]] = []

    def __call__(
        self,
        command: Sequence[str],
    ) -> subprocess.CompletedProcess[str]:
        command_tuple = tuple(command)
        self.commands.append(command_tuple)
        command_text = " ".join(command_tuple)
        if "build_repo_handoff.py" in command_text:
            if self.handoff_returncode != 0:
                return completed(
                    stdout="",
                    stderr="handoff failed",
                    returncode=self.handoff_returncode,
                )
            return completed(stdout=handoff_block())
        if "smoke_checked_quote_launcher.ps1" in command_text:
            stdout = self.smoke_stdout
            if stdout is None:
                stdout = "\n".join(
                    [
                        "CHECKED_QUOTE_SMOKE_REPORT_START",
                        "",
                        "Result:",
                        "PASS",
                        "",
                        "CHECKED_QUOTE_SMOKE_REPORT_END",
                    ]
                )
            return completed(stdout=stdout, returncode=self.smoke_returncode)
        if self.fail_command_part and self.fail_command_part in command_text:
            if self.noisy_failure:
                stderr = "\n".join(f"line {index}" for index in range(1, 61))
            else:
                stderr = "small failure"
            return completed(stderr=stderr, returncode=1)
        return completed(stdout="ok")


def render(
    mode: str,
    runner: FakeRunner,
    include_quote_smoke: bool = False,
) -> str:
    report = finish.run_checks(
        mode,
        runner=runner,
        include_quote_smoke=include_quote_smoke,
    )
    return cast(str, finish.format_report(report))


def command_texts(runner: FakeRunner) -> list[str]:
    return [" ".join(command) for command in runner.commands]


def test_fast_mode_does_not_run_pytest() -> None:
    runner = FakeRunner()

    output = render("fast", runner)

    assert "pytest: skip" in output
    assert not any(" -m pytest" in command for command in command_texts(runner))


def test_fast_mode_does_not_run_quote_smoke_by_default() -> None:
    runner = FakeRunner()

    output = render("fast", runner)

    assert "quote smoke:" not in output
    assert not any(
        "smoke_checked_quote_launcher.ps1" in command
        for command in command_texts(runner)
    )


def test_full_mode_runs_pytest() -> None:
    runner = FakeRunner()

    output = render("full", runner)

    assert "pytest: pass" in output
    assert any(" -m pytest" in command for command in command_texts(runner))


def test_full_mode_does_not_run_quote_smoke_by_default() -> None:
    runner = FakeRunner()

    output = render("full", runner)

    assert "quote smoke:" not in output
    assert not any(
        "smoke_checked_quote_launcher.ps1" in command
        for command in command_texts(runner)
    )


def test_include_quote_smoke_invokes_smoke_helper() -> None:
    runner = FakeRunner()

    render("fast", runner, include_quote_smoke=True)

    assert any(
        "smoke_checked_quote_launcher.ps1" in command
        for command in command_texts(runner)
    )


def test_quote_smoke_pass_is_reported_and_output_is_preserved() -> None:
    smoke_output = "\n".join(
        [
            "CHECKED_QUOTE_SMOKE_REPORT_START",
            "Synthetic smoke details",
            "Result:",
            "PASS",
            "CHECKED_QUOTE_SMOKE_REPORT_END",
        ]
    )
    runner = FakeRunner(smoke_stdout=smoke_output, smoke_returncode=0)

    output = render("fast", runner, include_quote_smoke=True)

    assert output.startswith("CHECKED_QUOTE_SMOKE_REPORT_START")
    assert "Synthetic smoke details" in output
    assert "quote smoke: pass" in output
    assert "Failures:\nnone" in output


def test_quote_smoke_nonzero_exit_is_reported_as_failure() -> None:
    runner = FakeRunner(smoke_returncode=1)

    output = render("fast", runner, include_quote_smoke=True)

    assert "quote smoke: fail" in output
    assert "quote smoke failed:" in output


def test_quote_smoke_missing_marker_is_reported_as_failure() -> None:
    runner = FakeRunner(smoke_stdout="Result:\nPASS\n", smoke_returncode=0)

    output = render("fast", runner, include_quote_smoke=True)

    assert "quote smoke: fail" in output
    assert "quote smoke failed:" in output


def test_quote_smoke_missing_pass_result_is_reported_as_failure() -> None:
    runner = FakeRunner(
        smoke_stdout="\n".join(
            [
                "CHECKED_QUOTE_SMOKE_REPORT_START",
                "Result:",
                "FAIL",
                "CHECKED_QUOTE_SMOKE_REPORT_END",
            ]
        ),
        smoke_returncode=0,
    )

    output = render("fast", runner, include_quote_smoke=True)

    assert "quote smoke: fail" in output
    assert "quote smoke failed:" in output


def test_all_checks_pass_exit_code_zero_and_report_says_pass() -> None:
    report = finish.run_checks("fast", runner=FakeRunner())
    output = finish.format_report(report)

    assert finish.report_exit_code(report) == 0
    assert "mypy: pass" in output
    assert "repo handoff: pass" in output
    assert "Failures:\nnone" in output


def test_one_check_fails_exit_code_one_and_short_excerpt() -> None:
    report = finish.run_checks(
        "fast",
        runner=FakeRunner(fail_command_part="-m mypy", noisy_failure=True),
    )
    output = finish.format_report(report)

    assert finish.report_exit_code(report) == 1
    assert "mypy: fail" in output
    assert "mypy failed:" in output
    assert "line 21" in output
    assert "line 60" in output
    assert "line 1" not in output


def test_report_contains_finish_markers() -> None:
    output = render("fast", FakeRunner())

    assert output.startswith("CODEX_FINISH_REPORT_START")
    assert output.endswith("CODEX_FINISH_REPORT_END")


def test_report_includes_nested_handoff_when_handoff_succeeds() -> None:
    output = render("fast", FakeRunner())

    assert "CHATGPT_HANDOFF_START" in output
    assert "CHATGPT_HANDOFF_END" in output
    assert "GitHub Actions:\nhttps://github.example/actions/1" in output


def test_handoff_failure_is_reported_as_failure() -> None:
    report = finish.run_checks("fast", runner=FakeRunner(handoff_returncode=1))
    output = finish.format_report(report)

    assert finish.report_exit_code(report) == 1
    assert "repo handoff: fail" in output
    assert "handoff failed" in output


def test_output_does_not_include_file_contents_or_generated_client_data() -> None:
    output = render("fast", FakeRunner())

    assert "Наименование | Ед. изм. | Количество" not in output
    assert "1000;1000;120" not in output
    assert "client bank details" not in output


def test_invalid_mode_fails_cleanly(capsys: Any) -> None:
    exit_code = finish.main(["--mode", "slow"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "invalid mode" in captured.err
