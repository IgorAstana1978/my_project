"""Source-bound print-only v0.5 DRAFT successor. No approval/render capability."""

from __future__ import annotations

import argparse
import copy
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from dinva_print_contract import nominal_page_capacity
from extract_dinva_classic_presentation_profile_v0_2 import (
    REQUIRED_FAMILY_SHA256S,
    BoundInput,
    canonical_json,
    load_bound,
    load_strict_json,
    publish_draft_profile,
    require,
    sha256_bytes,
)

APPROVED_V04_SHA256 = "dd2b7f01af54529f8d5f62ebeab168cb95b800af7fc55108822cafb306b5e4a6"
S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
PRINT_LOCATOR = (
    "xl/worksheets/sheet1.xml:pageSetUpPr,pageSetup,pageMargins,rowBreaks,colBreaks;"
    "xl/workbook.xml:definedNames"
)


def family_print(source: BoundInput) -> dict[str, Any]:
    loaded = load_bound(source, "print family")
    with ZipFile(loaded.path) as archive:
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        book = ET.fromstring(archive.read("xl/workbook.xml"))
    setup = sheet.find(f"{{{S}}}pageSetup")
    props = sheet.find(f"{{{S}}}sheetPr/{{{S}}}pageSetUpPr")
    margins = sheet.find(f"{{{S}}}pageMargins")
    require(
        setup is not None and props is not None and margins is not None,
        "family print settings missing",
    )
    assert setup is not None and props is not None and margins is not None
    require(
        setup.get("paperSize") == "9"
        and setup.get("orientation") == "portrait"
        and setup.get("scale") == "54"
        and setup.get("fitToHeight") == "0"
        and setup.get("fitToWidth") is None
        and props.get("fitToPage") in {"1", "true"},
        "family print semantics differ",
    )
    require(
        all(sheet.find(f"{{{S}}}{tag}") is None for tag in ("rowBreaks", "colBreaks")),
        "family manual breaks differ",
    )
    require(
        not any(
            n.get("name") in {"_xlnm.Print_Area", "_xlnm.Print_Titles"}
            for n in book.findall(f"{{{S}}}definedNames/{{{S}}}definedName")
        ),
        "family print names differ",
    )
    require(
        set(margins.attrib) == {"left", "right", "top", "bottom", "header", "footer"},
        "family margins incomplete",
    )
    result = {
        "paper_size": setup.get("paperSize"),
        "orientation": setup.get("orientation"),
        "scale": int(setup.get("scale", "0")),
        "fit_to_height": 0,
        "fit_to_width": None,
        "fit_to_page": True,
        "margins": {key: float(value) for key, value in margins.attrib.items()},
    }
    load_bound(source, "print family TOCTOU")
    return result


