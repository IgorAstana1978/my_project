"""Source-only review of text annotations on PDF schematics."""

from __future__ import annotations

import hashlib
import io
import json
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import project_spec_extraction as core
from governed_case_intake import (
    SCHEMATIC_OPEN_GAPS,
    SCHEMATIC_REVIEW_HOLD,
    SCHEMATIC_REVIEW_SCHEMA,
    GovernedIntake,
)
from governed_rotated_extraction import (
    POWER_BOARD_RE,
    POWER_MCB_RE,
    POWER_TITLE_RE,
    exact_specification_identity,
    parse_qf_apparatus,
    read_visible_page,
    requested_specification_header_role,
)
from pypdf import PdfReader

TITLE_RE = re.compile(
    rf"(?:{core.SCHEMATIC_TITLE_RE.pattern}|{POWER_TITLE_RE.pattern})\b\s*[:–—]?",
    re.IGNORECASE,
)
LABEL_RE = re.compile(r"([^()]+?)(?:\s*\(([^()]+)\))?")
ENCLOSURE_RE = re.compile(r"ЩР[нв](?=[- .\d])(?=[^)]*\d)[-\w. ]+", re.IGNORECASE)
FEEDER_RE = re.compile(r"от\s+ВРУ(?:\s+\d+[А-ЯA-Z]?)?", re.IGNORECASE)
CAD_HEADERS = {"position", "description", "type_model", "unit", "quantity"}


def evidence(
    block: core.PdfBlock, file_name: str, page: int, reason: str, confidence: float
) -> core.Provenance:
    coordinates = f"x={block.x:.1f}, y={block.y:.1f}"
    return core.Provenance(
        source_file=file_name,
        source_type="pdf",
        locator=f"page={page}; block={block.number}; {coordinates}",
        raw_text=block.text,
        confidence=confidence,
        reason=reason,
        page=page,
        block_coordinates=coordinates,
    )


def board_label(text: str) -> tuple[str, str | None] | None:
    label = LABEL_RE.fullmatch(text.strip())
    if label is None:
        return None
    designation = label[1].strip()
    if not (
        designation.upper() in {"НЩР", "АВР"}
        or core.SCHEMATIC_BOARD_RE.fullmatch(designation)
        or POWER_BOARD_RE.fullmatch(designation)
    ) or re.search(r"[А-ЯЁA-Z]\s+\d", designation, re.IGNORECASE):
        return None
    enclosure = label[2]
    return designation, (
        enclosure if enclosure and ENCLOSURE_RE.fullmatch(enclosure) else None
    )


def follows_line(anchor: core.PdfBlock, block: core.PdfBlock, dx: float) -> bool:
    return (
        block.x > 0 and abs(block.x - anchor.x) <= dx and 0 < anchor.y - block.y <= 24
    )


def apparatus(
    blocks: Sequence[core.PdfBlock],
    index: int,
    file_name: str,
    page: int,
    confidence: float,
) -> core.ComponentCandidate | None:
    anchor = blocks[index]
    parts = [anchor]
    for offset in range(3):
        raw = " ".join(block.text for block in parts)
        if core.QF_APPARATUS_RE.fullmatch(raw) or POWER_MCB_RE.fullmatch(raw):
            parsed = parse_qf_apparatus(raw)
            if (
                parsed["poles"] in {"1P", "2P", "3P", "4P"}
                and parsed["current"]
                and (parsed["current"].endswith(("A", "А")) or parsed["residual"])
            ):
                result = core.qf_component_from_segment(
                    core.QfSegment(core.qf_designation(raw), raw, anchor),
                    file_name,
                    page,
                    confidence,
                )
                if result.model is None:
                    result = replace(
                        result,
                        model=parsed["model"],
                        rating=parsed["rating"],
                        label=raw,
                        note=(
                            f"qf_designation={core.qf_designation(raw)}; "
                            f"poles={parsed['poles']}; current={parsed['current']}"
                        ),
                        red_flags=["schematic QF requires Igor review"],
                    )
                result.provenance = [
                    evidence(
                        part, file_name, page, "explicit QF annotation", confidence
                    )
                    for part in parts
                ]
                return result
        following = index + offset + 1
        if following >= len(blocks) or not follows_line(
            parts[-1], blocks[following], 4
        ):
            break
        parts.append(blocks[following])
    return None


