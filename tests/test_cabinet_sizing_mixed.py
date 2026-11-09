"""Installed-inventory opt-in; every source and admission is TEST-only."""

import hashlib
import json
from pathlib import Path
from typing import Any

import cabinet_sizing as sizing  # type: ignore[import-not-found]
import cabinet_sizing_evidence as evidence  # type: ignore[import-not-found]
import cabinet_sizing_module_accounting as modules  # type: ignore[import-not-found]
import pytest
from module_accounting_fixtures import repin
from test_cabinet_sizing_catalogue import expanded, inject, quote_request, record
from test_versioned_metal_source import synthetic_sources as synthetic_sources


def pin_fact(path: Path, data: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    path.write_text(json.dumps(data), encoding="utf-8")
    binding = dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    monkeypatch.setattr(
        evidence,
        "AUTHORIZED",
        evidence.AUTHORIZED
        | {("pragmatic_source_fact", str(path.resolve()), binding["sha256"])},
    )
    return binding


def make_installed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    item: Any,
    request: Any,
    name: str = "mixed",
) -> Any:
    raw = tmp_path / (name + "-primary.txt")
    raw.write_text(
        "TEST complete installed assembly, connections, zones and inventory facts"
    )
    raw_ref = dict(path=str(raw), sha256=hashlib.sha256(raw.read_bytes()).hexdigest())
    ref = dict(raw_ref, locator="TEST explicit source facts")
    fact = evidence.pragmatic_source_fact(
        request["case_id"], item, request["source_facts"][item["item_id"]]
    )
    classes = evidence.envelopes(request["devices"])
    data: Any = dict(
        schema_version=modules.MIXED_SOURCE_SCHEMA,
        project_fact=fact,
        inventory_scope=modules.SCOPE,
        quantity=item["quantity"],
        project_min_din_free_percent=0,
        project_min_panel_free_percent=0,
        products=[],
        profiles=[],
        instances=[],
        geometry=[],
        candidates=[],
        raw_sources=[raw_ref],
    )
    groups = []
    for ci, c in enumerate(item["components"]):
        env = classes[evidence.class_for(c, request["devices"])]
        kind = env["mounting"]
        h, w, d = env["dimensions_mm"]
        pid = "CORE-" + str(ci)
        dims = list(map(str, [h, w, d]))
        shape = dict(
            nominal_modules=1 if kind == "DIN" else None,
            width_mm=str(w) if kind == "DIN" else None,
            area_mm2=None if kind == "DIN" else str(h * w),
        )
        data["products"].append(
            dict(
                id=pid,
                manufacturer="TEST",
                sku="TEST-" + pid,
                revision="TEST-v1",
                mounting=kind,
                source=ref,
                **shape,
            )
        )
        data["profiles"].append(
            dict(
                id=pid,
                product_ids=[pid],
                left_gap_mm=0,
                right_gap_mm=0,
                allowed_zones=[kind],
                source=ref,
                **shape,
            )
        )
        data["geometry"].append(
            dict(
                profile_id=pid,
                dimensions_mm=dims,
                clearance_mm=list(map(str, env["clearance_mm"])),
                pair_gap_mm=[0, 0],
                extent_scope="INSTALLED_ASSEMBLY_WITH_CONNECTIONS",
                source=ref,
            )
        )
        for unit in range(1, c["quantity"] + 1):
            iid = pid + "-" + str(unit)
            data["instances"].append(
                dict(id=iid, component_id=c["component_id"], unit=unit, product_id=pid)
            )
            groups.append(
                dict(id=iid, profile_id=pid, instance_ids=[iid], zone_id=kind)
            )
    for n in range(3):
        pid = "AUX-" + str(n)
        shape = dict(nominal_modules=None, width_mm=None, area_mm2=400)
        data["products"].append(
            dict(
                id=pid,
                manufacturer="TEST",
                sku="TEST-" + pid,
                revision="TEST-v1",
                mounting="PANEL",
                source=ref,
                **shape,
            )
        )
        data["profiles"].append(
            dict(
                id=pid,
                product_ids=[pid],
                left_gap_mm=0,
                right_gap_mm=0,
                allowed_zones=["PANEL"],
                source=ref,
                **shape,
            )
        )
        data["instances"].append(
            dict(id=pid, component_id=None, unit=1, product_id=pid)
        )
        groups.append(dict(id=pid, profile_id=pid, instance_ids=[pid], zone_id="PANEL"))
        data["geometry"].append(
            dict(
                profile_id=pid,
                dimensions_mm=[20, 20, 10],
                clearance_mm=[0, 0, 0, 0],
                pair_gap_mm=[0, 0],
                extent_scope="INSTALLED_ASSEMBLY_WITH_CONNECTIONS",
                source=ref,
            )
        )
    zones = [
        dict(
            id=kind,
            kind=kind,
            capacity_modules=10 if kind == "DIN" else None,
            capacity_mm=100 if kind == "DIN" else None,
            capacity_area_mm2=None if kind == "DIN" else 20000,
            origin_mm=[0, 0, 0] if kind == "DIN" else [100, 0, 0],
            usable_mm=[100, 100, 100] if kind == "DIN" else [200, 100, 100],
            mounting_plane_mm=0,
            panel_material="metal",
            panel_thickness_mm=2,
            barriers_compatible=True,
            source=ref,
        )
        for kind in ["DIN", "PANEL"]
    ]
    data["candidates"] = [
        dict(
            cabinet_code="TEST-CAB",
            dimensions_mm=[300, 300, 150],
            zones=zones,
            groups=groups,
            source=ref,
        )
    ]
    path = tmp_path / (name + ".json")
    request["source_facts"][item["item_id"]] = pin_fact(path, data, monkeypatch)
    return data, path


