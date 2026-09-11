"""Prepare OSHB's OSIS XML without flattening its reading alternatives.

Only the Python standard library is required. See docs/HEBREW-PREPARATION.md
for the chosen text layer, language labels, and reproducible acquisition.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Iterator
import xml.etree.ElementTree as ET


OSIS = "http://www.bibletechnologies.net/2003/OSIS/namespace"
NS = {"o": OSIS}
SOURCE_URL = "https://github.com/openscriptures/morphhb"
PINNED_REVISION = "3d15126fb1ef74867fc1434be1942e837932691f"
BOOKS = (
    "Gen", "Exod", "Lev", "Num", "Deut", "Josh", "Judg", "Ruth",
    "1Sam", "2Sam", "1Kgs", "2Kgs", "1Chr", "2Chr", "Ezra", "Neh",
    "Esth", "Job", "Ps", "Prov", "Eccl", "Song", "Isa", "Jer", "Lam",
    "Ezek", "Dan", "Hos", "Joel", "Amos", "Obad", "Jonah", "Mic",
    "Nah", "Hab", "Zeph", "Hag", "Zech", "Mal",
)
LANGUAGE_PREFIXES = {"H": "hbo", "A": "arc"}
PARAGRAPH_MARKERS = {"x-samekh", "x-pe"}
INLINE_SEGMENTS = {"x-small", "x-large", "x-suspended"}
MAIN_SEGMENTS = {
    "x-sof-pasuq", "x-maqqef", "x-paseq", "x-reversednun",
    *PARAGRAPH_MARKERS,
}
READING_METHOD = {
    "text_layer": "main/ketiv",
    "selection": "Direct verse words and punctuation; ketiv retained; all notes and qere/accent alternatives excluded from text.",
    "unicode": "Original code points retained; no Unicode normalization or removal of vowel/accent marks.",
    "morpheme_delimiter": "ASCII slash removed only from rendered word text; raw_text and morpheme_segments preserve it.",
    "paragraph_markers": "Standalone x-samekh/x-pe glyphs excluded from text and retained in segments with source positions.",
    "other_segments": "Maqqef, sof-pasuq, paseq, reversed-nun and inline special-letter characters retained; segment attributes preserved.",
    "spacing": "One space between ordinary words/standalone signs; maqqef joins neighbors; sof-pasuq attaches to preceding text.",
    "language": "Each word follows its upstream morphology prefix H=hbo or A=arc; verse is mul only when both occur in main text.",
    "notes": "Structured mixed-content trees retained separately, including catchWord, rdg, types, attributes and tails.",
    "versification": "Bible.MT as encoded in OSHB; no English reference remapping.",
    "order": "Conventional 39-file order; not a claim about an ancient canonical book order.",
}


class SourceError(ValueError):
    """Source structure or annotation differs from the supported format."""


def _tag(element: ET.Element) -> str:
    prefix = "{" + OSIS + "}"
    if not element.tag.startswith(prefix):
        raise SourceError(f"Unexpected XML namespace/tag: {element.tag!r}")
    return element.tag[len(prefix):]


def _tree(element: ET.Element) -> dict:
    """Lossless element content/attributes, except namespace prefix spelling."""
    return {
        "tag": _tag(element),
        "attributes": dict(element.attrib),
        "text": element.text,
        "children": [_tree(child) for child in element],
        "tail": element.tail,
    }


def _word(element: ET.Element, source_position: int) -> dict:
    for attribute in ("id", "lemma", "morph"):
        if not element.get(attribute):
            raise SourceError(f"Word lacks {attribute}: {ET.tostring(element, encoding='unicode')}")
    morph = element.attrib["morph"]
    if morph[:1] not in LANGUAGE_PREFIXES:
        raise SourceError(f"Unknown morphology language prefix: {morph!r}")
    if element.get("type") not in (None, "x-ketiv"):
        raise SourceError(f"Unsupported word reading type: {element.get('type')!r}")
    # itertext is safe ONLY after checking the permitted inline descendants.
    # In particular, a future inline note must never become training text.
    for child in element.iter():
        if child is element:
            continue
        if _tag(child) != "seg" or child.get("type") not in INLINE_SEGMENTS:
            raise SourceError(f"Unsupported inline word element: {_tag(child)!r}")
        if len(child):
            raise SourceError("Nested special-letter segmentation is unsupported")
    raw_text = "".join(element.itertext())
    if not raw_text or any(char.isspace() for char in raw_text):
        raise SourceError(f"Empty word or unexpected whitespace: {raw_text!r}")
    if any(char.isascii() and char.isalpha() for char in raw_text):
        raise SourceError(f"Unexpected Latin prose in a biblical word: {raw_text!r}")
    record = {
        "source_position": source_position,
        "id": element.attrib["id"],
        "attributes": dict(element.attrib),
        "raw_text": raw_text,
        "text": raw_text.replace("/", ""),
        "morpheme_segments": raw_text.split("/"),
        "language": LANGUAGE_PREFIXES[morph[0]],
    }
    if len(element):
        record["inline_content"] = _tree(element)
    return record


def _note(element: ET.Element, source_position: int, after_token: int | None) -> dict:
    permitted = {"note", "catchWord", "rdg", "w", "seg"}
    for descendant in element.iter():
        if _tag(descendant) not in permitted:
            raise SourceError(f"Unknown note element: {_tag(descendant)!r}")
        if _tag(descendant) == "w":
            _word(descendant, source_position)  # Check even excluded alternatives.
    return {
        "source_position": source_position,
        "after_token_index": after_token,
        "included_in_text": False,
        "content": _tree(element),
    }


def _assert_layout_whitespace(text: str | None, where: str) -> None:
    if text and text.strip():
        raise SourceError(f"Unmarked text in {where}: {text!r}")


def _verse(element: ET.Element, book: str, chapter: int, verse: int) -> dict:
    reference = f"{book}.{chapter}.{verse}"
    if element.get("osisID") != reference:
        raise SourceError(f"Expected verse {reference}, got {element.get('osisID')!r}")
    _assert_layout_whitespace(element.text, reference)
    tokens: list[dict] = []
    segments: list[dict] = []
    notes: list[dict] = []
    pieces: list[tuple[str, str]] = []
    for position, child in enumerate(element):
        tag = _tag(child)
        _assert_layout_whitespace(child.tail, reference)
        if tag == "w":
            token = _word(child, position)
            token["index"] = len(tokens)
            tokens.append(token)
            pieces.append(("word", token["text"]))
        elif tag == "seg":
            kind = child.get("type")
            if kind not in MAIN_SEGMENTS or len(child):
                raise SourceError(f"Unsupported verse segment in {reference}: {kind!r}")
            raw_text = child.text or ""
            if not raw_text or any(c.isascii() and c.isalpha() for c in raw_text):
                raise SourceError(f"Invalid segment text in {reference}: {raw_text!r}")
            included = kind not in PARAGRAPH_MARKERS
            segments.append({
                "source_position": position,
                "after_token_index": len(tokens) - 1 if tokens else None,
                "attributes": dict(child.attrib),
                "raw_text": raw_text,
                "included_in_text": included,
            })
            if included:
                pieces.append((kind, raw_text))
        elif tag == "note":
            notes.append(_note(child, position, len(tokens) - 1 if tokens else None))
        else:
            raise SourceError(f"Unsupported verse element in {reference}: {tag!r}")
    if not tokens:
        raise SourceError(f"Verse contains no main-text words: {reference}")
    rendered = ""
    previous = None
    for kind, text in pieces:
        join = kind in {"x-maqqef", "x-sof-pasuq"} or previous == "x-maqqef"
        rendered += ("" if not rendered or join else " ") + text
        previous = kind
    languages = sorted({token["language"] for token in tokens})
    spans = []
    for token in tokens:
        if not spans or spans[-1]["language"] != token["language"]:
            spans.append({"language": token["language"], "token_start": token["index"], "token_end_exclusive": token["index"] + 1})
        else:
            spans[-1]["token_end_exclusive"] += 1
    return {
        "id": f"oshb:{reference}", "source_id": "oshb",
        "book": book, "chapter": chapter, "verse": verse,
        "source_ref": reference, "reference_system": "Bible.MT",
        "language": languages[0] if len(languages) == 1 else "mul",
        "languages": languages, "text_layer": "main/ketiv",
        "text": rendered, "tokens": tokens, "language_spans": spans,
        "segments": segments, "notes": notes,
    }


def parse_book(path: Path) -> Iterator[dict]:
    """Yield validated verse records from one OSHB book file."""
    tree = ET.parse(path)
    root = tree.getroot()
    if _tag(root) != "osis":
        raise SourceError(f"Not an OSIS document: {path.name}")
    books = root.findall("o:osisText/o:div", NS)
    if len(books) != 1 or books[0].get("type") != "book":
        raise SourceError(f"Expected exactly one book div: {path.name}")
    book = books[0]
    book_id = book.get("osisID")
    if book_id != path.stem or book_id not in BOOKS:
        raise SourceError(f"Book identity mismatch: {path.name}: {book_id!r}")
    if not len(book):
        raise SourceError(f"Book has no chapters: {book_id}")
    for chapter_number, chapter in enumerate(book, start=1):
        if _tag(chapter) != "chapter" or chapter.get("osisID") != f"{book_id}.{chapter_number}":
            raise SourceError(f"Non-contiguous or unexpected chapter in {book_id}")
        if not len(chapter):
            raise SourceError(f"Chapter has no verses: {chapter.get('osisID')}")
        _assert_layout_whitespace(chapter.text, chapter.get("osisID", "chapter"))
        for verse_number, verse in enumerate(chapter, start=1):
            if _tag(verse) != "verse":
                raise SourceError(f"Unexpected chapter element: {_tag(verse)}")
            _assert_layout_whitespace(verse.tail, chapter.get("osisID", "chapter"))
            yield _verse(verse, book_id, chapter_number, verse_number)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _artifact(path: Path, base: Path) -> dict:
    return {"path": path.relative_to(base).as_posix(), "bytes": path.stat().st_size, "sha256": _sha256(path)}


def _revision(source_dir: Path) -> str | None:
    if not (source_dir / ".git").exists():
        return None
    result = subprocess.run(["git", "-C", str(source_dir), "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
    dirty = subprocess.run(["git", "-C", str(source_dir), "status", "--porcelain", "--untracked-files=no", "--", "wlc", "parsing/HebrewMorphologyCodes.html", "LICENSE.md", "README.md"], capture_output=True, text=True, check=True)
    if dirty.stdout.strip():
        raise SourceError("Tracked source inputs have local modifications; preserve an unmodified source snapshot")
    return result.stdout.strip()


def verify_release_source(source_dir: Path, manifest_path: Path) -> str:
    """Require the reviewed release pin and consumed input hashes before writes.

    A source archive has no Git identity, so its complete input hashes provide
    the release identity. The generic prepare() API remains useful for fixtures.
    """
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest["source_id"] != "oshb" or manifest["pinned_commit"] != PINNED_REVISION:
            raise SourceError("Source manifest does not identify the reviewed OSHB release pin")
        artifacts = [entry["artifact"] for entry in manifest["books"]] + manifest["supporting_source_artifacts"]
        expected = {f"wlc/{book}.xml" for book in BOOKS} | {
            "LICENSE.md", "README.md", "wlc/VerseMap.xml", "parsing/HebrewMorphologyCodes.html",
        }
        paths = [artifact["path"] for artifact in artifacts]
        if set(paths) != expected or len(paths) != len(expected):
            raise SourceError("Source manifest must hash exactly all reviewed OSHB inputs")
        revision = _revision(source_dir)
        if revision is not None and revision != PINNED_REVISION:
            raise SourceError(f"OSHB source revision does not match release pin: {revision}")
        for artifact in artifacts:
            path = source_dir / artifact["path"]
            if not path.is_file():
                raise SourceError(f"Missing pinned OSHB input: {artifact['path']}")
            if path.stat().st_size != artifact["bytes"] or _sha256(path) != artifact["sha256"]:
                raise SourceError(f"OSHB release input hash mismatch: {artifact['path']}")
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise SourceError(f"Cannot verify OSHB release source manifest: {error}") from error
    return PINNED_REVISION


def prepare(source_dir: Path, output_dir: Path) -> dict:
    """Validate all 39 books and write verses.jsonl and summary.json.

    source_dir is the upstream repository root. The result is the same dictionary
    saved to summary.json. No API or training calls are made.
    """
    source_dir, output_dir = Path(source_dir), Path(output_dir)
    wlc = source_dir / "wlc"
    files = {path.stem: path for path in wlc.glob("*.xml") if path.stem != "VerseMap"}
    if set(files) != set(BOOKS):
        raise SourceError(f"Book inventory mismatch: missing={sorted(set(BOOKS) - set(files))}, unexpected={sorted(set(files) - set(BOOKS))}")
    for notice in ("LICENSE.md", "README.md"):
        if not (source_dir / notice).is_file():
            raise SourceError(f"Missing source notice: {notice}")
    revision = _revision(source_dir)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    languages: Counter = Counter()
    word_languages: Counter = Counter()
    note_types: Counter = Counter()
    segment_types: Counter = Counter()
    word_ids: set[str] = set()
    book_inventory = []
    total = Counter()
    mixed = []
    with tempfile.TemporaryDirectory(prefix="oshb-prepare-", dir=output_dir.parent) as temporary:
        staging = Path(temporary)
        with (staging / "verses.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
            for book in BOOKS:
                counts = Counter()
                book_languages: Counter = Counter()
                chapter_sizes: Counter = Counter()
                for record in parse_book(files[book]):
                    for token in record["tokens"]:
                        if token["id"] in word_ids:
                            raise SourceError(f"Duplicate source word ID: {token['id']}")
                        word_ids.add(token["id"])
                        word_languages[token["language"]] += 1
                        if token["attributes"].get("type") == "x-ketiv":
                            total["ketiv_words"] += 1
                    for note in record["notes"]:
                        content = note["content"]
                        note_types[content["attributes"].get("type", "untyped")] += 1
                        stack = [content]
                        while stack:
                            item = stack.pop()
                            if item["tag"] == "w":
                                source_id = item["attributes"]["id"]
                                if source_id in word_ids:
                                    raise SourceError(f"Duplicate source word ID: {source_id}")
                                word_ids.add(source_id)
                                total["note_words"] += 1
                            if item["tag"] == "rdg":
                                total["reading_alternatives"] += 1
                            stack.extend(item["children"])
                    for segment in record["segments"]:
                        segment_types[segment["attributes"]["type"]] += 1
                        if not segment["included_in_text"]:
                            total["paragraph_markers_excluded_from_text"] += 1
                    languages[record["language"]] += 1
                    book_languages[record["language"]] += 1
                    chapter_sizes[record["chapter"]] += 1
                    if record["language"] == "mul":
                        mixed.append(record["source_ref"])
                    for key, value in {"verses": 1, "main_words": len(record["tokens"]), "notes": len(record["notes"]), "segments": len(record["segments"])}.items():
                        counts[key] += value
                        total[key] += value
                    handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
                counts["chapters"] = len(chapter_sizes)
                total["chapters"] += len(chapter_sizes)
                book_inventory.append({"book": book, **dict(counts), "verse_languages": dict(sorted(book_languages.items())), "chapter_verse_counts": [chapter_sizes[n] for n in sorted(chapter_sizes)], "artifact": _artifact(files[book], source_dir)})
        artifacts = [_artifact(source_dir / name, source_dir) for name in ("LICENSE.md", "README.md", "wlc/VerseMap.xml", "parsing/HebrewMorphologyCodes.html") if (source_dir / name).exists()]
        summary = {
            "schema_version": 1, "source_id": "oshb", "source_repository": SOURCE_URL,
            "source_revision": revision, "text_layer": "main/ketiv", "method": READING_METHOD,
            "counts": {"books": len(BOOKS), **dict(sorted(total.items()))},
            "verse_languages": dict(sorted(languages.items())),
            "main_word_languages": dict(sorted(word_languages.items())),
            "mixed_language_verses": mixed, "note_types": dict(sorted(note_types.items())),
            "segment_types": dict(sorted(segment_types.items())), "books": book_inventory,
            "supporting_source_artifacts": artifacts,
            "output_artifact": _artifact(staging / "verses.jsonl", staging),
        }
        (staging / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        output_dir.mkdir(parents=True, exist_ok=True)
        for filename in ("verses.jsonl", "summary.json"):
            os.replace(staging / filename, output_dir / filename)
    return summary


def write_notices(source_dir: Path, notices_dir: Path) -> list[dict]:
    """Copy upstream notices and preserve each distinct XML header's content."""
    notices_dir.mkdir(parents=True, exist_ok=True)
    for original, destination in (("LICENSE.md", "LICENSE.md"), ("README.md", "UPSTREAM-README.md")):
        shutil.copyfile(source_dir / original, notices_dir / destination)
    headers = {}
    for book in BOOKS:
        header = ET.parse(source_dir / "wlc" / f"{book}.xml").find("o:osisText/o:header", NS)
        if header is None:
            raise SourceError(f"Missing source header: {book}")
        content = _tree(header)
        # Outer layout whitespace is not part of the header notice itself.
        content["tail"] = None
        key = json.dumps(content, ensure_ascii=False, sort_keys=True)
        entry = headers.setdefault(key, {"books": [], "header": content})
        entry["books"].append(book)
    (notices_dir / "XML-HEADER-NOTICES.json").write_text(json.dumps({"source": SOURCE_URL, "description": "Upstream header declarations preserved as declarations by their authors, not new rights determinations.", "headers": list(headers.values())}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return [_artifact(notices_dir / name, notices_dir) for name in ("LICENSE.md", "UPSTREAM-README.md", "XML-HEADER-NOTICES.json")]


def source_manifest(summary: dict, notice_artifacts: list[dict], acquired_date: str | None = None,
                    verified_revision: str | None = None) -> dict:
    """Return portable provenance and rights metadata for the prepared release."""
    return {
        "schema_version": 1, "source_id": "oshb", "name": "Open Scriptures Hebrew Bible",
        "repository": SOURCE_URL, "pinned_commit": verified_revision or summary["source_revision"],
        "source_git_revision": summary["source_revision"],
        "release_input_hashes_verified": verified_revision is not None,
        "acquired_date": acquired_date or date.today().isoformat(),
        "scope": "All 39 OSHB wlc book XML files; Hebrew and Aramaic; Masoretic/Leningrad base; Bible.MT references.",
        "status": "Prepared and mechanically validated; no expert textual review, model training or publication performed.",
        "licenses": [
            {"component": "Underlying Westminster Leningrad Codex text", "status": "Public domain according to upstream LICENSE.md and README.md"},
            {"component": "OSHB lemma and morphology annotations", "spdx": "CC-BY-4.0", "url": "https://creativecommons.org/licenses/by/4.0/", "attribution": "Original work of the Open Scriptures Hebrew Bible available at https://github.com/openscriptures/morphhb"},
        ],
        "redistribution": "Retain upstream attribution, license links and modification notices for annotations and derived data. Original project code license does not replace upstream data terms.",
        "preparation_command": "python -m bibleprep.hebrew --source-dir data/raw/oshb --output-dir data/processed/oshb --manifest manifests/oshb.json --notices-dir licenses/oshb",
        "preparation_module": "bibleprep/hebrew.py", "preparation_module_sha256": _sha256(Path(__file__)), "method": summary["method"],
        "source_notices_directory": "licenses/oshb", "notice_artifacts": notice_artifacts,
        "counts": summary["counts"], "verse_languages": summary["verse_languages"],
        "main_word_languages": summary["main_word_languages"], "mixed_language_verses": summary["mixed_language_verses"],
        "books": summary["books"], "supporting_source_artifacts": summary["supporting_source_artifacts"],
        "prepared_artifact": {**summary["output_artifact"], "path": "data/processed/oshb/verses.jsonl"},
        "prepared_summary_sha256": hashlib.sha256((json.dumps(summary, ensure_ascii=False, indent=2) + "\n").encode("utf-8")).hexdigest(),
        "source_exclusions": ["Non-wlc repository collections", "VerseMap.xml is hashed for provenance but not ingested or used to remap references"],
        "training_text_exclusions": ["All note prose", "Qere and accent alternatives", "Standalone samekh/pe paragraph-marker glyphs", "XML ASCII slash morpheme delimiters"],
        "limitations": ["Main/ketiv is an explicit reading-layer choice, not a recovered autograph", "Pointed ordinary words and often unpointed ketiv are retained as encoded; no missing vocalization is reconstructed", "Language labels follow OSHB annotations rather than a new linguistic adjudication", "Book and verse counts use this exact source's inventory and versification"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=Path("data/raw/oshb"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed/oshb"))
    parser.add_argument("--source-manifest", type=Path,
                        default=Path(__file__).resolve().parents[1] / "manifests" / "oshb.json",
                        help="Reviewed release manifest used to verify source revision and input hashes before preparation")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--notices-dir", type=Path)
    parser.add_argument("--acquired-date", help="Acquisition date YYYY-MM-DD; defaults to today when creating a new manifest")
    args = parser.parse_args(argv)
    if args.manifest and not args.notices_dir:
        parser.error("--manifest requires --notices-dir to preserve source notices")
    verified_revision = verify_release_source(args.source_dir, args.source_manifest)
    summary = prepare(args.source_dir, args.output_dir)
    notices = write_notices(args.source_dir, args.notices_dir) if args.notices_dir else []
    if args.manifest:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(source_manifest(summary, notices, args.acquired_date, verified_revision), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"source_id": "oshb", "source_revision": summary["source_revision"], "counts": summary["counts"], "verse_languages": summary["verse_languages"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
