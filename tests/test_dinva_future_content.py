from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import build_future_dinva_document as future  # type: ignore[import-not-found]
import dinva_future_content as content  # type: ignore[import-not-found]
import pytest
from openpyxl import load_workbook  # type: ignore[import-untyped]
from test_build_dinva_document_from_case import bridge, inputs, source_payload
from test_dinva_v0_5_print_successor import print_successor
from test_render_dinva_classic_quote_invoice import canonical_file


def component(
    label: str, rating: str, quantity: int, *, section: str = "", group: int = 1
) -> dict[str, Any]:
    return {
        "label": label,
        "rating": rating,
        "quantity": quantity,
        "unit": "шт.",
        "section": section,
        "group_size": group,
        "source_locator": "/items/0/detailed_technical_composition",
    }


def make_plan(
    tmp_path: Path,
    monkeypatch: Any,
    *,
    native: bool = False,
    case_id: str = "CASE-NEW-FUTURE",
    count: int = 1,
) -> tuple[Any, Any]:
    monkeypatch.setenv("DINVA_RENDERER_TEST_MODE", "1")
    s = source_payload(tmp_path, case_id, count)
    if native:
        s["metadata"]["document_number"] = None
        s["items"][0]["enclosure"] = "600×400×250 мм"
    s["schema_version"] = future.SOURCE_SCHEMA
    s["context"] = {
        "case_id": s["case_id"],
        "case_state": "NEW_FUTURE",
        "future_cases_only": True,
        "historical_repricing_authorized": False,
    }
    s["items"][0][
        "detailed_technical_composition"
    ] = "ВА47 1Р 6А — 2шт.; ППН-35 160А — 6шт."
    s["items"][0]["technical_display"] = [
        component("ВА47 1Р", "6А", 2),
        component("ППН-35", "160А", 6, section="Секция1", group=3),
    ]
    for i, item in enumerate(s["items"][1:], 1):
        item["detailed_technical_composition"] = s["items"][0][
            "detailed_technical_composition"
        ]
        item["technical_display"] = copy.deepcopy(s["items"][0]["technical_display"])
        for c in item["technical_display"]:
            c["source_locator"] = f"/items/{i}/detailed_technical_composition"
    s["terms"].update(commercial_lines=None, validity=None, delivery=None)
    ref = tmp_path / "canonical.synthetic.xls"
    ref.write_bytes(b"SYNTHETIC CANONICAL CONTENT")
    s["source_bindings"].append(
        {
            "role": "CANONICAL_744_1",
            "path": str(ref),
            "sha256": bridge.digest(ref.read_bytes()),
        }
    )
    sp = tmp_path / "future-source.json"
    canonical_file(sp, s)
    case = bridge.Snapshot(sp, sp.read_bytes())
    core = future.prepare_core(
        s,
        {
            "role": "AUTHORITATIVE_DOCUMENT_TEXT_SOURCE",
            "path": str(sp),
            "sha256": case.sha256,
        },
    )
    approval = {
        "schema_version": bridge.APPROVAL_SCHEMA,
        "case_id": s["case_id"],
        "authority": "IGOR_DIRECT_HUMAN_APPROVAL",
        "approved_by": "Igor",
        "approved_at": "2026-10-02T09:00:00+05:00",
        "approval_id": "SYNTHETIC",
        "approved_case_source_sha256": case.sha256,
        "approved_document_fingerprint": bridge.renderer.document_fingerprint(core),
        "technical_composition_approved": True,
        "prices_approved": True,
        "commercial_terms_approved": True,
        "rendering_authorized": True,
        "client_send_authorized": False,
    }
    ap = tmp_path / "future-approval.json"
    canonical_file(ap, approval)
    decision = bridge.Snapshot(ap, ap.read_bytes())
    return future.preflight(case, decision, allow_test_profile=True), (case, decision)


def test_compact_sections_preserve_project_ratings_and_group_quantity() -> None:
    components = [
        component("ППН-35", "160А", 3, section="Секция1", group=3),
        component("ППН-35", "160А", 3, section="Секция1", group=3),
        component("ППН-35", "100А", 3, section="Секция1", group=3),
        component("ВА47 1Р", "6А", 2),
    ]
    result = content.technical_display(components)
    assert result == "Секция1: ППН-35 160А - 2гр.; 100А - 1гр.;\nВА47 1Р 6А - 2шт.;"
    with pytest.raises(ValueError, match="incomplete"):
        content.technical_display([component("ППН-35", "160А", 5, group=3)])


def test_engineering_notes_have_no_invented_quantity() -> None:
    note = {**component("N не коммутируется.", "", 1), "quantity": None, "unit": "note"}
    assert content.technical_display([note]) == "N не коммутируется.;"
    with pytest.raises(ValueError, match="invent"):
        content.technical_display([{**note, "quantity": 1}])


def test_section_fuse_groups_use_canonical_descending_current() -> None:
    parts = [
        component("ППН-35", f"{a}А", 3, section="Секция2", group=3)
        for a in [63, 250, 32, 40]
    ]
    assert (
        content.technical_display(parts)
        == "Секция2: ППН-35 250А - 1гр.; 63А - 1гр.; 40А - 1гр.; 32А - 1гр.;"
    )


