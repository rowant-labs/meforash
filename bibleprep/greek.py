"""Prepare the pinned Faithlife SBLGNT without changing Greek Unicode spelling.

Only the standard library is required. Source hashes are checked against the
repository manifest before any output is written. This module does not train a
model, download sources, or contact an API.
"""

from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import unicodedata
import xml.etree.ElementTree as ET


BOOKS = (
    "Matt", "Mark", "Luke", "John", "Acts", "Rom", "1Cor", "2Cor",
    "Gal", "Eph", "Phil", "Col", "1Thess", "2Thess", "1Tim", "2Tim",
    "Titus", "Phlm", "Heb", "Jas", "1Pet", "2Pet", "1John", "2John",
    "3John", "Jude", "Rev",
)
MANIFEST_PATH = Path(__file__).resolve().parents[1] / "manifests" / "sblgnt.json"
APPARATUS_MARKER = re.compile(r"[⸀⸁][0-9]*|[⸂⸃⸄⸅]")
VERSE_LINE = re.compile(r"(\S+) ([1-9][0-9]*):([1-9][0-9]*)\t(.*)")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _lexical_characters(text: str) -> str:
    # This is only a comparison, never the stored spelling or a normalization.
    return "".join(
        char for char in text
        if unicodedata.category(char)[0] in "LM" or char == "ʼ"
    )


def _xml_verses(path: Path) -> tuple[str, dict]:
    root = ET.parse(path).getroot()
    if root.tag != "book" or set(e.tag for e in root) - {"title", "p"}:
        raise ValueError(f"Unexpected SBLGNT XML structure: {path.name}")
    title = root.findtext("title")
    if not title:
        raise ValueError(f"Missing book title: {path.name}")
    verses = {}
    current = None
    last_ref = (0, 0)
    for paragraph_index, paragraph in enumerate(root.findall("p"), 1):
        for element in paragraph:
            if element.tag == "verse-number":
                source_ref = element.attrib.get("id", "")
                match = re.fullmatch(r".+ ([1-9][0-9]*):([1-9][0-9]*)", source_ref)
                if not match:
                    raise ValueError(f"Invalid XML verse ID: {source_ref!r}")
                ref = tuple(map(int, match.groups()))
                if ref <= last_ref:
                    raise ValueError(f"Duplicate or out-of-order XML verse: {source_ref}")
                last_ref = ref
                current = {"source_ref": source_ref, "words": [], "paragraphs": []}
                verses[ref] = current
            elif element.tag == "w":
                if current is None or not element.text or len(element):
                    raise ValueError(f"Word outside verse or invalid word in {path.name}")
                paragraphs = current["paragraphs"]
                if not paragraphs or paragraphs[-1]["number"] != paragraph_index:
                    paragraphs.append({"number": paragraph_index,
                                       "start_word": len(current["words"]),
                                       "end_word": len(current["words"])})
                current["words"].append(element.text)
                paragraphs[-1]["end_word"] += 1
            elif element.tag not in {"prefix", "suffix"}:
                raise ValueError(f"Unexpected XML element {element.tag!r} in {path.name}")
    return title, verses


def _remove_apparatus_markers(source_text: str) -> tuple[str, list]:
    # Strip only leading/trailing layout spaces, not interior whitespace.
    trimmed = source_text.strip()
    leading = len(source_text) - len(source_text.lstrip())
    removed = 0
    markers = []
    for match in APPARATUS_MARKER.finditer(trimmed):
        markers.append({"symbol": match.group(),
                        "source_start": leading + match.start(),
                        "source_end": leading + match.end(),
                        "text_offset": match.start() - removed})
        removed += len(match.group())
    return APPARATUS_MARKER.sub("", trimmed), markers


def _span_kind(book: str, chapter: int, verse: int, opening: str) -> str:
    if opening == "[":
        return "doubtful_wording"
    if (book, chapter, verse) == ("Mark", 16, 8):
        return "shorter_ending_of_mark"
    if (book, chapter, verse) == ("Mark", 16, 9):
        return "longer_ending_of_mark"
    if (book, chapter, verse) == ("John", 7, 53):
        return "pericope_adulterae"
    return "double_bracketed_material"


