"""Prepare a bounded, private lexical metadata sample from pinned STEP files.

Hebrew definitions are withheld because the selected file explicitly requests
separate Online Bible permission. Greek long definitions are also omitted; the
sample preserves all name-disambiguation rows for six selected Strong IDs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
REVISION = "c5407786ede9b26a8998366524076f7c739dccdd"
SOURCES = {
    "TBESH": {"language": "Hebrew", "sha256": "464dccadd95fd8620dd05fa0d7a4caba58ec3c4d5db3ebf38e43d046ca25b591"},
    "TBESG": {"language": "Greek", "sha256": "312f723d7b8ef263bbdfb0451c9b8057125804dfff390b6f8544cff2a84b57f4"},
}
SELECTED = ("G0746", "G2098", "G2316", "G2424", "G5207", "G5547")


def source_url(code):
    language = SOURCES[code]["language"]
    path = f"Lexicons/{code} - Translators Brief lexicon of Extended Strongs for {language} - STEPBible.org CC BY.txt"
    return "https://raw.githubusercontent.com/STEPBible/STEPBible-Data/" + REVISION + "/" + quote(path)


def prepare(hebrew, greek):
    for code, raw in (("TBESH", hebrew), ("TBESG", greek)):
        if hashlib.sha256(raw).hexdigest() != SOURCES[code]["sha256"]:
            raise ValueError("Lexical source does not match its pinned hash")
    rows = []
    fields = ("estrong", "dstrong_raw", "ustrong", "headword", "transliteration", "morphology", "gloss")
    for number, line in enumerate(greek.decode("utf-8-sig").splitlines(), 1):
        columns = line.split("\t")
        if columns[0] not in SELECTED:
            continue
        if len(columns) != 8:
            raise ValueError("Unexpected selected lexical row shape")
        rows.append({**dict(zip(fields, columns[:7])), "source_line": number,
                     "source_row_sha256": hashlib.sha256(line.encode()).hexdigest()})
    if {r["estrong"] for r in rows} != set(SELECTED) or len(rows) != 10:
        raise ValueError("Selected lexical inventory changed")
    return {"schema_version": 1, "status": "private_research_sample", "source_revision": REVISION,
            "sources": {k: {**v, "url": source_url(k)} for k, v in SOURCES.items()},
            "selected_greek_strong_ids": list(SELECTED), "greek_metadata_rows": rows,
            "hebrew_definition_rows_imported": 0, "greek_long_definitions_imported": 0,
            "hebrew_exclusion": "The TBESH header explicitly requests Online Bible permission for its abridged definitions; the general CC BY notice is not treated as settling that component.",
            "observed_greek_license": "CC-BY-4.0",
            "attribution": "STEPBible.org, based on work at Tyndale House Cambridge; TBESG identifies Abbott-Smith, Middle Liddell and STEP scholarship as its lexical sources.",
            "change_notice": "Select six eStrong values; preserve all ten matching rows and their original first seven fields. Omit the long-definition column. Preserve upstream disambiguation rather than forcing an automatic verse match.",
            "app_display": "pending", "training": "pending", "adapter_release": "pending",
            "limitations": ["Lexical glosses are possible meanings, not proof of a passage's intended meaning.",
                            "Name-disambiguation rows require contextual matching; no automatic word alignment is supplied.",
                            "No historical conclusions, chat-context change or training examples are created."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true", help="Fetch missing, hash-pinned public source files")
    args = parser.parse_args(argv)
    source_dir = ROOT / "data/raw/evidence-v1/step"
    raw = {}
    for code in SOURCES:
        path = source_dir / (code + ".txt")
        if not path.exists() and args.fetch:
            with urlopen(source_url(code), timeout=20) as response:
                data = response.read(8000001)
            if len(data) > 8000000 or hashlib.sha256(data).hexdigest() != SOURCES[code]["sha256"]:
                raise ValueError("Downloaded lexical source did not match the pinned artifact")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        raw[code] = path.read_bytes()
    result = prepare(raw["TBESH"], raw["TBESG"])
    destination = ROOT / "data/evidence/lexical-v1/step-greek-metadata.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode()
    if destination.exists() and destination.read_bytes() != data:
        raise ValueError("Refusing to overwrite a different lexical preview")
    destination.write_bytes(data)
    destination.chmod(0o600)
    print(json.dumps({"status": result["status"], "greek_metadata_rows": len(result["greek_metadata_rows"]),
                      "hebrew_definition_rows": 0, "greek_long_definitions": 0, "model_calls": 0}))


if __name__ == "__main__":
    main()
