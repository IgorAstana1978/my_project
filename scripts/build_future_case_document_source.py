"""Bound future input/result/document-source producers; no approval promotion."""

from __future__ import annotations

import argparse
import copy
import json
import os
import tempfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import build_dinva_document_from_case as bridge
import build_price_calculator_input_draft_from_confirmed_composition as input_builder
import run_checked_price_calculator_from_completed_draft as runner
from future_case_hardening import future_input_projection, future_only, require
from price_baseline_contract import (
    DEFAULT_ACTIVE_SELECTOR,
    resolve_active_price_baseline,
)

RESULT_SCHEMA = "checked_future_pricing_result.v0.1"
REVIEW_SCHEMA = "future_document_review.v0.1"
COMPOSITION_ROLE = "CONFIRMED_FUTURE_COMPOSITION"
CALCULATION_ROLE = "CHECKED_FUTURE_CALCULATION"
REVIEW_ROLE = "FUTURE_DOCUMENT_REVIEW"


class FlowPlan(bridge.Plan):
    @property
    def encoded(self) -> bytes:
        # The existing completed-input validator requires CSV-column key order.
        # Preserve producer order; do not change the calculator contract.
        return (
            json.dumps(self.document, ensure_ascii=False, allow_nan=False, indent=2)
            + "\n"
        ).encode("utf-8")


def binding(role: str, snapshot: bridge.Snapshot) -> dict[str, str]:
    return {"role": role, "path": str(snapshot.path), "sha256": snapshot.sha256}


def bound_snapshot(record: dict[str, str]) -> bridge.Snapshot:
    bridge.obj(record, {"role", "path", "sha256"}, "binding")
    require(Path(record["path"]).is_absolute(), "binding path must be absolute")
    return bridge.load(Path(record["path"]), record["sha256"])


def plan(payload: dict[str, Any], snapshots: list[bridge.Snapshot]) -> bridge.Plan:
    policy = bridge.Snapshot(Path(__file__).resolve(), Path(__file__).read_bytes())
    result = FlowPlan(payload, tuple([*snapshots, policy]))
    result.recheck()
    return result


def pricing_input(confirmed: bridge.Snapshot, operator: bridge.Snapshot) -> bridge.Plan:
    data = confirmed.payload()
    future_only(data.get("future_context"))
    completion = bridge.obj(
        operator.payload(),
        {
            "completed_by",
            "completed_at",
            "completion_note",
        },
        "operator completion",
    )
    for key in completion:
        bridge.text(completion[key], key)
    require(
        datetime.fromisoformat(completion["completed_at"]).utcoffset() is not None,
        "operator completion timestamp requires timezone",
    )
    result = input_builder.BuildResult(confirmed.path, operator.path)
    payload = input_builder.build_output_payload(data, result)
    require(
        payload is not None and not result.red_flags,
        "future input builder: " + "; ".join(result.red_flags),
    )
    payload = copy.deepcopy(dict(payload))
    payload["operator_completion"] = completion
    future_input_projection({"path": str(confirmed.path), "sha256": confirmed.sha256})
    return plan(payload, [confirmed, operator])


