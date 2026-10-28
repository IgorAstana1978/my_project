"""Synthetic authority only. No real engineering approval or operational writes."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import cabinet_sizing as sizing  # type: ignore[import-not-found]
import pytest
from test_versioned_metal_source import synthetic_sources as synthetic_sources


def provision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case_id: str,
    items: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[Path]]:
    """Create explicit test-only approved geometry, not production sizing rules."""
    requests = []
    paths = []
    for item in items:
        existing = item.get("cabinet", {})
        code = existing.get("cabinet_code", "CAB-KRN-24")
        if code not in sizing.CABINETS and not code.startswith("METAL-"):
            code = "CAB-KRN-24"  # Synthetic fixture identity, never runtime fallback.
        name, kind, outer = sizing.cabinet_identity(code)
        data: dict[str, Any] = {
            "devices": {},
            "cabinet": {
                "cabinet_code": code,
                "cabinet_label": existing.get("cabinet_label") or name,
                "cabinet_type": kind,
                "dimensions_mm": outer,
                "usable_mm": [n - 2 for n in outer],
            },
            "layout": {
                "case_id": case_id,
                "item_id": item["item_id"],
                "apparatus_sha256": sizing.apparatus_hash(item),
                "cabinet_code": code,
                "edge_mm": [0, 0, 0],
                "gap_mm": [1, 1, 1],
                "reserve": {"origin_mm": [0, 0, 0], "dimensions_mm": [1, 1, 1]},
                "placements": [],
            },
        }
        position = 2
        for c in item["components"]:
            cid = c["component_id"]
            data["devices"][cid] = {
                "component_sha256": sizing.digest(c),
                "dimensions_mm": [1, 1, 1],
            }
            qty = c.get("quantity", c.get("quantity_guess"))
            for n in range(1, qty + 1):
                data["layout"]["placements"].append(
                    {"component_id": cid, "unit": n, "origin_mm": [2, position, 2]}
                )
                position += 2
        path = tmp_path / f"synthetic-sizing-{uuid4().hex}.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        pins = {
            (role, str(path.resolve()), sha) for role in ("device", "cabinet", "layout")
        }
        monkeypatch.setattr(sizing, "APPROVED_SOURCES", sizing.APPROVED_SOURCES | pins)

        def ref(pointer: str, path: Path = path, sha: str = sha) -> dict[str, str]:
            return {"path": str(path.resolve()), "sha256": sha, "pointer": pointer}

        requests.append(
            {
                "item_id": item["item_id"],
                "devices": {
                    c["component_id"]: ref("/devices/" + c["component_id"])
                    for c in item["components"]
                },
                "cabinet": ref("/cabinet"),
                "layout": ref("/layout"),
            }
        )
        paths.append(path)
    return {"case_id": case_id, "items": requests}, paths


def install_legacy_test_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    item_geometry: dict[str, dict[str, str]] | None = None,
) -> None:
    """Supply synthetic reusable facts to old scenarios; run the real selector."""
    original = sizing.size_composition

    def with_synthetic_inputs(case_id: str, items: Any, request: Any = None) -> Any:
        if request is None:
            request, _ = provision_auto(
                tmp_path, monkeypatch, case_id, list(items), item_geometry=item_geometry
            )
        return original(case_id, items, request)

    monkeypatch.setattr(sizing, "size_composition", with_synthetic_inputs)


def provision_auto(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case_id: str,
    items: list[dict[str, Any]],
    *,
    item_geometry: dict[str, dict[str, str]] | None = None,
) -> tuple[dict[str, Any], list[Path]]:
    """Tiny geometry, authorized only in a monkeypatched test registry."""
    import cabinet_sizing_evidence as evidence  # type: ignore[import-not-found]
    from cabinet_sizing_selector import REQUEST_SCHEMA  # type: ignore[import-not-found]
    from test_cabinet_sizing_selector import (
        synthetic_cab,
        synthetic_record,
        synthetic_zone,
    )

    records, mappings, cabinets, facts = {}, {}, {}, {}
    for item in items:
        # Explicit geometry is synthetic source authority declared by the fixture,
        # never a production fallback derived from device kind or selected output.
        geometry = (item_geometry or {}).get(item["item_id"], {})
        code = geometry.get(
            "cabinet_code", item.get("cabinet", {}).get("cabinet_code", "CAB-KRN-24")
        )
        mounting = geometry.get("mounting", "DIN")
        assert mounting in {"DIN", "PANEL"}
        if "cabinet_code" in geometry:
            sizing.cabinet_identity(code)
        else:
            try:
                sizing.cabinet_identity(code)
            except sizing.SizingHold, TypeError:
                code = "CAB-KRN-24"
        cab = synthetic_cab(code)
        outer = cab["dimensions_mm"]
        cab["zones"] = [
            synthetic_zone(mounting, width=outer[1] - 2, height=outer[0] - 2)
        ]
        cab["zones"][0]["usable_mm"][2] = outer[2] - 2
        cab["zones"][0]["rails_mm"] = [0] if mounting == "DIN" else []
        label = geometry.get(
            "cabinet_label", item.get("cabinet", {}).get("cabinet_label")
        )
        if isinstance(label, str) and label:
            cab["cabinet_label"] = label
        cabinets[code] = cab
        for comp in item["components"]:
            signature = {
                "component_code": comp.get(
                    "component_code", comp.get("component_code_guess")
                ),
                "component_label": comp.get(
                    "component_label", comp.get("component_label_guess")
                ),
            }
            cid = sizing.digest({"signature": signature, "mounting": mounting})[:16]
            record = synthetic_record(cid, mounting=mounting, size=[1, 1, 1])
            record["rail_offset_mm"] = 0 if mounting == "DIN" else None
            records[cid] = record
            mappings[cid] = {"signature": signature, "class_id": cid}
        facts[item["item_id"]] = {
            "case_id": case_id,
            "item_id": item["item_id"],
            "apparatus_sha256": sizing.apparatus_hash(item),
            "dimensions_status": "EXPLICIT",
            "dimensions_mm": outer,
            "installation": "SURFACE",
            "prior_approval": {"status": "NONE"},
            "raw_sources": [],
        }
    values = {
        "devices": {
            "records": list(records.values()),
            "mappings": list(mappings.values()),
        },
        "catalogue": {"cabinets": list(cabinets.values())},
        **facts,
    }
    request: dict[str, Any] = {
        "schema_version": REQUEST_SCHEMA,
        "case_id": case_id,
        "source_facts": {},
    }
    paths = []
    for name, value in values.items():
        role = name if name in {"devices", "catalogue"} else "source_fact"
        path = tmp_path / f"synthetic-auto-{uuid4().hex}.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        monkeypatch.setattr(
            evidence,
            "AUTHORIZED",
            evidence.AUTHORIZED | {(role, str(path.resolve()), sha)},
        )
        binding = {"path": str(path), "sha256": sha}
        if role == "source_fact":
            request["source_facts"][name] = binding
        else:
            request[role] = binding
        paths.append(path)
    return request, paths


@pytest.fixture
def item() -> dict[str, Any]:
    return {
        "item_id": "ITEM-001",
        "product_name": "Synthetic board",
        "quantity": 1,
        "components": [
            {
                "component_id": "COMP-001",
                "component_code": "SYNTHETIC",
                "component_label": "Synthetic device",
                "quantity": 2,
                "install_type": "modular_1p",
            }
        ],
        "cabinet": {"cabinet_code": "CAB-KRN-24", "cabinet_label": "Synthetic label"},
    }


def test_exact_selection_and_revalidation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, item: Any
) -> None:
    request, _ = provision(tmp_path, monkeypatch, "CASE-SYNTHETIC", [item])
    report = sizing.size_composition("CASE-SYNTHETIC", [item], request)
    item["cabinet"] = report["items"][0]["cabinet"]
    assert item["cabinet"]["dimensions_mm"] == [395, 330, 100]
    assert item["cabinet"]["cabinet_type"] == "KRN"
    sizing.verify_report(report, [item], expected_case_id="CASE-SYNTHETIC")
    item["cabinet"]["dimensions_mm"][0] += 1
    with pytest.raises(sizing.SizingHold):
        sizing.verify_report(report, [item], expected_case_id="CASE-SYNTHETIC")


def test_missing_evidence_is_first_specific_hold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, item: Any, synthetic_sources: Any
) -> None:
    import cabinet_sizing_evidence as evidence  # type: ignore[import-not-found]
    from test_cabinet_sizing_catalogue import inject, record
    from test_cabinet_sizing_selector import provide

    inject(monkeypatch, [record("SYNTHETIC-CABINET")])
    _, request, _ = provide(tmp_path, monkeypatch)
    monkeypatch.setattr(evidence, "default_binding", lambda: request["devices"])
    with pytest.raises(sizing.SizingHold, match="HOLD_UNMAPPED_OR_AMBIGUOUS_APPARATUS"):
        sizing.size_composition("CASE-SYNTHETIC", [item])


def test_data_claim_does_not_authorize_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, item: Any
) -> None:
    request, _ = provision(tmp_path, monkeypatch, "CASE-SYNTHETIC", [item])
    monkeypatch.setattr(sizing, "APPROVED_SOURCES", frozenset())
    with pytest.raises(sizing.SizingHold, match="HOLD_UNAPPROVED_SOURCE:device"):
        sizing.size_composition("CASE-SYNTHETIC", [item], request)


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ("drift", "HOLD_SOURCE_SHA_DRIFT"),
        ("composition", "HOLD_DEVICE_SIGNATURE"),
        ("case", "HOLD_CASE_BINDING"),
        ("coverage", "HOLD_DEVICE_COVERAGE"),
        ("pointer", "HOLD_SOURCE_POINTER"),
        ("duplicate", "HOLD_DUPLICATE_COMPONENT"),
    ],
)
def test_binding_rejections(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    item: Any,
    mutation: str,
    reason: str,
) -> None:
    request, paths = provision(tmp_path, monkeypatch, "CASE-SYNTHETIC", [item])
    if mutation == "drift":
        paths[0].write_bytes(paths[0].read_bytes() + b" ")
    elif mutation == "composition":
        item["components"][0]["quantity"] += 1
    elif mutation == "case":
        request["case_id"] = "CASE-OTHER"
    elif mutation == "coverage":
        request["items"][0]["devices"] = {}
    elif mutation == "pointer":
        request["items"][0]["devices"]["COMP-001"]["pointer"] = "/absent"
    elif mutation == "duplicate":
        item["components"].append(copy.deepcopy(item["components"][0]))
    with pytest.raises(sizing.SizingHold, match=reason):
        sizing.size_composition("CASE-SYNTHETIC", [item], request)


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ("overlap", "HOLD_LAYOUT_COLLISION"),
        ("outside", "HOLD_LAYOUT_OUTSIDE"),
        ("omit", "HOLD_LAYOUT_DEVICE_COVERAGE"),
        ("reserve", "HOLD_SCHEMA:layout"),
        ("dimension", "HOLD_CABINET_DIMENSION_IDENTITY"),
        ("type", "HOLD_CABINET_TYPE"),
        ("signature", "HOLD_LAYOUT_COMPOSITION_BINDING"),
        ("bool", "HOLD_INVALID_MM_VECTOR"),
    ],
)
def test_even_approved_inconsistent_geometry_holds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    item: Any,
    mutation: str,
    reason: str,
) -> None:
    request, paths = provision(tmp_path, monkeypatch, "CASE-SYNTHETIC", [item])
    data = json.loads(paths[0].read_bytes())
    layout = data["layout"]
    if mutation == "overlap":
        layout["placements"][1]["origin_mm"] = layout["placements"][0]["origin_mm"]
    elif mutation == "outside":
        layout["placements"][0]["origin_mm"] = [10000, 0, 0]
    elif mutation == "omit":
        layout["placements"].pop()
    elif mutation == "reserve":
        del layout["reserve"]
    elif mutation == "dimension":
        data["cabinet"]["dimensions_mm"][0] += 1
    elif mutation == "type":
        data["cabinet"]["cabinet_type"] = "KRV"
    elif mutation == "signature":
        layout["apparatus_sha256"] = "0" * 64
    elif mutation == "bool":
        data["devices"]["COMP-001"]["dimensions_mm"][0] = True
    paths[0].write_text(json.dumps(data), encoding="utf-8")
    sha = hashlib.sha256(paths[0].read_bytes()).hexdigest()
    monkeypatch.setattr(
        sizing,
        "APPROVED_SOURCES",
        frozenset((r, str(paths[0]), sha) for r in ["device", "cabinet", "layout"]),
    )
    for ref in [
        *request["items"][0]["devices"].values(),
        request["items"][0]["cabinet"],
        request["items"][0]["layout"],
    ]:
        ref["sha256"] = sha
    with pytest.raises(sizing.SizingHold, match=reason):
        sizing.size_composition("CASE-SYNTHETIC", [item], request)


def test_historical_validation_and_new_approval_gate(tmp_path: Path) -> None:
    import validate_confirmed_composition_artifact as validator  # type: ignore[import-not-found]

    example = (
        Path(__file__).resolve().parents[1]
        / "examples/confirmed_composition_artifact.example.json"
    )
    assert validator.validate_confirmed_composition_artifact(example).status == "PASS"
    result = validator.validate_confirmed_composition_artifact(
        example, before_human_approval_1=True
    )
    assert result.status == "FAIL"
    assert any(
        "HOLD_SIZING_REQUIRED_BEFORE_HUMAN_APPROVAL_1" in s for s in result.red_flags
    )


def test_builder_missing_sizing_stops_before_any_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, synthetic_sources: Any
) -> None:
    import cabinet_sizing_evidence as evidence  # type: ignore[import-not-found]
    from test_build_confirmed_composition_from_preliminary_bundle import (
        builder,
        create_bundle,
    )
    from test_cabinet_sizing_catalogue import inject, record
    from test_cabinet_sizing_selector import provide

    inject(monkeypatch, [record("SYNTHETIC-CABINET")])
    _, request, _ = provide(tmp_path, monkeypatch)
    monkeypatch.setattr(evidence, "default_binding", lambda: request["devices"])
    root, _ = create_bundle(tmp_path)
    result = builder.run_builder(
        case_id="CASE-TEST-001",
        confirmation_id="SYNTHETIC",
        approval_channel="synthetic",
        canonical_root=root,
        input_fn=lambda _: pytest.fail("must not request approval"),
        output_fn=lambda _: None,
    )
    assert result.status == "HOLD" and not result.output_created
    assert result.red_flags[0] == "HOLD_UNMAPPED_OR_AMBIGUOUS_APPARATUS"


@pytest.mark.parametrize("raw", [b"{", b"\xff", b'{"case_id":1,"case_id":2}'])
def test_pinned_malformed_request_is_hold(tmp_path: Path, raw: bytes) -> None:
    path = tmp_path / "malformed.json"
    path.write_bytes(raw)
    with pytest.raises(sizing.SizingHold, match="HOLD_MALFORMED"):
        sizing.load_request(path, hashlib.sha256(raw).hexdigest())


def test_exact_metal_identity_preserved() -> None:
    _, kind, size = sizing.cabinet_identity("METAL-500X400X250-D22")
    assert kind == "METAL" and size == [500, 400, 250]
    with pytest.raises(sizing.SizingHold):
        sizing.cabinet_identity("METAL-500X400X250-D28")


def test_new_dimensions_cannot_downgrade_to_legacy(tmp_path: Path) -> None:
    import validate_confirmed_composition_artifact as validator  # type: ignore[import-not-found]

    example = (
        Path(__file__).resolve().parents[1]
        / "examples/confirmed_composition_artifact.example.json"
    )
    data = json.loads(example.read_bytes())
    data["items"][0]["cabinet"].update(cabinet_type="UNPROVEN", dimensions_mm=[1, 2, 3])
    path = tmp_path / "unproven.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    result = validator.validate_confirmed_composition_artifact(path)
    assert result.status == "FAIL"
    assert any(
        "HOLD_SIZING_REQUIRED_BEFORE_HUMAN_APPROVAL_1" in f for f in result.red_flags
    )


def test_validator_binds_case_and_rejects_malformed_items(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import validate_confirmed_composition_artifact as validator  # type: ignore[import-not-found]

    example = (
        Path(__file__).resolve().parents[1]
        / "examples/confirmed_composition_artifact.example.json"
    )
    data = json.loads(example.read_bytes())
    request, _ = provision(tmp_path, monkeypatch, "CASE-SYNTHETIC", data["items"])
    report = sizing.size_composition("CASE-SYNTHETIC", data["items"], request)
    data.update(case_id="CASE-SYNTHETIC", cabinet_sizing=report)
    for item, selected in zip(data["items"], report["items"], strict=True):
        item["cabinet"] = selected["cabinet"]
    path = tmp_path / "confirmed.json"

    def check(**kwargs: Any) -> Any:
        path.write_text(json.dumps(data), encoding="utf-8")
        return validator.validate_confirmed_composition_artifact(path, **kwargs)

    assert (
        check(before_human_approval_1=True, expected_case_id="CASE-SYNTHETIC").status
        == "FAIL"
    )
    assert check(before_human_approval_1=True).status == "FAIL"
    assert (
        check(before_human_approval_1=True, expected_case_id="CASE-OTHER").status
        == "FAIL"
    )
    data["future_context"] = {"case_id": "CASE-OTHER"}
    assert any("HOLD_SIZING_CASE_BINDING" in f for f in check().red_flags)
    del data["future_context"]
    data["items"] = "x"
    data["cabinet_sizing"]["sources"] = None
    assert check().status == "FAIL"


def test_cli_hold_and_request_positive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, item: Any, capsys: Any
) -> None:
    path = tmp_path / "composition.json"
    path.write_text(json.dumps({"items": [item]}), encoding="utf-8")
    args = ["--composition-json", str(path), "--case-id", "CASE-SYNTHETIC"]
    assert sizing.main(args) == 2
    assert json.loads(capsys.readouterr().out)["results"][0]["status"] == "HOLD"
    request, _ = provision(tmp_path, monkeypatch, "CASE-SYNTHETIC", [item])
    rp = tmp_path / "request.json"
    rp.write_text(json.dumps(request), encoding="utf-8")
    assert (
        sizing.main(
            args
            + [
                "--request-json",
                str(rp),
                "--request-sha256",
                hashlib.sha256(rp.read_bytes()).hexdigest(),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["results"][0]["status"] == "PROPOSED"
    path.write_text(json.dumps({"items": [item, item]}), encoding="utf-8")
    assert sizing.main(args) == 2
    assert json.loads(capsys.readouterr().out)["first_missing"] == "HOLD_DUPLICATE_ITEM"
    path.write_bytes(b"{")
    assert sizing.main(args) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "HOLD"


@pytest.mark.parametrize("tamper_after_phrase", [False, True])
def test_real_builder_gate_and_post_phrase_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tamper_after_phrase: bool,
) -> None:
    from test_build_confirmed_composition_from_preliminary_bundle import (
        answers,
        builder,
        create_batch_bundle,
        fixed_now,
    )

    root, _, decisions = create_batch_bundle(tmp_path)
    snapshot = builder.load_snapshot(
        builder.resolve_case_paths("CASE-TEST-001", canonical_root=root)
    )
    state = builder.apply_batch_decisions(
        snapshot, builder.load_decisions_input(decisions), case_id="CASE-TEST-001"
    )
    request, sources = provision_auto(
        tmp_path, monkeypatch, "CASE-TEST-001", state.items
    )
    path = tmp_path / "sizing-request.json"
    path.write_text(json.dumps(request), encoding="utf-8")
    summary: list[str] = []

    def drift() -> None:
        if tamper_after_phrase:
            sources[0].write_bytes(sources[0].read_bytes() + b" ")

    result = builder.run_builder(
        case_id="CASE-TEST-001",
        confirmation_id="SYNTHETIC-SIZING",
        approval_channel="synthetic_test",
        canonical_root=root,
        decisions_json=decisions,
        cabinet_sizing_json=path,
        cabinet_sizing_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        input_fn=answers(["SYNTHETIC APPROVAL"]),
        approval_phrase="SYNTHETIC APPROVAL",
        now_fn=fixed_now,
        output_fn=summary.append,
        before_drift_check=drift,
    )
    assert "dimensions H/W/D mm" in "\n".join(summary)
    if tamper_after_phrase:
        assert result.status == "HOLD" and not result.output_created
        assert not (root / "CASE-TEST-001" / "confirmed").exists()
    else:
        assert result.status == "PASS" and result.output_created
        artifact = json.loads((result.output_dir / builder.ARTIFACT_NAME).read_bytes())
        assert artifact["case_id"] == "CASE-TEST-001"
        assert artifact["items"][0]["cabinet"]["dimensions_mm"] == [395, 330, 100]
