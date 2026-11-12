"""Count what a project PDF says, page by page (Igor 2026-11-12).

Usage: pdf_digest.py <project.pdf> [<more.pdf> ...] <out_folder>

Reads the text layer of each PDF (no OCR) and writes to <out_folder>:
  digest.txt          - per file and page: board names, enclosures, input
                        cables and a table "apparatus -> how many times";
  pages/<file>_pN.txt - the raw text of every page, for searching.

It is a counting aid for Claude, who still reads the drawings with his own
eyes: the digest says, for example, "VA47-29 1P 10A - 20", and if Claude's own
count differs he looks again. It does not know which board an apparatus
belongs to when several boards share one page - it only counts per page.
A page without a text layer (a scan) is reported as such.

Operator tool for Claude; not part of the governed chain.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

from pypdf import PdfReader

# Latin letters that look like Cyrillic ones, as drawn in projects.
LOOKALIKE = str.maketrans(
    {
        "A": "А",
        "B": "В",
        "C": "С",
        "E": "Е",
        "H": "Н",
        "K": "К",
        "M": "М",
        "O": "О",
        "P": "Р",
        "T": "Т",
        "X": "Х",
        "a": "а",
        "c": "с",
        "e": "е",
        "o": "о",
        "p": "р",
        "x": "х",
    }
)

# Breaker and switch types. Order matters: longer names first.
TYPE = (
    r"(?:ВА47-(?:29|100|125|63|60)|ВА-?47|ВА88-\d\d|ВА99(?:-\d+)?|ВА5[579](?:-\d\d)?"
    r"|ВА51-\d\d|ВА04-\d\d|АЕ\d{4}|ВН-?32|ВН-?63|ВН-?125|ВН-?100"
    r"|АД-?1[24]|АВДТ-?\d\d|ДИФ-?\d+|УЗО|ВД1-63|АП-?50"
    r"|ВР32-\d\d(?:\s?\d{5})?|ПЦ-\d{3}|ППН-?\d\d|ПН-?2|NB1-63|NXB-63|NM1-\d+|DZ47)"
)
SEP = r"[\s,;]*"

KIND = "(?P<kind>" + TYPE + ")"
P_ = r"(?P<poles>[1-4])\s?[РрP](?![а-я])"
C_ = r"(?:\s?(?P<char>[ВСDД])(?=\s?\d))?"
L_ = r"(?:[\s,]*(?P<leak>\d{2,3})\s?м[Аа])?"
R_ = r"(?P<rating>\d{1,4}(?:,\d)?)\s?[Аа]"
# A plain designation between type and poles: "ВА88-35 QF1 3Р, 250А".
# Not "QF4М4" - in that style the type comes after the rating.
QF_ = r"(?:QF\d{1,2}(?![А-ЯA-Z])" + SEP + r")?"
# In order: earlier patterns claim their text first.
APPARATUS = [
    # "АВДТ32 2Р С16/30мА"
    re.compile(
        KIND
        + SEP
        + P_
        + SEP
        + r"(?P<char>[ВСD])?\s?(?P<rating>\d{1,3})\s?/\s?(?P<leak>\d{2,3})\s?м[Аа]"
    ),
    # "ВА47-29 3Р D 25А", "ВН-32 3Р,25А", "ВА88-35 QF1 3Р, 250А", "АД12 2Р 30мА 16А"
    re.compile(KIND + SEP + QF_ + P_ + SEP + C_ + SEP + r"(?:[ВСDД])?" + L_ + SEP + R_),
    # "3Р, 20А ВА47-29" (type after rating)
    re.compile(P_ + SEP + C_ + L_ + SEP + R_ + SEP + KIND),
    # "АВДТ34 40А,300мА" (no poles written)
    re.compile(KIND + SEP + R_ + r"[\s,]*(?P<leak>\d{2,3})\s?м[Аа]"),
    # Table columns without "А": "ВА47-29 1Р 10 10" glued into "1Р1010"
    # (rated current, then trip current).
    re.compile(KIND + SEP + P_ + r"\s?(?P<columns>\d{1,3}\s?\d{1,3})(?![\d,.А])"),
]
STANDARD = [
    "250",
    "200",
    "160",
    "125",
    "100",
    "80",
    "63",
    "50",
    "40",
    "32",
    "25",
    "20",
    "16",
    "10",
    "6",
]


def split_columns(digits: str) -> str | None:
    """'1010' -> '10', '6350' -> '50': two standard ratings, keep the trip one."""
    digits = digits.replace(" ", "")
    for first in STANDARD:
        if digits.startswith(first) and digits[len(first) :] in STANDARD:
            return digits[len(first) :]
    return digits if digits in STANDARD else None


TYPE_ONLY = re.compile(TYPE)

# Specification row:
# "..., 1Р+N, 16А, 30мА, 6кА, х-ка С АВДТ32 247-204-0170 "IЕК" шт. 20".
SPEC = re.compile(
    r"([1-4])\s?Р(\+N)?[,\s]+(\d{1,4})\s?А[,\s]+(?:(\d{2,3})\s?м[Аа][,\s]+)?"
    r"(?:\d+(?:,\d)?\s?к[Аа][,\s]+)?(?:х-ка\s?([ВСD])\s?)?(" + TYPE + r")"
    r"[^\n]{0,60}?шт\.?\s?(\d{1,4})"
)
CONTACTOR_MOD = re.compile(r"КМ-?(\d{2,3})А?\s?(\d)N[ОO]")  # KM-16A 2NO
CONTACTOR_KMI = re.compile(r"КМИ-?\s?(\d{5})")
CONTACTOR_ANY = re.compile(r"(?:Контактор|Пускатель)[^\n]{0,30}?(\d{1,3})\s?А")
THERMAL = re.compile(r"(?:РТИ|РТЛ|РТТ|ТРН)-?\s?(\d{4,5})")
FUSE_IN = re.compile(r"In\.?в\.?\s?=\s?(\d+)\s?А")

BOARD = re.compile(
    r"(?<![А-Яа-я])((?:[А-Я]{0,3}Щ[А-Я]{0,5}|АВР|ВРУ|ШУ|ЯУО|ЯТП|УКРМ|Я5\d{3})"
    r"(?:-[А-Я]{1,4})?[- ]?\d{0,3}(?:[.,]\d{1,2})?(?:-\d{1,2})?)(?![А-Яа-я\d])"
)
NOT_BOARD = {"Щ", "ЩИТ", "ЩИТА", "ЩИТОВ", "ЩИТЕ"}
ENCLOSURE = re.compile(
    r"(ЩРн-?\s?\d{1,3}\s?з|ЩРв-?\s?\d{1,3}\s?з|ЩУРн[^\s,)]*|ЩМП-?\d{1,2}(?:-\d)?"
    r"|ВРУ1?-\d{2}-\d{2}|ША\d{4}-\d{2,4}|ЩО-?70[^\s,)]*|IP\s?\d\d|КРН-?\d+|КРВ-?\d+"
    r"|\d{3,4}\s?[хx×]\s?\d{3,4}\s?[хx×]\s?\d{3,4})"
)
# Standard cross-sections; the drawing often glues the line length right after.
SECTION = r"(?:240|185|150|120|300|95|70|50|35|25|16|10|2,5|1,5|6|4)"
CABLE = re.compile(
    r"((?:А?ВВГ|А?ВБбШв|ВВГнг|АПвБбШп|ПвБбШв|КВВГ|КГ)[^\s\d]{0,14}[\s-]*"
    r"(\d)\s?[хx×]\s?" + SECTION + r"(?:\s?\+\s?\d\s?[хx×]\s?" + SECTION + r")?)"
)
FROM = re.compile(
    r"(?:[Оо]т|ОТ)\s+([^\n]{0,30}?)\s*(?=(?:А?ВВГ|А?ВБбШв|АПвБбШп|ПвБбШв))"
)


def norm(text: str) -> str:
    text = text.translate(LOOKALIKE)
    text = text.replace(" ", " ").replace("ё", "е")
    return re.sub(r"[ \t]+", " ", text)


def spec_rows(text: str) -> tuple[Counter[str], list[tuple[int, int]]]:
    """Specification rows with an explicit quantity: label -> sum of "шт."."""
    found: Counter[str] = Counter()
    spans: list[tuple[int, int]] = []
    for m in SPEC.finditer(text):
        poles, plus_n, rating, leak, char, kind, qty = m.groups()
        label = f"{kind} {poles}Р" + ("+N" if plus_n else "")
        if char:
            label += f" {char}"
        if leak:
            label += f" {leak}мА"
        label += f" {rating}А"
        found[label] += int(qty)
        spans.append((m.start(), m.end()))
    return found, spans


def apparatus(
    text: str, used: list[tuple[int, int]] | None = None
) -> tuple[Counter[str], Counter[str]]:
    """Return (typed apparatus with poles and rating, bare type mentions)."""
    found: Counter[str] = Counter()
    used = list(used or [])
    for rx in APPARATUS:
        for m in rx.finditer(text):
            if any(m.start() < e and s < m.end() for s, e in used):
                continue
            used.append((m.start(), m.end()))
            g = m.groupdict()
            if g.get("columns") is not None:
                g["rating"] = split_columns(g["columns"])
                if g["rating"] is None:
                    continue
            label = re.sub(r"\s", " ", g["kind"])
            if g.get("poles"):
                label += f" {g['poles']}Р"
            if g.get("char"):
                label += f" {g['char'].replace('Д', 'D')}"
            if g.get("leak"):
                label += f" {g['leak']}мА"
            label += f" {g['rating']}А"
            if g.get("columns") is not None:
                label += "  (номинал из столбцов без «А»)"
            if _odd(g["kind"], g["rating"]):
                label += "  (?) проверить глазами"
            found[label] += 1
    bare: Counter[str] = Counter()
    for m in TYPE_ONLY.finditer(text):
        if not any(s <= m.start() < e for s, e in used):
            bare[m.group(0)] += 1
    return found, bare


def _odd(kind: str, rating: str) -> bool:
    """A rating this series is not made for: likely a mis-read."""
    amps = float(rating.replace(",", "."))
    if kind.startswith(("ВА47-29", "ВА-47", "ВА47 ", "АВДТ", "АД")) or kind == "ВА47":
        return amps > 63
    if kind.startswith("ВА47-100"):
        return amps > 100
    if kind.startswith(("ВА88", "ВА57", "ВА59", "ВА99")):
        return amps < 16
    return False


def page_digest(text: str) -> list[str]:
    t = norm(text)
    out: list[str] = []
    boards: Counter[str] = Counter()
    for m in BOARD.finditer(t):
        b = m.group(1).strip()
        # "32АЩС-71": the А of "32А" is glued to the board name.
        if (
            b.startswith("А")
            and m.start() > 0
            and t[m.start() - 1].isdigit()
            and len(b) > 1
            and b[1] in "ЩВРШЯУ"
        ):
            b = b[1:]
        boards[b] += 1
    boards = Counter(
        {b: n for b, n in boards.items() if b.upper() not in NOT_BOARD and len(b) > 1}
    )
    if boards:
        out.append(
            "  Щиты (как в тексте): "
            + ", ".join(
                f"{b}" + (f" ×{n}" if n > 1 else "") for b, n in boards.most_common(25)
            )
        )
    encl = Counter(e.strip() for e in ENCLOSURE.findall(t))
    if encl:
        out.append(
            "  Корпуса/размеры/IP: "
            + ", ".join(
                e + (f" ×{n}" if n > 1 else "") for e, n in encl.most_common(15)
            )
        )
    sources = [s.strip(" ,;:") for s in FROM.findall(t) if s.strip(" ,;:")]
    if sources:
        out.append("  «От …» перед кабелем: " + "; ".join(dict.fromkeys(sources)))
    cables = Counter(f"{c[0].strip()}" for c in CABLE.findall(t))
    big = {
        c: n
        for c, n in cables.items()
        if (m := re.search(r"(\d)\s?[хx×]\s?(" + SECTION + ")", c))
        and float(m.group(2).replace(",", ".")) >= 6
    }
    if big:
        out.append(
            "  Кабели от 6 мм² (кандидаты во вводной): "
            + ", ".join(c + (f" ×{n}" if n > 1 else "") for c, n in sorted(big.items()))
        )
    spec, spec_spans = spec_rows(t)
    if spec:
        out.append("  По спецификации (тип, полюса, номинал → сумма «шт.»):")
        for label, n in sorted(spec.items(), key=_sort_key):
            out.append(f"    {label} - {n}")
    found, bare = apparatus(t, spec_spans)
    if found:
        out.append("  Аппараты (тип, полюса, номинал → сколько раз в тексте):")
        for label, n in sorted(found.items(), key=_sort_key):
            out.append(f"    {label} - {n}")
        out.append(f"    всего: {sum(found.values())}")
    if bare:
        out.append(
            "  Тип без полюсов/номинала рядом: "
            + ", ".join(f"{k} ×{n}" for k, n in bare.most_common())
        )
    mod = Counter(f"{a}А {p}NO" for a, p in CONTACTOR_MOD.findall(t))
    if mod:
        out.append(
            "  Модульные контакторы: "
            + ", ".join(f"{k} - {n}" for k, n in sorted(mod.items()))
        )
    kmi = Counter(CONTACTOR_KMI.findall(t))
    if kmi:
        out.append(
            "  КМИ: " + ", ".join(f"КМИ-{k} - {n}" for k, n in sorted(kmi.items()))
        )
    other = Counter(CONTACTOR_ANY.findall(t))
    if other:
        out.append(
            "  «Контактор/Пускатель … А»: "
            + ", ".join(
                f"{k}А - {n}" for k, n in sorted(other.items(), key=lambda x: int(x[0]))
            )
        )
    thermal = Counter(THERMAL.findall(t))
    if thermal:
        out.append(
            "  Тепловые реле: "
            + ", ".join(f"{k} - {n}" for k, n in sorted(thermal.items()))
        )
    fuses = Counter(FUSE_IN.findall(t))
    if fuses:
        out.append(
            "  Плавкие вставки In.в: "
            + ", ".join(
                f"{k}А - {n}" for k, n in sorted(fuses.items(), key=lambda x: int(x[0]))
            )
        )
    for word in ("резерв", "Резерв"):
        n = t.count(word)
        if n:
            out.append(f"  Слово «резерв»: {n} раз(а)")
            break
    return out


def _sort_key(item: tuple[str, int]) -> tuple[str, int, float]:
    label = item[0]
    m = re.match(r"(.+?) (\d)Р.*? (\d+(?:,\d)?)А$", label)
    if not m:
        return (label, 0, 0.0)
    return (m.group(1), int(m.group(2)), -float(m.group(3).replace(",", ".")))


def digest_pdf(path: Path, pages_dir: Path, number: int) -> list[str]:
    lines = [f"=== {number:02d}. {path.parent.name[:24]}/{path.name}"]
    try:
        reader = PdfReader(str(path))
    except Exception as exc:  # noqa: BLE001 - report and go on
        return lines + [f"  не открывается: {exc}"]
    stem = f"{number:02d}_" + re.sub(r"[^\w.-]+", "_", path.stem)[:60]
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:  # noqa: BLE001
            lines.append(f"--- стр. {i}: текст не читается ({exc})")
            continue
        (pages_dir / f"{stem}_p{i}.txt").write_text(text, encoding="utf-8")
        if len(text.strip()) < 40:
            lines.append(f"--- стр. {i}: текста нет (скан?) — читать только глазами")
            continue
        body = page_digest(text)
        lines.append(
            f"--- стр. {i}" + ("" if body else ": аппаратов и щитов не найдено")
        )
        lines.extend(body)
    return lines


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    *pdfs, out = argv[1:]
    out_dir = Path(out)
    pages_dir = out_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "Подсчёт по тексту PDF (pdf_digest.py). Подсказка для сверки, не состав КП:",
        "числа — сколько раз запись встречается в тексте страницы. Если на странице",
        "несколько щитов, аппараты всех щитов сложены вместе. Спецификация и",
        "схема на одной странице дают двойной счёт. Сверять со своим чтением глазами.",
        "",
    ]
    for number, p in enumerate(pdfs, start=1):
        lines.extend(digest_pdf(Path(p), pages_dir, number))
        lines.append("")
    (out_dir / "digest.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"digest: {out_dir / 'digest.txt'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
