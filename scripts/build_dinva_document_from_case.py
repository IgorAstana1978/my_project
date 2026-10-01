"""Preflight or immutably publish a source-bound DINVA document from any Case.

Approval JSON is evidence of a contract claim, never publication permission.
The default CLI is read-only; publication needs a separate exact authorization.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast

import render_dinva_classic_quote_invoice as renderer
import validate_dinva_classic_quote_invoice as validator

SOURCE_SCHEMA = "dinva_case_document_source.v0.1"
APPROVAL_SCHEMA = "dinva_case_document_approval.v0.1"
SCOPE = "DINVA_CASE_DOCUMENT_MODEL_ONLY"
PUBLICATION_ACTION = "IGOR_DINVA_CASE_DOCUMENT_PUBLICATION_AUTHORIZED"
SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
SOURCE_KEYS = {
    "schema_version",
    "case_id",
    "metadata",
    "items",
    "terms",
    "approved_grand_total_kzt",
    "source_bindings",
}
METADATA_KEYS = {
    "document_type",
    "document_number",
    "document_date",
    "currency",
    "payer",
    "object_name",
    "basis",
    "apparatus_heading",
    "sections",
    "vat",
    "amount_words",
    "signatures",
}
ITEM_KEYS = {
    "item_id",
    "name",
    "unit",
    "quantity",
    "detailed_technical_composition",
    "enclosure",
    "approved_unit_price_kzt",
    "approved_line_total_kzt",
}
TERM_KEYS = {
    "payment",
    "delivery",
    "manufacturing_lead_time",
    "validity",
    "commercial_lines",
}
APPROVAL_KEYS = {
    "schema_version",
    "case_id",
    "authority",
    "approved_by",
    "approved_at",
    "approval_id",
    "approved_case_source_sha256",
    "approved_document_fingerprint",
    "technical_composition_approved",
    "prices_approved",
    "commercial_terms_approved",
    "rendering_authorized",
    "client_send_authorized",
}
DEFAULT_DELIVERY = "EXW г. Астана"
DEFAULT_SIGNATURES = {
    "director_title": "Директор",
    "director_name": "Никольченко И.В.",
    "executor_label": "Исполнитель:",
    "executor_title": "Инженер-Электрик ПТО",
    "executor_name": "Марат А.К.",
    "executor_full_text": "Инженер-Электрик ПТО Марат А.К.",
}
DEFAULTS_ROLE = "GOVERNED_DINVA_DOCUMENT_DEFAULTS"
RESERVED_ROLES = {
    "AUTHORITATIVE_DOCUMENT_TEXT_SOURCE",
    "CASE_HUMAN_APPROVAL",
    DEFAULTS_ROLE,
}


class BridgeError(ValueError):
    """The supplied Case cannot become an approved DINVA document."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BridgeError(message)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def encode(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def obj(
    value: object,
    keys: set[str],
    label: str,
    *,
    optional: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    require(isinstance(value, Mapping), f"{label} must be an object")
    data = dict(cast(Mapping[str, Any], value))
    require(keys - optional <= set(data) <= keys, f"{label} fields mismatch")
    return data


def text(value: object, label: str) -> str:
    require(isinstance(value, str) and bool(value.strip()), f"missing {label}")
    return cast(str, value)


def sha(value: object, label: str) -> str:
    result = text(value, label)
    require(SHA_RE.fullmatch(result) is not None, f"invalid {label}")
    return result


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    raise BridgeError(f"non-finite JSON number: {value}")


