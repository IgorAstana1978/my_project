"""Future content adapter with separate exact governed v0.3 publication."""

from __future__ import annotations

import argparse
import copy
from datetime import datetime
from pathlib import Path
from typing import Any

import build_dinva_document_from_case as bridge
import dinva_future_content as content
from future_case_hardening import future_only, require

SOURCE_SCHEMA = "dinva_future_case_document_source.v0.1"


def prepare_core(source: dict[str, Any], binding: dict[str, str]) -> dict[str, Any]:
    require(
        set(source) == bridge.SOURCE_KEYS | {"context"}, "future source fields mismatch"
    )
    require(source["schema_version"] == SOURCE_SCHEMA, "future source schema mismatch")
    future_only(source["context"])
    require(
        source["context"]["case_id"] == source["case_id"],
        "future Case identity mismatch",
    )
    normalized = copy.deepcopy(source)
    normalized.pop("context")
    normalized["schema_version"] = bridge.SOURCE_SCHEMA
    for item in normalized["items"]:
        require(
            set(item) == bridge.ITEM_KEYS | {"technical_display"},
            "future item fields mismatch",
        )
        item.pop("technical_display")
    terms = normalized["terms"]
    require(
        terms["payment"] is None, "payment override needs a governed commercial role"
    )
    terms["delivery"] = terms.get("delivery") or bridge.DEFAULT_DELIVERY
    terms["validity"] = terms.get("validity") or "3 банковских дней"
    lines = content.commercial_block(terms)
    require(
        terms["commercial_lines"] in (None, [], lines),
        "unsupported commercial override",
    )
    # Reuse original core/defaults/arithmetic shapes. No source bytes are rewritten.
    terms["commercial_lines"] = [terms["manufacturing_lead_time"], terms["delivery"]]
    core = bridge.prepare_core(normalized, binding)
    core["schema_version"] = content.DOCUMENT_VERSION
    canonical = [b for b in source["source_bindings"] if b["role"] == "CANONICAL_744_1"]
    require(len(canonical) == 1, "canonical reference binding required")
    core["presentation_policy"] = {
        "policy_id": content.POLICY_ID,
        "policy_sha256": bridge.defaults_source().sha256,
        "canonical_sha256": canonical[0]["sha256"],
        "source_sha256": binding["sha256"],
    }
    core["presentation_policy"]["policy_sha256"] = bridge.digest(
        Path(content.__file__).read_bytes()
    )
    for i, (original, item) in enumerate(
        zip(source["items"], core["items"], strict=True)
    ):
        item["display_policy"] = content.POLICY_ID
        item["apparatus"].update(
            text=content.technical_display(original["technical_display"]),
            source_locator=f"/items/{i}/technical_display",
        )
    core["terms"]["commercial_lines"] = [
        {
            "source_order": i + 1,
            "text": line,
            "source_sha256": binding["sha256"],
            "source_locator": "/terms",
        }
        for i, line in enumerate(lines)
    ]
    core["terms"]["manufacturing_lead_time_provenance"].update(
        source_order=6,
        source_text=lines[5],
        source_locator="/terms",
        normalization_rule="CANONICAL_744_1_EXACT_APPROVED_LEAD_INSERTION",
    )
    return core


