"""Canonical 744-1 content transforms; engineering facts stay separate."""

from __future__ import annotations

import json
import re
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

from future_case_hardening import number, require, strict_pairs
from price_baseline_contract import sha256_file

DOCUMENT_VERSION = "dinva_quote_invoice_document.v0.3"
POLICY_ID = "DINVA_744_1_CONTENT_V1"
CANONICAL_SHA = "99ae60e322c5d98f767bceca8b4520fc5ec26aa55c166e385a7308faa7658b66"


def technical_display(components: Sequence[Mapping[str, Any]]) -> str:
    require(bool(components), "display components missing")
    sections: OrderedDict[str, OrderedDict[tuple[str, str, str], Decimal | None]] = (
        OrderedDict()
    )
    for c in components:
        require(
            set(c)
            == {
                "section",
                "label",
                "rating",
                "quantity",
                "unit",
                "group_size",
                "source_locator",
            },
            "display component fields mismatch",
        )
        require(
            all(
                isinstance(c[k], str)
                for k in ("section", "label", "rating", "unit", "source_locator")
            ),
            "display component text invalid",
        )
        require(
            bool(c["label"].strip()) and c["source_locator"].startswith("/"),
            "display locator/label missing",
        )
        require(
            c["unit"] in {"шт.", "м", "гр.", "компл.", "note"},
            "display unit unsupported",
        )
        group = c["group_size"]
        require(type(group) is int and group in {1, 3}, "group conversion unsupported")
        if c["unit"] == "note":
            require(
                c["quantity"] is None and group == 1 and c["rating"] == "",
                "engineering note cannot invent a quantity/rating",
            )
            sections.setdefault(c["section"], OrderedDict())[
                (c["label"], "", "note")
            ] = None
            continue
        quantity = number(c["quantity"])
        require(
            group == 1 or c["unit"] == "шт." and quantity % 3 == 0,
            "incomplete three-phase group",
        )
        unit = "гр." if group == 3 else c["unit"]
        key = (c["label"], c["rating"], unit)
        bucket = sections.setdefault(c["section"], OrderedDict())
        previous = bucket.get(key, Decimal(0))
        require(previous is not None, "component/note type mismatch")
        bucket[key] = previous + quantity / group
    lines = []
    for section, bucket in sections.items():
        parts = []
        previous_label = None
        entries = list(bucket.items())
        # 744-1 section groups descend by the approved fuse current, preserving
        # every family/quantity. Other apparatus and unparsed ratings stay put.
        fuse_slots = [
            i
            for i, ((label, rating, unit), _) in enumerate(entries)
            if section
            and unit == "гр."
            and label.startswith(("ППН-", "ПН-2", "PPN-", "PN-2"))
            and re.fullmatch(r"\d+\s*[АA]", rating)
        ]
        ordered = sorted(
            (entries[i] for i in fuse_slots),
            key=lambda entry: int(re.match(r"\d+", entry[0][1]).group()),
            reverse=True,
        )
        for i, entry in zip(fuse_slots, ordered, strict=True):
            entries[i] = entry
        for (label, rating, unit), quantity in entries:
            if unit == "note":
                parts.append(label.rstrip(";"))
                previous_label = None
                continue
            # Canonical sections abbreviate repeated apparatus family, not facts.
            prefix = label if label != previous_label or not rating else ""
            name = " ".join(x for x in (prefix, rating) if x)
            require(quantity is not None, "component quantity missing")
            q = format(quantity.normalize(), "f")
            parts.append(f"{name} - {q}{unit}")
            previous_label = label
        lines.append((f"{section}: " if section else "") + "; ".join(parts) + ";")
    return "\n".join(lines)


def commercial_block(terms: Mapping[str, Any]) -> list[str]:
    lead, delivery = terms["manufacturing_lead_time"], terms["delivery"]
    validity = terms.get("validity") or "3 банковских дней"
    require(
        all(
            isinstance(v, str) and bool(v.strip()) and "\n" not in v
            for v in (lead, delivery, validity)
        ),
        "commercial values missing or multiline",
    )
    return [
        f" Коммерческое предложение действительно в течение {validity}",
        " Электрооборудование обмену и возврату не подлежит",
        " Спецификация счёта/КП после внесения предоплаты изменению не подлежит",
        (
            " К счёту/КП выше одного миллиона тенге прилагается договор. "
            "Без договора выполнение работ по счёту/КП не производится."
        ),
        (
            " Оплата данного счёта/КП подразумевает полное согласие плательщика "
            "с предложенной спецификацией."
        ),
        (
            f" Предположительный срок изготовления {lead}  с первого рабочего дня "
            "после дня поступления средств "
        ),
        " на расчетный счет, точный срок изготовления уточнять после оплаты.",
        f" Примечание: условия поставки {delivery}",
    ]


