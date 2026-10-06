from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import build_future_case_document_source as flow  # type: ignore[import-not-found]
import build_future_dinva_document as future  # type: ignore[import-not-found]
import pytest
from openpyxl import load_workbook  # type: ignore[import-untyped]
from test_build_confirmed_composition_from_preliminary_bundle import (
    builder,
    create_bundle,
    valid_batch_decisions,
)
from test_build_dinva_document_from_case import source_payload
from test_dinva_v0_5_print_successor import print_successor
from test_future_case_hardening import binding, price_chain
from test_render_dinva_classic_quote_invoice import canonical_file

bridge = flow.bridge


def snapshot(path: Path, value: Any) -> Any:
    path.write_bytes(bridge.encode(value))
    return bridge.load(path, bridge.digest(path.read_bytes()))


def materialize(candidate: Any, output: Path, action: str, regenerate: Any) -> Any:
    flow.publish_exact(
        candidate,
        output,
        flow.candidate_authorization(candidate, output, action),
        flow.candidate_authorization(candidate, output, action),
        regenerate,
    )
    return bridge.load(output, bridge.digest(output.read_bytes()))


def composition_inputs(tmp_path: Path) -> dict[str, Any]:
    def equipment(draft: dict[str, Any]) -> None:
        draft["red_flags"] = ["Synthetic source warning."]
        draft["assumptions"] = ["Synthetic technical extraction assumption."]
        draft["items"][0]["quantity_guess"] = 2
        draft["items"][0]["components"][0].update(
            component_code_guess="MCCB",
            component_label_guess="Breaker 3P 63A",
            install_type_guess="mccb_up_to_100a",
        )

    root, draft = create_bundle(tmp_path, mutate_draft=equipment)
    case = root / "CASE-TEST-001"
    decisions = valid_batch_decisions(case, draft)
    decisions["items"][0]["manufacturer"] = "EKF"
    decisions["items"][0]["quantity"] = 2
    group = decisions["items"][0]["component_groups"][0]
    group.update(
        final_description="EKF, Breaker 3P 63A", install_type="mccb_up_to_100a"
    )
    dp = snapshot(tmp_path / "composition-review.json", decisions)
    context = {
        "case_id": case.name,
        "case_state": "NEW_FUTURE",
        "future_cases_only": True,
        "historical_repricing_authorized": False,
    }
    classification = {
        "family": "ЩР",
        "execution": "STANDARD",
        "circuits": [
            {
                "circuit_id": "INPUT",
                "conductor_mm2": 25,
                "protection_component_ids": ["COMP-001"],
            }
        ],
        "roles": {"COMP-001": "POWER_BREAKER"},
        "categories": {"COMP-001": "MCCB 3P 16-63A"},
        "fuses": {},
        "interlocks": {"mechanical": False, "electrical": False},
        "overrides": {},
    }
    rp = snapshot(
        tmp_path / "future-review.json",
        {
            "schema_version": "future_composition_review.v0.1",
            "case_id": case.name,
            "draft_id": draft["draft_id"],
            "input_sha256": decisions["input_sha256"],
            "future_context": context,
            "items": [
                {"item_id": "ITEM-001", "technical_classification": classification}
            ],
        },
    )
    return {"root": root, "case": case, "decisions": dp, "review": rp}


def build_composition(inputs: dict[str, Any], **kwargs: Any) -> Any:
    return builder.run_builder(
        case_id=inputs["case"].name,
        confirmation_id="SYNTHETIC-COMPOSITION",
        approval_channel="synthetic_test_only",
        canonical_root=inputs["root"],
        decisions_json=inputs["decisions"].path,
        future_review_json=inputs["review"].path,
        future_review_sha256=inputs["review"].sha256,
        output_fn=lambda _: None,
        **kwargs,
    )


