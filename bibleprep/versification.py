"""Prepare a conservative English-to-MT reference map from pinned STEP data.

Only unambiguous whole-verse rows in the upstream summary are imported. Split,
empty and specially marked rows are blocked rather than silently approximated.
This affects lookup only: no training artifact is changed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import quote
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
REVISION = "c5407786ede9b26a8998366524076f7c739dccdd"
SOURCE_PATH = "Versification/TVTMS - Translators Versification Traditions with Methodology for Standardisation for Eng+Heb+Lat+Grk+Others - STEPBible.org CC BY.txt"
SOURCE_URL = "https://raw.githubusercontent.com/STEPBible/STEPBible-Data/" + REVISION + "/" + quote(SOURCE_PATH)
SOURCE_SHA256 = "63058e0f20201af4bdaa7d830da5be8f493455d947c5f147d84840b33db9ddf8"
BOOK_CODES = {"1Sa": "1Sam", "2Sa": "2Sam", "1Ki": "1Kgs", "2Ki": "2Kgs",
              "1Ch": "1Chr", "2Ch": "2Chr", "Psa": "Ps", "Ecc": "Eccl",
              "Sng": "Song", "Eze": "Ezek", "Joe": "Joel", "Jon": "Jonah", "Nam": "Nah",
              "Exo": "Exod", "Deu": "Deut", "Ezk": "Ezek", "Jol": "Joel", "Zec": "Zech"}
REF = re.compile(r"([1-3]?[A-Za-z]+)\.(\d+):(\d+)")


def canonical(value):
    match = REF.fullmatch(value.strip())
    if not match:
        return None
    book, chapter, verse = match.groups()
    return f"{BOOK_CODES.get(book, book)}.{int(chapter)}.{int(verse)}"


def prepare(raw: bytes) -> dict:
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise ValueError("The reference-mapping source does not match its pinned hash.")
    lines = raw.decode("utf-8-sig").splitlines()
    start = next(i for i, line in enumerate(lines)
                 if line.startswith("English (NRSV, ESV, KJV etc)\tHebrew MT"))
    end = next(i for i in range(start + 1, len(lines))
               if lines[i].startswith("Phrases and Abbreviations to translate"))
    mappings, blocked = {}, {}
    for number in range(start + 1, end):
        line = lines[number]
        if not line.strip() or line.startswith("'="):
            continue
        columns = line.split("\t")
        left, right = columns[0].strip(), columns[1].strip()
        key = canonical(left.lstrip("*"))
        if not key:
            raise ValueError("Unexpected row in the pinned reference summary.")
        if key in mappings or key in blocked:
            raise ValueError("Duplicate source reference in the mapping summary.")
        target = canonical(right)
        if target and not left.startswith("*"):
            mappings[key] = target
        else:
            blocked[key] = {"reason": "split, empty, or marked upstream mapping", "source_line": number + 1}
    return {
        "schema_version": 1, "status": "limited_lookup_mapping",
        "source_url": SOURCE_URL, "source_revision": REVISION, "source_sha256": SOURCE_SHA256,
        "license": "CC-BY-4.0", "attribution": "STEPBible.org, based on work at Tyndale House Cambridge",
        "method": "Extract unmarked whole-verse pairs from the English-to-Hebrew-MT summary; rename book codes, trim layout whitespace; block all other rows. No source wording is changed.",
        "limitations": ["Not a universal mapping for every Bible edition.",
                        "Untabulated references retain their coordinates; the target must exist in the pinned OSHB edition.",
                        "Split/empty/marked rows require clarification; no subverse alignment is inferred.",
                        "New Testament lookups use SBLGNT numbering, not this map."],
        "mappings": mappings, "blocked": blocked,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true", help="Fetch the pinned public mapping source if absent.")
    args = parser.parse_args(argv)
    path = ROOT / "data/raw/step-versification/TVTMS.txt"
    if not path.exists() and args.fetch:
        raw = urlopen(SOURCE_URL, timeout=30).read()
        result = prepare(raw)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    else:
        result = prepare(path.read_bytes())
    out = ROOT / "manifests/chat-versification-v1.json"
    data = (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode()
    if out.exists() and out.read_bytes() != data:
        raise ValueError("Refusing to overwrite a different reference map.")
    out.write_bytes(data)
    print(json.dumps({"mappings": len(result["mappings"]), "blocked": len(result["blocked"])}))


if __name__ == "__main__":
    main()
