"""Preliminary requested-supply extraction from rotated CAD PDF tables."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import project_spec_extraction as core
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

POWER_TITLE_RE = re.compile(
    r"принципиальн\w*\s+схем\w*\s+силов\w*\s+щит\w*", re.IGNORECASE
)
POWER_BOARD_RE = re.compile(r"ЩС\s*-?\s*\d+(?:[./-]\d+)*", re.IGNORECASE)
POWER_MCB_RE = re.compile(
    r"^QF\s*\d+\s*(?P<model>ВА47-?29)\s*(?P<poles>[1-4]\s*[PР])\s*"
    r"(?P<trip>[BCD])?\s*(?P<current>\d+(?:[.,]\d+)?)\s*(?P<amp>[AА])\b",
    re.IGNORECASE,
)


def parse_qf_apparatus(segment: str) -> dict[str, str | None]:
    """Extend source recognition here, preserving the frozen policy owner bytes."""
    parsed = core.parse_qf_apparatus(segment)
    if parsed["model"]:
        return parsed
    match = POWER_MCB_RE.match(compact_text(segment))
    if match is None:
        return parsed
    current = match.group("current") + match.group("amp").upper()
    trip = (match.group("trip") or "").upper()
    return {
        "model": match.group("model"),
        "poles": match.group("poles").upper().replace(" ", "").replace("Р", "P"),
        "trip": trip or None,
        "current": current,
        "residual": None,
        "rating": trip + current,
    }


def schematic_boards(
    file_name: str, page_number: int, blocks: Sequence[PdfBlock], page_text: str
) -> list[BoardCandidate]:
    titles = core.find_schematic_board_titles(blocks, page_text)
    for index, block in enumerate(blocks):
        header = POWER_TITLE_RE.search(block.text)
        if header is None:
            continue
        suffix = block.text[header.end() :]
        if index + 1 < len(blocks):
            suffix += " " + blocks[index + 1].text
        name = POWER_BOARD_RE.search(suffix) or core.SCHEMATIC_BOARD_RE.search(suffix)
        if name is None:
            raise ExtractionError("power schematic board title is incomplete")
        designation = exact_specification_identity(name.group())
        if not any(title.normalized == designation for title in titles):
            titles.append(
                core.SchematicBoardTitle(
                    designation,
                    designation,
                    compact_text(block.text + " " + suffix),
                    block,
                )
            )
    boards: dict[str, BoardCandidate] = {}
    for segment in core.qf_segments_from_blocks(blocks, page_text):
        title = core.nearest_schematic_board(segment, titles)
        if title is None:
            if titles:
                raise ExtractionError("schematic QF board assignment is ambiguous")
            continue
        component = core.qf_component_from_segment(
            segment, file_name, page_number, 0.82
        )
        parsed = parse_qf_apparatus(segment.raw_text)
        if component.model is None and parsed["model"]:
            component.model = parsed["model"]
            component.rating = parsed["rating"]
            component.label = " ".join(
                str(value)
                for value in (
                    segment.designation,
                    parsed["model"],
                    parsed["poles"],
                    parsed["rating"],
                )
            )
            component.note = "; ".join(
                [
                    f"qf_designation={segment.designation}",
                    *[
                        f"{key}={parsed[key]}"
                        for key in ("poles", "trip", "current")
                        if parsed[key]
                    ],
                ]
            )
            component.red_flags.remove("schematic QF has missing apparatus fields")
        key = exact_specification_identity(title.designation)
        if key not in boards:
            boards[key] = BoardCandidate(
                title.designation,
                key,
                title.title,
                None,
                [
                    Provenance(
                        source_file=file_name,
                        source_type="pdf",
                        locator=(
                            f"page={page_number}; block={title.block.number}; "
                            "schematic title"
                        ),
                        raw_text=title.title,
                        confidence=0.82,
                        reason="schematic title matched explicit designation",
                        page=page_number,
                        block_coordinates=(
                            f"x={title.block.x:.1f}, y={title.block.y:.1f}"
                        ),
                    )
                ],
                0.82,
                source_types={"pdf"},
            )
        boards[key].components.append(component)
    return list(boards.values())


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
    if normalized in {"кол", "количество", "qty", "quantity"}:
        return "quantity"
    return None


def extract_requested_specification_page(
    file_name: str,
    page_number: int,
    blocks: Sequence[PdfBlock],
    requested_supply: Sequence[tuple[str, int]],
    excluded_components: Sequence[tuple[str, int]],
    *,
    identity_aliases: Mapping[str, str] | None = None,
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
        if identity_aliases:
            identities = {identity_aliases.get(key, key) for key in identities}
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


def decision_texts(intake: GovernedIntake) -> list[str]:
    """Use only the already SHA-bound intake text; this never grants approval."""
    data = json.loads(intake.raw)
    return [record["text"] for record in data["human_decisions"]]


def decision_aliases(intake: GovernedIntake) -> dict[str, str]:
    aliases: dict[str, str] = {}
    wanted = {exact_specification_identity(name) for name, _ in intake.requested_supply}
    for body in decision_texts(intake):
        text = DASH_RE.sub("-", compact_text(body).replace("`", "")).strip("- ;.")
        match = re.fullmatch(
            r"второй щит\s*[:=]\s*(\S+)\s*;\s*(\S+)\s*"
            r"(?:в спецификации\s*)?[-=]\s*ошибка",
            text,
            re.IGNORECASE,
        )
        if match is None:
            continue
        target, source = map(exact_specification_identity, match.groups())
        if target not in wanted or source in wanted or source == target:
            raise ExtractionError(
                "Human identity correction contradicts requested scope"
            )
        if source in aliases and aliases[source] != target:
            raise ExtractionError("Human identity corrections are contradictory")
        aliases[source] = target
    return aliases


def rating_corrections(
    intake: GovernedIntake,
) -> dict[tuple[str, str], tuple[str, int]]:
    poles: dict[str, str] = {}
    counts: dict[tuple[str, str], int] = {}
    wanted = {exact_specification_identity(name) for name, _ in intake.requested_supply}
    for body in decision_texts(intake):
        text = compact_text(body).replace("`", "").strip("- ;.")
        pole = re.fullmatch(r"([BCD]\d+)\s*=\s*([1-4][PР])", text, re.IGNORECASE)
        count = re.fullmatch(
            r"(\S+):\s*([BCD]\d+)\s*[×xх]\s*(\d+)", text, re.IGNORECASE
        )
        if pole:
            rating, value = pole.groups()
            rating, value = rating.upper(), value.upper().replace("Р", "P")
            if rating in poles and poles[rating] != value:
                raise ExtractionError("Human pole corrections are contradictory")
            poles[rating] = value
        if count:
            board, rating, quantity = count.groups()
            key = exact_specification_identity(board), rating.upper()
            if key[0] not in wanted:
                raise ExtractionError(
                    "Human apparatus correction is outside requested scope"
                )
            value_int = int(quantity)
            if value_int <= 0 or key in counts and counts[key] != value_int:
                raise ExtractionError("Human apparatus counts are contradictory")
            counts[key] = value_int
    return {key: (poles[key[1]], qty) for key, qty in counts.items() if key[1] in poles}


def specification_breakers(
    blocks: Sequence[PdfBlock], wanted: set[str], aliases: Mapping[str, str]
) -> dict[str, Counter[tuple[str, str, str]]]:
    """Bind named apparatus rows to explicit quantity-column tokens, never offsets."""
    headers = {
        role: block
        for block in blocks
        if (role := requested_specification_header_role(block.text))
    }
    quantity_x, unit_x = headers["quantity"].x, headers["unit"].x
    quantity_band = (unit_x + quantity_x) / 2
    rows = [
        block
        for block in blocks
        if block.x > quantity_band and re.fullmatch(r"\d+", block.text)
    ]
    result: dict[str, Counter[tuple[str, str, str]]] = {}
    active: str | None = None
    for index, block in enumerate(blocks):
        identity = exact_specification_identity(block.text)
        identity = aliases.get(identity, identity)
        if identity in wanted:
            active = identity
            result.setdefault(active, Counter())
            continue
        if active is None or not block.text.startswith("Выключатель автоматический"):
            continue
        model = re.search(r"ВА47-?29|ВА88[- ]?32", block.text, re.IGNORECASE)
        apparatus = re.search(
            r"([1-4][PР])\s*(\d+(?:[.,]\d+)?)\s*[AА]\b", block.text, re.IGNORECASE
        )
        trip = re.search(r'характеристика\s*"?([BCD])', block.text, re.IGNORECASE)
        if model is None or apparatus is None:
            raise ExtractionError("requested specification apparatus is unrecognized")
        tail: list[PdfBlock] = []
        for value in blocks[index + 1 :]:
            if value.text.startswith(("Выключатель", "Щит", "Кабель", "Труба")):
                break
            if (
                aliases.get(
                    exact_specification_identity(value.text),
                    exact_specification_identity(value.text),
                )
                in wanted
            ):
                break
            tail.append(value)
        quantities = [value for value in tail if value in rows]
        if len(quantities) != 1:
            raise ExtractionError("requested apparatus quantity is ambiguous")
        quantity = quantities[0]
        anchors = [
            value for value in tail if headers["type_model"].x < value.x < unit_x
        ]
        if block.x >= 0:
            anchors.append(block)
        if not anchors or any(
            min(rows, key=lambda value: abs(value.y - anchor.y)) != quantity
            for anchor in anchors
        ):
            raise ExtractionError(
                "requested apparatus row/quantity alignment is ambiguous"
            )
        key = (
            model.group().upper().replace(" ", "-"),
            apparatus.group(1).upper().replace("Р", "P"),
            (trip.group(1).upper() if trip else "") + apparatus.group(2),
        )
        result[active][key] += int(quantity.text)
    return result


def specification_enclosures(
    blocks: Sequence[PdfBlock], wanted: set[str], aliases: Mapping[str, str]
) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    active: str | None = None
    for block in blocks:
        identity = exact_specification_identity(block.text)
        identity = aliases.get(identity, identity)
        if identity in wanted:
            active = identity
        cabinet = re.search(r"типа\s+(ЩР[нв].+)", block.text)
        if active and cabinet:
            result.setdefault(active, set()).add(compact_text(cabinet.group(1)))
    return result


def reconcile_schematic(
    board: BoardCandidate,
    specification: Counter[tuple[str, str, str]],
    corrections: Mapping[tuple[str, str], tuple[str, int]],
) -> None:
    schematic: Counter[tuple[str, str, str]] = Counter()
    for component in board.components:
        parsed = parse_qf_apparatus(component.provenance[0].raw_text)
        key = (
            str(parsed["model"]),
            str(parsed["poles"]),
            str(parsed["rating"]).replace("А", "").replace("A", ""),
        )
        schematic[key] += 1
    normalized = specification.copy()
    for key, quantity in specification.items():
        model, poles, rating = key
        decision = corrections.get(
            (exact_specification_identity(board.designation), rating)
        )
        if decision is None:
            continue
        target = model, decision[0], rating
        if quantity != decision[1] or schematic[target] != decision[1]:
            raise ExtractionError("Human apparatus count does not match both sources")
        if poles == decision[0]:
            continue
        del normalized[key]
        normalized[target] += quantity
    if normalized != schematic:
        raise ExtractionError("unresolved schematic/specification apparatus conflict")


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
    enclosures: dict[str, list[Provenance]] = {}
    aliases = decision_aliases(intake)
    corrections = rating_corrections(intake)
    specification_counts: dict[str, Counter[tuple[str, str, str]]] = {}
    specification_cabinets: dict[str, set[str]] = {}
    source_schematics: dict[str, BoardCandidate] = {}
    schematic_page_counts: dict[int, int] = {}
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

        page_text = page.extract_text(visitor_text=capture) or ""
        blocks = visible_pdf_blocks(raw_blocks)
        page_boards = schematic_boards(project_pdf.name, page_number, blocks, page_text)
        if page_boards:
            schematic_page_counts[page_number] = sum(
                len(board.components) for board in page_boards
            )
            for board in page_boards:
                key = exact_specification_identity(board.designation)
                if key in source_schematics:
                    raise ExtractionError(
                        "schematic board occurs on multiple source pages"
                    )
                source_schematics[key] = board
        for block in blocks:
            enclosure = re.fullmatch(r"(.+?)\s*\((ЩР[нв].+)\)", block.text)
            if enclosure is None:
                continue
            key = exact_specification_identity(enclosure.group(1))
            enclosures.setdefault(key, []).append(
                Provenance(
                    source_file=project_pdf.name,
                    source_type="pdf",
                    locator=f"page={page_number}; block={block.number}; enclosure",
                    raw_text=enclosure.group(2),
                    confidence=0.82,
                    reason="enclosure explicitly named alongside schematic board",
                    page=page_number,
                    block_coordinates=f"x={block.x:.1f}, y={block.y:.1f}",
                )
            )
        result = extract_requested_specification_page(
            project_pdf.name,
            page_number,
            blocks,
            intake.requested_supply,
            intake.excluded_components,
            identity_aliases=aliases,
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
        counts = specification_breakers(
            blocks,
            {exact_specification_identity(name) for name, _ in intake.requested_supply},
            aliases,
        )
        specification_counts.update(counts)
        specification_cabinets.update(
            specification_enclosures(
                blocks,
                {
                    exact_specification_identity(name)
                    for name, _ in intake.requested_supply
                },
                aliases,
            )
        )
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
    for board in boards:
        matches = [
            source_board
            for source_board in source_schematics.values()
            if exact_specification_identity(source_board.designation)
            == exact_specification_identity(board.designation)
            and any(
                "qf_designation=" in (component.note or "")
                for component in source_board.components
            )
        ]
        if len(matches) > 1:
            raise ExtractionError("requested schematic board identity is ambiguous")
        if not matches:
            continue
        source_board = matches[0]
        qfs = [
            core.qf_designation(c.provenance[0].raw_text)
            for c in source_board.components
        ]
        if len(qfs) != len(set(qfs)):
            raise ExtractionError("requested schematic has duplicate QF identities")
        if any(
            component.quantity != 1
            or not component.model
            or not component.rating
            or "schematic QF has missing apparatus fields" in component.red_flags
            for component in source_board.components
        ):
            raise ExtractionError(
                "requested schematic has incomplete/duplicate QF facts"
            )
        board.components = copy.deepcopy(source_board.components)
        board.provenance.extend(source_board.provenance)
        board.red_flags.extend(source_board.red_flags)
        if specification_counts.get(exact_specification_identity(board.designation)):
            reconcile_schematic(
                board,
                specification_counts[exact_specification_identity(board.designation)],
                corrections,
            )

    manifest = json.loads(base.manifest_text)
    for source in manifest["sources"]:
        for page in source.get("pages", []):
            if page["page"] in schematic_page_counts:
                page["qf_components_extracted"] = schematic_page_counts[page["page"]]
                page["qf_unresolved_count"] = (
                    page["qf_tokens_detected"] - page["qf_components_extracted"]
                )
                if page["qf_unresolved_count"] != 0:
                    raise ExtractionError(
                        "governed schematic QF coverage is incomplete"
                    )
    manifest["case_id"] = intake.case_id
    intake_data = json.loads(intake.raw)
    if re.search(
        r"\bNEW_FUTURE\b", intake_data.get("client_request", {}).get("text", "")
    ):
        manifest["future_context"] = {
            "case_id": intake.case_id,
            "case_state": "NEW_FUTURE",
            "future_cases_only": True,
            "historical_repricing_authorized": False,
        }
    manifest["governed_intake_sha256"] = intake.sha256
    manifest["scope_classification"] = classified_rows
    manifest["human_decision_applications"] = {
        "identity_aliases": aliases,
        "apparatus_corrections": [
            {"designation": board, "rating": rating, "poles": poles, "quantity": qty}
            for (board, rating), (poles, qty) in corrections.items()
        ],
        "evidence": json.loads(intake.raw)["human_decisions"],
        "technical_approval_applied": False,
    }
    manifest_text = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    )
    manifest_sha = hashlib.sha256(manifest_text.encode("utf-8")).hexdigest()
    draft = copy.deepcopy(base.draft)
    draft["draft_id"] = f"PRELIM-MIXED-{manifest_sha[:12].upper()}"
    draft["created_at"] = datetime.now(UTC).isoformat()
    draft["source"]["raw_input_sha256"] = manifest_sha
    draft["source"]["source_summary"] = "Governed rotated CAD PDF extraction bundle."
    draft["source"]["source_files"] = copy.deepcopy(manifest["sources"])
    draft["items"] = [
        board_to_draft(board, f"ITEM-{index:03d}")
        for index, board in enumerate(boards, start=1)
    ]
    superseded = {
        f"PDF page {page} has QF tokens without schematic board title"
        for page in schematic_page_counts
    }
    draft["red_flags"] = [flag for flag in draft["red_flags"] if flag not in superseded]
    for board, item in zip(boards, draft["items"], strict=True):
        item["evidence"].extend(
            f"Human Decision (intake SHA={intake.sha256}): {body}"
            for body in decision_texts(intake)
        )
        evidence = enclosures.get(exact_specification_identity(board.designation), [])
        labels = {record.raw_text for record in evidence}
        spec_labels = specification_cabinets.get(
            exact_specification_identity(board.designation), set()
        )
        if labels and spec_labels and labels != spec_labels:
            raise ExtractionError(
                "unresolved schematic/specification enclosure conflict"
            )
        if len(labels) > 1:
            raise ExtractionError("requested schematic enclosure is contradictory")
        if labels:
            item["cabinet_guess"] = {
                "code_guess": None,
                "label_guess": next(iter(labels)),
                "confidence": min(record.confidence for record in evidence),
                "evidence": [
                    f"{record.locator}: {record.raw_text}" for record in evidence
                ],
                "red_flags": ["source enclosure requires Igor technical review"],
            }
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
    summary["qf_components_extracted"] = sum(
        page["qf_components_extracted"]
        for source in manifest["sources"]
        for page in source.get("pages", [])
    )
    summary["qf_unresolved_count"] = sum(
        page["qf_unresolved_count"]
        for source in manifest["sources"]
        for page in source.get("pages", [])
    )
    summary["switchboards_pdf"] = len(boards)
    summary["composition_rows_extracted"] = sum(
        len(board.components) for board in boards
    )
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
