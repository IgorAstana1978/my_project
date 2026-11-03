"""Portable, synthetic admission chain; never creates real Human Approval."""

from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path
from typing import Any

import pytest
from test_build_confirmed_composition_from_preliminary_bundle import (
    create_bundle,
    fixed_now,
    valid_batch_decisions,
)
from test_cabinet_sizing_selector import synthetic_record

evidence = importlib.import_module("cabinet_sizing_evidence")
adapter = importlib.import_module("cabinet_sizing_decisions")
sizing = importlib.import_module("cabinet_sizing")
pragmatic = importlib.import_module("cabinet_sizing_pragmatic")
builder = importlib.import_module("build_confirmed_composition_from_preliminary_bundle")
validator = importlib.import_module("validate_confirmed_composition_artifact")


def write(path: Path, data: Any) -> dict[str, str]:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return {"path": str(path), "sha256": builder.sha256_bytes(path.read_bytes())}


def admit(monkeypatch: pytest.MonkeyPatch, binding: dict[str, str], role: str) -> None:
    monkeypatch.setattr(
        evidence,
        "AUTHORIZED",
        evidence.AUTHORIZED | {(role, binding["path"], binding["sha256"])},
    )


@pytest.fixture
def chain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    # A complete synthetic 3-board/46-ID chain, with the real electrical shapes.
    def mutate(draft: dict[str, Any]) -> None:
        draft["red_flags"] = ["Synthetic source warning"]
        draft["assumptions"] = ["Synthetic preliminary extraction"]
        template = draft["items"][0]
        items = []
        for n, count in enumerate((21, 13, 12), 1):
            item = copy.deepcopy(template)
            item.update(item_id=f"ITEM-{n:03}", product_name_guess=f"source {n}")
            item["components"] = []
            for index in range(count):
                c = copy.deepcopy(template["components"][0])
                code = "ВА88-32" if n == 1 and index == 0 else "АВДТ32"
                if n > 1 and index == 0:
                    code = "ВН-32"
                rating = {"ВА88-32": "63А", "ВН-32": "25А"}.get(code, "C16/30мА")
                if code == "АВДТ32" and (
                    (n == 1 and 7 <= index <= 11) or (n == 2 and index in {2, 12})
                ):
                    rating = "C20/30мА"
                poles = "2P" if code == "АВДТ32" else "3P"
                c.update(
                    component_id=f"ITEM-{n:03}-COMP-{index + 1:03}",
                    component_code_guess=code,
                    component_label_guess=f"QF{index} {code} {poles} {rating}",
                    model_guess=code,
                    rating_guess=rating,
                    brand_guess=None,
                    quantity_guess=1,
                    install_type_guess="manual_review_required",
                )
                item["components"].append(c)
            items.append(item)
        draft["items"] = items

    case_id = evidence.WU15_CASE
    root, draft = create_bundle(tmp_path, case_id=case_id, mutate_draft=mutate)
    case = root / case_id
    monkeypatch.setattr(evidence, "WU15_CASE_ROOT", root)
    monkeypatch.setattr(
        evidence,
        "WU15_DRAFT_SHA",
        builder.sha256_bytes((case / builder.DRAFT_NAME).read_bytes()),
    )
    monkeypatch.setattr(
        adapter,
        "MANIFEST_SHA",
        builder.sha256_bytes((case / builder.MANIFEST_NAME).read_bytes()),
    )
    monkeypatch.setattr(
        adapter,
        "REVIEW_SHA",
        builder.sha256_bytes((case / builder.REVIEW_NAME).read_bytes()),
    )
    pdf = tmp_path / "synthetic.pdf"
    pdf.write_bytes(b"synthetic original bytes")
    pdf_sha = builder.sha256_bytes(pdf.read_bytes())
    monkeypatch.setattr(evidence, "WU15_PDF_SHA", pdf_sha)
    base = write(
        tmp_path / "base.json",
        {
            "case_source": {"path": str(pdf), "sha256": pdf_sha},
            "boards": {
                name: {"explicit_source_cabinet_dimensions_mm": None}
                for name in adapter.NAMES.values()
            },
        },
    )
    monkeypatch.setattr(evidence, "PRAGMATIC_REVIEW", Path(base["path"]))
    monkeypatch.setattr(evidence, "PRAGMATIC_REVIEW_SHA", base["sha256"])
    admit(monkeypatch, base, "pragmatic_source_fact")
    decisions = valid_batch_decisions(case, draft)
    decisions["case_id"] = case_id
    decisions["items"] = []
    for item in draft["items"]:
        groups = []
        for c in item["components"]:
            code = c["component_code_guess"]
            groups.append(
                {
                    "component_ids": [c["component_id"]],
                    "total_quantity": 1,
                    "final_description": "TEST, "
                    + c["component_label_guess"].split(" ", 1)[1],
                    "install_type": adapter.INSTALL_TYPES[code],
                    "substitution": None,
                    "acknowledged_red_flags": c["red_flags"],
                }
            )
        decisions["items"].append(
            {
                "item_id": item["item_id"],
                "product_name": adapter.NAMES[item["item_id"]],
                "quantity": 2,
                "manufacturer": "TEST",
                "acknowledged_red_flags": item["red_flags"],
                "cabinet": {"acknowledged_red_flags": []},
                "component_groups": groups,
            }
        )
    decision_binding = write(tmp_path / "decisions.json", decisions)
    admit(monkeypatch, decision_binding, "pragmatic_source_fact")
    data = {
        "schema_version": adapter.SCHEMA,
        "case_id": case_id,
        "base_source_fact": base,
        "decisions": decision_binding,
    }
    binding = write(tmp_path / "adapter.json", data)
    admit(monkeypatch, binding, "pragmatic_source_fact")
    device = write(
        tmp_path / "devices.json",
        {
            "records": [synthetic_record()],
            "mappings": [
                {"signature": {"component_code": code}, "class_id": "DIN"}
                for code in adapter.INSTALL_TYPES
            ],
        },
    )
    admit(monkeypatch, device, "devices")
    snapshot = builder.load_snapshot(
        builder.resolve_case_paths(case_id, canonical_root=root)
    )
    state = builder.apply_batch_decisions(
        snapshot,
        builder.load_decisions_input(Path(decision_binding["path"])),
        case_id=case_id,
        automatic_cabinet=True,
    )
    request = {
        "schema_version": pragmatic.REQUEST_SCHEMA,
        "case_id": case_id,
        "devices": device,
        "source_facts": {i["item_id"]: binding for i in state.items},
    }
    return {
        "case_id": case_id,
        "root": root,
        "case": case,
        "draft": draft,
        "state": state,
        "snapshot": snapshot,
        "request": request,
        "binding": binding,
        "data": data,
        "decisions": decisions,
        "decision_binding": decision_binding,
        "pdf": pdf,
    }


