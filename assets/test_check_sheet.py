#!/usr/bin/env python3
"""test_check_sheet.py — prove the gate catches the defects it claims to.

A validator that passes everything is worse than no validator, because it converts
"nobody checked" into "it was checked and it's fine". So each case below breaks a working
sheet in exactly one historically-real way and asserts the matching check flips to FAIL.

    ./test_check_sheet.py [path/to/a/good/sheet.html]     # defaults to ../demo/sheet.html
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_sheet                                          # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT = os.path.join(HERE, "..", "demo", "sheet.html")


def set_items(html: str, mutate) -> str:
    m = re.search(r'(<script id="ITEMS" type="application/json">)(.*?)(</script>)', html, re.S)
    items = json.loads(m.group(2))
    return html[:m.start(2)] + json.dumps(mutate(items)) + html[m.end(2):]


def set_config(html: str, mutate) -> str:
    m = re.search(r'(<script id="CONFIG" type="application/json">)(.*?)(</script>)', html, re.S)
    cfg = json.loads(m.group(2))
    return html[:m.start(2)] + json.dumps(mutate(cfg)) + html[m.end(2):]


def drop_config_key(key):
    def f(cfg):
        cfg.pop(key, None)
        return cfg
    return f


# (name, mutation, the check label that must go FAIL)
CASES = [
    ("brief has no fold toggle",
     lambda h: h.replace('id="fold"', 'id="notfold"'),
     "the brief has a fold toggle"),

    ("brief height is unbounded",
     lambda h: re.sub(r"(#brief\s*\{[^}]*)max-height\s*:\s*[^;}]+;?", r"\1", h),
     "the brief's height is BOUNDED"),

    ("filter bar is inside the folding region",
     lambda h: h.replace('<div class="bar">', '<div id="brief"><div class="bar">', 1)
                .replace("</header>", "</div></header>", 1),
     "the filter bar is OUTSIDE the folding region"),

    ("no copy button for the save path",
     lambda h: h.replace("data-copy=", "data-nocopy=").replace("clipboard.writeText", "noop"),
     "a copy button exists for the save path"),

    ("group labels are not sticky",
     lambda h: re.sub(r"(\.gh\s*\{[^}]*)position\s*:\s*sticky", r"\1position:static", h),
     "group labels are sticky"),

    ("short groups are not de-stuck",
     lambda h: h.replace("nostick", "xxstick"),
     "short groups are de-stuck"),

    ("sticky offset is hardcoded",
     lambda h: h.replace("g.style.top = h + 'px'", "g.style.top = '96px'")
                .replace("offsetHeight", "clientTop"),
     "sticky offset comes from the MEASURED header height"),

    ("localStorage key is not namespaced",
     lambda h: h.replace("localStorage.setItem(NS + k", "localStorage.setItem('decisions'"),
     "localStorage keys are namespaced per sheet"),

    ("pulls a script from a CDN",
     lambda h: h.replace("</head>", '<script src="https://cdn.example.com/x.js"></script></head>'),
     "no CDN or remote assets"),

    ("ships a blank sheet — nothing pre-filled",
     lambda h: set_items(h, lambda its: [{**i, "prefill": None} for i in its]),
     "rows are pre-filled"),

    ("duplicate row ids",
     lambda h: set_items(h, lambda its: [{**i, "id": "same"} for i in its]),
     "row ids are unique"),

    ("rows say what they ARE, not what they DO",
     lambda h: set_items(h, lambda its: [{**i, "effect": ""} for i in its]),
     "every row says what it DOES"),

    ("pre-fill uses a value that is not an option",
     lambda h: set_items(h, lambda its: [{**i, "prefill": "maybe"} for i in its]),
     "pre-fill values are valid options"),

    ("a thumbnail does not exist on disk",
     lambda h: set_items(h, lambda its: [{**i, "thumb": "sprites/nope.png"} if i.get("thumb") else i
                                         for i in its]),
     "thumbnails resolve on disk"),

    ("posture is not stated",
     lambda h: set_config(h, drop_config_key("posture")),
     "posture is stated in the page"),

    ("two options share a hotkey",
     lambda h: set_config(h, lambda c: {**c, "options": [{**o, "hotkey": "1"} for o in c["options"]]}),
     "decision hotkeys are unique"),
]


def severity_of(results, label):
    for sev, lab, _ in results:
        if lab == label:
            return sev
    return "MISSING"


def main() -> int:
    good = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else DEFAULT)
    if not os.path.isfile(good):
        print(f"no sheet to mutate: {good}\nRun demo/make_demo.py first.", file=sys.stderr)
        return 2
    with open(good, "r", encoding="utf-8") as fh:
        base = fh.read()

    # The unmutated sheet must pass, or every case below proves nothing.
    baseline = check_sheet.check(good, None)
    base_fails = [lab for sev, lab, _ in baseline if sev == check_sheet.FAIL]
    rows = [(not base_fails, "baseline: the good sheet passes",
             "" if not base_fails else f"already failing: {base_fails}")]

    tmp = tempfile.mkdtemp(prefix="check-sheet-test-")
    # thumbnails are resolved relative to the sheet, so mutate in place beside the real one
    workdir = os.path.dirname(good)

    for name, mutate, label in CASES:
        broken = os.path.join(workdir, ".broken_test_sheet.html")
        try:
            with open(broken, "w", encoding="utf-8") as fh:
                fh.write(mutate(base))
            sev = severity_of(check_sheet.check(broken, None), label)
            rows.append((sev == check_sheet.FAIL, name,
                         f'"{label}" -> {sev}' if sev != check_sheet.FAIL else ""))
        finally:
            if os.path.exists(broken):
                os.unlink(broken)
    os.rmdir(tmp)

    print()
    for ok, name, detail in rows:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))
    bad = [r for r in rows if not r[0]]
    print(f"\n  {len(rows) - len(bad)}/{len(rows)} caught"
          + (f" — {len(bad)} DEFECT(S) SLIPPED THROUGH THE GATE" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
