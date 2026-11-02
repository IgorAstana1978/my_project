"""Read-only WU15 projection of separately admitted technical batch decisions.

Registry admission is external Human authority, never inferred from JSON claims.
This module does not publish decisions, confirm a composition or select cabinets.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import cabinet_sizing_evidence as evidence
from cabinet_sizing import SizingHold, apparatus_hash, require
from governed_case_intake import _pairs

SCHEMA = "cabinet_sizing.pragmatic_decisions.v0.1"
MANIFEST_SHA = "92ebc785cf3002967ba1282b4c669fa854e4cd54f16c72e7af8584c105710668"
REVIEW_SHA = "25bc56874349e33baad85b5df51ceb8011344972d18aeb341da77642c6a4ae2b"
NAMES = {"ITEM-001": "ЩО6", "ITEM-002": "НЩР", "ITEM-003": "АВР"}
INSTALL_TYPES = {
    "ВА88-32": "mccb_up_to_100a",
    "АВДТ32": "diff_1p_n",
    "ВН-32": "load_switch_3p",
}


def source_fact(case_id: str, item: Any, binding: Any, data: Any) -> dict[str, Any]:
    """Rebuild the exact normalized apparatus without running an approval prompt."""
    builder = importlib.import_module(
        "build_confirmed_composition_from_preliminary_bundle"
    )
    try:
        return _source_fact(case_id, item, binding, data)
    except SizingHold:
        raise
    except (builder.WorkflowError, ValueError, KeyError, TypeError, OSError) as exc:
        raise SizingHold("HOLD_PRAGMATIC_DECISIONS_INVALID") from exc


def _source_fact(case_id: str, item: Any, binding: Any, data: Any) -> dict[str, Any]:
    builder = importlib.import_module(
        "build_confirmed_composition_from_preliminary_bundle"
    )

    require(
        isinstance(data, dict)
        and set(data) == {"schema_version", "case_id", "base_source_fact", "decisions"}
        and data["schema_version"] == SCHEMA,
        "HOLD_PRAGMATIC_DECISIONS_SCHEMA",
    )
    require(
        case_id == data["case_id"] == evidence.WU15_CASE,
        "HOLD_SOURCE_FACT_COMPOSITION_BINDING",
    )
    require(
        data["base_source_fact"] == evidence.pragmatic_default_binding(),
        "HOLD_PRAGMATIC_DECISIONS_BASE",
    )
    # Both the adapter AND the decisions must have separate exact admission.
    # A caller SHA or an approval flag cannot extend AUTHORIZED.
    require(
        evidence.read(binding, "pragmatic_source_fact") == data,
        "HOLD_PRAGMATIC_DECISIONS_DRIFT",
    )
    decisions = evidence.read(data["decisions"], "pragmatic_source_fact")
    paths = builder.resolve_case_paths(case_id, canonical_root=evidence.WU15_CASE_ROOT)
    pins = {
        builder.MANIFEST_NAME: MANIFEST_SHA,
        builder.DRAFT_NAME: evidence.WU15_DRAFT_SHA,
        builder.REVIEW_NAME: REVIEW_SHA,
    }
    raw = {
        name: evidence.safe_bytes(evidence.WU15_CASE_ROOT / case_id / name, sha)
        for name, sha in pins.items()
    }
    draft = json.loads(
        raw[builder.DRAFT_NAME].decode("utf-8"), object_pairs_hook=_pairs
    )
    builder.validate_existing_contracts(paths)
    builder.check_review_card_consistency(raw[builder.REVIEW_NAME], draft)
    builder.validate_identifier_integrity(draft)
    builder.validate_source_metadata_integrity(draft)
    require(
        [i["item_id"] for i in draft["items"]] == list(NAMES)
        and [len(i["components"]) for i in draft["items"]] == [21, 13, 12],
        "HOLD_SOURCE_FACT_COMPOSITION_BINDING",
    )
    snapshot = builder.InputSnapshot(
        paths=paths,
        manifest_bytes=raw[builder.MANIFEST_NAME],
        draft_bytes=raw[builder.DRAFT_NAME],
        review_bytes=raw[builder.REVIEW_NAME],
        hashes=pins,
        draft=draft,
    )
    decision_snapshot = builder.load_decisions_input(Path(data["decisions"]["path"]))
    require(
        decision_snapshot.sha256 == data["decisions"]["sha256"]
        and decision_snapshot.data == decisions,
        "HOLD_PRAGMATIC_DECISIONS_DRIFT",
    )
    # Reuse coverage, red-flag, source SHA, quantity and manufacturer validation.
    # This is preparation only: no phrase, output, approval record or token.
    state = builder.apply_batch_decisions(
        snapshot, decision_snapshot, case_id=case_id, automatic_cabinet=True
    )
    for original, normalized, decision in zip(
        draft["items"], state.items, decisions["items"], strict=True
    ):
        require(
            normalized["product_name"] == NAMES[original["item_id"]],
            "HOLD_PRAGMATIC_DECISIONS_NAME",
        )
        # This adapter admits normalization, never electrical substitutions,
        # new apparatus, transfers between boards, or switching automation.
        require(
            all(g["substitution"] is None for g in decision["component_groups"]),
            "HOLD_PRAGMATIC_DECISIONS_SUBSTITUTION",
        )
        for source, final in zip(
            original["components"], normalized["components"], strict=True
        ):
            code = source["component_code_guess"]
            require(
                code in INSTALL_TYPES and final["install_type"] == INSTALL_TYPES[code],
                "HOLD_PRAGMATIC_DECISIONS_INSTALL_TYPE",
            )
            # Closed description forms preserve all nominal/pole/curve/RCD
            # parameters. Extra contradictory ratings cannot hide after a match.
            label = source["component_label_guess"]
            without_qf = label.split(" ", 1)[1]
            allowed = {
                f"{decision['manufacturer']}, {label}",
                f"{decision['manufacturer']}, {without_qf}",
            }
            require(
                final["component_label"] in allowed,
                "HOLD_PRAGMATIC_DECISIONS_DESCRIPTION",
            )
    selected = [i for i in state.items if i["item_id"] == item["item_id"]]
    require(
        len(selected) == 1 and apparatus_hash(selected[0]) == apparatus_hash(item),
        "HOLD_SOURCE_FACT_COMPOSITION_BINDING",
    )
    original = next(i for i in draft["items"] if i["item_id"] == item["item_id"])
    fact = evidence.pragmatic_source_fact(case_id, original, data["base_source_fact"])
    builder.assert_snapshot_unchanged(snapshot)
    builder.assert_decisions_unchanged(decision_snapshot)
    for name, sha in pins.items():
        evidence.safe_bytes(evidence.WU15_CASE_ROOT / case_id / name, sha)
    require(
        evidence.read(binding, "pragmatic_source_fact") == data
        and evidence.read(data["decisions"], "pragmatic_source_fact") == decisions,
        "HOLD_PRAGMATIC_DECISIONS_DRIFT",
    )
    return dict(
        fact,
        apparatus_sha256=apparatus_hash(item),
        raw_sources=[
            *fact["raw_sources"],
            *[
                {"path": str(paths.case_dir / name), "sha256": sha}
                for name, sha in pins.items()
                if name != builder.DRAFT_NAME
            ],
            dict(data["decisions"]),
        ],
    )