@pytest.fixture
def mixed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, synthetic_sources: Any
) -> Any:
    item, req = expanded(tmp_path, monkeypatch, fact={"installation": None})
    inject(monkeypatch, [record("TEST-CAB")])
    req = quote_request(req, synthetic_sources, {"I": "TEST-CAB"})
    data, path = make_installed(tmp_path, monkeypatch, item, req)
    return item, req, data, path


def module_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, item: Any, req: Any
) -> Any:
    base = sizing.size_composition(req["case_id"], [item], req)
    item["cabinet"] = base["items"][0]["cabinet"]
    projection = base["items"][0]["layout"]["installed_inventory"]
    data = dict(
        schema_version=modules.EVIDENCE_SCHEMA,
        case_id=req["case_id"],
        composition_sha256=modules.composition_hash([item]),
        sizing_sha256=sizing.digest(base),
        inventory_scope=modules.SCOPE,
        products=list(projection["products"].values()),
        profiles=list(projection["profiles"].values()),
        boards=[projection["board"]],
        raw_sources=json.loads(
            Path(req["source_facts"][item["item_id"]]["path"]).read_bytes()
        )["raw_sources"],
    )
    path = tmp_path / "module.json"
    binding = repin(monkeypatch, path, data)
    base = modules.size_base(req["case_id"], [item], req, binding)
    data["sizing_sha256"] = sizing.digest(base)
    binding = repin(monkeypatch, path, data)
    return base, binding, data


def test_full_mixed_pass_and_exact_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mixed: Any
) -> None:
    item, req, _, _ = mixed
    base, binding, _ = module_source(tmp_path, monkeypatch, item, req)
    report = modules.build_sizing_report("CASE", [item], base, binding)
    sizing.verify_before_ha1(report, [item], expected_case_id="CASE")
    selection = base["items"][0]
    assert selection["calculation_status"] == "PASS"
    assert (
        selection["physical_fit_status"]
        == selection["minimality_status"]
        == "NOT_VERIFIED"
    )
    assert len(selection["layout"]["placements"]) == 6
    assert (
        report["module_ledger"]["items"][0]["zones"][1]["occupied_area_mm2"] == "1200"
    )
    with pytest.raises(sizing.SizingHold, match="HOLD_MODULE_LEDGER_REQUIRED"):
        sizing.verify_report(
            sizing.size_composition("CASE", [item], req),
            [item],
            expected_case_id="CASE",
        )