def _annotate_brackets(records: list[dict]) -> None:
    """Track bracket ranges across verse/chapter boundaries in a whole book."""
    starts = []
    position = 0
    for record in records:
        starts.append(position)
        position += len(record["text"]) + 1
        record.update(editorial_spans=[], alternatives=[])
    joined = "\n".join(record["text"] for record in records)
    active = None
    spans = []
    for offset, char in enumerate(joined):
        if char in "[⟦":
            if active is not None:
                raise ValueError("Nested editorial brackets require explicit review")
            active = (offset, char)
        elif char in "]⟧":
            if active is None or {"[": "]", "⟦": "⟧"}[active[1]] != char:
                raise ValueError("Unmatched editorial closing bracket")
            spans.append((active[0], offset + 1, active[1]))
            active = None
    if active is not None:
        raise ValueError("Unclosed editorial bracket at end of book")

    for number, (start, end, opening) in enumerate(spans, 1):
        first = bisect_right(starts, start) - 1
        last = bisect_right(starts, end - 1) - 1
        first_record = records[first]
        group_id = f"{first_record['id']}:editorial:{number}"
        kind = _span_kind(first_record["book"], first_record["chapter"],
                          first_record["verse"], opening)
        status = "doubtful" if opening == "[" else "double_bracketed"
        source_span = {
            "start": {"id": first_record["id"], "offset": start - starts[first]},
            "end": {"id": records[last]["id"], "offset": end - starts[last]},
        }
        for index in range(first, last + 1):
            record = records[index]
            local_start = max(0, start - starts[index])
            local_end = min(len(record["text"]), end - starts[index])
            span = {"group_id": group_id, "kind": kind, "editorial_status": status,
                    "start": local_start, "end": local_end,
                    "opens_here": index == first, "closes_here": index == last,
                    "source_span": source_span}
            record["editorial_spans"].append(span)
            if opening == "⟦":
                text = record["text"][local_start:local_end]
                if index == first:
                    text = text[1:]
                if index == last:
                    text = text[:-1]
                record["alternatives"].append({**span, "text": text.strip()})

    for record in records:
        main_text = record["text"]
        for alternative in reversed(record["alternatives"]):
            main_text = main_text[:alternative["start"]] + main_text[alternative["end"]:]
        record["main_text"] = main_text.strip()
        if record["alternatives"]:
            record["editorial_status"] = (
                "main_with_supplement" if record["main_text"] else "supplement_only"
            )
        elif record["editorial_spans"]:
            record["editorial_status"] = "main_with_doubtful_wording"
        else:
            record["editorial_status"] = "main"


def parse_book(text_path: Path, xml_path: Path, book: str) -> list[dict]:
    """Parse paired official text/XML files; reject mismatched lexical content."""
    if book not in BOOKS:
        raise ValueError(f"Unsupported OSIS book: {book}")
    title, xml_verses = _xml_verses(xml_path)
    lines = text_path.read_text(encoding="utf-8-sig").splitlines()
    if not lines or lines[0] != title:
        raise ValueError(f"Text/XML book titles differ: {book}")
    records = []
    previous = (0, 0)
    for line_number, line in enumerate(lines[1:], 2):
        if not line.strip():
            continue
        match = VERSE_LINE.fullmatch(line)
        if not match or match[1] != book:
            raise ValueError(f"Malformed verse line: {book}:{line_number}")
        chapter, verse = int(match[2]), int(match[3])
        ref = (chapter, verse)
        if ref <= previous:
            raise ValueError(f"Duplicate or out-of-order verse: {book}.{chapter}.{verse}")
        previous = ref
        source_text = match[4]
        text, markers = _remove_apparatus_markers(source_text)
        xml = xml_verses.get(ref)
        if not text or xml is None:
            raise ValueError(f"Empty text or missing XML verse: {book}.{chapter}.{verse}")
        if _lexical_characters(text) != _lexical_characters("".join(xml["words"])):
            raise ValueError(f"Text/XML Greek spelling mismatch: {book}.{chapter}.{verse}")
        records.append({
            "id": f"sblgnt:{book}.{chapter}.{verse}", "source_id": "sblgnt",
            "book": book, "chapter": chapter, "verse": verse, "language": "grc",
            "text": text, "source_text": source_text,
            "source_ref": xml["source_ref"],
            "source_file": f"data/sblgnt/text/{book}.txt", "source_line": line_number,
            "word_count": len(xml["words"]), "paragraphs": xml["paragraphs"],
            "apparatus_markers": markers,
        })
    if len(records) != len(xml_verses):
        raise ValueError(f"Text/XML verse inventory differs: {book}")
    _annotate_brackets(records)
    return records


