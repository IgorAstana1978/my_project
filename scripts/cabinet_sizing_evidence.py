"""Code-authorized reusable sizing evidence; hashes alone confer no authority."""

from __future__ import annotations

import hashlib
import json
import re
import stat
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from cabinet_sizing import SizingHold, require
from governed_case_intake import _pairs

ROOT = Path(
    "C:/Users/IgorN/.codex/visualizations/2026/10/19/"
    "01a152a7-a41d-7070-900c-b4f6cf4744e6"
)
REFERENCE = ROOT / "wu15-device-envelope-v02/reference-envelopes.json"
REFERENCE_SHA = "cf09e8a17f0017d170cfd82d612caa6d51b1891c4719c5824c04d4111f0188ae"
PRAGMATIC_REVIEW = (
    ROOT / "wu15-reserve-source-precedence/cabinet-research/cabinet-evidence.json"
)
PRAGMATIC_REVIEW_SHA = (
    "8ec1d8925ad9974a7ce3596ca9445678b5b4fab2bab4e8d40651f4112109ba88"
)
WU15_CASE = (
    "CASE-TELEGRAM-B4D84204A74200E06B5A18BD371C949ABB899372265FBCDCF2ECF2C898B13A4B"
)
WU15_DRAFT_SHA = "218c3dcd135c1e08bdf573aac00e96e8cd4cb0b8bb0a2044c9faa6cbae5754ae"
WU15_CASE_ROOT = Path(
    "C:/Users/IgorN/Documents/production_ai_cases/telegram-employee-cases"
)
WU15_PDF_SHA = "c25dae3b09123621cf14a484c70d02b086e315b57a68ed3e1c9aeba79bc55b1c"
# Direct Igor manufacturer decision, 2026-10-30; exact catalogue 2026.10.21
# identities only. No CAD/assembly, usable interior or physical FIT authority.
METAL_STANDARD_ROOT = Path(
    "C:/Users/IgorN/.codex/visualizations/2026/10/30/"
    "01a18cd5-327b-7d63-befa-6cf988eed444/"
    "standard-metal-manufacturer-decision-20261030-v01"
)
METAL_STANDARD_BINDINGS = {
    f"CATALOGUE-METAL-ROW-{row}": {
        "path": str(METAL_STANDARD_ROOT / f"metal-row-{row}.json"),
        "sha256": sha,
    }
    for row, sha in {
        8: "73bd77f6047edfbeb75c23a5629ac827880e28f2d90c8984f7600e34bcff0572",
        9: "0f2c208fce2e938e3e1a1e95c1bb46f143b2d9c23b2b0fd5aa1f6b4b140fbab1",
        10: "3e038bb359e017230a6ea14bb3965bc854d0f88dc462d2c1cc62acd94927963c",
        11: "05f415394b461822f9c8d927dc5567bc61906a3a2cf30f0ffda3d20953560905",
        12: "a3bf9e2625cca58c66d14bd35207e56d01e4b28eb9ec9273a60e3a61bf1b40cf",
        13: "5e3436954efd886f64e5e72c5ab934f6293efeb8f36fb2501606666b47f49154",
        14: "afca96975dbce794642455b07b7396611fe086b1752ec52381a15f07d018f4a1",
        15: "f9114d1c66ff8c17d250c94ab39511ad201bef516b0a605215d96bfe418569f6",
        16: "849d11a0fa6ff7e170bc17f2dc192051206608b8b16d777d368269fcca368a3f",
        17: "7e7b76fbfcc39489271cc52bfad1ffef10a4372939f9aeb148195ccba4507a02",
        18: "4f40529660a7dcc9af347f1e011c330687701e560a014b7c10878c066f8b0802",
        19: "449beb778b2d098780b31652d512cd3e13767437354995ee6f0d046976f13e69",
        20: "3cdaaf16731e23a1206ccc7a775a9b132a51ba6c7553d5c45289d63b6e8cdfbd",
        21: "cf28955d2e78c2a7e17d3850c0d4c96f20312a8275efb282eb9a5a379a5a02d8",
        22: "3fc5eeecc121ef7131d4b03899664660164e4cc2a1b1103242835a07f098d20d",
        23: "e55f2d6e4111ceb799fd2c4c3d2f9f5e0627470379b69986f3f249fa9f3137ee",
        24: "7002c54508d3e37212fd91c17e2c57bef8e33a18da017130370aaff28651e0bf",
        25: "d8b02f03994b62e09f53349022824ffbc612fa149c1437133c77086a4c0debe0",
        26: "eff64a29b16e118ccc32edce5dd0f743b99d139b63adc05fe4dcc39f527e7bd2",
        27: "24979253f2b3415264f2f75681ecf167c202db17cf6da9bbbf5aaabac9292afa",
        28: "476d6b4ded53baa104bb1d4c4317948e065aaba2458bbce4808e65321864a32c",
        29: "b1040b809a6eb62d60e1d5dbc9403fff64569c58516cad4321a1f18da2b799bd",
        30: "dd131ab3dc5b98bad93e749fdb1f814219a299875d96c398e48cb039c91f5e1d",
        31: "32aba513a8611035499a8712d39850b97735009fdb043045e98bd2f6252892e4",
        32: "918ac6456df69765e8ad175d5c6991f06c23d42c61981ec84fa1efaf5e8c8679",
        33: "e69d9d31c8499441dd651429ac4ad8ebd46bc6fc3078793a4640a0db42c60667",
        34: "a173c03af252b01748264b9f2d7f8037543aa935240b4dde3f195c54f0450216",
        35: "49c376849a052d128becf79c446f0b90676b2b298ebbe3ddc6c8b8ebcdc3ccf2",
        36: "3e4d84611cdf5f6319630cca86de5470b3ff20f4d3e596d08880f879def271c5",
        37: "fb73c7982463b49c9236ee01754445918d71617fbc98530c6b116160345820c4",
        38: "9e56f63ffe23ea5136edd36325dca47531d29203cdd03726371bcf2520d33da8",
        39: "f9ac4e27d4190d8ad8770c87f1e33805ab429bdffcce310fa1ea4da422d794e7",
        40: "ba2639aac519e6a6a2e72fb9aca0986dfcfa379ae6723facee6c5fb5b91e654a",
        41: "969adeb9beb9dc019fc6364f5b38a6df5e8b4f626a1df0ae0c981889445fa716",
        42: "972716164897c510a78b180248751857ede68d3ecb50bdc9ced2c70925db4e5c",
        43: "e815599f3e1c22fec741a262b5365d01ef6a7a5e5958f69b8c0041e9f0111a87",
        44: "3f84fb9b1df5e5c15099dbab0d42da1c516686fd41bc092b83c4c849f13fc72f",
        45: "7810e35bb31f9b872ed3971ae311a03734bffa6083b9036d13280e24f6c39d9a",
        46: "e05d23a8d9aa5017f915eb036a0f3798268bb608886a0d26dd82272f801eefe2",
        47: "1f6778832f257c2deba6576fff8a74e1881d0424afc0bfc8977423a23b79c8fc",
    }.items()
}
# Admission is a reviewed code change, never an approval flag inside input JSON.
# Exact cabinet-interior authority remains empty. The preliminary source review
# below is separately admitted and cannot authorize exact mounting geometry.
AUTHORIZED: frozenset[tuple[str, str, str]] = frozenset(
    {
        ("devices", str(REFERENCE.resolve()), REFERENCE_SHA),
        (
            "devices",
            str(
                Path(
                    "C:/Users/IgorN/.codex/visualizations/2026/11/04/"
                    "01a1a5cb-2980-7991-9ac6-f76358deaacc/"
                    "iek-case-evidence-review-20261105-v1/"
                    "devices.din.frozen.DRAFT.json"
                ).resolve()
            ),
            "e07815e93861883641bb9481d5b8b7b755a463691aee5af4385f4159f25848bb",
        ),
        (
            "pragmatic_source_fact",
            str(PRAGMATIC_REVIEW.resolve()),
            PRAGMATIC_REVIEW_SHA,
        ),
    }
) | frozenset(
    ("metal_standard_construction", str(Path(b["path"]).resolve()), b["sha256"])
    for b in METAL_STANDARD_BINDINGS.values()
)