def test_future_preflight_preserves_engineering_and_sources(
    tmp_path: Path, monkeypatch: Any
) -> None:
    plan, inputs = make_plan(tmp_path, monkeypatch)
    d = plan.document
    assert (
        d["items"][0]["detailed_technical_composition"]
        == inputs[0].payload()["items"][0]["detailed_technical_composition"]
    )
    assert (
        d["items"][0]["apparatus"]["text"]
        == "ВА47 1Р 6А - 2шт.;\nСекция1: ППН-35 160А - 2гр.;"
    )
    assert len(d["terms"]["commercial_lines"]) == 8
    assert "15 рабочих дней" in d["terms"]["commercial_lines"][5]["text"]
    assert (
        d["terms"]["commercial_lines"][-1]["text"]
        == " Примечание: условия поставки EXW г. Астана"
    )
    assert future.preflight(*inputs, allow_test_profile=True).encoded == plan.encoded


@pytest.mark.parametrize(
    "case_id,count", [("CASE-OTHER-FUTURE", 2), ("CASE-THIRD-FUTURE", 7)]
)
def test_content_adapter_is_case_agnostic(
    tmp_path: Path, monkeypatch: Any, case_id: str, count: int
) -> None:
    plan, _ = make_plan(tmp_path, monkeypatch, case_id=case_id, count=count)
    assert plan.document["document_id"] == case_id
    assert len(plan.document["items"]) == count
    assert all(
        i["apparatus"]["source_locator"] == f"/items/{n}/technical_display"
        for n, i in enumerate(plan.document["items"])
    )


def test_accepted_preview_is_read_only_not_future_apply(
    tmp_path: Path, monkeypatch: Any
) -> None:
    s = source_payload(tmp_path, "CASE-LABORATORY-VRU-20260924-001", 1)
    accepted = bridge.preflight(*inputs(tmp_path, s))
    before = accepted.encoded
    ref = tmp_path / "canonical-preview.synthetic.xls"
    ref.write_bytes(b"SYNTHETIC")
    canonical = bridge.Snapshot(ref, ref.read_bytes())
    monkeypatch.setattr(content, "CANONICAL_SHA", canonical.sha256)
    _, profile, _ = print_successor(tmp_path, monkeypatch)
    preview = future.preview_accepted(
        accepted, [[component("ВА47 1Р", "6А", 2)]], canonical, profile
    )
    assert (
        preview["accepted_grand_total_kzt"]
        == accepted.document["approved_grand_total_kzt"]
    )
    assert preview["prices_unchanged"] and preview["full_engineering_unchanged"]
    assert (
        not preview["real_render_authorized"] and not preview["client_send_authorized"]
    )
    assert accepted.encoded == before


@pytest.mark.parametrize(
    "mutation",
    ["rating", "quantity", "engineering", "terms", "order", "locator", "policy"],
)
def test_independent_content_tamper_rejected(
    tmp_path: Path, monkeypatch: Any, mutation: str
) -> None:
    plan, _ = make_plan(tmp_path, monkeypatch)
    d = copy.deepcopy(plan.document)
    if mutation == "rating":
        d["items"][0]["apparatus"]["text"] = d["items"][0]["apparatus"]["text"].replace(
            "6А", "10А"
        )
    elif mutation == "quantity":
        d["items"][0]["apparatus"]["text"] = d["items"][0]["apparatus"]["text"].replace(
            "2гр.", "1гр."
        )
    elif mutation == "engineering":
        d["items"][0]["detailed_technical_composition"] += " OTHER"
    elif mutation == "terms":
        d["terms"]["commercial_lines"].pop()
    elif mutation == "order":
        d["terms"]["commercial_lines"].reverse()
    elif mutation == "locator":
        d["items"][0]["apparatus"]["source_locator"] = "/items/other"
    else:
        d["presentation_policy"]["policy_sha256"] = "0" * 64
    fp = bridge.renderer.document_fingerprint(d)
    d["document_fingerprint"] = fp
    d["approval_provenance"]["approved_document_fingerprint"] = fp
    with pytest.raises(ValueError):
        bridge.validator.validate_document_contract(d, allow_test_profile=True)


def test_v05_render_uses_display_and_canonical_bottom_alignment(
    tmp_path: Path, monkeypatch: Any
) -> None:
    plan, _ = make_plan(tmp_path, monkeypatch)
    _, profile, _ = print_successor(tmp_path, monkeypatch)
    pp = tmp_path / "profile.json"
    ps = canonical_file(pp, profile)
    dp = tmp_path / "document.json"
    ds = canonical_file(dp, plan.document)
    out = tmp_path / "future.synthetic.xlsx"
    bridge.renderer.render(
        profile_path=pp,
        expected_profile_sha256=ps,
        document_path=dp,
        expected_document_sha256=ds,
        output=out,
        allow_test_profile=True,
    )
    bridge.validator.validate_or_raise(
        out, profile, ps, plan.document, ds, allow_test_profile=True
    )
    w = load_workbook(out)
    s = w.active
    assert s["F17"].value == plan.document["items"][0]["apparatus"]["text"]
    for row in range(21, 29):
        assert (
            s[f"C{row}"].value
            == plan.document["terms"]["commercial_lines"][row - 21]["text"]
        )
    assert s["C27"].alignment.horizontal == "general"
    assert s["C22"].font.sz == 16 and s["C22"].font.b
    w.close()