@pytest.mark.parametrize(
    "fault,reason",
    [
        ("scope", "HOLD_MIXED_COMPLETE_INVENTORY"),
        ("hwd", "HOLD_DIMENSION_VECTOR"),
        ("clearance", "HOLD_MIXED_CLEARANCE_SCHEMA"),
        ("overlap", "HOLD_MIXED_ZONES_OVERLAP"),
        ("double", "HOLD_MODULE_DUPLICATE_OR_UNKNOWN_FOOTPRINT"),
        ("inclusion", "HOLD_MODULE_FOOTPRINT_MEMBERS"),
        ("body", "HOLD_MIXED_INSTALLED_ASSEMBLY_REQUIRED"),
        ("reserve", "HOLD_MODULE_RESERVE:PANEL"),
        ("capacity", "HOLD_MIXED_CAPACITY_OUTSIDE_GEOMETRY"),
        ("zone", "HOLD_MODULE_PLACEMENT_CONSTRAINT"),
        ("modules", "HOLD_MODULE_NOMINAL_MODULES_REQUIRED"),
        ("bounds", "HOLD_MIXED_ZONE_OUTSIDE_CABINET"),
        ("packing", "MIXED_SOURCE_ZONE_GEOMETRY_INSUFFICIENT"),
        ("raw", "HOLD_MODULE_UNBOUND_RAW_SOURCE"),
        ("identity", "HOLD_MIXED_CABINET_IDENTITY"),
        ("project", "HOLD_INVALID_EXACT_MM"),
    ],
)
def test_mixed_negative_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mixed: Any, fault: str, reason: str
) -> None:
    item, req, data, path = mixed
    c = data["candidates"][0]
    if fault == "scope":
        data["inventory_scope"] = "PARTIAL"
    elif fault == "hwd":
        data["geometry"][-1]["dimensions_mm"] = None
    elif fault == "clearance":
        data["geometry"][-1]["clearance_mm"] = None
    elif fault == "overlap":
        c["zones"][1]["origin_mm"] = [0, 0, 0]
    elif fault == "double":
        c["groups"][-1]["instance_ids"] = c["groups"][-2]["instance_ids"]
    elif fault == "inclusion":
        data["profiles"][-1]["product_ids"] = ["AUX-1"]
    elif fault == "body":
        data["geometry"][0]["extent_scope"] = "BODY_ONLY"
    elif fault == "reserve":
        c["zones"][1]["capacity_area_mm2"] = 1200
    elif fault == "capacity":
        c["zones"][1]["capacity_area_mm2"] = 30000
    elif fault == "zone":
        c["groups"][-1]["zone_id"] = "ABSENT"
    elif fault == "modules":
        data["products"][0]["nominal_modules"] = None
    elif fault == "bounds":
        c["zones"][1]["origin_mm"] = [200, 0, 0]
    elif fault == "packing":
        data["geometry"][-1]["dimensions_mm"][2] = 120
    elif fault == "raw":
        data["geometry"][-1]["source"] = dict(
            data["geometry"][-1]["source"], sha256="0" * 64
        )
    elif fault == "identity":
        c["dimensions_mm"] = [300, 300, 151]
    elif fault == "project":
        data["project_min_panel_free_percent"] = None
    req["source_facts"]["I"] = pin_fact(path, data, monkeypatch)
    with pytest.raises(sizing.SizingHold, match=reason):
        sizing.size_composition("CASE", [item], req)


@pytest.mark.parametrize("target", ["geometry", "primary", "ledger", "result"])
def test_mixed_exact_recompute_rejects_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mixed: Any, target: str
) -> None:
    item, req, data, path = mixed
    base, binding, ledger = module_source(tmp_path, monkeypatch, item, req)
    report = modules.build_sizing_report("CASE", [item], base, binding)
    if target == "geometry":
        path.write_bytes(path.read_bytes() + b" ")
    elif target == "primary":
        Path(data["raw_sources"][0]["path"]).write_text("DRIFT")
    elif target == "result":
        report["base_report"]["items"][0]["layout"]["placements"][0]["origin_mm"][
            0
        ] = "1"
    else:
        ledger["boards"][0]["zones"][1]["capacity_area_mm2"] = 19000
        binding = repin(monkeypatch, Path(binding["path"]), ledger)
        report["sources"]["module_evidence"] = binding
        report["module_ledger"]["evidence_binding"] = binding
    with pytest.raises(sizing.SizingHold, match="HOLD_"):
        sizing.verify_before_ha1(report, [item], expected_case_id="CASE")


def test_mixed_cannot_enlarge_known_construction_capacity(
    monkeypatch: pytest.MonkeyPatch, mixed: Any
) -> None:
    item, req, _, _ = mixed
    cab = record("TEST-CAB")
    cab["din_capacity_binding"] = dict(
        rail_count=1, rail_capacity_mm=50, total_capacity_mm=50, modules_per_rail=12
    )
    inject(monkeypatch, [cab])
    with pytest.raises(
        sizing.SizingHold, match="HOLD_MIXED_CONSTRUCTION_CAPACITY_CONFLICT"
    ):
        sizing.size_composition("CASE", [item], req)


