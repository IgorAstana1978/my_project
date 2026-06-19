import importlib.util
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType
from typing import Any, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "build_repo_handoff.py"


def load_script_module(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


handoff = cast(
    Any,
    load_script_module("build_repo_handoff_for_test", SCRIPT),
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


class FakeRunner:
    def __init__(
        self,
        status_stdout: str = "",
        upstream_stdout: str = "origin/main\n",
        upstream_returncode: int = 0,
        gh_stdout: str = "",
        gh_returncode: int = 1,
        gh_not_found: bool = False,
        full_path_gh_stdout: str = "",
        full_path_gh_returncode: int = 1,
        full_path_gh_not_found: bool = True,
    ) -> None:
        self.status_stdout = status_stdout
        self.upstream_stdout = upstream_stdout
        self.upstream_returncode = upstream_returncode
        self.gh_stdout = gh_stdout
        self.gh_returncode = gh_returncode
        self.gh_not_found = gh_not_found
        self.full_path_gh_stdout = full_path_gh_stdout
        self.full_path_gh_returncode = full_path_gh_returncode
        self.full_path_gh_not_found = full_path_gh_not_found
        self.commands: list[tuple[str, ...]] = []

    def __call__(
        self,
        command: Sequence[str],
    ) -> subprocess.CompletedProcess[str]:
        command_tuple = tuple(command)
        self.commands.append(command_tuple)
        if command_tuple == ("git", "rev-parse", "--show-toplevel"):
            return completed("C:/repo\n")
        if command_tuple == ("git", "branch", "--show-current"):
            return completed("main\n")
        if command_tuple == ("git", "log", "-1", "--oneline"):
            return completed("abc1234 feat: demo\n")
        if command_tuple == ("git", "rev-parse", "HEAD"):
            return completed("abc1234fullsha\n")
        if command_tuple == ("git", "status", "--short", "--untracked-files=all"):
            return completed(self.status_stdout)
        if command_tuple == (
            "git",
            "rev-parse",
            "--abbrev-ref",
            "--symbolic-full-name",
            "@{u}",
        ):
            return completed(
                self.upstream_stdout,
                returncode=self.upstream_returncode,
            )
        if command_tuple[:3] == ("gh", "run", "list"):
            if self.gh_not_found:
                raise FileNotFoundError("gh")
            return completed(self.gh_stdout, returncode=self.gh_returncode)
        if command_tuple[:3] == (
            handoff.STANDARD_WINDOWS_GH,
            "run",
            "list",
        ):
            if self.full_path_gh_not_found:
                raise FileNotFoundError(handoff.STANDARD_WINDOWS_GH)
            return completed(
                self.full_path_gh_stdout,
                returncode=self.full_path_gh_returncode,
            )
        raise AssertionError(f"unexpected command: {command_tuple}")


def render_with_runner(runner: FakeRunner, skip_ci: bool = False) -> str:
    packet = handoff.build_handoff(runner=runner, skip_ci=skip_ci)
    return cast(str, handoff.format_handoff(packet))


def gh_run(conclusion: str, url: str = "https://github.example/actions/1") -> str:
    return json.dumps(
        [
            {
                "databaseId": 1,
                "headSha": "abc1234",
                "status": "completed",
                "conclusion": conclusion,
                "url": url,
                "workflowName": "CI",
                "displayTitle": "CI",
            }
        ]
    )


def test_clean_repo_status() -> None:
    output = render_with_runner(FakeRunner())

    assert "Git status:\nclean" in output
    assert "Changed files:\nnone" in output


def test_dirty_repo_status_lists_changed_files_without_contents() -> None:
    output = render_with_runner(
        FakeRunner(status_stdout=" M README.md\n?? docs/new.md\n")
    )

    assert "Git status:\ndirty" in output
    assert " M README.md" in output
    assert "?? docs/new.md" in output
    assert "secret file content" not in output


def test_missing_upstream_does_not_fail() -> None:
    output = render_with_runner(FakeRunner(upstream_stdout="", upstream_returncode=1))

    assert "Remote:\nnot configured" in output


def test_missing_gh_reports_unknown_ci() -> None:
    output = render_with_runner(FakeRunner(gh_returncode=1))

    assert "CI:\nunknown" in output
    assert "GitHub Actions:\nnot available" in output


def test_gh_not_found_reports_unknown_ci_with_note() -> None:
    output = render_with_runner(FakeRunner(gh_not_found=True))

    assert "CI:\nunknown" in output
    assert "GitHub Actions:\nnot available" in output
    assert "GitHub CLI gh not found." in output


def test_full_sha_is_used_for_actions_lookup() -> None:
    runner = FakeRunner(gh_stdout=gh_run("success"), gh_returncode=0)

    render_with_runner(runner)

    assert ("git", "rev-parse", "HEAD") in runner.commands
    gh_command = next(
        command for command in runner.commands if command[:3] == ("gh", "run", "list")
    )
    assert gh_command[gh_command.index("--commit") + 1] == "abc1234fullsha"


def test_full_path_gh_is_used_when_plain_gh_is_not_found() -> None:
    output = render_with_runner(
        FakeRunner(
            gh_not_found=True,
            full_path_gh_stdout=gh_run("success"),
            full_path_gh_returncode=0,
            full_path_gh_not_found=False,
        )
    )

    assert "CI:\nsuccess" in output
    assert "GitHub Actions:\nhttps://github.example/actions/1" in output


def test_both_gh_locations_missing_reports_unknown_ci_with_note() -> None:
    output = render_with_runner(
        FakeRunner(gh_not_found=True, full_path_gh_not_found=True)
    )

    assert "CI:\nunknown" in output
    assert "GitHub Actions:\nnot available" in output
    assert "GitHub CLI gh not found." in output


def test_gh_success_reports_success_and_url() -> None:
    output = render_with_runner(
        FakeRunner(gh_stdout=gh_run("success"), gh_returncode=0)
    )

    assert "CI:\nsuccess" in output
    assert "GitHub Actions:\nhttps://github.example/actions/1" in output


def test_gh_failure_reports_failure_and_url() -> None:
    output = render_with_runner(
        FakeRunner(gh_stdout=gh_run("failure"), gh_returncode=0)
    )

    assert "CI:\nfailure" in output
    assert "GitHub Actions:\nhttps://github.example/actions/1" in output


def test_output_contains_handoff_markers() -> None:
    output = render_with_runner(FakeRunner())

    assert output.startswith("CHATGPT_HANDOFF_START")
    assert output.endswith("CHATGPT_HANDOFF_END")


def test_output_does_not_include_file_contents() -> None:
    output = render_with_runner(
        FakeRunner(status_stdout=" M docs/status.md\n?? scripts/helper.py\n")
    )

    assert "docs/status.md" in output
    assert "scripts/helper.py" in output
    assert "Наименование | Ед. изм. | Количество" not in output
    assert "1000;1000;120" not in output


def test_no_ci_skips_gh_command() -> None:
    runner = FakeRunner()
    output = render_with_runner(runner, skip_ci=True)

    assert "CI:\nunknown" in output
    assert "GitHub Actions:\nnot available" in output
    assert all(command[:1] != ("gh",) for command in runner.commands)
