"""ZIP-level drawing/media snapshot helper for .xlsx packages."""

from __future__ import annotations

import hashlib
import posixpath
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

RELATIONSHIPS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
WORKSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
OFFICE_RELATIONSHIPS_NS = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
)
DRAWING_REL_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing"
)
IMAGE_REL_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
)


class DrawingMediaSnapshotError(Exception):
    """Expected fail-closed snapshot or comparison error."""


@dataclass(frozen=True, order=True)
class WorksheetDrawingReference:
    worksheet_part: str
    relationship_part: str
    relationship_id: str
    target: str
    target_part: str


@dataclass(frozen=True)
class DrawingMediaSnapshot:
    media_paths: tuple[str, ...]
    drawing_paths: tuple[str, ...]
    drawing_rels_paths: tuple[str, ...]
    worksheet_drawing_references: tuple[WorksheetDrawingReference, ...]
    part_hashes: tuple[tuple[str, str], ...]
    relationship_hashes: tuple[tuple[str, str], ...]


def fail(message: str) -> None:
    raise DrawingMediaSnapshotError(message)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sorted_zip_paths(names: list[str], prefix: str) -> tuple[str, ...]:
    return tuple(sorted(name for name in names if name.startswith(prefix)))


def relationship_part_for_source(source_part: str) -> str:
    source_dir = posixpath.dirname(source_part)
    source_name = posixpath.basename(source_part)
    return posixpath.join(source_dir, "_rels", f"{source_name}.rels")


def resolve_relationship_target(source_part: str, target: str) -> str:
    source_dir = posixpath.dirname(source_part)
    normalized = posixpath.normpath(posixpath.join(source_dir, target))
    return normalized.lstrip("/")


def read_xml(archive: zipfile.ZipFile, part: str) -> ElementTree.Element:
    try:
        data = archive.read(part)
    except KeyError:
        fail(f"required relationship part is missing: {part}")
    try:
        return ElementTree.fromstring(data)
    except ElementTree.ParseError as error:
        fail(f"invalid XML part {part}: {error}")


def relationships_by_id(
    archive: zipfile.ZipFile, relationship_part: str
) -> dict[str, tuple[str, str]]:
    root = read_xml(archive, relationship_part)
    relationships: dict[str, tuple[str, str]] = {}
    for relationship in root.findall(f"{{{RELATIONSHIPS_NS}}}Relationship"):
        relationship_id = relationship.attrib.get("Id")
        relationship_type = relationship.attrib.get("Type")
        target = relationship.attrib.get("Target")
        if relationship_id is None or relationship_type is None or target is None:
            fail(f"relationship is incomplete: {relationship_part}")
        relationships[relationship_id] = (relationship_type, target)
    return relationships


def worksheet_paths(names: list[str]) -> tuple[str, ...]:
    return tuple(
        sorted(
            name
            for name in names
            if name.startswith("xl/worksheets/") and name.endswith(".xml")
        )
    )


def drawing_reference_ids(
    archive: zipfile.ZipFile, worksheet_part: str
) -> tuple[str, ...]:
    root = read_xml(archive, worksheet_part)
    references: list[str] = []
    for drawing in root.findall(f".//{{{WORKSHEET_NS}}}drawing"):
        relationship_id = drawing.attrib.get(f"{{{OFFICE_RELATIONSHIPS_NS}}}id")
        if relationship_id is None:
            fail(f"worksheet drawing reference is missing r:id: {worksheet_part}")
        references.append(relationship_id)
    return tuple(sorted(references))


def worksheet_drawing_references(
    archive: zipfile.ZipFile, names: list[str]
) -> tuple[WorksheetDrawingReference, ...]:
    references: list[WorksheetDrawingReference] = []
    name_set = set(names)
    for worksheet_part in worksheet_paths(names):
        reference_ids = drawing_reference_ids(archive, worksheet_part)
        if not reference_ids:
            continue
        relationship_part = relationship_part_for_source(worksheet_part)
        if relationship_part not in name_set:
            fail(f"worksheet drawing relationship part is missing: {relationship_part}")
        relationships = relationships_by_id(archive, relationship_part)
        for relationship_id in reference_ids:
            if relationship_id not in relationships:
                fail(
                    "worksheet drawing relationship is missing: "
                    f"{worksheet_part}#{relationship_id}"
                )
            relationship_type, target = relationships[relationship_id]
            if relationship_type != DRAWING_REL_TYPE:
                fail(
                    "worksheet drawing relationship has unexpected type: "
                    f"{worksheet_part}#{relationship_id}"
                )
            references.append(
                WorksheetDrawingReference(
                    worksheet_part=worksheet_part,
                    relationship_part=relationship_part,
                    relationship_id=relationship_id,
                    target=target,
                    target_part=resolve_relationship_target(worksheet_part, target),
                )
            )
    return tuple(sorted(references))


