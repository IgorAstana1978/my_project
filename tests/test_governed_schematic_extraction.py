"""Governed CAD schematics must retain source QFs, including power boards."""

# ruff: noqa: E402

import hashlib
import json
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import governed_rotated_extraction as governed  # type: ignore[import-not-found]
import project_spec_extraction as core  # type: ignore[import-not-found]
from governed_case_intake import GovernedIntake  # type: ignore[import-not-found]


class CadPage:
    rotation = 270
    mediabox = type("Box", (), {"width": 842, "height": 1191})()

    def __init__(self, blocks: list[tuple[str, float, float]]) -> None:
        self.blocks = blocks

    def extract_text(self, *, visitor_text: Any) -> str:
        for text, x, y in self.blocks:
            visitor_text(
                text,
                [1, 0, 0, 1, 0, 0],
                [0, -1, 1, 0, y, 1191 - x],
                None,
                12,
            )
        return "\n".join(text for text, _, _ in self.blocks)


def schematic(name: str, ratings: list[str], shift: float) -> CadPage:
    blocks: list[tuple[str, float, float]] = [
        ("Принципиальная схема силового щита", 40 + shift, 60),
        (name, 40 + shift, 45),
        (f"{name} (ЩРн 24з-1 36 УХЛ3 IP31)", 250 + shift, 730),
    ]
    for index, rating in enumerate(ratings):
        model = "ВА88-32" if rating == "100А" else "ВА47-29"
        blocks.extend(
            [
                (f"QF{index}", 100 + index * 80 + shift, 650),
                (model, 100 + index * 80 + shift, 635),
                (f"3P {rating}", 100 + index * 80 + shift, 620),
            ]
        )
    return CadPage(blocks)


def intake_for(pdf: Path) -> GovernedIntake:
    raw = json.dumps({"human_decisions": []}).encode()
    return GovernedIntake(
        path=pdf.parent / "intake.json",
        raw=raw,
        sha256=hashlib.sha256(raw).hexdigest(),
        case_id="CASE-SYNTHETIC-CAD",
        version="V001",
        project_pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
        project_pdf_path=pdf,
        base_manifest_sha256="0" * 64,
        requested_supply=(("ЩС-85", 1), ("ЩС-86", 1)),
        excluded_components=(("METER-X", 1),),
    )


@pytest.mark.parametrize("shift", [0.0, 125.0])
def test_governed_retains_thirteen_qfs_and_source_enclosures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, shift: float
) -> None:
    pdf = tmp_path / "synthetic.pdf"
    pdf.write_bytes(b"synthetic reader fixture, not client data")
    pages = [
        schematic("ЩС-85", ["D32А", "D25А", "D25А", "D16А", "D25А", "D25А"], shift),
        schematic(
            "ЩС-86", ["100А", "D25А", "D25А", "D16А", "D40А", "D40А", "D16А"], shift
        ),
        CadPage(
            [
                ("Позиция", 50 + shift, 740),
                ("Наименование и техническая характеристика", 150 + shift, 740),
                ("Тип, марка, обозначение", 350 + shift, 740),
                ("Ед. измерения", 450 + shift, 740),
                ("Кол.", 550 + shift, 740),
                ("ЩС-85", 50 + shift, 700),
                ("шт", 450 + shift, 700),
                ("1", 550 + shift, 700),
                ("ЩС-86", 50 + shift, 650),
                ("шт", 450 + shift, 650),
                ("1", 550 + shift, 650),
                ("METER-X", 150 + shift, 600),
                ("шт", 450 + shift, 600),
                ("1", 550 + shift, 600),
            ]
        ),
    ]
    reader = type("Reader", (), {"is_encrypted": False, "pages": pages})()
    monkeypatch.setattr(core, "PdfReader", lambda *_a, **_k: reader)
    monkeypatch.setattr(governed, "PdfReader", lambda *_a, **_k: reader)

    result = governed.build_governed_rotated_artifacts(pdf, intake_for(pdf))

    assert [len(item["components"]) for item in result.draft["items"]] == [6, 7]
    assert result.summary["composition_rows_extracted"] == 13
    assert result.summary["qf_components_extracted"] == 13
    assert result.summary["qf_unresolved_count"] == 0
    for item in result.draft["items"]:
        assert item["cabinet_guess"]["label_guess"] == "ЩРн 24з-1 36 УХЛ3 IP31"
        for component in item["components"]:
            assert component["model_guess"] in {"ВА47-29", "ВА88-32"}
            assert component["quantity_guess"] == 1
            assert component["rating_guess"]
            assert component["requires_igor_confirmation"] is True
            assert "qf=" in component["provenance"][0]["locator"]
            assert component["provenance"][0]["page"] in (1, 2)
    assert result.draft["safety"]["confirmed_by_igor"] is False