@pytest.fixture
def chain(tmp_path: Path, monkeypatch: Any) -> dict[str, Any]:
    monkeypatch.setenv("DINVA_RENDERER_TEST_MODE", "1")
    inputs = composition_inputs(tmp_path)
    result = build_composition(inputs, input_fn=lambda _: builder.APPROVAL_PHRASE)
    assert result.status == "PASS", result.red_flags
    cp = inputs["case"] / "confirmed" / builder.ARTIFACT_NAME
    confirmed = bridge.load(cp, bridge.digest(cp.read_bytes()))
    operator = snapshot(
        tmp_path / "operator.json",
        {
            "completed_by": "Synthetic operator",
            "completed_at": "2026-10-06T15:00:00+05:00",
            "completion_note": "Synthetic source review",
        },
    )

    def make_input() -> Any:
        return flow.pricing_input(confirmed, operator)

    completed = materialize(
        make_input(), tmp_path / "completed.json", "pricing-input", make_input
    )
    price_chain(tmp_path, monkeypatch)
    import future_case_hardening as rules  # type: ignore[import-not-found]

    monkeypatch.setattr(
        flow, "resolve_active_price_baseline", rules.resolve_active_price_baseline
    )
    cabinet = {
        **binding(tmp_path, "cabinet-cost.json", 10000),
        "role": "ENCLOSURE_COST",
    }
    work = binding(tmp_path, "work-cost.json", 6000)
    costs = snapshot(
        tmp_path / "costs.json",
        {
            "case_id": inputs["case"].name,
            "items": [
                {"item_id": "ITEM-001", "cabinet_cost": cabinet, "work_source": work}
            ],
        },
    )
    selector = tmp_path / "selector.json"
    # The existing synthetic price-chain fixture isolates price authority.
    selector.write_bytes(b"SYNTHETIC SELECTOR")

    def make_calc() -> Any:
        return flow.calculation(completed, costs, selector)

    calculated = materialize(
        make_calc(), tmp_path / "calculation.json", "calculation", make_calc
    )
    p = calculated.payload()["items"][0]
    base = source_payload(tmp_path, inputs["case"].name, 1)
    base["metadata"]["amount_words"]["amount_kzt"] = calculated.payload()[
        "grand_total_kzt"
    ]
    base["terms"].update(commercial_lines=None, validity=None, delivery=None)
    canonical = snapshot(tmp_path / "canonical.synthetic.xls", {"SYNTHETIC": True})
    review = snapshot(
        tmp_path / "document-review.json",
        {
            "schema_version": flow.REVIEW_SCHEMA,
            "case_id": inputs["case"].name,
            "metadata": base["metadata"],
            "terms": base["terms"],
            "approved_grand_total_kzt": calculated.payload()["grand_total_kzt"],
            "items": [
                {
                    "item_id": "ITEM-001",
                    "quantity": p["quantity"],
                    "approved_unit_price_kzt": p["unit_price_kzt"],
                    "approved_line_total_kzt": p["line_total_kzt"],
                    "unit": "компл.",
                    "technical_display": [
                        {
                            "component_id": "COMP-001",
                            "section": "",
                            "label": "EKF, Breaker 3P 63A",
                            "rating": "",
                            "quantity": 2,
                            "unit": "шт.",
                            "group_size": 1,
                            "source_locator": "/items/0/detailed_technical_composition",
                        }
                    ],
                }
            ],
            "source_bindings": [flow.binding("CANONICAL_744_1", canonical)],
        },
    )

    def make_source() -> Any:
        return flow.document_source(confirmed, calculated, review)

    source = materialize(
        make_source(), tmp_path / "document-source.json", "document-source", make_source
    )
    core = future.prepare_core(
        source.payload(), flow.binding("AUTHORITATIVE_DOCUMENT_TEXT_SOURCE", source)
    )
    approval = snapshot(
        tmp_path / "human-price-terms-approval.json",
        {
            "schema_version": bridge.APPROVAL_SCHEMA,
            "case_id": inputs["case"].name,
            "authority": "IGOR_DIRECT_HUMAN_APPROVAL",
            "approved_by": "Igor",
            "approved_at": "2026-10-06T15:05:00+05:00",
            "approval_id": "SYNTHETIC-ONLY",
            "approved_case_source_sha256": source.sha256,
            "approved_document_fingerprint": bridge.renderer.document_fingerprint(core),
            "technical_composition_approved": True,
            "prices_approved": True,
            "commercial_terms_approved": True,
            "rendering_authorized": True,
            "client_send_authorized": False,
        },
    )
    return {
        **inputs,
        "confirmed": confirmed,
        "operator": operator,
        "completed": completed,
        "costs": costs,
        "calculated": calculated,
        "document_review": review,
        "source": source,
        "approval": approval,
        "selector": selector,
    }