def test_unadmitted_installed_source_cannot_opt_in(
    monkeypatch: pytest.MonkeyPatch, mixed: Any
) -> None:
    item, req, _, _ = mixed
    b = req["source_facts"]["I"]
    monkeypatch.setattr(
        evidence,
        "AUTHORIZED",
        frozenset(x for x in evidence.AUTHORIZED if x[2] != b["sha256"]),
    )
    with pytest.raises(sizing.SizingHold, match="HOLD_UNAPPROVED_REUSABLE_SOURCE"):
        sizing.size_composition("CASE", [item], req)


@pytest.mark.parametrize(
    "stage", ["before_phrase", "after_phrase", "publication", "success"]
)
def test_mixed_native_three_ha1_rechecks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, synthetic_sources: Any, stage: str
) -> None:
    from module_accounting_fixtures import NATIVE_BUILD
    from test_build_confirmed_composition_from_preliminary_bundle import (
        builder,
        create_batch_bundle,
        fixed_now,
    )
    from test_cabinet_sizing_catalogue import builder_request

    root, _, decisions = create_batch_bundle(tmp_path)
    snapshot = builder.load_snapshot(
        builder.resolve_case_paths("CASE-TEST-001", canonical_root=root)
    )
    state = builder.apply_batch_decisions(
        snapshot,
        builder.load_decisions_input(decisions),
        case_id="CASE-TEST-001",
        automatic_cabinet=True,
    )
    assert len(state.items) == 1
    req = quote_request(
        builder_request(tmp_path, monkeypatch, state.items),
        synthetic_sources,
        {state.items[0]["item_id"]: "TEST-CAB"},
    )
    inject(monkeypatch, [record("TEST-CAB")])
    data, path = make_installed(tmp_path, monkeypatch, state.items[0], req)
    base, binding, _ = module_source(tmp_path, monkeypatch, state.items[0], req)
    monkeypatch.setattr(modules, "build_sizing_report", NATIVE_BUILD)
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(req), encoding="utf-8")
    prompts = []

    def drift() -> None:
        path.write_bytes(path.read_bytes() + b" ")

    def output(text: str) -> None:
        if stage == "before_phrase" and "FINAL TECHNICAL" in text:
            drift()

    def ask(prompt: str) -> str:
        prompts.append(prompt)
        return "SYNTHETIC APPROVAL"

    if stage == "publication":

        def publication(**kwargs: Any) -> None:
            drift()
            kwargs["recheck"]()
            pytest.fail("Drift must stop publication")

        monkeypatch.setattr(builder, "publish_atomically", publication)
    result = builder.run_builder(
        case_id="CASE-TEST-001",
        confirmation_id="TEST-MIXED",
        approval_channel="synthetic",
        canonical_root=root,
        decisions_json=decisions,
        cabinet_sizing_json=request_path,
        cabinet_sizing_sha256=hashlib.sha256(request_path.read_bytes()).hexdigest(),
        module_evidence_json=Path(binding["path"]),
        module_evidence_sha256=binding["sha256"],
        input_fn=ask,
        output_fn=output,
        approval_phrase="SYNTHETIC APPROVAL",
        now_fn=fixed_now,
        before_drift_check=drift if stage == "after_phrase" else None,
    )
    assert result.status == ("PASS" if stage == "success" else "HOLD"), result.red_flags
    assert result.output_created == (stage == "success")
    assert len(prompts) == (0 if stage == "before_phrase" else 1)
    if stage == "success":
        artifact = json.loads((result.output_dir / builder.ARTIFACT_NAME).read_bytes())
        assert artifact["safety"]["production_authorized"] is False
        assert artifact["safety"]["price_approved_by_igor"] is False


def test_area_reserve_pass_does_not_replace_rectangle_calculation(
    monkeypatch: pytest.MonkeyPatch, mixed: Any
) -> None:
    item, req, data, path = mixed
    zone = data["candidates"][0]["zones"][1]
    zone.update(usable_mm=[100, 100, 100], capacity_area_mm2=10000)
    for i, (h, w) in enumerate([(60, 60), (60, 60), (10, 10)]):
        data["geometry"][i + 1]["dimensions_mm"] = [h, w, 10]
        data["products"][i + 1]["area_mm2"] = h * w
        data["profiles"][i + 1]["area_mm2"] = h * w
    req["source_facts"]["I"] = pin_fact(path, data, monkeypatch)
    # 7300/10000 has27% spare, but two60x60 rectangles cannot share100x100.
    with pytest.raises(
        sizing.SizingHold, match="MIXED_SOURCE_ZONE_GEOMETRY_INSUFFICIENT"
    ):
        sizing.size_composition("CASE", [item], req)


