"""Automatic contract tests; all injected engineering facts are synthetic."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import cabinet_sizing as sizing  # type: ignore[import-not-found]
import cabinet_sizing_evidence as evidence  # type: ignore[import-not-found]
import cabinet_sizing_selector as selector  # type: ignore[import-not-found]
import pytest


def test_automatic_request_never_accepts_caller_cabinet() -> None:
    item = {"item_id": "I", "components": [{"component_id": "C"}]}
    with pytest.raises(sizing.SizingHold, match="HOLD_AUTOMATIC_REQUEST_SCHEMA"):
        sizing.size_composition(
            "CASE",
            [item],
            {"schema_version": "cabinet_sizing.auto_request.v0.2", "cabinet": {}},
        )


def synthetic_record(
    class_id: str = "DIN", *, mounting: str = "DIN", size: Any = None
) -> dict[str, Any]:
    return {
        "record_id": class_id + "-a",
        "class_id": class_id,
        "mounting": mounting,
        "form_factor": "TEST_" + mounting,
        "dimensions_mm": size or [80, "20.25", 30],
        "clearance_mm": [0, 0, 0, 0],
        "pair_gap_mm": [0, 0],
        "extra_gap_mm": 0,
        "rail_offset_mm": 40 if mounting == "DIN" else None,
        "rail_back_mm": 0 if mounting == "DIN" else None,
        "requirements": {"min_ip": [3, 0], "shock_class": None},
        "body_reference": None,
        "sources": [],
    }


def synthetic_zone(
    kind: str = "DIN", *, width: Any = 100, height: Any = 200, origin: Any = None
) -> dict[str, Any]:
    return {
        "zone_id": kind,
        "kind": kind,
        "origin_mm": origin or [0, 0, 0],
        "usable_mm": [height, width, 90],
        "rails_mm": [40] if kind == "DIN" else [],
        "mounting_plane_mm": 0,
        "panel_material": "metal",
        "panel_thickness_mm": 2,
        "barriers_compatible": True,
    }


def synthetic_cab(code: str = "CAB-KRN-12", zones: Any = None) -> dict[str, Any]:
    name, kind, outer = sizing.cabinet_identity(code)
    return {
        "cabinet_code": code,
        "cabinet_label": name,
        "cabinet_type": kind,
        "dimensions_mm": outer,
        "installation": "SURFACE",
        "ip": [3, 0],
        "shock_class": "I",
        "zones": zones or [synthetic_zone()],
    }


def provide(
    tmp: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    item: Any = None,
    records: Any = None,
    cabinets: Any = None,
    fact: Any = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Path]]:
    item = copy.deepcopy(
        item
        or {
            "item_id": "I",
            "product_name": "test",
            "quantity": 1,
            "components": [
                {"component_id": "C", "component_code": "TEST_DIN", "quantity": 3}
            ],
        }
    )
    records = records or [synthetic_record()]
    facts = {
        "case_id": "CASE",
        "item_id": item["item_id"],
        "apparatus_sha256": sizing.apparatus_hash(item),
        "dimensions_status": "ABSENT",
        "dimensions_mm": None,
        "installation": "SURFACE",
        "prior_approval": {"status": "NONE"},
        "raw_sources": [],
    }
    facts.update(fact or {})
    objects = {
        "devices": {
            "records": records,
            "mappings": [
                {"signature": {"component_code": "TEST_" + cid}, "class_id": cid}
                for cid in sorted({r["class_id"] for r in records})
            ],
        },
        "catalogue": {
            "cabinets": cabinets or [synthetic_cab(), synthetic_cab("CAB-KRN-24")]
        },
        "source_fact": facts,
    }
    request = {
        "schema_version": selector.REQUEST_SCHEMA,
        "case_id": "CASE",
        "source_facts": {},
    }
    paths = {}
    for role, value in objects.items():
        path = tmp / (role + ".json")
        path.write_text(json.dumps(value), encoding="utf-8")
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        monkeypatch.setattr(
            evidence,
            "AUTHORIZED",
            evidence.AUTHORIZED | {(role, str(path.resolve()), sha)},
        )
        binding = {"path": str(path), "sha256": sha}
        if role == "source_fact":
            request["source_facts"][item["item_id"]] = binding
        else:
            request[role] = binding
        paths[role] = path
    return item, request, paths


def test_selects_without_cabinet_or_placements_with_exact_fractional_widths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Hand calculation: three widths20.25 occupy60.75 of100; KRN12 is unique min.
    item, request, _ = provide(tmp_path, monkeypatch)
    report = sizing.size_composition("CASE", [item], request)
    selection = report["items"][0]
    assert "cabinet" not in item and "placements" not in json.dumps(request)
    assert selection["cabinet"]["cabinet_code"] == "CAB-KRN-12"
    assert selection["layout"]["reserve"]["DIN"]["free_mm"] == "39.25"
    assert [p["origin_mm"][1] for p in selection["layout"]["placements"]] == [
        "0",
        "20.25",
        "40.5",
    ]
    item["cabinet"] = selection["cabinet"]
    sizing.verify_report(
        report, [item], expected_case_id="CASE", before_human_approval_1=True
    )


@pytest.mark.parametrize("width,passes", [("25", True), ("25.000001", False)])
def test_din_total_capacity_quarter_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, width: str, passes: bool
) -> None:
    record = synthetic_record(size=[80, width, 30])
    item, request, _ = provide(tmp_path, monkeypatch, records=[record])
    if passes:
        assert (
            sizing.size_composition("CASE", [item], request)["items"][0]["layout"][
                "reserve"
            ]["DIN"]["free_mm"]
            == "25"
        )
    else:
        with pytest.raises(sizing.SizingHold, match="HOLD_NO_VALID_APPROVED_CABINET"):
            sizing.size_composition("CASE", [item], request)


@pytest.mark.parametrize("height,passes", [(900, True), ("900.000001", False)])
def test_panel_area_quarter_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, height: Any, passes: bool
) -> None:
    item = {
        "item_id": "I",
        "components": [
            {"component_id": "C", "component_code": "TEST_PANEL", "quantity": 1}
        ],
    }
    item, request, _ = provide(
        tmp_path,
        monkeypatch,
        item=item,
        records=[synthetic_record("PANEL", mounting="PANEL", size=[height, 500, 30])],
        cabinets=[
            synthetic_cab(
                "METAL-1000X600X250",
                zones=[synthetic_zone("PANEL", width=600, height=1000)],
            )
        ],
    )
    if passes:
        assert (
            sizing.size_composition("CASE", [item], request)["items"][0]["layout"][
                "reserve"
            ]["PANEL"]["free_mm2"]
            == "150000"
        )
    else:
        with pytest.raises(sizing.SizingHold, match="HOLD_NO_VALID_APPROVED_CABINET"):
            sizing.size_composition("CASE", [item], request)


def test_source_exact_size_never_falls_through_to_bigger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    small = synthetic_cab(zones=[synthetic_zone(width=80)])
    bigger = synthetic_cab("CAB-KRN-24", [synthetic_zone(width=200)])
    item, request, _ = provide(
        tmp_path,
        monkeypatch,
        cabinets=[small, bigger],
        fact={"dimensions_status": "EXPLICIT", "dimensions_mm": [265, 330, 100]},
    )
    with pytest.raises(sizing.SizingHold, match="HOLD_SOURCE_DIMENSIONS_INCOMPATIBLE"):
        sizing.size_composition("CASE", [item], request)


def test_source_exact_valid_size_is_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    item, request, _ = provide(
        tmp_path,
        monkeypatch,
        fact={"dimensions_status": "EXPLICIT", "dimensions_mm": [395, 330, 100]},
    )
    assert (
        sizing.size_composition("CASE", [item], request)["items"][0]["cabinet"][
            "cabinet_code"
        ]
        == "CAB-KRN-24"
    )


def test_axis_max_is_brand_neutral_and_mounting_classes_cannot_merge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = synthetic_record(size=[70, 20, 35])
    b = synthetic_record(size=[80, 21, 30])
    b["record_id"] = "DIN-b"
    item, request, _ = provide(tmp_path, monkeypatch, records=[a, b])
    env = sizing.size_composition("CASE", [item], request)["items"][0]["envelopes"][
        "DIN"
    ]
    assert env["dimensions_mm"] == ["80", "21", "35"]
    b["form_factor"] = "ANOTHER"
    _, request, _ = provide(tmp_path, monkeypatch, records=[a, b])
    with pytest.raises(sizing.SizingHold, match="HOLD_CROSS_FORM_FACTOR_MERGE"):
        sizing.size_composition("CASE", [item], request)


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ("source_drift", "HOLD_SOURCE_SHA_DRIFT"),
        ("unapproved", "HOLD_UNAPPROVED_REUSABLE_SOURCE"),
        ("case", "HOLD_CASE_BINDING"),
        ("apparatus", "HOLD_SOURCE_FACT_COMPOSITION_BINDING"),
        ("unknown_size", "HOLD_SOURCE_DIMENSIONS_AMBIGUOUS"),
        ("unknown_install", "HOLD_SOURCE_INSTALLATION_AMBIGUOUS"),
        ("shrink", "HOLD_CABINET_CHANGE_REQUIRES_NEW_HUMAN_APPROVAL"),
    ],
)
def test_evidence_and_approval_boundaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str, reason: str
) -> None:
    fact: dict[str, Any] = {}
    if mutation == "unknown_size":
        fact["dimensions_status"] = "UNKNOWN"
    if mutation == "unknown_install":
        fact["installation"] = None
    if mutation == "shrink":
        fact["prior_approval"] = {
            "status": "APPROVED",
            "cabinet_code": "CAB-KRN-24",
            "dimensions_mm": [395, 330, 100],
        }
    item, request, paths = provide(tmp_path, monkeypatch, fact=fact)
    if mutation == "source_drift":
        paths["devices"].write_bytes(paths["devices"].read_bytes() + b" ")
    if mutation == "unapproved":
        monkeypatch.setattr(evidence, "AUTHORIZED", frozenset())
    if mutation == "case":
        request["case_id"] = "OTHER"
    if mutation == "apparatus":
        item["components"][0]["quantity"] = 2
    with pytest.raises(sizing.SizingHold, match=reason):
        sizing.size_composition("CASE", [item], request)


def test_search_limit_cannot_be_interpreted_as_smaller_impossible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    item, request, _ = provide(tmp_path, monkeypatch)
    monkeypatch.setattr(selector, "SEARCH_LIMIT", 0)
    with pytest.raises(sizing.SizingHold, match="HOLD_LAYOUT_SEARCH_UNCERTAIN"):
        sizing.size_composition("CASE", [item], request)


def test_equal_size_alternatives_hold_without_tie_guess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    item, request, _ = provide(
        tmp_path,
        monkeypatch,
        cabinets=[synthetic_cab("CAB-KRN-48"), synthetic_cab("CAB-KRN-54")],
    )
    with pytest.raises(sizing.SizingHold, match="HOLD_SMALLEST_CABINET_AMBIGUOUS"):
        sizing.size_composition("CASE", [item], request)


@pytest.mark.skipif(
    not evidence.REFERENCE.exists(),
    reason="Local authoritative evidence pool is not distributed with code",
)
def test_real_reference_envelopes_reach_exact_cabinet_evidence_gap() -> None:
    item = {
        "item_id": "I",
        "components": [
            {
                "component_id": "C",
                "component_code": "АВДТ32",
                "component_label": "QF1 АВДТ32 2P C16/30мА",
                "quantity": 1,
            }
        ],
    }
    with pytest.raises(
        sizing.SizingHold, match="HOLD_MISSING_CABINET_USABLE_INTERIOR_INSTALL_EVIDENCE"
    ):
        sizing.size_composition("CASE", [item], selector.request_for("CASE"))


@pytest.mark.skipif(
    not evidence.REFERENCE.exists(),
    reason="Local authoritative evidence pool is not distributed with code",
)
def test_standalone_cli_uses_same_hold_class_and_all_real_signatures(
    tmp_path: Path,
) -> None:
    items = [
        {
            "item_id": f"I{n}",
            "components": [
                {
                    "component_id": "C",
                    "component_code_guess": model,
                    "component_label_guess": label,
                    "quantity_guess": 1,
                }
            ],
        }
        for n, (model, label) in enumerate(
            [
                ("ВА88-32", "QF0 ВА88-32 3P 63А"),
                ("АВДТ32", "QF1 АВДТ32 2P C20/30мА"),
                ("ВН-32", "QF0 ВН-32 3P 25А"),
            ]
        )
    ]
    path = tmp_path / "composition.json"
    path.write_text(json.dumps({"items": items}), encoding="utf-8")
    request_path = tmp_path / "exact-request.json"
    request_path.write_text(json.dumps(selector.request_for("CASE")), encoding="utf-8")
    process = subprocess.run(
        [
            sys.executable,
            "-B",
            str(Path(sizing.__file__)),
            "--case-id",
            "CASE",
            "--composition-json",
            str(path),
            "--request-json",
            str(request_path),
            "--request-sha256",
            hashlib.sha256(request_path.read_bytes()).hexdigest(),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 2, process.stderr
    results = json.loads(process.stdout)["results"]
    assert [r["first_missing"] for r in results] == [
        "HOLD_MISSING_CABINET_USABLE_INTERIOR_INSTALL_EVIDENCE"
    ] * 3


def test_nonmodular_defaults_cannot_be_waived_by_record_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    item = {
        "item_id": "I",
        "components": [
            {"component_id": "C", "component_code": "TEST_PANEL", "quantity": 1}
        ],
    }
    item, request, _ = provide(
        tmp_path,
        monkeypatch,
        item=item,
        records=[synthetic_record("PANEL", mounting="PANEL", size=[80, 60, 20])],
        cabinets=[
            synthetic_cab(zones=[synthetic_zone("PANEL", width=100, height=100)])
        ],
    )
    with pytest.raises(sizing.SizingHold, match="HOLD_NO_VALID_APPROVED_CABINET"):
        sizing.size_composition("CASE", [item], request)


@pytest.mark.parametrize(
    "din_width,panel_height,passes",
    [(25, 900, True), (26, 900, False), (25, 901, False)],
)
def test_mixed_reserve_passes_independently_without_cross_compensation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    din_width: int,
    panel_height: int,
    passes: bool,
) -> None:
    item = {
        "item_id": "I",
        "components": [
            {"component_id": "D", "component_code": "TEST_DIN", "quantity": 3},
            {"component_id": "P", "component_code": "TEST_PANEL", "quantity": 1},
        ],
    }
    # Separate proven zones:100DINmm and600000panelmm2. Neither can subsidise the other.
    zones = [
        synthetic_zone("DIN", width=100, height=200),
        synthetic_zone("PANEL", width=600, height=1000, origin=[200, 0, 0]),
    ]
    item, request, _ = provide(
        tmp_path,
        monkeypatch,
        item=item,
        records=[
            synthetic_record(size=[80, din_width, 30]),
            synthetic_record("PANEL", mounting="PANEL", size=[panel_height, 500, 30]),
        ],
        cabinets=[synthetic_cab("METAL-1200X800X300", zones)],
    )
    if passes:
        reserve = sizing.size_composition("CASE", [item], request)["items"][0][
            "layout"
        ]["reserve"]
        assert (
            reserve["DIN"]["free_mm"] == "25"
            and reserve["PANEL"]["free_mm2"] == "150000"
        )
    else:
        with pytest.raises(sizing.SizingHold, match="HOLD_NO_VALID_APPROVED_CABINET"):
            sizing.size_composition("CASE", [item], request)


@pytest.mark.parametrize("drift_before_phrase", [False, True])
def test_builder_needs_no_cabinet_selection_and_rechecks_before_phrase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, drift_before_phrase: bool
) -> None:
    from test_build_confirmed_composition_from_preliminary_bundle import (
        builder,
        create_batch_bundle,
        fixed_now,
    )
    from test_cabinet_sizing import provision_auto

    root, _, decisions_path = create_batch_bundle(tmp_path)
    decisions = json.loads(decisions_path.read_bytes())
    for entry in decisions["items"]:
        entry["cabinet"].pop("code")
        entry["cabinet"].pop("label")
    decisions_path.write_text(json.dumps(decisions), encoding="utf-8")
    snapshot = builder.load_snapshot(
        builder.resolve_case_paths("CASE-TEST-001", canonical_root=root)
    )
    state = builder.apply_batch_decisions(
        snapshot,
        builder.load_decisions_input(decisions_path),
        case_id="CASE-TEST-001",
        automatic_cabinet=True,
    )
    request, sources = provision_auto(
        tmp_path, monkeypatch, "CASE-TEST-001", state.items
    )
    path = tmp_path / "automatic-request.json"
    path.write_text(json.dumps(request), encoding="utf-8")
    prompts = []

    def ask(prompt: str) -> str:
        prompts.append(prompt)
        return "SYNTHETIC APPROVAL"

    def show(value: str) -> None:
        if drift_before_phrase and "FINAL TECHNICAL COMPOSITION REVIEW" in value:
            sources[0].write_bytes(sources[0].read_bytes() + b" ")

    result = builder.run_builder(
        case_id="CASE-TEST-001",
        confirmation_id="SYNTHETIC",
        approval_channel="synthetic",
        canonical_root=root,
        decisions_json=decisions_path,
        cabinet_sizing_json=path,
        cabinet_sizing_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        approval_phrase="SYNTHETIC APPROVAL",
        input_fn=ask,
        output_fn=show,
        now_fn=fixed_now,
    )
    if drift_before_phrase:
        assert result.status == "HOLD" and prompts == [] and not result.output_created
    else:
        assert (
            result.status == "PASS"
            and len(prompts) == 1
            and "exact approval phrase" in prompts[0]
        )


@pytest.mark.parametrize("usable_width", [100, 150])
def test_din_manufacturer_horizontal_pair_gap_cannot_be_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, usable_width: int
) -> None:
    record = synthetic_record(size=[80, 30, 30])
    record["pair_gap_mm"] = [0, 50]
    item = {
        "item_id": "I",
        "components": [
            {"component_id": "C", "component_code": "TEST_DIN", "quantity": 2}
        ],
    }
    item, request, _ = provide(
        tmp_path,
        monkeypatch,
        item=item,
        records=[record],
        cabinets=[synthetic_cab(zones=[synthetic_zone(width=usable_width)])],
    )
    # 30+50+30=110mm cannot fit in100mm even though the two widths alone do.
    if usable_width == 100:
        with pytest.raises(sizing.SizingHold, match="HOLD_NO_VALID_APPROVED_CABINET"):
            sizing.size_composition("CASE", [item], request)
    else:
        layout = sizing.size_composition("CASE", [item], request)["items"][0]["layout"]
        assert [p["origin_mm"][1] for p in layout["placements"]] == ["0", "80"]
        assert layout["reserve"]["DIN"]["occupied_mm"] == "110"


def test_din_manufacturer_vertical_pair_requirement_holds_when_unsupported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = synthetic_record(size=[80, 70, 30])
    record["pair_gap_mm"] = [70, 0]
    zone = synthetic_zone(height=260)
    zone["rails_mm"] = [40, 180]
    item = {
        "item_id": "I",
        "components": [
            {"component_id": "C", "component_code": "TEST_DIN", "quantity": 2}
        ],
    }
    item, request, _ = provide(
        tmp_path,
        monkeypatch,
        item=item,
        records=[record],
        cabinets=[synthetic_cab("CAB-KRN-24", [zone])],
    )
    # 140mm pitch minus80mm height leaves60mm, below the required70mm.
    with pytest.raises(
        sizing.SizingHold, match="HOLD_DIN_VERTICAL_PAIR_CLEARANCE_UNSUPPORTED"
    ):
        sizing.size_composition("CASE", [item], request)
