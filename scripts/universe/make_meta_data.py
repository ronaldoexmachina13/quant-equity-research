"""Write assets/meta_data.js from the dated headings in docs/LIMITATIONS_PLAN.md.

The dashboard's status strip and amendment log read this file, so the counts and
dates shown on the pages come from the plan itself and are never typed by hand.
Only headings of the form "## <title> (YYYY-MM-DD, <what it was written before>)"
are used. The text of the plan is not changed.

Run from the repository root:  python -m scripts.universe.make_meta_data
Unlike the result files, this file is derived and small, so it is overwritten.
"""
import json
import re
from pathlib import Path

PLAN = Path("docs/LIMITATIONS_PLAN.md")
OUT = Path("assets/meta_data.js")
HEADING = re.compile(r"^## (?P<title>.+?) \((?P<date>\d{4}-\d{2}-\d{2}),? (?P<note>[^)]*)\)\s*$")


def entry_id(title):
    """A15 for 'Amendment 15', PH2B for 'Phase 2B detailed design: ...'."""
    m = re.match(r"Amendment (\d+)", title)
    if m:
        return "A" + m.group(1)
    m = re.match(r"Phase (\w+) detailed design", title)
    if m:
        return "PH" + m.group(1)
    return title[:4].upper()


def main():
    entries = []
    for line in PLAN.read_text(encoding="utf-8").splitlines():
        m = HEADING.match(line)
        if m:
            note = m.group("note").strip()
            entries.append({
                "id": entry_id(m.group("title")),
                "date": m.group("date"),
                "title": m.group("title"),
                "note": note[:1].upper() + note[1:],
            })
    meta = {"planFile": str(PLAN).replace("\\", "/"), "entries": entries}
    text = ("/* Written by make_meta_data.py from the dated headings of docs/LIMITATIONS_PLAN.md. "
            "Do not edit by hand. */\nconst META = " + json.dumps(meta, indent=1, ensure_ascii=False) + ";\n")
    with open(OUT, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    print(f"wrote {OUT}: {len(entries)} dated entries, latest {entries[-1]['id']} ({entries[-1]['date']})")


if __name__ == "__main__":
    main()
