"""Read-only handoff from a pinned WU13 review package to versioned PDF intake.

Supply a separate working Case with the exact base review files and an already
reviewed governed intake. Its client_request.source_locator binds the package
as <absolute operator-package.json path>#sha256=<pinned package SHA-256>.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import TypedDict

import build_confirmed_composition_from_preliminary_bundle as composition
from extract_mixed_source_composition_case import MANIFEST_NAME
from governed_case_intake import load_governed_intake
from governed_telegram_intake import (
    PROJECT_ROOT,
    TelegramHold,
    encode,
    operator_package,
    parse_event,
    safe_path,
    sha,
    verify_case,
    verify_files,
)
from wu13_employee_telegram import Config, authorized, load


class VersionedArguments(TypedDict):
    case_id: str
    project_pdf: Path
    extraction_version: str
    intake_json: Path
    canonical_root: Path


def preflight(
    *,
    profile: Path,
    package_path: Path,
    package_sha256: str,
    canonical_root: Path,
    intake_json: Path,
    intake_sha256: str,
    extraction_version: str,
) -> VersionedArguments:
    """Return existing extractor arguments. Both pins come from the caller."""
    try:
        config = Config.read(profile)
        for path in (package_path, canonical_root, intake_json):
            safe_path(path.absolute())
        package_path = package_path.resolve(strict=True)
        folder = package_path.parent
        if (
            package_path.name != "operator-package.json"
            or folder.parent != config.receipts
        ):
            raise TelegramHold("operator package is outside the WU13 receipt root")

        def read(path: Path) -> bytes:
            safe_path(path)
            if not path.is_file():
                raise TelegramHold("missing or unsafe preflight input")
            return path.read_bytes()

        package_raw = read(package_path)
        if sha(package_raw) != package_sha256:
            raise TelegramHold("operator package SHA-256 mismatch")
        package = load(package_raw)
        pdf = folder / "source.pdf"
        raw, body = read(folder / "update.json"), read(pdf)
        case_id, receipt, files = parse_event(raw, body, sha(body), config.policy)
        if (
            folder.name != case_id
            or not authorized(load(raw), config)
            or receipt["document"]["file"] != pdf.name
        ):
            raise TelegramHold("WU13 PDF or employee identity mismatch")
        receipt_raw = encode(receipt)
        review = config.cases / case_id
        hashes = package["review_files"]
        expected_package = operator_package(case_id, receipt_raw, review, hashes)
        if package_raw != encode(expected_package):
            raise TelegramHold("operator package provenance mismatch")
        receipt_files = {
            **files,
            "receipt.json": receipt_raw,
            "operator-package.json": package_raw,
        }
        verify_files(folder, receipt_files)
        verify_case(review, hashes)
        paths = composition.resolve_case_paths(case_id, canonical_root=config.cases)
        snapshot = composition.load_snapshot(paths)
        sources = load(snapshot.manifest_bytes)["sources"]
        if (
            snapshot.hashes != hashes
            or len(sources) != 1
            or sources[0]["source_type"] != "pdf"
            or sources[0]["file_name"] != pdf.name
            or sources[0]["sha256"] != receipt["document"]["sha256"]
        ):
            raise TelegramHold("review bundle does not identify the received PDF")

        canonical_root = canonical_root.resolve(strict=True)
        intake_json = intake_json.resolve(strict=True)
        working_case = canonical_root / case_id
        safe_path(working_case)
        if any(
            working_case.is_relative_to(root)
            or root.is_relative_to(working_case)
            or intake_json.is_relative_to(root)
            for root in (config.receipts, config.cases, PROJECT_ROOT)
        ):
            raise TelegramHold("governed intake requires a separate root outside Git")
        paths = composition.resolve_case_paths(
            case_id,
            canonical_root=canonical_root,
            extraction_version=extraction_version,
        )
        if os.path.lexists(paths.manifest.parent):
            raise TelegramHold("versioned extraction already exists")
        verify_case(paths.case_dir, hashes)
        safe_path(intake_json)
        if not intake_json.is_file():
            raise TelegramHold("governed intake must be an existing file")
        intake = load_governed_intake(
            intake_json,
            case_id=case_id,
            version=extraction_version,
            project_pdf=pdf,
            base_manifest=paths.case_dir / MANIFEST_NAME,
        )
        request = load(intake.raw)["client_request"]
        if (
            intake.sha256 != intake_sha256
            or intake.project_pdf_sha256 != receipt["document"]["sha256"]
            or intake.base_manifest_sha256 != hashes[MANIFEST_NAME]
            or request["source_locator"] != f"{package_path}#sha256={package_sha256}"
        ):
            raise TelegramHold("governed intake does not bind the WU13 package")
        config.unchanged()
        verify_files(folder, receipt_files)
        verify_case(review, hashes)
        verify_case(paths.case_dir, hashes)
        if read(intake_json) != intake.raw or os.path.lexists(paths.manifest.parent):
            raise TelegramHold("governed input or output drifted during preflight")
    except TelegramHold:
        raise
    except (
        composition.WorkflowError,
        OSError,
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        RecursionError,
    ) as err:
        raise TelegramHold("malformed or unavailable governed intake evidence") from err
    return {
        "case_id": case_id,
        "project_pdf": pdf,
        "extraction_version": extraction_version,
        "intake_json": intake_json,
        "canonical_root": canonical_root,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("profile", "package-path", "canonical-root", "intake-json"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    for name in ("package-sha256", "intake-sha256", "extraction-version"):
        parser.add_argument(f"--{name}", required=True)
    try:
        arguments = preflight(**vars(parser.parse_args()))
    except TelegramHold as error:
        print(f"HOLD: {error}")
        return 1
    print("REVIEW_REQUIRED: HUMAN_APPROVAL_1 remains required")
    for name, value in arguments.items():
        print(f"{name}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