def test_power_board_tokens_and_apparatus_are_controlled() -> None:
    assert governed.POWER_TITLE_RE.search("Принципиальная схема силового щитаЩС-85")
    assert governed.POWER_TITLE_RE.search("План сетей ЩС-85") is None
    assert governed.parse_qf_apparatus("QF4ВА47-293P D 25А")["model"] == "ВА47-29"
    assert governed.parse_qf_apparatus("QF4UNKNOWN 3P D25А")["model"] is None


def test_decision_conflict_resolution_is_exact_and_count_bound(tmp_path: Path) -> None:
    pdf = tmp_path / "synthetic.pdf"
    pdf.write_bytes(b"synthetic")
    intake = intake_for(pdf)
    texts = [
        "второй щит: ЩС-86; ЩС-8 в спецификации — ошибка;",
        "D16 = 3P;",
        "ЩС-85: D16 ×1;",
        "ЩС-86: D16 ×2;",
    ]
    raw = json.dumps({"human_decisions": [{"text": body} for body in texts]}).encode()
    intake = replace(intake, raw=raw)
    assert governed.decision_aliases(intake) == {"ЩС-8": "ЩС-86"}
    corrections = governed.rating_corrections(intake)
    assert corrections == {("ЩС-85", "D16"): ("3P", 1), ("ЩС-86", "D16"): ("3P", 2)}
    components = [
        core.qf_component_from_segment(
            core.QfSegment(
                f"QF{i}",
                f"QF{i} ВА47-29 3P {rating}А",
                core.PdfBlock("", 20, 30, i + 1),
            ),
            pdf.name,
            1,
            0.82,
        )
        for i, rating in enumerate(["D32", "D25", "D25", "D16", "D25", "D25"])
    ]
    for component in components:
        parsed = governed.parse_qf_apparatus(component.provenance[0].raw_text)
        component.model = parsed["model"]
        component.rating = parsed["rating"]
    board = core.BoardCandidate("ЩС-85", "ЩС-85", "ЩС-85", 1, [], 0.82, components)
    rows = Counter(
        {
            ("ВА47-29", "3P", "D32"): 1,
            ("ВА47-29", "3P", "D25"): 4,
            ("ВА47-29", "1P", "D16"): 1,
        }
    )
    with pytest.raises(core.ExtractionError, match="unresolved"):
        governed.reconcile_schematic(board, rows, {})
    governed.reconcile_schematic(board, rows, corrections)
    already_three_poles = rows.copy()
    del already_three_poles[("ВА47-29", "1P", "D16")]
    already_three_poles[("ВА47-29", "3P", "D16")] = 1
    with pytest.raises(core.ExtractionError, match="count does not match"):
        governed.reconcile_schematic(
            board, already_three_poles, {("ЩС-85", "D16"): ("3P", 2)}
        )
    wrong_count = rows.copy()
    wrong_count[("ВА47-29", "1P", "D16")] = 2
    with pytest.raises(core.ExtractionError, match="count does not match"):
        governed.reconcile_schematic(board, wrong_count, corrections)
    unknown = rows.copy()
    unknown[("ВА47-29", "3P", "D20")] = 1
    with pytest.raises(core.ExtractionError, match="unresolved"):
        governed.reconcile_schematic(board, unknown, corrections)


def test_specification_quantities_require_matching_row_geometry() -> None:
    block = core.PdfBlock
    blocks = [
        block("Позиция", 20, 700, 1),
        block("Наименование и техническая характеристика", 100, 700, 2),
        block("Тип, марка, обозначение", 300, 700, 3),
        block("Ед. измерения", 400, 700, 4),
        block("Кол.", 500, 700, 5),
        block("ЩС-85", 20, 650, 6),
        block(
            'Выключатель автоматический типа ВА47-29 характеристика "D" 1Р 16А',
            -1,
            650,
            7,
        ),
        block("catalog-code", 310, 600, 8),
        block("2", 500, 600, 9),
        block("шт", 400, 600, 10),
    ]
    result = governed.specification_breakers(blocks, {"ЩС-85"}, {})
    assert result["ЩС-85"] == Counter({("ВА47-29", "1P", "D16"): 2})
    blocks.append(block("9", 500, 650, 11))
    with pytest.raises(core.ExtractionError, match="quantity is ambiguous"):
        governed.specification_breakers(blocks, {"ЩС-85"}, {})