def calculation(
    completed: bridge.Snapshot,
    costs: bridge.Snapshot,
    selector: Path = DEFAULT_ACTIVE_SELECTOR,
) -> bridge.Plan:
    data = completed.payload()
    technical = data["source"]["future_technical_binding"]
    confirmed = bridge.load(Path(technical["path"]), technical["sha256"])
    context = confirmed.payload()["future_context"]
    future_only(context)
    baseline = resolve_active_price_baseline(selector)
    snapshots = [
        completed,
        costs,
        confirmed,
        bridge.load(selector, bridge.digest(selector.read_bytes())),
        bridge.load(baseline.path, baseline.sha256),
    ]
    if baseline.manifest_path is not None:
        snapshots.append(bridge.load(baseline.manifest_path, baseline.manifest_sha256))
    for item in costs.payload()["items"]:
        for key in ("cabinet_cost", "work_source"):
            record = item[key]
            snapshots.append(bridge.load(Path(record["path"]), record["sha256"]))
    for item in confirmed.payload()["items"]:
        for fields in item["technical_classification"]["overrides"].values():
            for record in fields.values():
                snapshots.append(bridge.load(Path(record["path"]), record["sha256"]))
    result = runner.run_checked_price_calculator_from_completed_draft(
        completed.path,
        None,
        active_selector_path=selector,
        future_cost_inputs=costs.path,
        expected_future_cost_inputs_sha256=costs.sha256,
    )
    require(
        result.status == "PASS",
        "checked calculation HOLD: " + "; ".join(result.red_flags),
    )
    items = []
    for item, application in zip(
        confirmed.payload()["items"], result.future_rule_applications, strict=True
    ):
        require(item["item_id"] == application["item_id"], "calculated item mismatch")
        unit = application["price"]["unit_price_kzt"]
        quantity = item["quantity"]
        items.append(
            {
                "item_id": item["item_id"],
                "quantity": quantity,
                "unit_price_kzt": unit,
                "line_total_kzt": unit * quantity,
                "rule_application": application,
            }
        )
    payload = {
        "schema_version": RESULT_SCHEMA,
        "status": "DRAFT_NOT_APPROVED",
        "context": context,
        "items": items,
        "grand_total_kzt": result.overall_preliminary_total,
        "completed_input": binding("COMPLETED_FUTURE_INPUT", completed),
        "cost_inputs": binding("FUTURE_COST_INPUTS", costs),
        "selector": str(selector.resolve()),
        "source_bindings": [
            binding(f"CALCULATION_INPUT_{i}", s) for i, s in enumerate(snapshots)
        ],
        "client_send_authorized": False,
    }
    return plan(payload, snapshots)


def verify_calculation(result: bridge.Snapshot) -> bridge.Plan:
    data = result.payload()
    require(
        data["schema_version"] == RESULT_SCHEMA
        and data["status"] == "DRAFT_NOT_APPROVED"
        and data["client_send_authorized"] is False,
        "calculation contract mismatch",
    )
    for record in data["source_bindings"]:
        bound_snapshot(record)
    fresh = calculation(
        bound_snapshot(data["completed_input"]),
        bound_snapshot(data["cost_inputs"]),
        Path(data["selector"]),
    )
    require(
        fresh.encoded == result.raw,
        "checked calculation input/item/quantity/price/total drift",
    )
    return fresh