def pragmatic_default_binding() -> dict[str, str]:
    return {"path": str(PRAGMATIC_REVIEW), "sha256": PRAGMATIC_REVIEW_SHA}


def _structural_projection_matches(item: Any, projected: Any) -> bool:
    """Only rename source fields; no description, quantity or install decision."""
    from cabinet_sizing import apparatus_hash

    actual = item["components"]
    source = projected["components"]
    if len(actual) != len(source):
        return False
    canonical = []
    for component, raw in zip(actual, source, strict=True):
        install = component.get("install_type")
        if install not in {None, raw["install_type_guess"]}:
            return False
        expected = {
            "component_id": raw["component_id"],
            "component_code": raw["component_code_guess"],
            "component_label": raw["component_label_guess"],
            "quantity": raw["quantity_guess"],
            "install_type": install,
        }
        if component != expected:
            return False
        canonical.append(expected)
    return apparatus_hash(item) == apparatus_hash(dict(projected, components=canonical))


def pragmatic_source_fact(case_id: str, item: Any, binding: Any) -> dict[str, Any]:
    """Narrow reviewed WU15 adapter; absence is never generalized to other Cases."""
    data = read(binding, "pragmatic_source_fact")
    if data.get("schema_version") == "cabinet_sizing.pragmatic_decisions.v0.1":
        from cabinet_sizing_decisions import source_fact

        return source_fact(case_id, item, binding, data)
    if binding != pragmatic_default_binding():
        return data
    from cabinet_sizing import apparatus_hash

    expected_case = WU15_CASE
    require(case_id == expected_case, "HOLD_SOURCE_FACT_COMPOSITION_BINDING")
    draft_path = WU15_CASE_ROOT / expected_case / "preliminary-composition-draft.json"
    raw = safe_bytes(draft_path, WU15_DRAFT_SHA)
    draft = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
    names = {"ITEM-001": "ЩО6", "ITEM-002": "НЩР", "ITEM-003": "АВР"}
    matches = [entry for entry in draft["items"] if entry["item_id"] == item["item_id"]]
    require(
        len(matches) == 1 and item["item_id"] in names,
        "HOLD_SOURCE_FACT_COMPOSITION_BINDING",
    )
    expected = matches[0]
    projected = dict(expected, product_name=names[item["item_id"]], quantity=1)
    require(
        apparatus_hash(item) in {apparatus_hash(expected), apparatus_hash(projected)}
        or _structural_projection_matches(item, projected),
        "HOLD_SOURCE_FACT_COMPOSITION_BINDING",
    )
    source = data["case_source"]
    require(
        source["sha256"] == WU15_PDF_SHA,
        "HOLD_SOURCE_FACT_RAW_BINDING",
    )
    safe_bytes(Path(source["path"]), source["sha256"])
    require(
        data["boards"][names[item["item_id"]]]["explicit_source_cabinet_dimensions_mm"]
        is None,
        "HOLD_SOURCE_DIMENSIONS_AMBIGUOUS",
    )
    # NONE is direct scoped Human authority, not an approval flag in that JSON.
    return {
        "case_id": case_id,
        "item_id": item["item_id"],
        "apparatus_sha256": apparatus_hash(item),
        "dimensions_status": "ABSENT",
        "dimensions_mm": None,
        "installation": None,
        "prior_approval": {"status": "NONE"},
        "raw_sources": [
            {"path": source["path"], "sha256": source["sha256"]},
            {
                "path": str(draft_path),
                "sha256": WU15_DRAFT_SHA,
            },
        ],
    }