def fact(chain: Any) -> Any:
    return evidence.pragmatic_source_fact(
        chain["case_id"], chain["state"].items[0], chain["binding"]
    )


def repin(chain: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    # Simulate separate exact test admission after mutation, to reach semantic checks.
    db = write(Path(chain["decision_binding"]["path"]), chain["decisions"])
    admit(monkeypatch, db, "pragmatic_source_fact")
    chain["data"]["decisions"] = db
    chain["binding"].update(write(Path(chain["binding"]["path"]), chain["data"]))
    admit(monkeypatch, chain["binding"], "pragmatic_source_fact")


def test_recompute_before_a1_and_full_validator(
    chain: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cabinet_sizing_module_accounting as modules  # type: ignore[import-not-found]
    from module_accounting_fixtures import provision_modules

    state = chain["state"]
    state.cabinet_sizing = sizing.size_composition(
        chain["case_id"], state.items, chain["request"]
    )
    for item, selection in zip(state.items, state.cabinet_sizing["items"], strict=True):
        item["cabinet"] = selection["cabinet"]
        assert selection["preliminary_only"]
        assert selection["unverified"]["installation_compatibility"] is None
    sizing.verify_report(
        state.cabinet_sizing,
        state.items,
        expected_case_id=chain["case_id"],
        before_human_approval_1=True,
    )
    builder.ensure_ready_for_approval(state)
    module_source, _ = provision_modules(
        tmp_path, monkeypatch, chain["case_id"], state.items, state.cabinet_sizing
    )
    state.cabinet_sizing = modules.build_sizing_report(
        chain["case_id"], state.items, state.cabinet_sizing, module_source
    )
    # Test-only hypothetical confirmed model, outside the real Case.
    artifact = builder.build_confirmed_artifact(
        confirmation_id="SYNTHETIC",
        confirmed_at=fixed_now().isoformat(),
        snapshot=chain["snapshot"],
        state=state,
    )
    path = tmp_path / "synthetic-artifact.json"
    write(path, artifact)
    result = validator.validate_confirmed_composition_artifact(
        path, before_human_approval_1=True, expected_case_id=chain["case_id"]
    )
    assert result.status == "PASS", result.red_flags
    assert sum(len(i["components"]) for i in artifact["items"]) == 46
    assert artifact["items"][2]["product_name"] == "АВР"
    assert not artifact["safety"]["price_approved_by_igor"]
    # Recompute remains valid after publication creates a confirmed directory.
    (chain["case"] / "confirmed").mkdir()
    fact(chain)


@pytest.mark.parametrize("which", ["adapter", "decisions"])
def test_arbitrary_sha_and_approval_flags_never_admit(chain: Any, which: str) -> None:
    binding = chain["binding"] if which == "adapter" else chain["decision_binding"]
    value = json.loads(Path(binding["path"]).read_bytes())
    value["approved"] = True
    new = write(Path(binding["path"]), value)
    if which == "adapter":
        chain["binding"].update(new)
    else:
        chain["data"]["decisions"] = new
    with pytest.raises(sizing.SizingHold):
        fact(chain)


@pytest.mark.parametrize("which", ["adapter", "decisions"])
def test_each_exact_admission_is_independently_required(
    chain: Any, monkeypatch: pytest.MonkeyPatch, which: str
) -> None:
    binding = chain["binding"] if which == "adapter" else chain["decision_binding"]
    monkeypatch.setattr(
        evidence,
        "AUTHORIZED",
        evidence.AUTHORIZED
        - {("pragmatic_source_fact", binding["path"], binding["sha256"])},
    )
    with pytest.raises(sizing.SizingHold, match="HOLD_UNAPPROVED_REUSABLE_SOURCE"):
        fact(chain)


def test_report_recompute_rejects_later_decision_drift(chain: Any) -> None:
    report = sizing.size_composition(
        chain["case_id"], chain["state"].items, chain["request"]
    )
    for item, selection in zip(chain["state"].items, report["items"], strict=True):
        item["cabinet"] = selection["cabinet"]
    path = Path(chain["decision_binding"]["path"])
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(sizing.SizingHold):
        sizing.verify_report(
            report,
            chain["state"].items,
            expected_case_id=chain["case_id"],
            before_human_approval_1=True,
        )


def test_drift_during_batch_replay_fails_closed(
    chain: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = builder.apply_batch_decisions

    def drift(*args: Any, **kwargs: Any) -> Any:
        state = original(*args, **kwargs)
        path = chain["case"] / builder.REVIEW_NAME
        path.write_bytes(path.read_bytes() + b" ")
        return state

    monkeypatch.setattr(builder, "apply_batch_decisions", drift)
    with pytest.raises(sizing.SizingHold):
        fact(chain)


@pytest.mark.parametrize("target", ["draft", "review", "manifest", "pdf", "decisions"])
def test_source_drift(chain: Any, target: str) -> None:
    paths = {
        "draft": chain["case"] / builder.DRAFT_NAME,
        "review": chain["case"] / builder.REVIEW_NAME,
        "manifest": chain["case"] / builder.MANIFEST_NAME,
        "pdf": chain["pdf"],
        "decisions": Path(chain["decision_binding"]["path"]),
    }
    path = paths[target]
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(sizing.SizingHold):
        fact(chain)


@pytest.mark.parametrize(
    "field",
    ["quantity", "component_label", "install_type", "component_code", "component_id"],
)
def test_unconfirmed_normalized_changes(chain: Any, field: str) -> None:
    c = chain["state"].items[0]["components"][0]
    c[field] = 2 if field == "quantity" else "unconfirmed"
    with pytest.raises(sizing.SizingHold):
        fact(chain)


@pytest.mark.parametrize(
    "attack",
    [
        "nominal",
        "extra_nominal",
        "install",
        "missing_id",
        "duplicate_id",
        "substitution",
        "quantity",
        "brand",
        "rename_avr",
    ],
)
def test_admitted_decisions_still_cannot_change_electrical_source(
    chain: Any, monkeypatch: pytest.MonkeyPatch, attack: str
) -> None:
    decision = chain["decisions"]["items"][0]
    group = decision["component_groups"][0]
    if attack == "nominal":
        group["final_description"] = group["final_description"].replace("63А", "80А")
    elif attack == "extra_nominal":
        group["final_description"] += " 80А"
    elif attack == "install":
        group["install_type"] = "load_switch_3p"
    elif attack == "missing_id":
        decision["component_groups"].pop()
    elif attack == "duplicate_id":
        decision["component_groups"].append(copy.deepcopy(group))
    elif attack == "substitution":
        group["substitution"] = {
            "original": chain["draft"]["items"][0]["components"][0][
                "component_label_guess"
            ],
            "final": group["final_description"],
            "reason": "test substitution",
        }
    elif attack == "quantity":
        decision["quantity"] = None
    elif attack == "brand":
        decision["manufacturer"] = "OTHER"
    else:
        chain["decisions"]["items"][2]["product_name"] = "automatic transfer panel"
    repin(chain, monkeypatch)
    with pytest.raises(sizing.SizingHold):
        fact(chain)


def test_builder_cannot_bypass_final_human_prompt(
    chain: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from module_accounting_fixtures import install_synthetic_modules

    install_synthetic_modules(tmp_path, monkeypatch)
    req = tmp_path / "request.json"
    binding = write(req, chain["request"])
    prompts = []

    def reject(prompt: str) -> str:
        prompts.append(prompt)
        return "NOT AN APPROVAL"

    result = builder.run_builder(
        case_id=chain["case_id"],
        confirmation_id="TEST",
        approval_channel="synthetic",
        canonical_root=chain["root"],
        decisions_json=Path(chain["decision_binding"]["path"]),
        cabinet_sizing_json=req,
        cabinet_sizing_sha256=binding["sha256"],
        input_fn=reject,
        output_fn=lambda _: None,
    )
    assert len(prompts) == 1
    assert result.status == "FAIL" and not result.output_created
    assert not (chain["case"] / "confirmed").exists()
