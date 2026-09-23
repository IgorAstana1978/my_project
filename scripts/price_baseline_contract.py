"""Fail-closed price-baseline bindings and active-manifest resolution."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

MANIFEST_SCHEMA = "price_baseline_manifest.v0.1"
SELECTOR_SCHEMA = "active_price_baseline_selector.v0.1"
APPROVAL_SCHEMA = "price_baseline_approval.v0.1"
APPROVAL_AUTHORITY = "IGOR_DIRECT_HUMAN_APPROVAL"
ACTIVE_VERSION = "active_approved"
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
UTC_TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")

CANONICAL_PRICE_ROOT = Path(
    r"C:\Users\IgorN\Documents\invoice_quote_filler_data\prices"
)
DEFAULT_ACTIVE_SELECTOR = CANONICAL_PRICE_ROOT / "active-price-baseline.json"


@dataclass(frozen=True)
class PriceBaseline:
    version: str
    path: Path
    sha256: str
    manifest_id: str | None = None
    manifest_path: Path | None = None
    manifest_sha256: str | None = None
    approval_id: str | None = None
    mapping_snapshot: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)


HISTORICAL = PriceBaseline(
    "historical_invoice519",
    Path(r"C:\Users\IgorN\Documents\invoice_quote_filler_data\prices\current")
    / "Таблица 05.01.2026 верная.xlsx",
    "79b3ace77e84b87c46eb708f1c3b2ae63b5c6d75c5ebf6889c12b99624112ba1",
)

# Compatibility-only binding for the already released successor. Future price-only
# releases resolve through ACTIVE_VERSION and do not add another Python constant.
SUCCESSOR = PriceBaseline(
    "successor_2026_09_09",
    Path(r"C:\Users\IgorN\Documents\invoice_quote_filler_data\prices\current")
    / "Таблица 09.09.2026 верная-2.xlsx",
    "02ca5be9b2eb6775289ee1053c389a659c85e2bd27a2b9867b7d523d6d6e4096",
)
BASELINES = {item.version: item for item in (HISTORICAL, SUCCESSOR)}


class BaselineContractError(ValueError):
    """An active price-baseline chain is missing, corrupt, or drifted."""


def normalize_kzt_literal(value: Any, *, allow_zero: bool = False) -> int | None:
    """Accept integer KZT or one IEEE-754 neighbor of an exact integer."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 or (allow_zero and value == 0) else None
    if not isinstance(value, float) or not math.isfinite(value):
        return None
    if value == 0:
        return 0 if allow_zero else None
    if value < 0:
        return None
    if value.is_integer():
        return int(value)
    for candidate in (math.floor(value), math.ceil(value)):
        if (
            candidate > 0
            and float(candidate) == candidate
            and value
            in (
                math.nextafter(float(candidate), -math.inf),
                math.nextafter(float(candidate), math.inf),
            )
        ):
            return candidate
    return None


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def _duplicate_key_guard(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BaselineContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json_bytes(raw: bytes, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(raw, object_pairs_hook=_duplicate_key_guard)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BaselineContractError(f"{label} is not strict UTF-8 JSON") from exc
    if not isinstance(value, Mapping):
        raise BaselineContractError(f"{label} root must be an object")
    return cast(Mapping[str, Any], value)


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise BaselineContractError(f"{label} fields mismatch")


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BaselineContractError(f"{label} must be a non-empty string")
    return value


def _sha(value: Any, label: str) -> str:
    text = _text(value, label)
    if SHA256_RE.fullmatch(text) is None:
        raise BaselineContractError(f"{label} must be lowercase SHA-256")
    return text


def _timestamp(value: Any, label: str) -> str:
    text = _text(value, label)
    if UTC_TIMESTAMP_RE.fullmatch(text) is None:
        raise BaselineContractError(f"{label} must be UTC second precision")
    return text


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BaselineContractError(f"{label} must be an object")
    return cast(Mapping[str, Any], value)


def _positive_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise BaselineContractError(f"{label} must be a positive integer")
    return value


def mapping_identity_fingerprint(identity: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(identity))


def validate_mapping_snapshot(value: Any) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list) or not value:
        raise BaselineContractError("mapping_snapshot must be a non-empty array")
    seen_ids: set[str] = set()
    snapshot: list[Mapping[str, Any]] = []
    for index, raw_entry in enumerate(value, start=1):
        entry = _mapping(raw_entry, f"mapping_snapshot[{index}]")
        _exact_keys(
            entry,
            {
                "mapping_id",
                "mapping_kind",
                "identity",
                "identity_fingerprint",
                "source",
                "prices",
            },
            f"mapping_snapshot[{index}]",
        )
        mapping_id = _text(entry["mapping_id"], "mapping_id")
        if mapping_id in seen_ids:
            raise BaselineContractError("duplicate mapping_id in mapping_snapshot")
        seen_ids.add(mapping_id)
        kind = _text(entry["mapping_kind"], "mapping_kind")
        if kind not in {
            "component_exact",
            "component_dynamic",
            "cabinet_exact",
            "cabinet_dynamic",
        }:
            raise BaselineContractError("unknown mapping_kind")
        identity = _mapping(entry["identity"], "mapping identity")
        fingerprint = _sha(entry["identity_fingerprint"], "identity_fingerprint")
        if mapping_identity_fingerprint(identity) != fingerprint:
            raise BaselineContractError("mapping identity fingerprint mismatch")
        source = _mapping(entry["source"], "mapping source")
        _exact_keys(
            source,
            {"sheet", "row", "label_cell", "price_cells"},
            "mapping source",
        )
        _text(source["sheet"], "mapping source sheet")
        _positive_int(source["row"], "mapping source row")
        _text(source["label_cell"], "mapping label_cell")
        cells = source["price_cells"]
        if not isinstance(cells, list) or not cells:
            raise BaselineContractError("mapping price_cells must be non-empty")
        if not all(isinstance(cell, str) and cell for cell in cells):
            raise BaselineContractError("mapping price_cells are invalid")
        prices = _mapping(entry["prices"], "mapping prices")
        expected_price_keys = (
            {"material_kzt", "work_kzt"}
            if kind.startswith("component_")
            else {"price_kzt"}
        )
        _exact_keys(prices, expected_price_keys, "mapping prices")
        for field_name in expected_price_keys:
            _positive_int(prices[field_name], f"mapping prices.{field_name}")
        snapshot.append(entry)
    return tuple(snapshot)


def validate_manifest(data: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    _exact_keys(
        data,
        {
            "schema_version",
            "manifest_id",
            "created_at",
            "predecessor",
            "workbook",
            "mapping_snapshot",
            "approval",
            "scope",
        },
        "manifest",
    )
    if data["schema_version"] != MANIFEST_SCHEMA:
        raise BaselineContractError("manifest schema_version mismatch")
    _text(data["manifest_id"], "manifest_id")
    _timestamp(data["created_at"], "manifest created_at")
    predecessor = data["predecessor"]
    if predecessor is not None:
        predecessor_map = _mapping(predecessor, "manifest predecessor")
        _exact_keys(
            predecessor_map,
            {"manifest_id", "manifest_sha256"},
            "manifest predecessor",
        )
        _text(predecessor_map["manifest_id"], "predecessor manifest_id")
        _sha(predecessor_map["manifest_sha256"], "predecessor manifest_sha256")
    workbook = _mapping(data["workbook"], "manifest workbook")
    _exact_keys(
        workbook,
        {"path", "sha256", "structural_fingerprint"},
        "manifest workbook",
    )
    workbook_path = Path(_text(workbook["path"], "workbook path"))
    if not workbook_path.is_absolute():
        raise BaselineContractError("workbook path must be absolute")
    _sha(workbook["sha256"], "workbook SHA-256")
    _sha(workbook["structural_fingerprint"], "structural fingerprint")
    snapshot = validate_mapping_snapshot(data["mapping_snapshot"])
    approval = _mapping(data["approval"], "manifest approval")
    _exact_keys(
        approval,
        {
            "schema_version",
            "authority",
            "approval_id",
            "approved_by",
            "approved_at",
            "candidate_audit_sha256",
            "approval_fingerprint",
        },
        "manifest approval",
    )
    if (
        approval["schema_version"] != APPROVAL_SCHEMA
        or approval["authority"] != APPROVAL_AUTHORITY
        or approval["approved_by"] != "Igor"
    ):
        raise BaselineContractError("manifest approval authority mismatch")
    _text(approval["approval_id"], "approval_id")
    _timestamp(approval["approved_at"], "approved_at")
    _sha(approval["candidate_audit_sha256"], "candidate audit SHA-256")
    _sha(approval["approval_fingerprint"], "approval fingerprint")
    scope = _mapping(data["scope"], "manifest scope")
    _exact_keys(
        scope,
        {"future_cases_only", "historical_repricing_authorized"},
        "manifest scope",
    )
    if (
        scope["future_cases_only"] is not True
        or scope["historical_repricing_authorized"] is not False
    ):
        raise BaselineContractError("manifest historical boundary is open")
    return snapshot


def validate_selector(data: Mapping[str, Any]) -> None:
    _exact_keys(
        data,
        {
            "schema_version",
            "manifest_id",
            "manifest_path",
            "manifest_sha256",
            "activated_at",
            "approval_id",
        },
        "active selector",
    )
    if data["schema_version"] != SELECTOR_SCHEMA:
        raise BaselineContractError("active selector schema_version mismatch")
    _text(data["manifest_id"], "selector manifest_id")
    manifest_path = Path(_text(data["manifest_path"], "selector manifest_path"))
    if not manifest_path.is_absolute():
        raise BaselineContractError("selector manifest_path must be absolute")
    _sha(data["manifest_sha256"], "selector manifest_sha256")
    _timestamp(data["activated_at"], "selector activated_at")
    _text(data["approval_id"], "selector approval_id")


def _read_exact(path: Path, label: str) -> bytes:
    try:
        if not path.is_file():
            raise BaselineContractError(f"{label} does not exist")
        return path.read_bytes()
    except OSError as exc:
        raise BaselineContractError(f"{label} could not be read") from exc


def resolve_active_price_baseline(
    selector_path: Path = DEFAULT_ACTIVE_SELECTOR,
) -> PriceBaseline:
    selector_file = selector_path.expanduser().resolve(strict=False)
    selector_raw = _read_exact(selector_file, "active selector")
    selector = load_json_bytes(selector_raw, "active selector")
    validate_selector(selector)

    manifest_file = Path(cast(str, selector["manifest_path"])).resolve(strict=False)
    expected_manifest_dir = selector_file.parent / "manifests"
    if manifest_file.parent != expected_manifest_dir.resolve(strict=False):
        raise BaselineContractError("selector manifest_path is outside manifests root")
    if manifest_file.name != f"{selector['manifest_id']}.json":
        raise BaselineContractError("selector manifest path/id mismatch")
    manifest_raw = _read_exact(manifest_file, "active manifest")
    manifest_sha = sha256_bytes(manifest_raw)
    if manifest_sha != selector["manifest_sha256"]:
        raise BaselineContractError("active manifest SHA-256 mismatch")
    manifest = load_json_bytes(manifest_raw, "active manifest")
    snapshot = validate_manifest(manifest)
    if manifest["manifest_id"] != selector["manifest_id"]:
        raise BaselineContractError("selector/manifest ID mismatch")
    approval = _mapping(manifest["approval"], "manifest approval")
    if approval["approval_id"] != selector["approval_id"]:
        raise BaselineContractError("selector/manifest approval mismatch")

    workbook = _mapping(manifest["workbook"], "manifest workbook")
    workbook_path = Path(cast(str, workbook["path"])).resolve(strict=False)
    price_root = selector_file.parent.resolve(strict=False)
    if (
        not workbook_path.is_relative_to(price_root)
        or workbook_path.suffix.casefold() != ".xlsx"
    ):
        raise BaselineContractError("active workbook is outside canonical price root")
    expected_workbook_sha = cast(str, workbook["sha256"])
    try:
        actual_workbook_sha = sha256_file(workbook_path)
    except OSError as exc:
        raise BaselineContractError("active workbook could not be read") from exc
    if actual_workbook_sha != expected_workbook_sha:
        raise BaselineContractError("active workbook SHA-256 mismatch")

    if _read_exact(selector_file, "active selector") != selector_raw:
        raise BaselineContractError("active selector changed during resolution")
    if _read_exact(manifest_file, "active manifest") != manifest_raw:
        raise BaselineContractError("active manifest changed during resolution")
    return PriceBaseline(
        version=ACTIVE_VERSION,
        path=workbook_path,
        sha256=expected_workbook_sha,
        manifest_id=cast(str, manifest["manifest_id"]),
        manifest_path=manifest_file,
        manifest_sha256=manifest_sha,
        approval_id=cast(str, approval["approval_id"]),
        mapping_snapshot=snapshot,
    )


def require_price_baseline(
    path: Path | None,
    version: str,
    *,
    active_selector_path: Path = DEFAULT_ACTIVE_SELECTOR,
) -> PriceBaseline:
    """Reject unknown versions, path aliases, drift, and corrupt active chains."""
    if version == ACTIVE_VERSION:
        active_baseline = resolve_active_price_baseline(active_selector_path)
        if path is not None and Path(os.path.abspath(path)) != Path(
            os.path.abspath(active_baseline.path)
        ):
            raise BaselineContractError("active price baseline path mismatch")
        return active_baseline
    static_baseline = BASELINES.get(version)
    if static_baseline is None:
        raise BaselineContractError("unknown price baseline version")
    if path is None or Path(os.path.abspath(path)) != Path(
        os.path.abspath(static_baseline.path)
    ):
        raise BaselineContractError("price baseline path/version mismatch")
    try:
        actual_sha = sha256_file(path)
    except OSError as exc:
        raise BaselineContractError(
            "price baseline workbook could not be read"
        ) from exc
    if actual_sha != static_baseline.sha256:
        raise BaselineContractError("price baseline SHA-256/version mismatch")
    return static_baseline


def resolve_price_baseline(
    path: Path | None,
    version: str | None,
    *,
    active_selector_path: Path = DEFAULT_ACTIVE_SELECTOR,
) -> PriceBaseline:
    """Resolve active baseline by default; explicit versions remain exact."""
    selected_version = ACTIVE_VERSION if version is None else version
    return require_price_baseline(
        path,
        selected_version,
        active_selector_path=active_selector_path,
    )