def summarize(records: list[dict]) -> dict:
    inventory = []
    for book in BOOKS:
        rows = [record for record in records if record["book"] == book]
        if not rows:
            continue
        chapters = {}
        for row in rows:
            chapters.setdefault(row["chapter"], set()).add(row["verse"])
        missing = [f"{book}.{chapter}.{verse}"
                   for chapter, verses in chapters.items()
                   for verse in range(1, max(verses) + 1) if verse not in verses]
        inventory.append({
            "book": book, "chapters": len(chapters), "verses": len(rows),
            "main_nonempty_verses": sum(bool(row["main_text"]) for row in rows),
            "source_words": sum(row["word_count"] for row in rows),
            "missing_internal_verse_numbers": missing,
            "chapter_verse_maxima": {str(ch): max(vs) for ch, vs in chapters.items()},
        })
    group_ids = {span["group_id"] for row in records for span in row["editorial_spans"]}
    return {
        "schema_version": 1, "source_id": "sblgnt", "language": "grc",
        "books": len(inventory), "verses": len(records),
        "main_nonempty_verses": sum(bool(row["main_text"]) for row in records),
        "source_words": sum(row["word_count"] for row in records),
        "text_characters": sum(len(row["text"]) for row in records),
        "main_text_characters": sum(len(row["main_text"]) for row in records),
        "alternative_fragments": sum(len(row["alternatives"]) for row in records),
        "editorial_groups": len(group_ids),
        "editorial_status_counts": dict(Counter(row["editorial_status"] for row in records)),
        "book_inventory": inventory,
        "missing_internal_verse_numbers": [ref for book in inventory
                                             for ref in book["missing_internal_verse_numbers"]],
        "numbering_note": "Internal gaps only; no text is invented for absent verse numbers. "
                          "Chapter maxima follow this edition, not an English versification.",
    }


def prepare(source_dir: Path, output_dir: Path) -> dict:
    """Validate the pinned source, write verses.jsonl/summary.json, return summary.

    ``source_dir`` is a Faithlife/SBLGNT checkout or archive root. ``output_dir``
    is the exact directory receiving the two prepared files. Hash validation
    also works with an archive that has no Git metadata.
    """
    source_dir, output_dir = Path(source_dir), Path(output_dir)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        relative = Path(entry["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Manifest source path must remain relative")
        path = source_dir / relative
        if not path.is_file() or sha256(path) != entry["sha256"]:
            raise ValueError(f"Missing or changed pinned SBLGNT source: {relative}")
    records = []
    for book in BOOKS:
        records.extend(parse_book(source_dir / "data/sblgnt/text" / f"{book}.txt",
                                  source_dir / "data/sblgnt/xml" / f"{book}.xml", book))
    summary = summarize(records)
    summary["source_revision"] = manifest["revision"]
    summary["license"] = "CC-BY-4.0"
    summary["preparation_version"] = 1
    output_dir.mkdir(parents=True, exist_ok=True)
    verses_path = output_dir / "verses.jsonl"
    with verses_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    summary["outputs"] = {"verses.jsonl": {"sha256": sha256(verses_path),
                                            "bytes": verses_path.stat().st_size}}
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=Path("data/raw/sblgnt"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed/sblgnt"))
    args = parser.parse_args()
    summary = prepare(args.source_dir, args.output_dir)
    print(json.dumps({key: summary[key] for key in
                      ("source_id", "source_revision", "books", "verses",
                       "main_nonempty_verses", "alternative_fragments")}, indent=2))


if __name__ == "__main__":
    main()