def display_text(item: Mapping[str, Any]) -> str:
    return (
        item["apparatus"]["text"]
        if "display_policy" in item
        else item["detailed_technical_composition"]
    )


def validate_future_content(
    document: Mapping[str, Any], *, test_mode: bool = False
) -> None:
    if document["schema_version"] != DOCUMENT_VERSION:
        return
    require(document["document_type"] == "QUOTE", "future content produces QUOTE only")
    policy = document["presentation_policy"]
    require(
        set(policy)
        == {"policy_id", "policy_sha256", "canonical_sha256", "source_sha256"},
        "future presentation policy fields",
    )
    require(
        policy["policy_id"] == POLICY_ID
        and policy["policy_sha256"] == sha256_file(Path(__file__)),
        "future policy drift",
    )
    bindings = {
        b["role"]: b for b in document["approval_provenance"]["source_bindings"]
    }
    require(
        "CANONICAL_744_1" in bindings
        and "AUTHORITATIVE_DOCUMENT_TEXT_SOURCE" in bindings
        and "GOVERNED_744_CONTENT_POLICY" in bindings,
        "future provenance roles missing",
    )
    for b in bindings.values():
        p = Path(b["path"])
        require(
            p.is_absolute() and sha256_file(p) == b["sha256"],
            "future provenance source drift",
        )
    canonical = bindings["CANONICAL_744_1"]["sha256"]
    require(
        test_mode or canonical == CANONICAL_SHA, "canonical 744-1 identity mismatch"
    )
    require(
        policy["canonical_sha256"] == canonical
        and policy["policy_sha256"]
        == bindings["GOVERNED_744_CONTENT_POLICY"]["sha256"],
        "content policy binding mismatch",
    )
    source_binding = bindings["AUTHORITATIVE_DOCUMENT_TEXT_SOURCE"]
    require(
        policy["source_sha256"] == source_binding["sha256"],
        "future source binding mismatch",
    )
    source = json.loads(
        Path(source_binding["path"]).read_bytes(), object_pairs_hook=strict_pairs
    )
    decision = json.loads(
        Path(bindings["CASE_HUMAN_APPROVAL"]["path"]).read_bytes(),
        object_pairs_hook=strict_pairs,
    )
    require(
        decision["approved_case_source_sha256"] == source_binding["sha256"]
        and decision["approved_document_fingerprint"]
        == document["document_fingerprint"],
        "external Human Approval binding drift",
    )
    require(len(source["items"]) == len(document["items"]), "display item set drift")
    for i, (original, item) in enumerate(
        zip(source["items"], document["items"], strict=True)
    ):
        require(
            item["detailed_technical_composition"]
            == original["detailed_technical_composition"],
            "engineering composition mutated",
        )
        require(
            all(
                c["source_locator"] == f"/items/{i}/detailed_technical_composition"
                for c in original["technical_display"]
            ),
            "component engineering provenance locator mismatch",
        )
        require(
            all(
                c["unit"] != "note"
                or c["label"] in original["detailed_technical_composition"]
                for c in original["technical_display"]
            ),
            "engineering note lacks exact source text",
        )
        require(item["display_policy"] == POLICY_ID, "display policy missing")
        a = item["apparatus"]
        require(
            a["text"] == technical_display(original["technical_display"]),
            "technical-to-display drift",
        )
        require(
            a["source_sha256"] == source_binding["sha256"]
            and a["source_locator"] == f"/items/{i}/technical_display",
            "display provenance mismatch",
        )
    lines = document["terms"]["commercial_lines"]
    require(
        [line["text"] for line in lines] == commercial_block(document["terms"]),
        "canonical commercial block incomplete/order/wording drift",
    )
    require(
        all(
            line["source_sha256"] == source_binding["sha256"]
            and line["source_locator"] == "/terms"
            for line in lines
        ),
        "commercial transformation provenance mismatch",
    )