def read_schematic(
    file_name: str,
    page: dict[str, Any],
    blocks: Sequence[core.PdfBlock],
    gaps: list[str],
) -> tuple[core.BoardCandidate, tuple[str, core.Provenance] | None] | None:
    number = page["page"]
    confidence = 0.82 if page["status"] == "text_available" else 0.45
    titles = [
        (i, heading)
        for i, block in enumerate(blocks)
        if (heading := TITLE_RE.match(block.text))
    ]
    anchors = [
        (i, f"QF{match['number']}")
        for i, block in enumerate(blocks)
        for match in core.QF_ANCHOR_RE.finditer(block.text)
    ]
    page.update(
        qf_tokens_detected=len(anchors),
        qf_components_extracted=0,
        qf_unresolved_count=len(anchors),
    )
    if len(titles) != 1:
        if titles or anchors:
            gaps.append(
                f"GAP page={number}: missing or ambiguous schematic board title"
            )
        return None

    index, heading = titles[0]
    title = label_block = blocks[index]
    suffix = title.text[heading.end() :].strip()
    if (
        not suffix
        and index + 1 < len(blocks)
        and follows_line(title, blocks[index + 1], 110)
    ):
        label_block = blocks[index + 1]
        suffix = label_block.text
    label = board_label(suffix) if title.x > 0 and title.y > 0 else None
    if label is None:
        gaps.append(
            f"GAP page={number}; block={title.number}: unknown board designation"
        )
        return None
    designation, enclosure = label
    provenance = [evidence(title, file_name, number, "schematic title", confidence)]
    if label_block != title:
        provenance.append(
            evidence(label_block, file_name, number, "board label", confidence)
        )
    board = core.BoardCandidate(
        designation,
        exact_specification_identity(designation),
        designation,
        None,
        provenance,
        confidence,
        source_types={"pdf"},
    )
    counts = Counter(name for _, name in anchors)
    by_block = Counter(i for i, _ in anchors)
    for anchor, name in anchors:
        block = blocks[anchor]
        component = None
        if counts[name] == by_block[anchor] == 1 and block.x > 0 and block.y > 0:
            component = apparatus(blocks, anchor, file_name, number, confidence)
        if component is None:
            board.red_flags.append(
                f"GAP page={number}; block={block.number}: {name} unresolved "
                "(duplicate identity, uncertain locator or incomplete annotation)"
            )
        else:
            board.components.append(component)

    # Preserve literal conductor and feeder annotations near the unique inlet.
    # Geometry here locates labels only. It cannot establish netlist or terminals.
    inlets = [blocks[i] for i, name in anchors if name == "QF0"]
    if len(inlets) == 1:
        inlet = inlets[0]
        labels = [
            block
            for block in blocks
            if block.x > 0
            and abs(block.x - inlet.x) <= 50
            and (
                (block.text in {"L1,L2,L3", "N", "PE"} and 0 < inlet.y - block.y <= 110)
                or (FEEDER_RE.fullmatch(block.text) and 0 < block.y - inlet.y <= 70)
            )
        ]
        for block in labels:
            board.provenance.append(
                evidence(
                    block,
                    file_name,
                    number,
                    "literal inlet annotation",
                    confidence,
                )
            )
    page.update(
        qf_components_extracted=len(board.components),
        qf_unresolved_count=len(anchors) - len(board.components),
    )
    cabinet = (
        (
            enclosure,
            evidence(label_block, file_name, number, "enclosure label", confidence),
        )
        if enclosure
        else None
    )
    return board, cabinet


def build_schematic_review_artifacts(
    project_pdf: Path,
    intake: GovernedIntake,
) -> core.ExtractionArtifacts:
    pdf_raw = project_pdf.read_bytes()
    if hashlib.sha256(pdf_raw).hexdigest() != intake.project_pdf_sha256:
        raise core.ExtractionError("schematic review PDF SHA-256 changed")
    base = core.build_artifacts(project_pdf, None)
    manifest = json.loads(base.manifest_text)
    source = manifest["sources"][0]
    if source["sha256"] != intake.project_pdf_sha256 or source["status"] != "processed":
        raise core.ExtractionError(
            "schematic review PDF is unavailable or its SHA changed"
        )
    gaps = list(SCHEMATIC_OPEN_GAPS)
    candidates = []
    reader = PdfReader(io.BytesIO(pdf_raw), strict=False)
    for page, pdf_page in zip(source["pages"], reader.pages, strict=True):
        if page["status"] not in {"text_available", "low_text_confidence"}:
            gaps.append(f"GAP page={page['page']}: {page['status']}")
            continue
        _, blocks = read_visible_page(pdf_page)
        if CAD_HEADERS <= {requested_specification_header_role(b.text) for b in blocks}:
            raise core.ExtractionError(
                "schematic review cannot bypass a CAD specification"
            )
        candidate = read_schematic(project_pdf.name, page, blocks, gaps)
        if candidate is not None:
            candidates.append((page, *candidate))

    occurrences = Counter(board.normalized for _, board, _ in candidates)
    boards = []
    items = []
    for page, board, cabinet in candidates:
        if occurrences[board.normalized] > 1:
            page.update(
                qf_components_extracted=0,
                qf_unresolved_count=page["qf_tokens_detected"],
            )
            gaps.append(
                f"GAP page={page['page']}: duplicate board identity {board.normalized}"
            )
            continue
        boards.append(board)
        item = core.board_to_draft(board, f"ITEM-{len(boards):03d}")
        if cabinet is not None:
            label, record = cabinet
            item["cabinet_guess"].update(
                label_guess=label,
                confidence=record.confidence,
                evidence=[f"pdf: {record.locator}: {record.raw_text}"],
            )
        items.append(item)

    manifest.update(
        case_id=intake.case_id,
        governed_intake_sha256=intake.sha256,
        review_mode=SCHEMATIC_REVIEW_SCHEMA,
        review_status=SCHEMATIC_REVIEW_HOLD,
        scope_classification=[],
    )
    manifest_text = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    )
    digest = hashlib.sha256(manifest_text.encode("utf-8")).hexdigest()
    draft = base.draft
    draft.update(
        draft_id=f"PRELIM-MIXED-{digest[:12].upper()}",
        items=items,
        red_flags=gaps,
        overall_confidence=min((b.confidence for b in boards), default=0.0),
        next_required_human_actions=["Resolve source gaps before HUMAN_APPROVAL_1."],
    )
    draft["source"].update(
        raw_input_sha256=digest,
        source_files=manifest["sources"],
        source_summary="Governed schematic-only PDF review.",
    )
    summary = draft["extraction_summary"]
    for key in ("qf_tokens_detected", "qf_components_extracted", "qf_unresolved_count"):
        summary[key] = sum(page.get(key, 0) for page in source["pages"])
    summary.update(
        switchboards_pdf=len(boards),
        conflicts_found=0,
        composition_rows_extracted=summary["qf_components_extracted"],
        review_rows=len(gaps) + len(boards) + summary["pdf_pages_manual_review"],
        ready_for_preliminary_workflow=False,
    )
    return core.ExtractionArtifacts(manifest_text, draft, summary, tuple(boards))
