"""Pinned non-financial catalogue source boundary and complete inventory."""

from pathlib import Path
from typing import Any

import cabinet_catalogue as catalogue  # type: ignore[import-not-found]
import cabinet_sizing as sizing  # type: ignore[import-not-found]
import cabinet_sizing_evidence as evidence  # type: ignore[import-not-found]
import pytest

pytestmark = pytest.mark.skipif(
    not catalogue.GENESIS_PATH.exists(),
    reason="Pinned local catalogue sources are not distributed with code",
)


@pytest.fixture
def local_inventory() -> Any:
    if not catalogue.GENESIS_PATH.exists():
        pytest.skip("Pinned local workbook not distributed")
    return catalogue.inventory()


def test_full_bounded_inventory_and_record_conflicts(local_inventory: Any) -> None:
    records = local_inventory["records"]
    assert len(records) == 70
    assert [
        sum(r["family"] == f for r in records) for f in ("METAL", "KRN", "KRV")
    ] == [49, 13, 8]
    assert len({r["cabinet_code"] for r in records}) == 70
    by_row = {r["row"]: r for r in records}
    assert by_row[10]["dimensions_mm"] == [300, 400, 150]
    assert by_row[12]["dimensions_mm"] == [400, 300, 150]
    assert by_row[34]["dimensions_mm"] is None
    assert by_row[34]["source"]["raw_dimension_values"] == [700, 500, "=400"]
    assert by_row[34]["label_dimensions_mm"] == [700, 500, 200]
    assert by_row[34]["interpretation_status"] == "UNKNOWN"
    assert by_row[64]["dimensions_mm"] == [540, 330, 100]
    assert by_row[64]["active_mapping"]["dimensions_mm"] == [330, 540, 100]
    assert by_row[64]["source_issues"] == ["HOLD_ACTIVE_MAPPING_AXIS_CONFLICT"]
    assert (
        by_row[48]["qualifier"]
        and "HOLD_SPECIAL_FORM_FACTOR_MOUNTING_EVIDENCE_REQUIRED"
        in by_row[48]["source_issues"]
    )
    assert local_inventory["out_of_scope"] == [
        {"rows": "57:59", "family": "KURN"},
        {"rows": "81+", "family": "OTHER_FAMILIES_AND_ACCESSORIES"},
    ]
    for record in records:
        assert record["source"]["sha256"] == catalogue.GENESIS_SHA
        assert record["source"]["dimension_cells"] == [
            f"{axis}{record['row']}" for axis in "EFG"
        ]
        assert not {"price", "price_kzt", "prices", "cost", "formulas"} & record.keys()


def test_parser_only_accesses_label_and_hwd_cells(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = catalogue.load_workbook
    accessed = []

    class Sheet:
        def __init__(self, inner: Any):
            self.inner = inner

        def __getitem__(self, cell: str) -> Any:
            accessed.append(cell)
            assert cell[0] in "AEFG"
            return self.inner[cell]

    class Book:
        def __init__(self, inner: Any):
            self.inner = inner

        def __getitem__(self, name: str) -> Any:
            assert name == "Лист1"
            return Sheet(self.inner[name])

        def close(self) -> None:
            self.inner.close()

    monkeypatch.setattr(
        catalogue, "load_workbook", lambda *a, **kw: Book(original(*a, **kw))
    )
    catalogue.inventory()
    assert len(accessed) == 284


@pytest.mark.parametrize(
    "pin", ["GENESIS_SHA", "SELECTOR_SHA", "MANIFEST_SHA", "ACTIVE_SHA"]
)
def test_source_and_active_chain_drift_are_closed(
    monkeypatch: pytest.MonkeyPatch, pin: str
) -> None:
    monkeypatch.setattr(catalogue, pin, "0" * 64)
    with pytest.raises(sizing.SizingHold, match="HOLD_.*DRIFT"):
        catalogue.inventory()


def test_reparse_source_is_rejected_before_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "is_symlink", lambda _: True)
    with pytest.raises(sizing.SizingHold, match="HOLD_SOURCE_REPARSE_POINT"):
        evidence.safe_bytes(tmp_path / "catalogue.xlsx", "0" * 64)


def test_header_axis_drift_is_not_reinterpreted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(catalogue, "HEADERS", dict(catalogue.HEADERS, E7="Width"))
    with pytest.raises(sizing.SizingHold, match="HOLD_CATALOGUE_HEADERS"):
        catalogue.inventory()
