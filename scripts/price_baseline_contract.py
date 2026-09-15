"""Exact, versioned price-workbook bindings for read-only future calculations."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PriceBaseline:
    version: str
    path: Path
    sha256: str


HISTORICAL = PriceBaseline(
    "historical_invoice519",
    Path(r"C:\Users\IgorN\Documents\invoice_quote_filler_data\prices\current")
    / "Таблица 05.01.2026 верная.xlsx",
    "79b3ace77e84b87c46eb708f1c3b2ae63b5c6d75c5ebf6889c12b99624112ba1",
)
SUCCESSOR = PriceBaseline(
    "successor_2026_09_09",
    Path(r"C:\Users\IgorN\Documents\invoice_quote_filler_data\prices\current")
    / "Таблица 09.09.2026 верная-2.xlsx",
    "02ca5be9b2eb6775289ee1053c389a659c85e2bd27a2b9867b7d523d6d6e4096",
)
BASELINES = {item.version: item for item in (HISTORICAL, SUCCESSOR)}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_price_baseline(path: Path, version: str) -> PriceBaseline:
    """Reject unknown versions, path aliases and changed workbook bytes."""
    baseline = BASELINES.get(version)
    if baseline is None:
        raise ValueError("unknown price baseline version")
    if Path(os.path.abspath(path)) != Path(os.path.abspath(baseline.path)):
        raise ValueError("price baseline path/version mismatch")
    try:
        actual_sha = sha256_file(path)
    except OSError as exc:
        raise ValueError("price baseline workbook could not be read") from exc
    if actual_sha != baseline.sha256:
        raise ValueError("price baseline SHA-256/version mismatch")
    return baseline
