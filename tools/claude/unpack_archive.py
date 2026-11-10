"""Unpack a RAR or ZIP archive from the bot, carefully (Igor 2026-11-10).

Usage: unpack_archive.py <source.rar|source.zip> <out_folder>

Uses the installed 7-Zip. Before unpacking it lists the archive and refuses
archives with a password, too many files or too much unpacked data. It unpacks
into a fresh temporary folder and copies into <out_folder> only project files
(PDF, Excel, pictures, AutoCAD drawings), flat, with safe names. Archives
inside the archive and every other file are skipped. <out_folder>/unpacked.txt
lists what was taken and what was skipped.

Operator tool for Claude; not part of the governed chain.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SEVEN_ZIP = Path(r"C:\Program Files\7-Zip\7z.exe")
TAKE = {".pdf", ".xlsx", ".xls", ".jpg", ".jpeg", ".png", ".webp", ".dwg"}
NESTED = {".rar", ".zip", ".7z", ".tar", ".gz", ".arj", ".cab"}
MAX_FILES = 300
MAX_TOTAL = 500 * 1024 * 1024  # unpacked bytes
TIMEOUT = 600
# A wrong password stops 7-Zip at once instead of waiting for a typed one.
NO_PASSWORD = "-pNOPASSWORD"


def seven(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed local program, no shell
        [str(SEVEN_ZIP), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=TIMEOUT,
        stdin=subprocess.DEVNULL,
        check=False,
    )


def listing(archive: Path) -> list[dict[str, str]]:
    """Entries of the archive; stops on a password or a damaged archive."""
    result = seven("l", "-slt", "-sccUTF-8", NO_PASSWORD, str(archive))
    if result.returncode != 0:
        tail = (result.stderr or result.stdout).strip().splitlines()[-3:]
        raise SystemExit("archive cannot be read (password?): " + " | ".join(tail))
    body = result.stdout.split("----------", 1)[-1]
    entries = []
    for block in body.split("\n\n"):
        fields = dict(
            line.split(" = ", 1) for line in block.splitlines() if " = " in line
        )
        if "Path" in fields:
            entries.append(fields)
    return entries


def safe_name(name: str, used: set[str]) -> str:
    stem = re.sub(r"[^\w\-. ()№,+]", "_", Path(name).stem).strip(" .") or "file"
    suffix = Path(name).suffix.lower()
    candidate, n = f"{stem}{suffix}", 2
    while candidate.lower() in used:
        candidate, n = f"{stem}_{n}{suffix}", n + 1
    used.add(candidate.lower())
    return candidate


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    archive, folder = Path(sys.argv[1]), Path(sys.argv[2])
    if not archive.is_file():
        raise SystemExit("archive not found")
    if not SEVEN_ZIP.is_file():
        raise SystemExit("7-Zip is not installed")
    entries = listing(archive)
    files = [e for e in entries if e.get("Folder") != "+"]
    if any(e.get("Encrypted") == "+" for e in files):
        raise SystemExit("archive has a password: ask the sender for the files")
    if len(files) > MAX_FILES:
        raise SystemExit(f"too many files in the archive: {len(files)}")
    total = sum(int(e.get("Size") or 0) for e in files)
    if total > MAX_TOTAL:
        raise SystemExit(f"too much unpacked data: {total} bytes")
    folder.mkdir(parents=True, exist_ok=True)
    taken: list[str] = []
    skipped: list[str] = []
    used = {p.name.lower() for p in folder.iterdir()}
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "x"
        result = seven("x", "-y", "-snl-", NO_PASSWORD, f"-o{work}", str(archive))
        if result.returncode != 0:
            raise SystemExit("unpacking failed: " + result.stdout.strip()[-300:])
        root = work.resolve()
        for path in sorted(work.rglob("*")):
            if path.is_symlink() or not path.is_file():
                continue
            if root not in path.resolve().parents:
                continue
            inner = path.relative_to(work).as_posix()
            suffix = path.suffix.lower()
            if suffix in TAKE:
                name = safe_name(path.name, used)
                shutil.copyfile(path, folder / name)
                taken.append(f"{name}\t<- {inner}")
            elif suffix in NESTED:
                skipped.append(f"{inner}\t(архив внутри архива)")
            else:
                skipped.append(inner)
    report = ["Взято:", *taken, "", "Пропущено:", *skipped, ""]
    (folder / "unpacked.txt").write_text("\n".join(report), encoding="utf-8")
    print(f"taken {len(taken)}, skipped {len(skipped)}; see unpacked.txt")


if __name__ == "__main__":
    main()
