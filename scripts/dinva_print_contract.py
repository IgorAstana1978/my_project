"""Canonical print policy and nominal capacity; never computes Excel page breaks."""

from collections.abc import Mapping
from math import isfinite
from typing import Any


def nominal_page_capacity(print_contract: Mapping[str, Any]) -> float:
    """Unscaled row points at stored scale, not native fit-to-width capacity.

    A4 paperSize=9 maps to ISO 216 210 x 297 mm; 72 pt/in and 25.4 mm/in
    are unit definitions. Excel's active fit-to-width may override stored scale.
    """
    if (
        print_contract["paper_size"] != "9"
        or print_contract["orientation"] != "portrait"
    ):
        raise ValueError("canonical print paper/orientation mismatch")
    margins = print_contract["margins"]
    top, bottom, scale = (
        float(margins["top"]),
        float(margins["bottom"]),
        float(print_contract["scale"]),
    )
    if (
        not all(isfinite(v) for v in (top, bottom, scale))
        or min(top, bottom) < 0
        or not 10 <= scale <= 400
    ):
        raise ValueError("invalid print margins/scale")
    result = (297 / 25.4 - top - bottom) * 72 / (scale / 100)
    if result <= 0:
        raise ValueError("print margins exhaust page height")
    return result