def test_new_case_all_producers_to_validated_xlsx(
    chain: dict[str, Any], tmp_path: Path, monkeypatch: Any
) -> None:
    source, approval = chain["source"], chain["approval"]
    plan = future.preflight(source, approval, allow_test_profile=True)
    output = tmp_path / "approved-v03.json"
    future.publish(
        plan,
        output,
        future.publication_authorization(plan, output),
        allow_test_profile=True,
    )
    assert output.read_bytes() == plan.encoded
    _, profile, _ = print_successor(tmp_path, monkeypatch)
    pp = tmp_path / "profile.json"
    ps = canonical_file(pp, profile)
    xlsx = tmp_path / "synthetic.xlsx"
    bridge.renderer.render(
        profile_path=pp,
        expected_profile_sha256=ps,
        document_path=output,
        expected_document_sha256=bridge.digest(output.read_bytes()),
        output=xlsx,
        allow_test_profile=True,
    )
    bridge.validator.validate_or_raise(
        xlsx,
        profile,
        ps,
        plan.document,
        bridge.digest(output.read_bytes()),
        allow_test_profile=True,
    )
    workbook = load_workbook(xlsx)
    assert (
        workbook.active["F17"].value == plan.document["items"][0]["apparatus"]["text"]
    )
    assert (
        plan.document["items"][0]["quantity"]
        == chain["confirmed"].payload()["items"][0]["quantity"]
    )
    assert (
        plan.document["approved_grand_total_kzt"]
        == chain["calculated"].payload()["grand_total_kzt"]
    )
    assert (
        plan.document["terms"]["manufacturing_lead_time"]
        == chain["document_review"].payload()["terms"]["manufacturing_lead_time"]
    )
    assert (
        chain["confirmed"].payload()["notes"][0]
        in plan.document["items"][0]["detailed_technical_composition"]
    )
    workbook.close()
    assert plan.document["approval_provenance"]["client_send_authorized"] is False
    receipt = json.loads(
        (chain["case"] / "confirmed" / builder.DECISIONS_NAME).read_bytes()
    )
    assert receipt["future_review"]["sha256"] == chain["review"].sha256


@pytest.mark.parametrize(
    "field",
    [
        "item_id",
        "quantity",
        "approved_unit_price_kzt",
        "approved_line_total_kzt",
        "total",
        "lead",
        "engineering",
        "enclosure",
    ],
)
def test_source_mismatch_even_with_new_caller_sha(
    chain: dict[str, Any], tmp_path: Path, field: str
) -> None:
    value = chain["source"].payload()
    if field == "total":
        value["approved_grand_total_kzt"] += 1
    elif field == "lead":
        value["terms"]["manufacturing_lead_time"] = "99 дней"
    elif field == "engineering":
        value["items"][0]["detailed_technical_composition"] = "other"
    elif field == "enclosure":
        value["items"][0]["enclosure"] = "other"
    elif field == "item_id":
        value["items"][0][field] = "OTHER"
    else:
        value["items"][0][field] += 1
    mutated = snapshot(tmp_path / "mutated-source.json", value)
    with pytest.raises(ValueError, match="drift"):
        flow.verify_source(mutated)


@pytest.mark.parametrize(
    "field", ["quantity", "unit_price_kzt", "line_total_kzt", "total", "item_id"]
)
def test_checked_result_is_recomputed(
    chain: dict[str, Any], tmp_path: Path, field: str
) -> None:
    value = chain["calculated"].payload()
    if field == "total":
        value["grand_total_kzt"] += 1
    elif field == "item_id":
        value["items"][0][field] = "OTHER"
    else:
        value["items"][0][field] += 1
    with pytest.raises(ValueError, match="drift"):
        flow.verify_calculation(snapshot(tmp_path / "bad-calculation.json", value))


@pytest.mark.parametrize(
    "field",
    [
        "quantity",
        "approved_unit_price_kzt",
        "approved_line_total_kzt",
        "item_id",
        "total",
    ],
)
def test_review_must_match_checked_result(
    chain: dict[str, Any], tmp_path: Path, field: str
) -> None:
    value = chain["document_review"].payload()
    if field == "total":
        value["approved_grand_total_kzt"] += 1
    elif field == "item_id":
        value["items"][0][field] = "OTHER"
    else:
        value["items"][0][field] += 1
    with pytest.raises(ValueError, match="mismatch"):
        flow.document_source(
            chain["confirmed"],
            chain["calculated"],
            snapshot(tmp_path / "bad-review.json", value),
        )