def number(value: Any, *, zero: bool = False) -> Decimal:
    require(type(value) in (int, float, str, Decimal), "HOLD_INVALID_EXACT_MM")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise SizingHold("HOLD_INVALID_EXACT_MM") from exc
    require(
        result.is_finite() and result >= 0 and (zero or result > 0),
        "HOLD_INVALID_EXACT_MM",
    )
    exponent = result.as_tuple().exponent
    require(
        isinstance(exponent, int) and exponent >= -6, "HOLD_MM_PRECISION_UNSUPPORTED"
    )
    require(result <= 100000, "HOLD_MM_RANGE_UNSUPPORTED")
    return result


def dimensions(value: Any, *, zero: bool = False) -> list[Decimal]:
    require(isinstance(value, list) and len(value) == 3, "HOLD_DIMENSION_VECTOR")
    return [number(v, zero=zero) for v in value]


def safe_bytes(path: Path, sha: str, *, limit: int = 16 * 1024 * 1024) -> bytes:
    require(path.is_absolute(), "HOLD_SOURCE_ABSOLUTE_PATH_REQUIRED")
    for ancestor in (path, *path.parents):
        if ancestor.exists():
            require(
                not ancestor.is_symlink()
                and not getattr(ancestor.lstat(), "st_file_attributes", 0)
                & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0),
                "HOLD_SOURCE_REPARSE_POINT",
            )
    raw = path.read_bytes()
    require(len(raw) <= limit, "HOLD_SOURCE_TOO_LARGE")
    require(hashlib.sha256(raw).hexdigest() == sha, "HOLD_SOURCE_SHA_DRIFT")
    return raw