def extract_profile_v0_5(predecessor: BoundInput) -> dict[str, Any]:
    require(
        predecessor.expected_sha256 == APPROVED_V04_SHA256,
        "v0.4 predecessor SHA mismatch",
    )
    parent = load_bound(predecessor, "approved v0.4 predecessor")
    profile = load_strict_json(parent.raw, "v0.4 profile")
    old = profile["presentation_contract"]
    fingerprint = sha256_bytes(canonical_json(old))
    approval = profile["approval_provenance"]
    require(
        profile["schema_version"] == "dinva_classic_presentation_profile.v0.4"
        and profile["profile_id"] == "DINVA_CLASSIC_QUOTE_INVOICE_V0_1_DYNAMIC_V0_4"
        and profile["artifact_status"] == "IMMUTABLE_APPROVED_PROFILE"
        and approval["status"] == "APPROVED"
        and approval["authority"] == "IGOR_DIRECT_HUMAN_APPROVAL"
        and approval["approved_contract_fingerprint"] == fingerprint
        and profile["presentation_contract_fingerprint"] == fingerprint,
        "v0.4 predecessor approval mismatch",
    )
    bindings = profile["reference_provenance"]
    require(len(bindings) == 10, "v0.4 binding count mismatch")
    sources = []
    family = []
    for binding in bindings:
        require(
            binding["actual_sha256"] == binding["expected_sha256"],
            "source binding mismatch",
        )
        source = BoundInput(Path(binding["path"]), binding["actual_sha256"])
        load_bound(source, "v0.4 provenance")
        sources.append(source)
        if binding["role"] == "CLASSIC_FAMILY_EVIDENCE":
            family.append(source)
    require(
        len(family) == 3
        and {s.expected_sha256 for s in family} == set(REQUIRED_FAMILY_SHA256S),
        "v0.5 family binding mismatch",
    )
    evidence = [family_print(source) for source in family]
    require(
        all(value == evidence[0] for value in evidence),
        "family print evidence disagrees",
    )
    successor = copy.deepcopy(profile)
    successor.update(
        schema_version="dinva_classic_presentation_profile.v0.5",
        profile_id="DINVA_CLASSIC_QUOTE_INVOICE_V0_1_DYNAMIC_V0_5",
        artifact_status="DRAFT_PROFILE_CANDIDATE",
    )
    contract = successor["presentation_contract"]
    contract["contract_version"] = "dinva_classic_presentation_contract.v0.5"
    contract["print"] = evidence[0]
    contract["layout"]["pagination"] = {
        "mode": "NATIVE_EXCEL_AUTO",
        "print_area": None,
        "repeat_rows": None,
        "manual_breaks": [],
        "source_sha256s": sorted(s.expected_sha256 for s in family),
        "source_locator": PRINT_LOCATOR,
        "capacity": {
            "method": "A4_PORTRAIT_MINUS_MARGINS_AT_STORED_SCALE",
            "paper_height_mm": 297,
            "paper_geometry_source": "OOXML paperSize=9;ISO216:A4=210x297mm",
            "nominal_unscaled_height_pt": nominal_page_capacity(evidence[0]),
            "usage": "REFERENCE_ONLY_NATIVE_FIT_TO_WIDTH_CONTROLS_PAGINATION",
        },
    }
    restored = copy.deepcopy(contract)
    restored["contract_version"] = old["contract_version"]
    restored["print"] = old["print"]
    restored["layout"]["pagination"] = old["layout"]["pagination"]
    require(
        canonical_json(restored) == canonical_json(old), "non-print contract mutation"
    )
    successor["presentation_contract_fingerprint"] = sha256_bytes(
        canonical_json(contract)
    )
    successor["approval_provenance"] = {
        "status": "DRAFT_UNAPPROVED",
        "authority": None,
        "approval_id": None,
        "approved_at": None,
        "approved_contract_fingerprint": None,
    }
    successor["reference_provenance"].append(
        {
            "path": str(parent.path),
            "expected_sha256": parent.sha256,
            "actual_sha256": parent.sha256,
            "role": "IMMUTABLE_APPROVED_V0_4_PREDECESSOR_PROFILE",
        }
    )
    for source in [predecessor, *sources]:
        load_bound(source, "v0.5 final TOCTOU")
    return successor


def publish_v0_5_draft(
    profile: dict[str, Any], predecessor: BoundInput, output: Path
) -> Path:
    def reread() -> None:
        require(
            canonical_json(extract_profile_v0_5(predecessor))
            == canonical_json(profile),
            "v0.5 DRAFT/source TOCTOU mismatch",
        )

    return publish_draft_profile(profile, output, verify_sources=reread)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approved-v0-4-profile", required=True, type=Path)
    parser.add_argument("--approved-v0-4-profile-sha256", required=True)
    parser.add_argument("--output-profile", required=True, type=Path)
    args = parser.parse_args()
    try:
        predecessor = BoundInput(
            args.approved_v0_4_profile, args.approved_v0_4_profile_sha256
        )
        result = extract_profile_v0_5(predecessor)
        output = publish_v0_5_draft(result, predecessor, args.output_profile)
    except (OSError, ValueError, KeyError) as exc:
        print(f"HOLD: {exc}")
        return 1
    print("DINVA_CLASSIC_PROFILE_V0_5=DRAFT_UNAPPROVED")
    print(f"FINGERPRINT={result['presentation_contract_fingerprint']}")
    print(f"SHA256={sha256_bytes(output.read_bytes())}")
    print(f"OUTPUT={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