def document_source(
    confirmed: bridge.Snapshot,
    calculated: bridge.Snapshot,
    reviewed: bridge.Snapshot,
) -> bridge.Plan:
    fresh = verify_calculation(calculated)
    composition = confirmed.payload()
    context = composition["future_context"]
    future_only(context)
    prices = calculated.payload()
    require(prices["context"] == context, "calculation Case/context mismatch")
    require(
        any(
            s.path == confirmed.path and s.sha256 == confirmed.sha256
            for s in fresh.snapshots
        ),
        "calculation composition binding mismatch",
    )
    review = bridge.obj(
        reviewed.payload(),
        {
            "schema_version",
            "case_id",
            "metadata",
            "terms",
            "items",
            "approved_grand_total_kzt",
            "source_bindings",
        },
        "document review",
    )
    require(
        review["schema_version"] == REVIEW_SCHEMA
        and review["case_id"] == context["case_id"],
        "review Case/schema mismatch",
    )
    require(
        review["approved_grand_total_kzt"] == prices["grand_total_kzt"],
        "reviewed total mismatch",
    )
    require(
        [i["item_id"] for i in review["items"]]
        == [i["item_id"] for i in composition["items"]],
        "reviewed item inventory mismatch",
    )
    items = []
    for index, (item, price, display) in enumerate(
        zip(composition["items"], prices["items"], review["items"], strict=True)
    ):
        bridge.obj(
            display,
            {
                "item_id",
                "quantity",
                "approved_unit_price_kzt",
                "approved_line_total_kzt",
                "unit",
                "technical_display",
            },
            "reviewed item",
        )
        require(
            display["item_id"] == price["item_id"]
            and type(display["quantity"]) is int
            and display["quantity"] == item["quantity"] == price["quantity"],
            "reviewed item/quantity mismatch",
        )
        require(
            type(display["approved_unit_price_kzt"]) is int
            and display["approved_unit_price_kzt"] == price["unit_price_kzt"]
            and type(display["approved_line_total_kzt"]) is int
            and display["approved_line_total_kzt"] == price["line_total_kzt"],
            "reviewed price/total mismatch",
        )
        engineering = "; ".join(
            f"{c['component_code']} / {c['component_label']} — {c['quantity']}"
            for c in item["components"]
        )
        if composition["notes"]:
            engineering += "; " + "; ".join(composition["notes"])
        parts = copy.deepcopy(display["technical_display"])
        component_ids = [p.get("component_id") for p in parts if p["unit"] != "note"]
        require(
            component_ids == [c["component_id"] for c in item["components"]],
            "reviewed display component inventory mismatch",
        )
        by_id = {c["component_id"]: c for c in item["components"]}
        for part in parts:
            component_id = part.pop("component_id", None)
            if part["unit"] == "note":
                require(
                    component_id is None
                    and part["quantity"] is None
                    and part["label"] in engineering,
                    "reviewed note must have an exact engineering source",
                )
            else:
                component = by_id[component_id]
                role = item["technical_classification"]["roles"][component_id]
                expected_quantity = component["quantity"] * (
                    3 if role == "FUSE_GROUP" else 1
                )
                require(
                    type(part["quantity"]) in (int, float)
                    and part["quantity"] == expected_quantity,
                    "reviewed display component quantity mismatch",
                )
            require(
                part["source_locator"]
                == f"/items/{index}/detailed_technical_composition",
                "reviewed display locator mismatch",
            )
        items.append(
            {
                "item_id": item["item_id"],
                "name": item["product_name"],
                "unit": display["unit"],
                "quantity": item["quantity"],
                "detailed_technical_composition": engineering,
                "enclosure": item["cabinet"]["cabinet_label"],
                "approved_unit_price_kzt": price["unit_price_kzt"],
                "approved_line_total_kzt": price["line_total_kzt"],
                "technical_display": parts,
            }
        )
    extra = [bound_snapshot(b) for b in review["source_bindings"]]
    payload = {
        "schema_version": "dinva_future_case_document_source.v0.1",
        "case_id": context["case_id"],
        "context": context,
        "metadata": copy.deepcopy(review["metadata"]),
        "terms": copy.deepcopy(review["terms"]),
        "items": items,
        "approved_grand_total_kzt": prices["grand_total_kzt"],
        "source_bindings": [
            binding(COMPOSITION_ROLE, confirmed),
            binding(CALCULATION_ROLE, calculated),
            binding(REVIEW_ROLE, reviewed),
            *copy.deepcopy(review["source_bindings"]),
        ],
    }
    return plan(payload, [confirmed, calculated, reviewed, *fresh.snapshots, *extra])


def verify_source(source: bridge.Snapshot) -> bridge.Plan:
    bindings = source.payload()["source_bindings"]
    selected = {}
    for role in (COMPOSITION_ROLE, CALCULATION_ROLE, REVIEW_ROLE):
        records = [b for b in bindings if b["role"] == role]
        require(len(records) == 1, "bound future flow role missing/ambiguous: " + role)
        selected[role] = bound_snapshot(records[0])
    fresh = document_source(
        selected[COMPOSITION_ROLE], selected[CALCULATION_ROLE], selected[REVIEW_ROLE]
    )
    require(
        fresh.encoded == source.raw,
        "document source composition/price/terms/lead time drift",
    )
    return fresh