@pytest.mark.parametrize(
    "gate",
    [
        "technical_composition_approved",
        "prices_approved",
        "commercial_terms_approved",
        "rendering_authorized",
        "approved_case_source_sha256",
        "approved_document_fingerprint",
        "approved_by",
        "authority",
        "client_send_authorized",
    ],
)
def test_document_human_gate_required(
    chain: dict[str, Any], tmp_path: Path, gate: str
) -> None:
    approval = chain["approval"].payload()
    approval[gate] = True if gate == "client_send_authorized" else False
    with pytest.raises((ValueError, TypeError)):
        future.preflight(
            chain["source"],
            snapshot(tmp_path / "bad-approval.json", approval),
            allow_test_profile=True,
        )


@pytest.mark.parametrize(
    "target",
    ["confirmed", "completed", "costs", "document_review", "source", "approval"],
)
def test_input_sha_drift_holds(
    chain: dict[str, Any], tmp_path: Path, target: str
) -> None:
    plan = future.preflight(chain["source"], chain["approval"], allow_test_profile=True)
    chain[target].path.write_bytes(chain[target].raw + b" ")
    out = tmp_path / "never.json"
    with pytest.raises(ValueError):
        future.publish(
            plan,
            out,
            future.publication_authorization(plan, out),
            allow_test_profile=True,
        )
    assert not out.exists()


def test_composition_gate_and_future_review_drift(tmp_path: Path) -> None:
    inputs = composition_inputs(tmp_path)
    result = build_composition(inputs, input_fn=lambda _: "PASS")
    assert result.status == "FAIL" and not (inputs["case"] / "confirmed").exists()
    result = build_composition(
        inputs,
        input_fn=lambda _: builder.APPROVAL_PHRASE,
        before_drift_check=lambda: inputs["review"].path.write_bytes(b"{}"),
    )
    assert result.status == "FAIL" and not (inputs["case"] / "confirmed").exists()


@pytest.mark.parametrize("case_id", ["CASE-LABORATORY-VRU-20260924-001", "Invoice519"])
def test_frozen_case_cannot_enter_future(tmp_path: Path, case_id: str) -> None:
    inputs = composition_inputs(tmp_path)
    value = inputs["review"].payload()
    value["future_context"]["case_id"] = case_id
    inputs["review"] = snapshot(inputs["review"].path, value)
    result = build_composition(
        inputs, input_fn=lambda _: pytest.fail("Human gate must not be reached")
    )
    assert result.status == "FAIL" and not (inputs["case"] / "confirmed").exists()


def test_publication_token_overwrite_and_foreign_race(
    chain: dict[str, Any], tmp_path: Path, monkeypatch: Any
) -> None:
    plan = future.preflight(chain["source"], chain["approval"], allow_test_profile=True)
    out = tmp_path / "approved.json"
    with pytest.raises(ValueError, match="authorization"):
        future.publish(plan, out, "PASS", allow_test_profile=True)
    out.write_bytes(b"foreign")
    with pytest.raises(ValueError, match="exists"):
        future.publish(
            plan,
            out,
            future.publication_authorization(plan, out),
            allow_test_profile=True,
        )
    assert out.read_bytes() == b"foreign"
    out.unlink()

    def race(_source: Any, target: Any) -> None:
        Path(target).write_bytes(b"foreign race")
        raise FileExistsError("foreign output")

    monkeypatch.setattr(flow.os, "link", race)
    with pytest.raises(FileExistsError):
        future.publish(
            plan,
            out,
            future.publication_authorization(plan, out),
            allow_test_profile=True,
        )
    assert out.read_bytes() == b"foreign race"


