"""Cabinet-sizing catalogue identities reach exact enclosure cost sources."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import future_case_hardening as f  # type: ignore[import-not-found]
import governed_metal_cost as metal  # type: ignore[import-not-found]
import pytest
from openpyxl import load_workbook  # type: ignore[import-untyped]
from test_versioned_metal_source import synthetic_sources as synthetic_sources


def add_row(source: Any, row: int, label: Any, size: Any, work: Any) -> None:
    from wu8_governed_sources import metal_identity  # type: ignore[import-not-found]

    path = Path(source["path"])
    book = load_workbook(path)
    sheet = book["Лист1"]
    identity = metal_identity(row, "x", tuple(size), *work)
    for cell, value in {**identity["formulas"], **identity["identity_values"]}.items():
        sheet[cell] = value
    sheet[f"A{row}"] = label
    book.save(path)
    book.close()
    source["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()


def test_catalogue_metal_row_prices_like_the_approved_ten(
    synthetic_sources: Any,
) -> None:
    genesis = synthetic_sources["2026.06.18"]
    add_row(genesis, 37, "800х600х250 ", [800, 600, 250], [3375, 700, 1500])
    add_row(genesis, 48, "1300х800х350 спец.", [1300, 800, 350], [1, 1, 1])
    add_row(genesis, 30, "600х500х250 ", [600, 500, 250], [1, 1, 1.5])
    add_row(genesis, 31, "600х600х200 ", [600, 600, 200], [1, 1, 1])
    approved = metal.resolve_versioned_metal_cost(
        (500, 400, 250), source_version="2026.06.18"
    )
    bridged = metal.resolve_catalogue_metal_cost(22)
    assert bridged["cost_kzt"] == approved["cost_kzt"]
    assert bridged["identity"] == approved["identity"]
    assert bridged["cabinet_code"] == "CATALOGUE-METAL-ROW-22"
    assert bridged["metal_source"] == genesis
    new = metal.resolve_catalogue_metal_cost(37)
    assert new["dimensions_mm"] == [800, 600, 250]
    assert new["source_locator"] == "Лист1!D37"
    assert new["cost_kzt"] > bridged["cost_kzt"]
    current = metal.resolve_catalogue_metal_cost(22, source_version="2026.10.21")
    assert current["cost_kzt"] > bridged["cost_kzt"]
    with pytest.raises(ValueError, match="special form factor"):
        metal.resolve_catalogue_metal_cost(48)
    with pytest.raises(ValueError, match="literal integers"):
        metal.resolve_catalogue_metal_cost(30)
    for row in (7, 57, "22"):
        with pytest.raises(ValueError, match="outside scope"):
            metal.resolve_catalogue_metal_cost(row)


def test_catalogue_metal_row_cannot_contradict_approved_size(
    synthetic_sources: Any,
) -> None:
    genesis = synthetic_sources["2026.06.18"]
    add_row(genesis, 22, "500х400х250 ", [500, 400, 250], [9999, 400, 1500])
    with pytest.raises(ValueError, match="conflicts with approved size"):
        metal.resolve_catalogue_metal_cost(22)


def test_catalogue_metal_row_formula_drift_holds(synthetic_sources: Any) -> None:
    genesis = synthetic_sources["2026.06.18"]
    path = Path(genesis["path"])
    book = load_workbook(path)
    book["Лист1"]["D22"] = "=1"
    book.save(path)
    book.close()
    genesis["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="formula drift: D22"):
        metal.resolve_catalogue_metal_cost(22)


def test_catalogue_metal_row_sheet_identity(synthetic_sources: Any) -> None:
    genesis = synthetic_sources["2026.06.18"]
    path = Path(genesis["path"])
    book = load_workbook(path)
    book.create_sheet("Extra")
    book.save(path)
    book.close()
    genesis["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="sheet identity"):
        metal.resolve_catalogue_metal_cost(22)


def item(code: str, label: str) -> dict[str, Any]:
    return {"cabinet": {"cabinet_code": code, "cabinet_label": label}}


RULES: dict[str, Any] = {"enclosure_mm": None}


def test_metal_catalogue_bridge_binds_label_and_technical_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def resolved(row: int) -> dict[str, Any]:
        calls.append(row)
        return {"cost_kzt": 21336, "dimensions_mm": [800, 600, 250]}

    monkeypatch.setattr(metal, "resolve_catalogue_metal_cost", resolved)
    result = f.catalogue_enclosure_cost(
        None, None, RULES, item("CATALOGUE-METAL-ROW-37", "800х600х250 "), "METAL", 37
    )
    assert calls == [37]
    assert result["cost_kzt"] == 21336
    assert result["technical_cabinet_code"] == "CATALOGUE-METAL-ROW-37"
    assert result["source_designation"] == "800х600х250 "
    with pytest.raises(f.RuleError, match="label/source dimension conflict"):
        f.catalogue_enclosure_cost(
            None,
            None,
            RULES,
            item("CATALOGUE-METAL-ROW-37", "800х600х300"),
            "METAL",
            37,
        )
    with pytest.raises(f.RuleError, match="size rule conflict"):
        f.catalogue_enclosure_cost(
            None,
            None,
            {"enclosure_mm": [600, 400, 250]},
            item("CATALOGUE-METAL-ROW-37", "800х600х250 "),
            "METAL",
            37,
        )


def test_modular_catalogue_bridge_uses_unique_cab_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = []

    def cost(ws: Any, baseline: Any, code: str) -> dict[str, Any]:
        seen.append((ws, code))
        size = f.governed_sources.CABINETS[code][2]
        return {"cabinet_code": code, "cost_kzt": 5000, "dimensions_mm": list(size)}

    monkeypatch.setattr(f.governed_sources, "cabinet_cost", cost)
    book = {"КРН": "krn-sheet"}
    label = "Корпус КРН-36 540х330х100 "
    result = f.catalogue_enclosure_cost(
        book, "baseline", RULES, item("CATALOGUE-KRN-ROW-64", label), "KRN", 64
    )
    assert seen == [("krn-sheet", "CAB-KRN-36")]
    assert result["cabinet_code"] == "CAB-KRN-36"
    assert result["technical_cabinet_code"] == "CATALOGUE-KRN-ROW-64"
    krv = f.catalogue_enclosure_cost(
        book,
        "baseline",
        RULES,
        item("CATALOGUE-KRV-ROW-77", "Корпус КРВ-36 550х320х125"),
        "KRV",
        77,
    )
    assert krv["cabinet_code"] == "CAB-KRV-36"
    for family, row in (("KRN", 60), ("KRV", 64)):
        with pytest.raises(f.RuleError, match="no exact cost identity"):
            f.catalogue_enclosure_cost(
                book, "baseline", RULES, item("X", "Корпус 265х330х100"), family, row
            )


def test_ordinary_enclosure_dispatches_catalogue_codes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []
    monkeypatch.setattr(
        f,
        "load_technical_binding",
        lambda *args: (None, item("CATALOGUE-METAL-ROW-37", "800х600х250 ")),
    )

    def fake(*args: Any) -> dict[str, Any]:
        calls.append(args[3:])
        return {"cost_kzt": 1}

    monkeypatch.setattr(f, "catalogue_enclosure_cost", fake)
    rules = {"context": None, "technical_binding": None, "enclosure_mm": None}
    assert f.ordinary_enclosure_cost("book", "baseline", rules) == {"cost_kzt": 1}
    assert calls[0][1:] == ("METAL", 37)
    for code in ("CATALOGUE-METAL-ROW-037", "CATALOGUE-KURN-ROW-57"):
        monkeypatch.setattr(
            f, "load_technical_binding", lambda *args, c=code: (None, item(c, "x"))
        )
        with pytest.raises(f.RuleError, match="exact cost mapping required"):
            f.ordinary_enclosure_cost("book", "baseline", rules)