@pytest.mark.parametrize("body_only", [False, True])
def test_panel_core_requires_installed_connection_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    synthetic_sources: Any,
    body_only: bool,
) -> None:
    from test_cabinet_sizing_selector import synthetic_record

    item = dict(
        item_id="I",
        product_name="TEST M63 assembly",
        quantity=1,
        components=[
            dict(component_id="P", component_code="TEST_PANEL", quantity=1),
            dict(component_id="D", component_code="TEST_DIN", quantity=1),
        ],
    )
    item, req = expanded(
        tmp_path,
        monkeypatch,
        item=item,
        records=[
            synthetic_record("PANEL", mounting="PANEL", size=[90, 20, 30]),
            synthetic_record(),
        ],
        fact={"installation": None},
    )
    req = quote_request(req, synthetic_sources, {"I": "TEST-CAB"})
    inject(monkeypatch, [record("TEST-CAB")])
    data, path = make_installed(tmp_path, monkeypatch, item, req)
    if body_only:
        data["geometry"][0]["extent_scope"] = "BODY_ONLY"
        req["source_facts"]["I"] = pin_fact(path, data, monkeypatch)
        with pytest.raises(
            sizing.SizingHold, match="HOLD_MIXED_INSTALLED_ASSEMBLY_REQUIRED"
        ):
            sizing.size_composition("CASE", [item], req)
    else:
        base, binding, _ = module_source(tmp_path, monkeypatch, item, req)
        report = modules.build_sizing_report("CASE", [item], base, binding)
        sizing.verify_before_ha1(report, [item], expected_case_id="CASE")


def test_shared_profile_ownership_is_counted_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mixed: Any
) -> None:
    item, req, data, path = mixed
    data["profiles"][1]["product_ids"] = ["AUX-0", "AUX-1"]
    data["profiles"][1]["area_mm2"] = 800
    del data["profiles"][2]
    data["geometry"][1]["dimensions_mm"] = [20, 40, 10]
    del data["geometry"][2]
    groups = data["candidates"][0]["groups"]
    groups[-3]["instance_ids"] = ["AUX-0", "AUX-1"]
    del groups[-2]
    req["source_facts"]["I"] = pin_fact(path, data, monkeypatch)
    base, binding, _ = module_source(tmp_path, monkeypatch, item, req)
    report = modules.build_sizing_report("CASE", [item], base, binding)
    sizing.verify_before_ha1(report, [item], expected_case_id="CASE")
    assert len(base["items"][0]["layout"]["placements"]) == 5


def test_legacy_marker_cannot_forge_mixed_proof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, synthetic_sources: Any
) -> None:
    from module_accounting_fixtures import provision_modules

    item, req = expanded(tmp_path, monkeypatch, fact={"installation": None})
    req = quote_request(req, synthetic_sources, {"I": "TEST-CAB"})
    inject(monkeypatch, [record("TEST-CAB")])
    base = sizing.size_composition("CASE", [item], req)
    item["cabinet"] = base["items"][0]["cabinet"]
    binding, data = provision_modules(tmp_path, monkeypatch, "CASE", [item], base)
    base = modules.size_base("CASE", [item], req, binding)
    data["sizing_sha256"] = sizing.digest(base)
    binding = repin(monkeypatch, Path(binding["path"]), data)
    report = modules.build_sizing_report("CASE", [item], base, binding)
    report["base_report"]["items"][0]["layout"][
        "calculation_schema"
    ] = modules.MIXED_LAYOUT_SCHEMA
    with pytest.raises(sizing.SizingHold, match="HOLD_SIZING_REPORT_DRIFT"):
        sizing.verify_before_ha1(report, [item], expected_case_id="CASE")


def test_mixed_identity_uses_exact_decimal_mm(
    monkeypatch: pytest.MonkeyPatch, mixed: Any
) -> None:
    item, req, data, path = mixed
    data["project_fact"].update(
        dimensions_status="EXPLICIT", dimensions_mm=["300", "300", "150"]
    )
    data["candidates"][0]["dimensions_mm"] = ["300", "300", "150"]
    req["source_facts"]["I"] = pin_fact(path, data, monkeypatch)
    assert (
        sizing.size_composition("CASE", [item], req)["items"][0]["calculation_status"]
        == "PASS"
    )