def hash_parts(
    archive: zipfile.ZipFile, paths: tuple[str, ...]
) -> tuple[tuple[str, str], ...]:
    return tuple((path, sha256_bytes(archive.read(path))) for path in sorted(paths))


def build_drawing_media_snapshot(xlsx_path: Path) -> DrawingMediaSnapshot:
    if not xlsx_path.is_file():
        fail(f"xlsx does not exist: {xlsx_path}")

    try:
        with zipfile.ZipFile(xlsx_path) as archive:
            names = archive.namelist()
            media_paths = sorted_zip_paths(names, "xl/media/")
            drawing_paths = sorted_zip_paths(names, "xl/drawings/")
            drawing_rels_paths = sorted_zip_paths(names, "xl/drawings/_rels/")
            drawing_xml_paths = tuple(
                path
                for path in drawing_paths
                if not path.startswith("xl/drawings/_rels/") and path.endswith(".xml")
            )
            worksheet_refs = worksheet_drawing_references(archive, names)
            worksheet_rels_paths = tuple(
                sorted({reference.relationship_part for reference in worksheet_refs})
            )
            part_hashes = hash_parts(
                archive,
                media_paths + drawing_xml_paths + drawing_rels_paths,
            )
            relationship_hashes = hash_parts(
                archive,
                worksheet_rels_paths + drawing_rels_paths,
            )
    except zipfile.BadZipFile as error:
        fail(f"invalid xlsx ZIP package: {error}")

    return DrawingMediaSnapshot(
        media_paths=media_paths,
        drawing_paths=drawing_xml_paths,
        drawing_rels_paths=drawing_rels_paths,
        worksheet_drawing_references=worksheet_refs,
        part_hashes=part_hashes,
        relationship_hashes=relationship_hashes,
    )


def hash_map(items: tuple[tuple[str, str], ...]) -> dict[str, str]:
    return dict(items)


def compare_path_sets(
    before: tuple[str, ...],
    after: tuple[str, ...],
    missing_message: str,
    unexpected_message: str,
) -> None:
    before_set = set(before)
    after_set = set(after)
    missing = sorted(before_set - after_set)
    if missing:
        fail(f"{missing_message}: {', '.join(missing)}")
    unexpected = sorted(after_set - before_set)
    if unexpected:
        fail(f"{unexpected_message}: {', '.join(unexpected)}")


def compare_hashes_for_paths(
    before: tuple[tuple[str, str], ...],
    after: tuple[tuple[str, str], ...],
    paths: tuple[str, ...],
    changed_message: str,
) -> None:
    before_hashes = hash_map(before)
    after_hashes = hash_map(after)
    for path in paths:
        before_hash = before_hashes[path]
        if path in after_hashes and after_hashes[path] != before_hash:
            fail(f"{changed_message}: {path}")


def compare_drawing_media_snapshots(
    before: DrawingMediaSnapshot, after: DrawingMediaSnapshot
) -> None:
    compare_path_sets(
        before.media_paths,
        after.media_paths,
        "media file missing",
        "unexpected media file",
    )
    compare_path_sets(
        before.drawing_paths,
        after.drawing_paths,
        "drawing XML missing",
        "unexpected drawing XML",
    )
    compare_path_sets(
        before.drawing_rels_paths,
        after.drawing_rels_paths,
        "relationship missing",
        "unexpected relationship",
    )
    compare_path_sets(
        tuple(str(item) for item in before.worksheet_drawing_references),
        tuple(str(item) for item in after.worksheet_drawing_references),
        "worksheet drawing reference missing",
        "unexpected worksheet drawing reference",
    )
    compare_hashes_for_paths(
        before.part_hashes,
        after.part_hashes,
        before.media_paths,
        "media file hash changed",
    )
    compare_hashes_for_paths(
        before.part_hashes,
        after.part_hashes,
        before.drawing_paths,
        "drawing XML hash changed",
    )
    compare_hashes_for_paths(
        before.relationship_hashes,
        after.relationship_hashes,
        tuple(path for path, _item_hash in before.relationship_hashes),
        "relationship changed",
    )
