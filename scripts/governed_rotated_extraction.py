"""Preliminary requested-supply extraction from rotated CAD PDF tables."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from governed_case_intake import GovernedIntake
from project_spec_extraction import (
    DASH_RE,
    BoardCandidate,
    ExtractionArtifacts,
    ExtractionError,
    PdfBlock,
    Provenance,
    board_to_draft,
    build_artifacts,
    compact_text,
    normalize_header,
)
from pypdf import PdfReader


@dataclass(frozen=True)
class RequestedSpecificationResult:
    attempted: bool
    gated: bool
    boards: tuple[BoardCandidate, ...] = ()
    rows: tuple[dict[str, Any], ...] = ()
    diagnostics: tuple[str, ...] = ()


def exact_specification_identity(value: str) -> str:
    text = DASH_RE.sub("-", compact_text(value).upper().replace("Ё", "Е"))
    return re.sub(r"\s*([./-])\s*", r"\1", text)


def requested_specification_header_role(value: str) -> str | None:
    normalized = normalize_header(value)
    if normalized in {"позиция", "поз"}:
        return "position"
    if normalized.startswith("наименование и техническая характеристика"):
        return "description"
    if normalized.startswith("тип марка обозначение"):
        return "type_model"
    if normalized in {"ед измерения", "единица измерения", "unit"}:
        return "unit"
    if normalized in {"количество", "qty", "quantity"}:
        return "quantity"
    return None


def extract_requested_specification_page(
    file_name: str,
    page_number: int,
    blocks: Sequence[PdfBlock],
    requested_supply: Sequence[tuple[str, int]],
    excluded_components: Sequence[tuple[str, int]],
) -> RequestedSpecificationResult:
    """Read stable CAD table rows; never infer membership from the PDF alone."""
    roles: dict[str, PdfBlock] = {}
    for block in blocks:
        role = requested_specification_header_role(block.text)
        if role and block.x > 0 and block.y > 0:
            roles[role] = block
    required = ("position", "description", "type_model", "unit", "quantity")
    if any(role not in roles for role in required):
        return RequestedSpecificationResult(False, False)
    headers = [roles[role] for role in required]
    if not all(a.x < b.x for a, b in zip(headers, headers[1:], strict=False)) or (
        max(block.y for block in headers) - min(block.y for block in headers) > 25
    ):
        return RequestedSpecificationResult(
            True, False, diagnostics=("CAD specification header geometry is ambiguous",)
        )
    position_x, description_x, model_x, unit_x, quantity_x = (
        block.x for block in headers
    )
    header_y = max(block.y for block in headers)
    quantity_blocks = [
        block
        for block in blocks
        if block.y < header_y - 20
        and abs(block.x - quantity_x) <= max(30, (quantity_x - unit_x) * 0.5)
        and re.fullmatch(r"\d+", block.text)
    ]
    row_centers: list[float] = []
    for block in sorted(quantity_blocks, key=lambda value: -value.y):
        if not any(abs(block.y - center) <= 5 for center in row_centers):
            row_centers.append(block.y)
    if not row_centers:
        return RequestedSpecificationResult(
            True, False, diagnostics=("CAD specification has no stable quantity rows",)
        )

    requested = {
        exact_specification_identity(name): (name, quantity)
        for name, quantity in requested_supply
    }
    excluded = {
        exact_specification_identity(name): (name, quantity)
        for name, quantity in excluded_components
    }
    seen_requested: set[str] = set()
    seen_excluded: set[str] = set()
    boards: list[BoardCandidate] = []
    classified: list[dict[str, Any]] = []
    diagnostics: list[str] = []
    for center in row_centers:
        row = sorted(
            (block for block in blocks if abs(block.y - center) <= 5),
            key=lambda block: block.number,
        )
        quantities = [block for block in row if block in quantity_blocks]
        units = [
            block
            for block in row
            if (
                block.x < 0
                or abs(block.x - unit_x) <= max(25, (quantity_x - unit_x) * 0.4)
            )
            and normalize_header(block.text)
            in {"компл", "комплект", "шт", "м", "pcs", "set"}
        ]
        if len(quantities) != 1 or len(units) != 1:
            diagnostics.append(
                f"PDF page {page_number} row y={center:.1f} has ambiguous unit/quantity"
            )
            continue
        quantity = int(quantities[0].text)
        if quantity <= 0:
            diagnostics.append(
                f"PDF page {page_number} row y={center:.1f} has invalid quantity"
            )
            continue
        row_text = " | ".join(block.text for block in row)
        identities = {
            exact_specification_identity(block.text)
            for block in row
            if block.x < description_x or block.x < unit_x and block.x >= model_x - 40
        }
        requested_hits = [key for key in requested if key in identities]
        excluded_hits = [
            key for key in excluded if key in exact_specification_identity(row_text)
        ]
        if len(requested_hits) + len(excluded_hits) > 1:
            diagnostics.append(
                f"PDF page {page_number} row y={center:.1f} "
                "has ambiguous scope identity"
            )
            continue
        classification = "project_context"
        designation = ""
        if requested_hits:
            key = requested_hits[0]
            designation, expected_quantity = requested[key]
            classification = "requested_supply"
            if key in seen_requested or quantity != expected_quantity:
                diagnostics.append(
                    f"PDF page {page_number} {designation} "
                    "quantity/identity mismatch"
                )
                continue
            seen_requested.add(key)
            locator = f"page={page_number}; CAD specification row y={center:.1f}"
            provenance = Provenance(
                source_file=file_name,
                source_type="pdf",
                locator=locator,
                raw_text=row_text,
                confidence=0.82,
                reason=(
                    "rotated CAD specification row and governed "
                    "requested-supply match"
                ),
                page=page_number,
                block_coordinates=f"y={center:.1f}",
            )
            boards.append(
                BoardCandidate(
                    designation=designation,
                    normalized=exact_specification_identity(designation),
                    title=designation,
                    quantity=quantity,
                    provenance=[provenance],
                    confidence=0.82,
                    red_flags=[
                        "technical component composition requires source-backed review"
                    ],
                    source_types={"pdf"},
                )
            )
        elif excluded_hits:
            key = excluded_hits[0]
            designation, expected_quantity = excluded[key]
            classification = "excluded_component"
            if key in seen_excluded or quantity != expected_quantity:
                diagnostics.append(
                    f"PDF page {page_number} {designation} exclusion mismatch"
                )
                continue
            seen_excluded.add(key)
        classified.append(
            {
                "page": page_number,
                "row_y": round(center, 1),
                "classification": classification,
                "designation": designation,
                "quantity": quantity,
                "source_text": row_text,
            }
        )
    if seen_requested != set(requested):
        diagnostics.append("requested supply is not fully matched to exact CAD rows")
    if seen_excluded != set(excluded):
        diagnostics.append(
            "excluded components are not fully matched to exact CAD rows"
        )
    return RequestedSpecificationResult(
        attempted=True,
        gated=not diagnostics,
        boards=tuple(boards) if not diagnostics else (),
        rows=tuple(classified),
        diagnostics=tuple(diagnostics),
    )


def page_space_coordinates(
    tm: Sequence[float],
    cm: Sequence[float],
    *,
    rotation: int,
    width: float,
    height: float,
) -> tuple[float, float]:
    """Map PDF text through the CTM and page rotation into visible page space."""
    x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
    y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
    if rotation == 90:
        x, y = y, width - x
    elif rotation == 180:
        x, y = width - x, height - y
    elif rotation == 270:
        x, y = height - y, x
    elif rotation != 0:
        raise ExtractionError("unsupported PDF page rotation")
    return round(x, 2), round(y, 2)


def collect_visible_pdf_block(
    blocks: list[tuple[str, float, float]],
    text: str,
    cm: Sequence[float],
    tm: Sequence[float],
    _font: Mapping[str, Any] | None,
    _font_size: float,
    *,
    rotation: int,
    width: float,
    height: float,
) -> None:
    if not compact_text(text):
        return
    if tm[4] == tm[5] == cm[4] == cm[5] == 0:
        blocks.append((text, 0.0, 0.0))
        return
    x, y = page_space_coordinates(tm, cm, rotation=rotation, width=width, height=height)
    blocks.append((text, x, y))


def visible_pdf_blocks(
    raw_blocks: Sequence[tuple[str, float, float]],
) -> list[PdfBlock]:
    result: list[PdfBlock] = []
    last_y = 0.0
    for number, (text, x, y) in enumerate(raw_blocks, start=1):
        value = compact_text(text)
        if not value:
            continue
        if x == y == 0 and last_y:
            # pypdf sometimes emits a continuation without a text matrix.
            # It can identify the same row, never a price or a column position.
            result.append(PdfBlock(value, -1.0, last_y, number))
        else:
            result.append(PdfBlock(value, x, y, number))
            if x > 0 and y > 0:
                last_y = y
    return result


def build_governed_rotated_artifacts(
    project_pdf: Path,
    intake: GovernedIntake,
) -> ExtractionArtifacts:
    """Select source-backed request rows without changing the frozen policy owner."""
    base = build_artifacts(project_pdf, None)
    reader = PdfReader(str(project_pdf), strict=False)
    boards_by_identity: dict[str, BoardCandidate] = {}
    classified_rows: list[dict[str, Any]] = []
    attempted = False
    for page_number, page in enumerate(reader.pages, start=1):
        if page.rotation not in {90, 270}:
            continue
        raw_blocks: list[tuple[str, float, float]] = []

        def capture(
            text: str,
            cm: Sequence[float],
            tm: Sequence[float],
            font: Mapping[str, Any] | None,
            font_size: float,
            current_blocks: list[tuple[str, float, float]] = raw_blocks,
            current_page: Any = page,
        ) -> None:
            collect_visible_pdf_block(
                current_blocks,
                text,
                cm,
                tm,
                font,
                font_size,
                rotation=current_page.rotation,
                width=float(current_page.mediabox.width),
                height=float(current_page.mediabox.height),
            )

        page.extract_text(visitor_text=capture)
        result = extract_requested_specification_page(
            project_pdf.name,
            page_number,
            visible_pdf_blocks(raw_blocks),
            intake.requested_supply,
            intake.excluded_components,
        )
        if not result.attempted:
            continue
        attempted = True
        if not result.gated:
            raise ExtractionError(
                "rotated CAD specification is ambiguous: "
                + "; ".join(result.diagnostics)
            )
        classified_rows.extend(result.rows)
        for board in result.boards:
            key = exact_specification_identity(board.designation)
            if key in boards_by_identity:
                raise ExtractionError(
                    "requested board occurs in multiple CAD specification rows"
                )
            boards_by_identity[key] = board
    if not attempted:
        raise ExtractionError("no rotated CAD specification table matched the intake")
    wanted = [exact_specification_identity(name) for name, _ in intake.requested_supply]
    if set(boards_by_identity) != set(wanted):
        raise ExtractionError(
            "requested supply is not fully evidenced by CAD specification"
        )
    boards = [boards_by_identity[key] for key in wanted]

    manifest = json.loads(base.manifest_text)
    manifest["governed_intake_sha256"] = intake.sha256
    manifest["scope_classification"] = classified_rows
    manifest_text = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    )
    manifest_sha = hashlib.sha256(manifest_text.encode("utf-8")).hexdigest()
    draft = copy.deepcopy(base.draft)
    draft["draft_id"] = f"PRELIM-MIXED-{manifest_sha[:12].upper()}"
    draft["created_at"] = datetime.now(UTC).isoformat()
    draft["source"]["raw_input_sha256"] = manifest_sha
    draft["source"]["source_summary"] = "Governed rotated CAD PDF extraction bundle."
    draft["items"] = [
        board_to_draft(board, f"ITEM-{index:03d}")
        for index, board in enumerate(boards, start=1)
    ]
    draft["overall_confidence"] = min(board.confidence for board in boards)
    draft["red_flags"] = list(
        dict.fromkeys(
            [
                *draft["red_flags"],
                "governed intake decisions require Igor technical composition review",
            ]
        )
    )
    summary = draft["extraction_summary"]
    summary["switchboards_pdf"] = len(boards)
    summary["composition_rows_extracted"] = 0
    summary["review_rows"] = (
        summary["pdf_pages_manual_review"]
        + len(boards)
        + sum(len(board.red_flags) for board in boards)
    )
    draft["next_required_human_actions"].append(
        "Review governed intake decisions and source-backed technical details "
        "before confirming composition."
    )
    return ExtractionArtifacts(
        manifest_text=manifest_text,
        draft=draft,
        summary=summary,
        boards=tuple(boards),
    )