def read(binding: Any, role: str) -> dict[str, Any]:
    require(
        isinstance(binding, dict) and set(binding) == {"path", "sha256"},
        "HOLD_AUTOMATIC_SOURCE_BINDING",
    )
    require(
        all(isinstance(v, str) and v for v in binding.values()),
        "HOLD_AUTOMATIC_SOURCE_BINDING",
    )
    path = Path(binding["path"])
    require(path.is_absolute(), "HOLD_SOURCE_ABSOLUTE_PATH_REQUIRED")
    require(
        (role, str(path.resolve()), binding["sha256"]) in AUTHORIZED,
        f"HOLD_UNAPPROVED_REUSABLE_SOURCE:{role}",
    )
    raw = safe_bytes(path, binding["sha256"], limit=1024 * 1024)
    data = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
    require(isinstance(data, dict), "HOLD_REUSABLE_SOURCE_SCHEMA")
    # The admitted artifact binds all raw evidence too. No unchecked URL facts.
    for ref in data.get("raw_sources", []):
        require(isinstance(ref, dict), "HOLD_RAW_SOURCE_SCHEMA")
        safe_bytes(Path(ref["path"]), ref["sha256"])
    return dict(data)


def default_binding() -> dict[str, str]:
    return {"path": str(REFERENCE), "sha256": REFERENCE_SHA}


def _reference_records(data: dict[str, Any]) -> list[dict[str, Any]]:
    authority = data["authority"]
    safe_bytes(Path(authority["path"]), authority["sha256"])
    result = []
    for record in data["records"]:
        for ref in record["sources"]:
            safe_bytes(Path(ref["path"]), ref["sha256"])
        cid = record["class_id"]
        constraints = record["constraints"]
        panel = cid == "MCCB_3P_STATIONARY_PANEL"
        common: dict[str, Any] = {
            "min_ip": [0, 0] if panel else [3, 0],
            "shock_class": "I" if cid == "SWITCH_DISCONNECTOR_3P_TH35" else None,
        }
        entry = {
            "record_id": record["record_id"],
            "class_id": cid,
            "mounting": "PANEL" if panel else "DIN",
            "form_factor": "MCCB_STATIONARY" if panel else "TH35_MODULAR",
            "dimensions_mm": record["dimensions_mm"],
            "clearance_mm": [50, 50, 20, 20] if panel else [0, 0, 0, 0],
            "pair_gap_mm": [0, 0],
            "extra_gap_mm": 0,
            "rail_offset_mm": None,
            "rail_back_mm": None,
            "requirements": common,
            "body_reference": None,
            "sources": record["sources"],
        }
        if panel:
            entry["body_reference"] = {
                "dimensions_mm": constraints["body_dimensions_mm"],
                "edge_mm": [122.5, 122.5, 20, 20],
                "pair_gap_mm": [122.5, 50],
                "metal_panel_min_mm": 1.5,
                "insulating_panel_min_mm": 6,
                "interphase_barriers_required": True,
            }
        result.append(entry)
    return result


