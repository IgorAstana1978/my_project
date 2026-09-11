"""Deterministic native-width helpers for governed DINVA text contracts."""

from __future__ import annotations

from collections.abc import Mapping
from math import floor, isfinite
from typing import Any


def column_width_points(width: float, maximum_digit_width_px: int) -> float:
    """Apply the ECMA-376 / Excel column-width pixel quantization."""

    if not isfinite(width) or width <= 0 or maximum_digit_width_px <= 0:
        raise ValueError("canonical spill column width invalid")
    pixels = floor(
        (256 * width + floor(128 / maximum_digit_width_px))
        / 256
        * maximum_digit_width_px
    )
    return pixels * 0.75


def canonical_spill_fit(
    rule: Mapping[str, Any], text: str, widths: Mapping[str, float]
) -> dict[str, float]:
    """Prove a no-wrap object fits the governed C:H native spill corridor.

    Embedded CR/LF characters have zero visible advance in the canonical
    no-wrap Excel presentation. The frozen per-glyph values are conservative
    native upper bounds, so an unknown glyph or any overflow fails closed.
    """

    if (
        rule.get("model") != "NATIVE_EXCEL_SINGLE_LINE_SPILL_V1"
        or rule.get("cell") != "C13"
        or rule.get("row_height_pt") != 26.1
        or rule.get("line_break_display") != "ZERO_ADVANCE_SINGLE_LINE"
        or rule.get("spill_columns") != list("CDEFGH")
        or rule.get("required_empty_cells") != ["D13", "E13", "F13", "G13", "H13"]
        or rule.get("maximum_digit_width_px") != 7
        or rule.get("horizontal_padding_px") != 5
    ):
        raise ValueError("canonical object spill contract mismatch")
    advances = rule.get("glyph_upper_advances_pt")
    if not isinstance(advances, Mapping) or not advances:
        raise ValueError("canonical object glyph advances missing")
    visible = text.replace("\r", "").replace("\n", "")
    required = 0.0
    for character in visible:
        raw = advances.get(str(ord(character)))
        if (
            not isinstance(raw, (int, float))
            or isinstance(raw, bool)
            or not isfinite(float(raw))
            or raw <= 0
        ):
            raise ValueError("unmeasured object glyph")
        required += float(raw)
    available = (
        sum(column_width_points(float(widths[column]), 7) for column in list("CDEFGH"))
        - 5 * 0.75
    )
    if available <= 0:
        raise ValueError("canonical object spill corridor invalid")
    if required > available:
        raise ValueError("object content exceeds canonical C13:H13 spill corridor")
    return {
        "required_upper_bound_pt": required,
        "available_pt": available,
        "minimum_margin_pt": available - required,
    }