def publish_exact(
    candidate: bridge.Plan,
    output: Path,
    authorization: str,
    expected: str,
    regenerate: Callable[[], bridge.Plan],
) -> Path:
    """Owned atomic publication; foreign outputs are never rollback targets."""
    fresh = regenerate()
    require(fresh.encoded == candidate.encoded, "candidate changed after review")
    candidate = fresh
    target = bridge.output_path(candidate, output)
    require(authorization == expected, "exact Human publication authorization required")
    candidate.recheck()
    descriptor, name = tempfile.mkstemp(prefix=".future-case-", dir=target.parent)
    staging = Path(name)
    owned = None
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(candidate.encoded)
            stream.flush()
            os.fsync(stream.fileno())
        stat = staging.stat()
        identity = (stat.st_dev, stat.st_ino)
        require(staging.read_bytes() == candidate.encoded, "staged bytes mismatch")
        candidate.recheck()
        os.link(staging, target)
        owned = identity
        stat = target.stat()
        require((stat.st_dev, stat.st_ino) == identity, "publication identity changed")
        candidate.recheck()
        require(target.read_bytes() == candidate.encoded, "published bytes mismatch")
        stat = target.stat()
        require((stat.st_dev, stat.st_ino) == identity, "publication identity changed")
        return target
    except BaseException:
        if owned is not None and target.exists():
            stat = target.stat()
            if (stat.st_dev, stat.st_ino) == owned:
                target.unlink()
        raise
    finally:
        staging.unlink(missing_ok=True)


def candidate_authorization(candidate: bridge.Plan, output: Path, action: str) -> str:
    inputs_sha = bridge.digest(
        bridge.encode([binding(str(i), s) for i, s in enumerate(candidate.snapshots)])
    )
    return (
        f"IGOR_FUTURE_FLOW_ARTIFACT_PUBLICATION_AUTHORIZED|ACTION={action}"
        f"|CANDIDATE_SHA256={bridge.digest(candidate.encoded)}"
        f"|INPUTS_SHA256={inputs_sha}"
        f"|OUTPUT_PATH_SHA256={bridge.digest(str(output.resolve()).encode('utf-8'))}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode", choices=("pricing-input", "calculation", "document-source")
    )
    for name in (
        "confirmed",
        "operator",
        "completed",
        "costs",
        "calculated",
        "reviewed",
    ):
        parser.add_argument("--" + name, type=Path)
        parser.add_argument("--" + name + "-sha256")
    parser.add_argument("--selector", type=Path, default=DEFAULT_ACTIVE_SELECTOR)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--authorization")
    args = parser.parse_args()

    def load(name: str) -> bridge.Snapshot:
        require(
            getattr(args, name) is not None
            and getattr(args, name + "_sha256") is not None,
            name + " exact path and SHA required",
        )
        return bridge.load(getattr(args, name), getattr(args, name + "_sha256"))

    def prepare() -> bridge.Plan:
        if args.mode == "pricing-input":
            return pricing_input(load("confirmed"), load("operator"))
        if args.mode == "calculation":
            return calculation(load("completed"), load("costs"), args.selector)
        return document_source(load("confirmed"), load("calculated"), load("reviewed"))

    try:
        candidate = prepare()
        bridge.output_path(candidate, args.output)
        print("FUTURE_FLOW_PREFLIGHT=PASS; HUMAN_APPROVAL=NOT_CREATED")
        print("CANDIDATE_SHA256=" + bridge.digest(candidate.encoded))
        if args.publish:
            publish_exact(
                candidate,
                args.output,
                args.authorization or "",
                candidate_authorization(candidate, args.output, args.mode),
                prepare,
            )
            print("IMMUTABLE_CANDIDATE_PUBLICATION=PASS")
        else:
            require(
                args.authorization is None,
                "authorization requires explicit publication",
            )
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"HOLD: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
