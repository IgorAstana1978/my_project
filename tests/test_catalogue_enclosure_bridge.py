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
    bridged = metal.resolve_catalogue_metal_cost(22, source_version="2026.06.18")
    assert bridged["cost_kzt"] == approved["cost_kzt"]
    assert bridged["identity"] == approved["identity"]
    assert bridged["cabinet_code"] == "CATALOGUE-METAL-ROW-22"
    assert bridged["metal_source"] == genesis
    new = metal.resolve_catalogue_metal_cost(37, source_version="2026.06.18")
    assert new["dimensions_mm"] == [800, 600, 250]
    assert new["source_locator"] == "Лист1!D37"
    assert new["cost_kzt"] > bridged["cost_kzt"]
    current = metal.resolve_catalogue_metal_cost(22, source_version="2026.10.21")
    assert current["cost_kzt"] > bridged["cost_kzt"]
    # Igor 2026-11-06: the catalogue prices from the latest metal list by default.
    assert metal.resolve_catalogue_metal_cost(22) == current
    with pytest.raises(ValueError, match="special form factor"):
        metal.resolve_catalogue_metal_cost(48, source_version="2026.06.18")
    with pytest.raises(ValueError, match="literal integers"):
        metal.resolve_catalogue_metal_cost(30, source_version="2026.06.18")
    for row in (7, 57, 81, "22"):
        with pytest.raises(ValueError, match="outside scope"):
            metal.resolve_catalogue_metal_cost(row)


def test_catalogue_metal_row_cannot_contradict_approved_size(
    synthetic_sources: Any,
) -> None:
    genesis = synthetic_sources["2026.06.18"]
    add_row(genesis, 22, "500х400х250 ", [500, 400, 250], [9999, 400, 1500])
    with pytest.raises(ValueError, match="conflicts with approved size"):
        metal.resolve_catalogue_metal_cost(22, source_version="2026.06.18")


def test_catalogue_modular_rows_price_from_metal_list(synthetic_sources: Any) -> None:
    genesis = synthetic_sources["2026.06.18"]
    add_row(genesis, 62, "Корпус КРН-18 265х440х100 ", [265, 440, 100], [1250, 350, 1])
    add_row(genesis, 77, "Корпус КРВ-36 550х320х125 ", [550, 320, 125], [1, 1, 1])
    add_row(genesis, 64, "Корпус КРН-36 999х330х100 ", [540, 330, 100], [1, 1, 1])
    add_row(genesis, 65, "540х440х100 ", [540, 440, 100], [1, 1, 1])
    krn = metal.resolve_catalogue_metal_cost(62, source_version="2026.06.18")
    assert krn["cabinet_code"] == "CATALOGUE-KRN-ROW-62"
    assert krn["source_locator"] == "Лист1!D62" and krn["cost_kzt"] > 0
    krv = metal.resolve_catalogue_metal_cost(77, source_version="2026.06.18")
    assert krv["cabinet_code"] == "CATALOGUE-KRV-ROW-77"
    for row in (64, 65):
        with pytest.raises(ValueError, match="modular enclosure label/size"):
            metal.resolve_catalogue_metal_cost(row, source_version="2026.06.18")


def test_catalogue_metal_row_formula_drift_holds(synthetic_sources: Any) -> None:
    genesis = synthetic_sources["2026.06.18"]
    path = Path(genesis["path"])
    book = load_workbook(path)
    book["Лист1"]["D22"] = "=1"
    book.save(path)
    book.close()
    genesis["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="formula drift: D22"):
        metal.resolve_catalogue_metal_cost(22, source_version="2026.06.18")


def test_catalogue_metal_row_sheet_identity(synthetic_sources: Any) -> None:
    genesis = synthetic_sources["2026.06.18"]
    path = Path(genesis["path"])
    book = load_workbook(path)
    book.create_sheet("Extra")
    book.save(path)
    book.close()
    genesis["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="sheet identity"):
        metal.resolve_catalogue_metal_cost(22, source_version="2026.06.18")


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
    labels = {64: "Корпус КРН-36 540х330х100 ", 77: "Корпус КРВ-36 550х320х125 "}

    def resolved(row: int) -> dict[str, Any]:
        seen.append(row)
        size = f.governed_sources.dimensions(labels.get(row, "Корпус КРН-9 1х1х1"))
        return {
            "cabinet_code": f"CATALOGUE-X-ROW-{row}",
            "cost_kzt": 9405,
            "dimensions_mm": list(size),
            "identity": {"label": labels.get(row, "Корпус КРН-9 1х1х1 ")},
        }

    monkeypatch.setattr(metal, "resolve_catalogue_metal_cost", resolved)
    label = "Корпус КРН-36 540х330х100 "
    result = f.catalogue_enclosure_cost(
        None, None, RULES, item("CATALOGUE-KRN-ROW-64", label), "KRN", 64
    )
    assert seen == [64]
    assert result["cabinet_code"] == "CAB-KRN-36"
    assert result["commercial_identity"] == "КРН-36"
    assert result["cost_kzt"] == 9405
    assert result["technical_cabinet_code"] == "CATALOGUE-KRN-ROW-64"
    krv = f.catalogue_enclosure_cost(
        None,
        None,
        RULES,
        item("CATALOGUE-KRV-ROW-77", "Корпус КРВ-36 550х320х125"),
        "KRV",
        77,
    )
    assert krv["cabinet_code"] == "CAB-KRV-36"
    for family, row in (("KRN", 60), ("KRV", 64)):
        with pytest.raises(f.RuleError, match="no exact cost identity"):
            f.catalogue_enclosure_cost(
                None, None, RULES, item("X", "Корпус 265х330х100"), family, row
            )
    labels[64] = "Корпус КРН-48 540х330х100 "
    with pytest.raises(f.RuleError, match="source name conflict"):
        f.catalogue_enclosure_cost(
            None, None, RULES, item("CATALOGUE-KRN-ROW-64", label), "KRN", 64
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