@dataclass(frozen=True)
class Snapshot:
    path: Path
    raw: bytes

    @property
    def sha256(self) -> str:
        return digest(self.raw)

    def payload(self) -> dict[str, Any]:
        try:
            data = json.loads(
                self.raw.decode("utf-8"),
                object_pairs_hook=reject_duplicates,
                parse_constant=reject_constant,
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BridgeError(f"invalid JSON: {self.path}") from exc
        require(isinstance(data, dict), "JSON root must be an object")
        return cast(dict[str, Any], data)


def load(path: Path, expected_sha: str) -> Snapshot:
    actual = path.resolve(strict=True)
    snapshot = Snapshot(actual, actual.read_bytes())
    require(
        snapshot.sha256 == sha(expected_sha, "input SHA"),
        f"input SHA mismatch: {actual}",
    )
    return snapshot


def formation_date() -> str:
    """New DINVA quotes use the factory's actual calendar date (UTC+05:00)."""
    return datetime.now(UTC).astimezone(timezone(timedelta(hours=5))).date().isoformat()


def defaults_source() -> Snapshot:
    path = Path(__file__).resolve(strict=True)
    return Snapshot(path, path.read_bytes())


def prepare_core(
    source: Mapping[str, Any],
    binding: dict[str, str],
    defaults_binding: dict[str, str] | None = None,
) -> dict[str, Any]:
    data = obj(source, SOURCE_KEYS, "Case source")
    require(data["schema_version"] == SOURCE_SCHEMA, "Case source schema mismatch")
    case_id = text(data["case_id"], "case_id")
    metadata = obj(
        data["metadata"],
        METADATA_KEYS,
        "metadata",
        optional=frozenset({"document_number", "document_date", "signatures"}),
    )
    require(metadata["document_type"] == "QUOTE", "Case bridge produces QUOTE only")
    number = metadata.get("document_number")
    metadata["document_number"] = (
        None if number in (None, "") else text(number, "document_number")
    )
    supplied_date = metadata.get("document_date")
    metadata["document_date"] = (
        formation_date()
        if supplied_date in (None, "")
        else text(supplied_date, "document_date")
    )
    if metadata.get("signatures") is None:
        metadata["signatures"] = copy.deepcopy(DEFAULT_SIGNATURES)
    for field in ("payer", "document_date", "apparatus_heading"):
        text(metadata[field], field)
    require(isinstance(data["items"], list) and bool(data["items"]), "items missing")
    items = []
    ids: set[str] = set()
    for index, raw_item in enumerate(data["items"]):
        item = obj(raw_item, ITEM_KEYS, f"item {index + 1}")
        item_id = text(item.pop("item_id"), "item_id")
        require(item_id not in ids, "duplicate item_id")
        ids.add(item_id)
        composition = text(item["detailed_technical_composition"], "composition")
        locator = f"/items/{index}/detailed_technical_composition"
        item.update(
            position=index + 1,
            apparatus={
                "text": composition,
                "source_role": binding["role"],
                "source_sha256": binding["sha256"],
                "source_locator": locator,
            },
            approval_reference={
                "pricing": f"{case_id}|/items/{index}/approved_unit_price_kzt",
                "technical": f"{case_id}|{locator}",
                "enclosure": f"{case_id}|/items/{index}/enclosure",
            },
        )
        items.append(item)
    terms = obj(data["terms"], TERM_KEYS, "terms", optional=frozenset({"delivery"}))
    supplied_delivery = terms.get("delivery")
    delivery = (
        DEFAULT_DELIVERY
        if supplied_delivery in (None, "")
        else text(supplied_delivery, "delivery")
    )
    terms["delivery"] = delivery
    lead = text(terms["manufacturing_lead_time"], "manufacturing_lead_time")
    lines = terms["commercial_lines"]
    require(isinstance(lines, list) and bool(lines), "commercial_lines missing")
    require(
        lines.count(lead) == 1,
        "lead time must occur verbatim once in approved commercial_lines",
    )
    terms["commercial_lines"] = [
        {
            "source_order": i + 1,
            "text": text(line, "commercial line"),
            "source_sha256": binding["sha256"],
            "source_locator": f"/terms/commercial_lines/{i}",
        }
        for i, line in enumerate(lines)
    ]
    if not any(delivery in text(line, "commercial line") for line in lines):
        delivery_binding = binding
        locator = "/terms/delivery"
        if supplied_delivery in (None, ""):
            policy = defaults_source()
            delivery_binding = defaults_binding or {
                "role": DEFAULTS_ROLE,
                "path": str(policy.path),
                "sha256": policy.sha256,
            }
            locator = "DEFAULT_DELIVERY"
        terms["commercial_lines"].append(
            {
                "source_order": len(lines) + 1,
                "text": delivery,
                "source_sha256": delivery_binding["sha256"],
                "source_locator": locator,
            }
        )
    lead_index = lines.index(lead)
    terms["manufacturing_lead_time_provenance"] = {
        "source_order": lead_index + 1,
        "source_text": lead,
        "normalized_text": lead,
        "source_sha256": binding["sha256"],
        "source_locator": f"/terms/commercial_lines/{lead_index}",
        "normalization_rule": "VERBATIM_APPROVED_CASE_TERM",
        "approval_reference": f"{case_id}|/terms/manufacturing_lead_time",
    }
    return {
        "schema_version": renderer.DOCUMENT_SCHEMA_VERSION,
        "document_family": renderer.FAMILY,
        "document_id": case_id,
        **copy.deepcopy(metadata),
        "items": items,
        "terms": terms,
        "approved_grand_total_kzt": data["approved_grand_total_kzt"],
    }


@dataclass(frozen=True)
class Plan:
    document: dict[str, Any]
    snapshots: tuple[Snapshot, ...]
    materialized: bool = True

    @property
    def encoded(self) -> bytes:
        return encode(self.document)

    def recheck(self) -> None:
        for snapshot in self.snapshots if self.materialized else self.snapshots[2:]:
            require(
                snapshot.path.read_bytes() == snapshot.raw,
                f"source changed after preflight: {snapshot.path}",
            )


def preflight(case: Snapshot, approval: Snapshot, *, preview: bool = False) -> Plan:
    if preview:
        require(
            not case.path.exists() and not approval.path.exists(),
            "preview requires unpublished prospective inputs",
        )
    require(case.path != approval.path, "Case and approval must be separate sources")
    require(
        not renderer.is_inside_project(case.path)
        and not renderer.is_inside_project(approval.path),
        "Case and approval inputs must be outside Git",
    )
    source = obj(case.payload(), SOURCE_KEYS, "Case source")
    decision = obj(approval.payload(), APPROVAL_KEYS, "Case Human Approval")
    require(decision["schema_version"] == APPROVAL_SCHEMA, "approval schema mismatch")
    require(decision["case_id"] == source["case_id"], "approval Case identity mismatch")
    require(
        decision["authority"] == "IGOR_DIRECT_HUMAN_APPROVAL"
        and decision["approved_by"] == "Igor",
        "Human Approval authority mismatch",
    )
    for key in (
        "technical_composition_approved",
        "prices_approved",
        "commercial_terms_approved",
        "rendering_authorized",
    ):
        require(decision[key] is True, f"approval missing: {key}")
    require(
        decision["client_send_authorized"] is False, "client sending must be closed"
    )
    text(decision["approval_id"], "approval_id")
    timestamp = text(decision["approved_at"], "approved_at")
    try:
        require(
            datetime.fromisoformat(timestamp).utcoffset() is not None,
            "approval timestamp must include a timezone",
        )
    except ValueError as exc:
        raise BridgeError("invalid approval timestamp") from exc
    require(
        sha(decision["approved_case_source_sha256"], "approved Case SHA")
        == case.sha256,
        "approved Case source SHA mismatch",
    )
    bindings = [
        {
            "role": "AUTHORITATIVE_DOCUMENT_TEXT_SOURCE",
            "path": str(case.path),
            "sha256": case.sha256,
        },
        {
            "role": "CASE_HUMAN_APPROVAL",
            "path": str(approval.path),
            "sha256": approval.sha256,
        },
    ]
    policy = defaults_source()
    policy_binding = {
        "role": DEFAULTS_ROLE,
        "path": str(policy.path),
        "sha256": policy.sha256,
    }
    bindings.append(policy_binding)
    snapshots = [case, approval, policy]
    roles = set(RESERVED_ROLES)
    require(
        isinstance(source["source_bindings"], list) and bool(source["source_bindings"]),
        "upstream source bindings missing",
    )
    for raw in source["source_bindings"]:
        b = obj(raw, {"role", "path", "sha256"}, "upstream source binding")
        role = text(b["role"], "upstream role")
        require(role not in roles, "duplicate or reserved source role")
        roles.add(role)
        upstream_path = Path(text(b["path"], "upstream path"))
        require(upstream_path.is_absolute(), "upstream path must be absolute")
        snap = load(upstream_path, b["sha256"])
        require(snap.path not in {case.path, approval.path}, "cyclic upstream binding")
        snapshots.append(snap)
        bindings.append({"role": role, "path": str(snap.path), "sha256": snap.sha256})
    document = prepare_core(source, bindings[0], policy_binding)
    fingerprint = renderer.document_fingerprint(document)
    require(
        sha(decision["approved_document_fingerprint"], "approved fingerprint")
        == fingerprint,
        "approved document fingerprint mismatch",
    )
    document["document_fingerprint"] = fingerprint
    document["approval_provenance"] = {
        "status": "APPROVED",
        "authority": decision["authority"],
        "approval_id": decision["approval_id"],
        "approved_at": timestamp,
        "approval_scope": SCOPE,
        "approved_document_fingerprint": fingerprint,
        "source_bindings": bindings,
        "source_sha256s": [b["sha256"] for b in bindings],
        "rendering_authorized": True,
        "client_send_authorized": False,
    }
    try:
        renderer.validate_document(document, allow_test_profile=False)
        validator.validate_document_contract(document, allow_test_profile=False)
    except (renderer.RendererError, validator.ValidationError) as exc:
        raise BridgeError(str(exc)) from exc
    plan = Plan(document, tuple(snapshots), materialized=not preview)
    plan.recheck()
    return plan


def output_path(plan: Plan, output: Path) -> Path:
    path = output.resolve(strict=False)
    require(path.suffix.lower() == ".json", "output must be JSON")
    require(path.parent.is_dir(), "output parent must already exist")
    require(not renderer.is_inside_project(path), "output must be outside Git")
    require(path not in {s.path for s in plan.snapshots}, "output aliases a source")
    require(not path.exists(), "output exists; overwrite is forbidden")
    return path


def publish(plan: Plan, output: Path, authorization: str) -> Path:
    require(
        plan.materialized, "preview input materialization requires exact Human Approval"
    )
    verified = preflight(plan.snapshots[0], plan.snapshots[1])
    require(verified.encoded == plan.encoded, "preflight plan was modified")
    plan = verified
    encoded = plan.encoded
    path = output_path(plan, output)
    expected = (
        f"{PUBLICATION_ACTION}|ACTION=IMMUTABLE_DOCUMENT_PUBLICATION"
        f"|CASE_SHA256={plan.snapshots[0].sha256}"
        f"|APPROVAL_SHA256={plan.snapshots[1].sha256}"
        f"|DOCUMENT_FINGERPRINT={plan.document['document_fingerprint']}"
        f"|OUTPUT_PATH_SHA256={digest(str(path).encode('utf-8'))}"
    )
    require(authorization == expected, "exact Human publication authorization required")
    plan.recheck()
    descriptor, temporary = tempfile.mkstemp(prefix=".dinva-case-", dir=path.parent)
    staging = Path(temporary)
    published = False
    identity: tuple[int, int] | None = None
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        stat = staging.stat()
        identity = (stat.st_dev, stat.st_ino)
        require(staging.read_bytes() == encoded, "staged bytes mismatch")
        plan.recheck()
        os.link(staging, path)
        published = True
        stat = path.stat()
        require((stat.st_dev, stat.st_ino) == identity, "publication identity mismatch")
        plan.recheck()
        require(path.read_bytes() == encoded, "published bytes mismatch")
        return path
    except BaseException:
        if published and path.exists():
            stat = path.stat()
            if (stat.st_dev, stat.st_ino) == identity:
                path.unlink()
        raise
    finally:
        staging.unlink(missing_ok=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-source", type=Path, required=True)
    parser.add_argument("--case-source-sha256", required=True)
    parser.add_argument("--case-approval", type=Path, required=True)
    parser.add_argument("--case-approval-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--authorization")
    args = parser.parse_args(argv)
    try:
        require(
            args.publish == (args.authorization is not None),
            "authorization is permitted only with explicit --publish",
        )
        plan = preflight(
            load(args.case_source, args.case_source_sha256),
            load(args.case_approval, args.case_approval_sha256),
        )
        target = output_path(plan, args.output)
        if args.publish:
            publish(plan, target, args.authorization)
        print(
            "DINVA_CASE_DOCUMENT=" + ("PUBLISHED" if args.publish else "PREFLIGHT_PASS")
        )
        print(f"DOCUMENT_FINGERPRINT={plan.document['document_fingerprint']}")
        print(f"CANDIDATE_SHA256={digest(plan.encoded)}")
        print(f"OUTPUT={target}")
        print("CLIENT_SEND=CLOSED")
        return 0
    except (OSError, ValueError) as exc:
        print(f"HOLD: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