def preflight(
    case: bridge.Snapshot,
    approval: bridge.Snapshot,
    *,
    allow_test_profile: bool = False,
) -> bridge.Plan:
    """Reuse bridge snapshots/core/validators without rebinding historical policy."""
    require(case.path != approval.path, "Case and approval must be separate")
    require(
        not bridge.renderer.is_inside_project(case.path)
        and not bridge.renderer.is_inside_project(approval.path),
        "real source must be outside Git",
    )
    source = case.payload()
    from build_future_case_document_source import COMPOSITION_ROLE, verify_source

    chain = None
    if not bridge.renderer.test_mode(allow_test_profile) or any(
        b["role"] == COMPOSITION_ROLE for b in source["source_bindings"]
    ):
        chain = verify_source(case)
    decision = bridge.obj(approval.payload(), bridge.APPROVAL_KEYS, "approval")
    require(
        decision["schema_version"] == bridge.APPROVAL_SCHEMA
        and decision["case_id"] == source["case_id"],
        "approval identity mismatch",
    )
    require(
        decision["authority"] == "IGOR_DIRECT_HUMAN_APPROVAL"
        and decision["approved_by"] == "Igor",
        "approval authority mismatch",
    )
    require(
        all(
            decision[k] is True
            for k in (
                "technical_composition_approved",
                "prices_approved",
                "commercial_terms_approved",
                "rendering_authorized",
            )
        )
        and decision["client_send_authorized"] is False,
        "approval scope missing",
    )
    require(
        datetime.fromisoformat(decision["approved_at"]).utcoffset() is not None
        and bool(decision["approval_id"]),
        "approval provenance missing",
    )
    require(
        decision["approved_case_source_sha256"] == case.sha256,
        "approved source SHA mismatch",
    )
    snapshots = [case, approval, bridge.defaults_source()]
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
        {
            "role": bridge.DEFAULTS_ROLE,
            "path": str(snapshots[2].path),
            "sha256": snapshots[2].sha256,
        },
    ]
    for role, path in (
        ("GOVERNED_744_CONTENT_POLICY", Path(content.__file__)),
        ("GOVERNED_FUTURE_DOCUMENT_ADAPTER", Path(__file__)),
    ):
        snap = bridge.Snapshot(path.resolve(), path.read_bytes())
        snapshots.append(snap)
        bindings.append({"role": role, "path": str(snap.path), "sha256": snap.sha256})
    roles = {b["role"] for b in bindings}
    for raw in source["source_bindings"]:
        b = bridge.obj(raw, {"role", "path", "sha256"}, "upstream")
        require(b["role"] not in roles, "duplicate/reserved source role")
        roles.add(b["role"])
        require(Path(b["path"]).is_absolute(), "upstream path must be absolute")
        snap = bridge.load(Path(b["path"]), b["sha256"])
        require(snap.path not in (case.path, approval.path), "cyclic source binding")
        snapshots.append(snap)
        bindings.append(
            {"role": b["role"], "path": str(snap.path), "sha256": snap.sha256}
        )
    if chain is not None:
        known = {(b["path"], b["sha256"]) for b in bindings}
        for index, snap in enumerate(chain.snapshots):
            if (str(snap.path), snap.sha256) in known:
                continue
            role = f"FUTURE_FLOW_SOURCE_{index}"
            require(role not in roles, "duplicate/reserved future source role")
            roles.add(role)
            known.add((str(snap.path), snap.sha256))
            snapshots.append(snap)
            bindings.append(
                {"role": role, "path": str(snap.path), "sha256": snap.sha256}
            )
    document = prepare_core(source, bindings[0])
    fp = bridge.renderer.document_fingerprint(document)
    require(
        fp == decision["approved_document_fingerprint"], "approved fingerprint mismatch"
    )
    document["document_fingerprint"] = fp
    document["approval_provenance"] = {
        "status": "APPROVED",
        "authority": decision["authority"],
        "approval_id": decision["approval_id"],
        "approved_at": decision["approved_at"],
        "approval_scope": "DINVA_FUTURE_744_CONTENT_MODEL_ONLY",
        "approved_document_fingerprint": fp,
        "source_bindings": bindings,
        "source_sha256s": [b["sha256"] for b in bindings],
        "rendering_authorized": True,
        "client_send_authorized": False,
    }
    bridge.renderer.validate_document(document, allow_test_profile=allow_test_profile)
    bridge.validator.validate_document_contract(
        document, allow_test_profile=allow_test_profile
    )
    plan = bridge.Plan(document, tuple(snapshots))
    if chain is not None:
        plan = bridge.Plan(document, (*plan.snapshots, *chain.snapshots))
    plan.recheck()
    return plan