def test_post_link_drift_rolls_back_only_owned_output(
    chain: dict[str, Any], tmp_path: Path, monkeypatch: Any
) -> None:
    plan = future.preflight(chain["source"], chain["approval"], allow_test_profile=True)
    out = tmp_path / "approved.json"
    real_link = flow.os.link

    def drift(source: Any, target: Any) -> None:
        real_link(source, target)
        chain["document_review"].path.write_bytes(b"{}")

    monkeypatch.setattr(flow.os, "link", drift)
    with pytest.raises(ValueError, match="changed"):
        future.publish(
            plan,
            out,
            future.publication_authorization(plan, out),
            allow_test_profile=True,
        )
    assert not out.exists() and not list(tmp_path.glob(".future-case-*"))


def test_unbound_test_preview_cannot_publish(tmp_path: Path, monkeypatch: Any) -> None:
    from test_dinva_future_content import make_plan

    plan, _ = make_plan(tmp_path, monkeypatch)
    out = tmp_path / "unbound.json"
    with pytest.raises(ValueError, match="role missing"):
        future.publish(
            plan,
            out,
            future.publication_authorization(plan, out),
            allow_test_profile=True,
        )
    assert not out.exists()


def test_production_preflight_requires_full_chain(
    tmp_path: Path, monkeypatch: Any
) -> None:
    from test_dinva_future_content import make_plan

    _, inputs = make_plan(tmp_path, monkeypatch)
    monkeypatch.delenv("DINVA_RENDERER_TEST_MODE")
    with pytest.raises(ValueError, match="role missing"):
        future.preflight(*inputs, allow_test_profile=True)


def test_memory_plan_tamper_and_output_subject(
    chain: dict[str, Any], tmp_path: Path
) -> None:
    plan = future.preflight(chain["source"], chain["approval"], allow_test_profile=True)
    out = tmp_path / "approved.json"
    token = future.publication_authorization(plan, out)
    with pytest.raises(ValueError, match="authorization"):
        future.publish(plan, tmp_path / "other.json", token, allow_test_profile=True)
    plan.document["terms"]["manufacturing_lead_time"] = "99 дней"
    with pytest.raises(ValueError, match="changed"):
        future.publish(plan, out, token, allow_test_profile=True)


def test_cli_preflight_is_read_only(
    chain: dict[str, Any], tmp_path: Path, monkeypatch: Any
) -> None:
    out = tmp_path / "prospective.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "flow",
            "pricing-input",
            "--confirmed",
            str(chain["confirmed"].path),
            "--confirmed-sha256",
            chain["confirmed"].sha256,
            "--operator",
            str(chain["operator"].path),
            "--operator-sha256",
            chain["operator"].sha256,
            "--output",
            str(out),
        ],
    )
    assert flow.main() == 0 and not out.exists()


@pytest.mark.parametrize(
    "leaf", ["work-cost.json", "cabinet-cost.json", "prices.xlsx", "selector.json"]
)
def test_leaf_input_drift_holds(
    chain: dict[str, Any], tmp_path: Path, leaf: str
) -> None:
    plan = future.preflight(chain["source"], chain["approval"], allow_test_profile=True)
    path = tmp_path / leaf
    path.write_bytes(path.read_bytes() + b" ")
    out = tmp_path / "never.json"
    with pytest.raises(ValueError):
        future.publish(
            plan,
            out,
            future.publication_authorization(plan, out),
            allow_test_profile=True,
        )
    assert not out.exists()


def test_foreign_replacement_after_link_is_preserved(
    chain: dict[str, Any], tmp_path: Path, monkeypatch: Any
) -> None:
    plan = future.preflight(chain["source"], chain["approval"], allow_test_profile=True)
    out = tmp_path / "approved.json"
    real_link = flow.os.link

    def replace(source: Any, target: Any) -> None:
        real_link(source, target)
        replacement = tmp_path / "foreign.json"
        replacement.write_bytes(Path(source).read_bytes())
        replacement.replace(target)

    monkeypatch.setattr(flow.os, "link", replace)
    with pytest.raises(ValueError, match="identity"):
        future.publish(
            plan,
            out,
            future.publication_authorization(plan, out),
            allow_test_profile=True,
        )
    assert out.exists() and out.read_bytes() == plan.encoded