def test_installed_source_cannot_downgrade_to_legacy_pragmatic(mixed: Any) -> None:
    item, req, _, _ = mixed
    legacy = {
        k: v for k, v in req.items() if k not in {"metal_source", "quote_choices"}
    }
    legacy["schema_version"] = "cabinet_sizing.pragmatic_metal_request.v0.1"
    with pytest.raises(sizing.SizingHold, match="HOLD_SOURCE_FACT_SCHEMA"):
        sizing.size_composition("CASE", [item], legacy)


@pytest.mark.parametrize("axis", [0, 1])
@pytest.mark.parametrize("required", [20, 30])
@pytest.mark.parametrize("gap_owner", [0, 1])
def test_pair_gaps_apply_between_panel_zones(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mixed: Any,
    axis: int,
    required: int,
    gap_owner: int,
) -> None:
    item, req, data, path = mixed
    candidate = data["candidates"][0]
    candidate["dimensions_mm"] = [400, 300, 150]
    inject(monkeypatch, [record("TEST-CAB", size=[400, 300, 150])])
    first_zone = candidate["zones"][1]
    first_zone.update(
        origin_mm=[120, 0, 0], usable_mm=[100, 100, 100], capacity_area_mm2=10000
    )
    candidate["zones"].append(
        dict(
            first_zone,
            id="PANEL-SECOND",
            origin_mm=[220, 0, 0] if axis == 0 else [120, 100, 0],
        )
    )
    candidate["zones"].append(
        dict(
            first_zone,
            id="PANEL-FAR",
            origin_mm=[330, 0, 0],
            usable_mm=[50, 50, 100],
            capacity_area_mm2=2500,
        )
    )
    shape = [80, 50, 10] if axis == 0 else [50, 80, 10]
    for index in (0, 1):
        data["geometry"][index + 1]["dimensions_mm"] = shape
        data["products"][index + 1]["area_mm2"] = 4000
        data["profiles"][index + 1]["area_mm2"] = 4000
    data["geometry"][gap_owner + 1]["pair_gap_mm"] = [required, required]
    data["profiles"][2]["allowed_zones"] = ["PANEL-SECOND"]
    candidate["groups"][-2]["zone_id"] = "PANEL-SECOND"
    data["profiles"][3]["allowed_zones"] = ["PANEL-FAR"]
    candidate["groups"][-1]["zone_id"] = "PANEL-FAR"
    req["source_facts"]["I"] = pin_fact(path, data, monkeypatch)
    if required == 30:
        # The source zones are disjoint and the body-to-body gap is only 20 mm.
        with pytest.raises(
            sizing.SizingHold, match="HOLD_MIXED_CROSS_ZONE_PAIR_GAP_UNCERTAIN"
        ) as held:
            sizing.size_composition("CASE", [item], req)
        outcome = held.value.details["candidate_outcomes"][0]
        assert outcome["quote_assessment"]["calculation_status"] == "HOLD"
    else:
        base, binding, _ = module_source(tmp_path, monkeypatch, item, req)
        report = modules.build_sizing_report("CASE", [item], base, binding)
        sizing.verify_before_ha1(report, [item], expected_case_id="CASE")
        placed = {p["group_id"]: p for p in base["items"][0]["layout"]["placements"]}
        assert placed["AUX-0"]["origin_mm"][:2] == ["120", "0"]
        assert placed["AUX-1"]["origin_mm"][:2] == (
            ["220", "0"] if axis == 0 else ["120", "100"]
        )


@pytest.mark.parametrize("required", [20, 30])
def test_pair_gaps_apply_between_din_and_panel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mixed: Any,
    required: int,
) -> None:
    item, req, data, path = mixed
    data["geometry"][1]["pair_gap_mm"] = [required, required]
    req["source_facts"]["I"] = pin_fact(path, data, monkeypatch)
    # Core DIN bodies end at H80 and the first PANEL body starts at H100.
    if required == 30:
        with pytest.raises(
            sizing.SizingHold, match="HOLD_MIXED_CROSS_ZONE_PAIR_GAP_UNCERTAIN"
        ):
            sizing.size_composition("CASE", [item], req)
    else:
        base, binding, _ = module_source(tmp_path, monkeypatch, item, req)
        report = modules.build_sizing_report("CASE", [item], base, binding)
        sizing.verify_before_ha1(report, [item], expected_case_id="CASE")
