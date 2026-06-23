"""Build a read-only repository handoff/status packet."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]
STANDARD_WINDOWS_GH = r"C:\Program Files\GitHub CLI\gh.exe"
GH_RUN_JSON_FIELDS = (
    "databaseId,headSha,status,conclusion,url,workflowName,displayTitle"
)
QUOTE_WORKFLOW_LINES = (
    "Quote workflow:",
    "canonical launcher:",
    "scripts/make_quote_capacity100_checked.ps1",
    "",
    "operator run card:",
    "docs/invoice_quote_filler_v0_2_1_operator_run_card.md",
    "",
    "canonical smoke:",
    "scripts/smoke_checked_quote_launcher.ps1",
    "",
    "manual stop:",
    "manual Igor check and Human Approval required before sending to client",
    "",
    "draft status:",
    "generated .xlsx is internal draft only",
)


@dataclass(frozen=True)
class CiInfo:
    status: str
    actions: str
    note: str | None = None


@dataclass(frozen=True)
class RepoHandoff:
    repo: str
    branch: str
    head: str
    git_status: str
    changed_files: tuple[str, ...]
    remote: str
    ci: str
    actions: str
    notes: tuple[str, ...]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a read-only Markdown handoff packet for ChatGPT."
    )
    parser.add_argument(
        "--no-ci",
        action="store_true",
        help="Skip optional GitHub Actions lookup through gh.",
    )
    return parser.parse_args(argv)


def run_command(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        capture_output=True,
        text=True,
        check=False,
        shell=False,
    )


def require_success(
    command: Sequence[str],
    runner: CommandRunner,
) -> subprocess.CompletedProcess[str]:
    result = runner(command)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        detail = f": {stderr}" if stderr else ""
        raise RuntimeError(f"command failed: {' '.join(command)}{detail}")
    return result


def stdout_line(result: subprocess.CompletedProcess[str], fallback: str) -> str:
    value = result.stdout.strip()
    return value if value else fallback


def optional_upstream(runner: CommandRunner) -> str:
    result = runner(
        ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]
    )
    if result.returncode != 0:
        return "not configured"
    return stdout_line(result, "not configured")


def changed_files_from_status(status_stdout: str) -> tuple[str, ...]:
    return tuple(line for line in status_stdout.splitlines() if line.strip())


def ci_status_from_run(run: dict[str, Any]) -> str:
    status = str(run.get("status") or "").casefold()
    conclusion = str(run.get("conclusion") or "").casefold()
    if status in {"queued", "in_progress", "waiting", "requested"}:
        return "in_progress"
    if conclusion == "success":
        return "success"
    if conclusion in {
        "action_required",
        "cancelled",
        "failure",
        "startup_failure",
        "timed_out",
    }:
        return "failure"
    return "unknown"


def lookup_ci(
    head: str,
    head_sha: str,
    runner: CommandRunner,
    skip_ci: bool,
) -> CiInfo:
    if skip_ci:
        return CiInfo(
            status="unknown",
            actions="not available",
            note="CI lookup skipped by --no-ci.",
        )

    result: subprocess.CompletedProcess[str] | None = None
    for gh_command in ("gh", STANDARD_WINDOWS_GH):
        try:
            result = runner(
                [
                    gh_command,
                    "run",
                    "list",
                    "--commit",
                    head_sha,
                    "--limit",
                    "1",
                    "--json",
                    GH_RUN_JSON_FIELDS,
                ]
            )
        except FileNotFoundError:
            continue
        break

    if result is None:
        return CiInfo(
            status="unknown",
            actions="not available",
            note="GitHub CLI gh not found.",
        )

    if result.returncode != 0:
        return CiInfo(
            status="unknown",
            actions="not available",
            note="GitHub Actions lookup unavailable.",
        )

    try:
        runs = json.loads(result.stdout)
    except json.JSONDecodeError:
        return CiInfo(
            status="unknown",
            actions="not available",
            note="GitHub Actions response was not valid JSON.",
        )

    if not isinstance(runs, list) or not runs:
        return CiInfo(
            status="unknown",
            actions="not available",
            note="No GitHub Actions run found for HEAD.",
        )

    first_run = runs[0]
    if not isinstance(first_run, dict):
        return CiInfo(
            status="unknown",
            actions="not available",
            note="GitHub Actions response had unexpected shape.",
        )

    url = first_run.get("url")
    return CiInfo(
        status=ci_status_from_run(first_run),
        actions=str(url) if url else "not available",
    )


def build_handoff(
    runner: CommandRunner = run_command,
    skip_ci: bool = False,
) -> RepoHandoff:
    repo_result = require_success(["git", "rev-parse", "--show-toplevel"], runner)
    branch_result = require_success(["git", "branch", "--show-current"], runner)
    head_result = require_success(["git", "log", "-1", "--oneline"], runner)
    head_sha_result = require_success(["git", "rev-parse", "HEAD"], runner)
    status_result = require_success(
        ["git", "status", "--short", "--untracked-files=all"],
        runner,
    )

    repo = stdout_line(repo_result, str(Path.cwd()))
    branch = stdout_line(branch_result, "unknown")
    head = stdout_line(head_result, "unknown")
    head_sha = stdout_line(head_sha_result, head.split(" ", 1)[0])
    changed_files = changed_files_from_status(status_result.stdout)
    git_status = "dirty" if changed_files else "clean"
    remote = optional_upstream(runner)
    ci = lookup_ci(head, head_sha, runner, skip_ci)
    notes = tuple(note for note in (ci.note,) if note)

    return RepoHandoff(
        repo=repo,
        branch=branch,
        head=head,
        git_status=git_status,
        changed_files=changed_files,
        remote=remote,
        ci=ci.status,
        actions=ci.actions,
        notes=notes,
    )


def format_lines(title: str, values: Sequence[str]) -> list[str]:
    lines = [f"{title}:"]
    if values:
        lines.extend(values)
    else:
        lines.append("none")
    return lines


def format_handoff(packet: RepoHandoff) -> str:
    lines = [
        "CHATGPT_HANDOFF_START",
        "",
        "Repo:",
        packet.repo,
        "",
        "Branch:",
        packet.branch,
        "",
        "HEAD:",
        packet.head,
        "",
        "Git status:",
        packet.git_status,
        "",
    ]
    lines.extend(format_lines("Changed files", packet.changed_files))
    lines.extend(
        [
            "",
            "Remote:",
            packet.remote,
            "",
            "CI:",
            packet.ci,
            "",
            "GitHub Actions:",
            packet.actions,
            "",
        ]
    )
    lines.extend(QUOTE_WORKFLOW_LINES)
    lines.append("")
    lines.extend(format_lines("Notes", packet.notes))
    lines.extend(["", "CHATGPT_HANDOFF_END"])
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        packet = build_handoff(skip_ci=args.no_ci)
    except RuntimeError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(format_handoff(packet))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