@pytest.mark.parametrize("fault", ["missing", "quantity", "duplicate", "note"])
def test_display_must_preserve_bound_component_counts(
    chain: dict[str, Any], tmp_path: Path, fault: str
) -> None:
    review = chain["document_review"].payload()
    parts = review["items"][0]["technical_display"]
    if fault == "missing":
        parts[0]["component_id"] = "OTHER"
    elif fault == "quantity":
        parts[0]["quantity"] += 1
    elif fault == "duplicate":
        parts.append(dict(parts[0]))
    else:
        parts.append(
            {"unit": "note", "label": "invented technical fact", "quantity": None}
        )
    with pytest.raises(ValueError, match="mismatch|source"):
        flow.document_source(
            chain["confirmed"],
            chain["calculated"],
            snapshot(tmp_path / "bad-display.json", review),
        )


def test_reviewed_manufacturer_cannot_use_other_brand_prices(tmp_path: Path) -> None:
    inputs = composition_inputs(tmp_path)
    decisions = inputs["decisions"].payload()
    decisions["items"][0]["manufacturer"] = "CHINT"
    decisions["items"][0]["component_groups"][0][
        "final_description"
    ] = "CHINT, Breaker 3P 63A"
    inputs["decisions"] = snapshot(inputs["decisions"].path, decisions)
    result = build_composition(
        inputs, input_fn=lambda _: pytest.fail("Human gate must not be reached")
    )
    assert result.status == "FAIL"
    assert "manufacturer conflicts" in result.red_flags[0]
    assert not (inputs["case"] / "confirmed").exists()


def test_composition_override_source_drift_holds(tmp_path: Path) -> None:
    inputs = composition_inputs(tmp_path)
    brand = snapshot(tmp_path / "reviewed-brand.json", {"value": "EKF"})
    review = inputs["review"].payload()
    review["items"][0]["technical_classification"]["overrides"] = {
        "human": {
            "automation_brand": {
                "path": str(brand.path),
                "sha256": brand.sha256,
                "locator": "/value",
            }
        }
    }
    inputs["review"] = snapshot(inputs["review"].path, review)
    result = build_composition(
        inputs,
        input_fn=lambda _: builder.APPROVAL_PHRASE,
        before_drift_check=lambda: brand.path.write_bytes(brand.raw + b" "),
    )
    assert result.status == "FAIL" and not (inputs["case"] / "confirmed").exists()


@pytest.mark.parametrize(
    "leaf_name", ["prices.xlsx", "work-cost.json", "cabinet-cost.json", "selector.json"]
)
def test_independent_validator_rechecks_pricing_leaf_after_publication(
    chain: dict[str, Any], tmp_path: Path, leaf_name: str
) -> None:
    plan = future.preflight(chain["source"], chain["approval"], allow_test_profile=True)
    output = tmp_path / "approved.json"
    future.publish(
        plan,
        output,
        future.publication_authorization(plan, output),
        allow_test_profile=True,
    )
    document = json.loads(output.read_bytes())
    bridge.validator.validate_document_contract(document, allow_test_profile=True)
    leaf = tmp_path / leaf_name
    leaf.write_bytes(leaf.read_bytes() + b" ")
    with pytest.raises(ValueError, match="drift"):
        bridge.validator.validate_document_contract(document, allow_test_profile=True)


def test_renderer_foreign_race_preserves_output(
    chain: dict[str, Any], tmp_path: Path, monkeypatch: Any
) -> None:
    plan = future.preflight(chain["source"], chain["approval"], allow_test_profile=True)
    document = tmp_path / "approved.json"
    future.publish(
        plan,
        document,
        future.publication_authorization(plan, document),
        allow_test_profile=True,
    )
    _, profile, _ = print_successor(tmp_path, monkeypatch)
    pp = tmp_path / "profile.json"
    ps = canonical_file(pp, profile)
    output = tmp_path / "foreign.xlsx"
    foreign = b"FOREIGN OUTPUT - MUST BE PRESERVED"

    def race(_source: Any, target: Any) -> None:
        Path(target).write_bytes(foreign)
        raise FileExistsError("foreign output appeared before link")

    monkeypatch.setattr(bridge.renderer.os, "link", race)
    with pytest.raises(bridge.renderer.RendererError):
        bridge.renderer.render(
            profile_path=pp,
            expected_profile_sha256=ps,
            document_path=document,
            expected_document_sha256=bridge.digest(document.read_bytes()),
            output=output,
            allow_test_profile=True,
        )
    assert output.exists(), "renderer rollback deleted the foreign output"
    assert output.read_bytes() == foreign