def preview_accepted(
    plan: bridge.Plan,
    components: list[list[dict[str, Any]]],
    canonical: bridge.Snapshot,
    profile: dict[str, Any],
) -> dict[str, Any]:
    """Display/layout diagnostics only. No repricing, approval promotion or output."""
    plan.recheck()
    require(canonical.sha256 == content.CANONICAL_SHA, "preview canonical identity")
    require(canonical.path.read_bytes() == canonical.raw, "preview canonical drift")
    require(
        len(components) == len(plan.document["items"]), "preview item count mismatch"
    )
    prospective = copy.deepcopy(plan.document)
    displays = []
    for i, (item, parts) in enumerate(
        zip(prospective["items"], components, strict=True)
    ):
        require(
            all(
                c["source_locator"] == f"/items/{i}/detailed_technical_composition"
                for c in parts
            ),
            "preview engineering locator mismatch",
        )
        require(
            all(
                c["unit"] != "note"
                or c["label"] in item["detailed_technical_composition"]
                for c in parts
            ),
            "preview note lacks exact engineering source",
        )
        text = content.technical_display(parts)
        displays.append(text)
        item["apparatus"]["text"] = text
        item["display_policy"] = content.POLICY_ID
    lines = content.commercial_block(prospective["terms"])
    prospective["terms"]["commercial_lines"] = [{"text": line} for line in lines]
    layout = bridge.renderer.dynamic_layout_plan(
        profile["presentation_contract"], prospective
    )
    plan.recheck()
    require(canonical.path.read_bytes() == canonical.raw, "preview canonical changed")
    return {
        "status": "UNAPPROVED_READ_ONLY_DISPLAY_PREVIEW",
        "accepted_document_sha256": bridge.digest(plan.encoded),
        "canonical_sha256": canonical.sha256,
        "full_engineering_unchanged": True,
        "prices_unchanged": True,
        "accepted_grand_total_kzt": plan.document["approved_grand_total_kzt"],
        "display_texts": displays,
        "commercial_lines": lines,
        "prospective_rows": [
            {"row": r["row"], "kind": r["kind"], "height": r["height"]}
            for r in layout["rows"]
        ],
        "real_render_authorized": False,
        "client_send_authorized": False,
        "new_exact_content_approval_required": True,
    }


def publication_authorization(plan: bridge.Plan, output: Path) -> str:
    return (
        "IGOR_DINVA_FUTURE_DOCUMENT_PUBLICATION_AUTHORIZED"
        "|ACTION=IMMUTABLE_DOCUMENT_V0_3_PUBLICATION"
        f"|CASE_SHA256={plan.snapshots[0].sha256}"
        f"|APPROVAL_SHA256={plan.snapshots[1].sha256}"
        f"|DOCUMENT_FINGERPRINT={plan.document['document_fingerprint']}"
        f"|DOCUMENT_SHA256={bridge.digest(plan.encoded)}"
        f"|OUTPUT_PATH_SHA256={bridge.digest(str(output.resolve()).encode('utf-8'))}"
    )


def publish(
    candidate: bridge.Plan,
    output: Path,
    authorization: str,
    *,
    allow_test_profile: bool = False,
) -> Path:
    from build_future_case_document_source import publish_exact, verify_source

    def regenerate() -> bridge.Plan:
        chain = verify_source(candidate.snapshots[0])
        fresh = preflight(
            candidate.snapshots[0],
            candidate.snapshots[1],
            allow_test_profile=allow_test_profile,
        )
        return bridge.Plan(fresh.document, (*fresh.snapshots, *chain.snapshots))

    fresh = regenerate()
    require(fresh.encoded == candidate.encoded, "future document changed after review")
    return publish_exact(
        fresh,
        output,
        authorization,
        publication_authorization(fresh, output),
        regenerate,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("case-source", "case-approval"):
        parser.add_argument("--" + name, type=Path, required=True)
        parser.add_argument("--" + name + "-sha256", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--authorization")
    args = parser.parse_args()
    try:
        plan = preflight(
            bridge.load(args.case_source, args.case_source_sha256),
            bridge.load(args.case_approval, args.case_approval_sha256),
        )
        if args.output is not None:
            bridge.output_path(plan, args.output)
        print("FUTURE_DOCUMENT_PREFLIGHT=PASS; PUBLICATION=CLOSED")
        print("CANDIDATE_SHA256=" + bridge.digest(plan.encoded))
        if args.publish:
            require(args.output is not None, "exact publication output required")
            publish(plan, args.output, args.authorization or "")
            print("FUTURE_DOCUMENT_PUBLICATION=PASS; CLIENT_SEND=CLOSED")
        else:
            require(
                args.authorization is None,
                "authorization requires explicit publication",
            )
        return 0
    except (ValueError, OSError, KeyError) as exc:
        print(f"HOLD: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