def envelopes(binding: Any) -> dict[str, dict[str, Any]]:
    data = read(binding, "devices")
    records = (
        _reference_records(data)
        if data.get("schema") == "wu15_device_envelope_v02_evidence_assessment"
        else data.get("records")
    )
    require(isinstance(records, list) and bool(records), "HOLD_MISSING_CLASS_EVIDENCE")
    assert isinstance(records, list)
    grouped: dict[str, list[dict[str, Any]]] = {}
    fields = {
        "record_id",
        "class_id",
        "mounting",
        "form_factor",
        "dimensions_mm",
        "clearance_mm",
        "pair_gap_mm",
        "extra_gap_mm",
        "rail_offset_mm",
        "rail_back_mm",
        "requirements",
        "body_reference",
        "sources",
    }
    for record in records:
        require(
            isinstance(record, dict) and set(record) == fields,
            "HOLD_DEVICE_RECORD_SCHEMA",
        )
        require(record["mounting"] in {"DIN", "PANEL"}, "HOLD_MOUNTING_CLASS")
        dimensions(record["dimensions_mm"])
        require(
            len(record["clearance_mm"]) == 4 and len(record["pair_gap_mm"]) == 2,
            "HOLD_CLEARANCE_SCHEMA",
        )
        for n in (
            record["clearance_mm"] + record["pair_gap_mm"] + [record["extra_gap_mm"]]
        ):
            number(n, zero=True)
        if record["rail_offset_mm"] is not None:
            number(record["rail_offset_mm"], zero=True)
        if record["rail_back_mm"] is not None:
            number(record["rail_back_mm"], zero=True)
        req = record["requirements"]
        require(
            isinstance(req, dict) and set(req) == {"min_ip", "shock_class"},
            "HOLD_UNSUPPORTED_MANUFACTURER_REQUIREMENT",
        )
        require(
            isinstance(req["min_ip"], list)
            and len(req["min_ip"]) == 2
            and all(type(v) is int and 0 <= v <= 9 for v in req["min_ip"]),
            "HOLD_IP_REQUIREMENT",
        )
        require(req["shock_class"] in {None, "I"}, "HOLD_SHOCK_REQUIREMENT")
        grouped.setdefault(record["class_id"], []).append(record)
    result = {}
    for cid, group in sorted(grouped.items()):
        require(
            len({(r["mounting"], r["form_factor"]) for r in group}) == 1,
            "HOLD_CROSS_FORM_FACTOR_MERGE",
        )
        # A different rail anchor/body geometry is not safely mergeable by MAX.
        anchors = {
            json.dumps(
                [r["rail_offset_mm"], r["rail_back_mm"], r["body_reference"]],
                sort_keys=True,
            )
            for r in group
        }
        require(len(anchors) == 1, "HOLD_AMBIGUOUS_MOUNTING_REFERENCE")
        default_edge = (
            [50, 50, 20, 20] if group[0]["mounting"] == "PANEL" else [0, 0, 0, 0]
        )
        result[cid] = {
            "class_id": cid,
            "mounting": group[0]["mounting"],
            "form_factor": group[0]["form_factor"],
            "dimensions_mm": [
                max(dimensions(r["dimensions_mm"])[i] for r in group) for i in range(3)
            ],
            "clearance_mm": [
                max(
                    Decimal(default_edge[i]),
                    *(number(r["clearance_mm"][i], zero=True) for r in group),
                )
                for i in range(4)
            ],
            "pair_gap_mm": [
                max(number(r["pair_gap_mm"][i], zero=True) for r in group)
                for i in range(2)
            ],
            "extra_gap_mm": max(number(r["extra_gap_mm"], zero=True) for r in group),
            "rail_offset_mm": group[0]["rail_offset_mm"],
            "rail_back_mm": group[0]["rail_back_mm"],
            "body_reference": group[0]["body_reference"],
            "min_ip": [
                max(r["requirements"]["min_ip"][i] for r in group) for i in range(2)
            ],
            "shock_class": (
                "I"
                if any(r["requirements"]["shock_class"] == "I" for r in group)
                else None
            ),
            "record_ids": sorted(r["record_id"] for r in group),
            "sources": [s for r in group for s in r["sources"]],
        }
    return result


def class_for(component: dict[str, Any], binding: Any) -> str:
    data = read(binding, "devices")
    if data.get("schema") != "wu15_device_envelope_v02_evidence_assessment":
        matches = [
            entry["class_id"]
            for entry in data.get("mappings", [])
            if all(
                component.get(k, component.get(k + "_guess")) == v
                for k, v in entry["signature"].items()
            )
        ]
        require(len(matches) == 1, "HOLD_UNMAPPED_OR_AMBIGUOUS_APPARATUS")
        return str(matches[0])
    code = component.get("component_code", component.get("component_code_guess"))
    label = component.get("component_label", component.get("component_label_guess", ""))
    require(
        isinstance(code, str) and isinstance(label, str),
        "HOLD_UNMAPPED_OR_AMBIGUOUS_APPARATUS",
    )
    text = re.sub(
        r"\s+",
        " ",
        label.upper().translate(str.maketrans({"А": "A", "С": "C", "Р": "P"})),
    )
    if code == "ВА88-32" and re.search(
        r"ВА88-32\s+3P\s+63A(?:\b|$)".replace("А", "A"), text
    ):
        return "MCCB_3P_STATIONARY_PANEL"
    if code == "АВДТ32" and re.search(
        r"AВДТ32\s+2P\s+C(?:16|20)\s*/\s*30МA(?:\b|$)", text
    ):
        return "RCBO_2_TOTAL_POLES_1P_N_TH35"
    if code == "ВН-32" and re.search(r"ВН-32\s+3P\s+25A(?:\b|$)", text):
        return "SWITCH_DISCONNECTOR_3P_TH35"
    raise SizingHold("HOLD_UNMAPPED_OR_AMBIGUOUS_APPARATUS")
