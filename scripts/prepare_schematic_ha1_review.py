"""Prepare a read-only HA1 review packet from a pinned schematic extraction."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import build_confirmed_composition_from_preliminary_bundle as builder
import cabinet_sizing as sizing
import cabinet_sizing_evidence as evidence
import cabinet_sizing_module_accounting as modules
from cabinet_sizing_catalogue import QUOTE_REQUEST_SCHEMA
from governed_case_intake import SCHEMATIC_OPEN_GAPS, SCHEMATIC_REVIEW_SCHEMA

INPUT_SCHEMA = "schematic_ha1_review_input.v0.1"
OUTPUT_SCHEMA = "schematic_ha1_review_packet.v0.1"


def decision_text(value: Any, label: str) -> str:
    text = builder.strict_nonempty_string(value, label)
    if text.strip().casefold() in {"unknown", "tbd", "?", "n/a", "none", "неизвестно"}:
        raise builder.WorkflowError(f"unresolved schematic decision: {label}")
    return text


def source_facts(snapshot: builder.InputSnapshot) -> dict[str, Any]:
    manifest = builder.parse_strict_json_object(snapshot.manifest_bytes, "manifest")
    draft = snapshot.draft
    if manifest.get("review_mode") != SCHEMATIC_REVIEW_SCHEMA:
        raise builder.WorkflowError("schematic-only extraction is required")
    summary = draft["extraction_summary"]
    count = sum(len(item["components"]) for item in draft["items"])
    if (
        draft.get("red_flags") != list(SCHEMATIC_OPEN_GAPS)
        or summary.get("qf_unresolved_count") != 0
        or count == 0
        or count != summary.get("qf_tokens_detected")
        or count != summary.get("qf_components_extracted")
    ):
        raise builder.WorkflowError("unresolved schematic extraction gaps or QF count")
    builder.validate_identifier_integrity(draft)
    builder.validate_source_metadata_integrity(draft)
    if any(
        not item.get("provenance")
        or not item.get("normalized_designation")
        or not item["components"]
        or any(
            not c.get("provenance")
            or not c.get("note_guess", "").startswith("qf_designation=QF")
            or type(c["quantity_guess"]) is not int
            or c["quantity_guess"] != 1
            for c in item["components"]
        )
        for item in draft["items"]
    ):
        raise builder.WorkflowError("schematic designation or QF provenance is missing")
    return {"qf_count": count, "items": draft["items"], "pdf": manifest["sources"][0]}


def verify_inventory_decisions(
    review: Any, snapshot: builder.InputSnapshot, state: builder.CompositionState
) -> None:
    assert state.cabinet_sizing is not None and state.batch_decisions is not None
    report = state.cabinet_sizing
    approved_boards = builder.exact_object(
        review, "boards", {item["item_id"] for item in state.items}
    )
    module_data = evidence.read(report["sources"]["module_evidence"], modules.ROLE)
    raw_sources = {(ref["path"], ref["sha256"]) for ref in module_data["raw_sources"]}
    for source_item, selection, item_decision in zip(
        snapshot.draft["items"],
        report["items"],
        state.batch_decisions["item_decisions"],
        strict=True,
    ):
        item_id = source_item["item_id"]
        board = builder.exact_object(
            approved_boards[item_id],
            item_id,
            {"qf_products", "accessories", "connections", "technical_requirements"},
        )
        if item_decision["product_name"] != source_item["normalized_designation"]:
            raise builder.WorkflowError(f"schematic designation changed: {item_id}")
        layout = selection["layout"]
        if layout.get("calculation_schema") != modules.MIXED_LAYOUT_SCHEMA:
            raise builder.WorkflowError(f"installed geometry required: {item_id}")
        inventory = layout["installed_inventory"]
        qf_products = {}
        accessories = {}
        for instance in inventory["board"]["instances"]:
            component_id = instance["component_id"]
            product_id = instance["product_id"]
            if component_id is None:
                accessories[instance["id"]] = product_id
            else:
                product = inventory["products"][product_id]
                if product["manufacturer"] != item_decision["manufacturer"]:
                    raise builder.WorkflowError(f"QF manufacturer mismatch: {item_id}")
                qf_products[component_id] = product_id
        if board["qf_products"] != qf_products:
            raise builder.WorkflowError(f"QF product mapping mismatch: {item_id}")
        if board["accessories"] != accessories:
            raise builder.WorkflowError(
                f"installed accessory coverage mismatch: {item_id}"
            )
        for field in ("connections", "technical_requirements"):
            ref = builder.exact_object(
                board[field], field, {"path", "sha256", "locator"}
            )
            path = decision_text(ref["path"], field)
            sha256 = decision_text(ref["sha256"], field)
            decision_text(ref["locator"], field)
            if (path, sha256) not in raw_sources:
                raise builder.WorkflowError(f"unbound {field} source: {item_id}")


def prepare_review(
    case_id: str,
    extraction_version: str,
    review_json: Path,
    review_sha256: str,
    *,
    canonical_root: Path = builder.CANONICAL_ROOT,
) -> dict[str, Any]:
    """Return a packet for Human Review after validating every pinned input."""
    review_input = builder.load_decisions_input(review_json)
    if review_input.sha256 != review_sha256:
        raise builder.WorkflowError("review decision input SHA-256 mismatch")
    review = builder.exact_object(
        review_input.data,
        "schematic review input",
        {
            "schema_version",
            "case_id",
            "extraction_version",
            "version_binding_sha256",
            "igor_decision_locator",
            "composition_decisions",
            "sizing_request",
            "module_evidence",
            "boards",
        },
    )
    if (
        review["schema_version"] != INPUT_SCHEMA
        or review["case_id"] != case_id
        or review["extraction_version"] != extraction_version
    ):
        raise builder.WorkflowError("schematic review input identity mismatch")
    decision_text(review["igor_decision_locator"], "Igor decision locator")
    version_sha = decision_text(
        review["version_binding_sha256"], "version binding SHA-256"
    )
    paths = builder.resolve_case_paths(
        case_id, canonical_root=canonical_root, extraction_version=extraction_version
    )
    source = builder.load_snapshot(paths, schematic_binding_sha256=version_sha)
    facts = source_facts(source)
    intake_name = "governed-intake.json"
    intake_bytes = evidence.safe_bytes(
        paths.manifest.with_name(intake_name), source.hashes[intake_name]
    )
    facts["governed_intake"] = builder.parse_strict_json_object(
        intake_bytes, intake_name
    )

    for name in ("composition_decisions", "sizing_request", "module_evidence"):
        ref = builder.exact_object(review[name], name, {"path", "sha256"})
        path = Path(builder.strict_nonempty_string(ref["path"], name))
        digest = builder.strict_nonempty_string(ref["sha256"], name)
        evidence.safe_bytes(path, digest)
    decisions_ref, sizing_ref = (
        review["composition_decisions"],
        review["sizing_request"],
    )
    decisions = builder.load_decisions_input(Path(decisions_ref["path"]))
    if decisions.sha256 != decisions_ref["sha256"]:
        raise builder.WorkflowError("composition decisions SHA-256 mismatch")
    request = sizing.load_request(Path(sizing_ref["path"]), sizing_ref["sha256"])
    if request.get("schema_version") != QUOTE_REQUEST_SCHEMA:
        raise builder.WorkflowError("schematic review requires QUOTE_PREPARATION v0.5")
    state = builder.apply_batch_decisions(
        source, decisions, case_id=case_id, automatic_cabinet=True
    )
    decision_text(state.supply_boundary, "supply boundary")
    builder.prepare_cabinet_sizing(case_id, state, request, review["module_evidence"])
    verify_inventory_decisions(review["boards"], source, state)
    builder.ensure_ready_for_approval(state)

    # Reverify the canonical PDF, intake, operator package and extraction before output.
    builder.validate_case_directory(paths, schematic_binding_sha256=version_sha)
    sizing.load_request(Path(sizing_ref["path"]), sizing_ref["sha256"])
    evidence.safe_bytes(decisions.path, decisions.sha256)
    evidence.safe_bytes(review_input.path, review_input.sha256)
    assert state.batch_decisions is not None
    # The confirmed builder's audit field presumes a separate direct approval.
    for record in state.batch_decisions["expanded_component_decisions"]:
        if record["substitution"] is not None:
            del record["substitution"]["explicit_igor_decision"]
    return {
        "schema_version": OUTPUT_SCHEMA,
        "status": "HUMAN_REVIEW_REQUIRED",
        "composition_confirmed": False,
        "human_approval_1_granted": False,
        "decision_provenance_status": "OPERATOR_SUPPLIED_UNVERIFIED",
        "electrical_applicability_status": "NOT_VERIFIED",
        "case_id": case_id,
        "extraction_version": extraction_version,
        "extraction_sha256": source.hashes,
        "source_facts": facts,
        "review_input_sha256": review_input.sha256,
        "review_input": review,
        "composition_decisions": state.batch_decisions,
        "supply_boundary": state.supply_boundary,
        "candidate_items": state.items,
        "cabinet_sizing": state.cabinet_sizing,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--extraction-version", required=True)
    parser.add_argument("--review-json", type=Path, required=True)
    parser.add_argument("--review-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        packet = prepare_review(
            args.case_id, args.extraction_version, args.review_json, args.review_sha256
        )
        sys.stdout.buffer.write(builder.canonical_json_bytes(packet))
    except (
        OSError,
        ValueError,
        builder.WorkflowError,
        sizing.SizingHold,
        KeyError,
        TypeError,
        AttributeError,
        RecursionError,
    ) as exc:
        print(f"HOLD: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
