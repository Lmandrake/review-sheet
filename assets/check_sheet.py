#!/usr/bin/env python3
"""check_sheet.py — refuse to hand over a review sheet a human cannot work in.

Every FAIL below is a defect a real person hit and complained about. They keep recurring
because prose in a skill file does not bind: an agent reads "the brief must fold", builds
the page from scratch, and ships one without a fold toggle. So the rule became a script.

    ./check_sheet.py path/to/sheet.html [--decisions path/to/decisions.json]

Exit 0 = safe to hand over. Exit 1 = FAILs present. Exit 2 = could not read the sheet.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from html.parser import HTMLParser

FAIL, WARN, OK = "FAIL", "WARN", "ok"


class Ancestry(HTMLParser):
    """Tracks where things sit, so we can ask 'is the filter bar inside the brief?'."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, dict]] = []
        self.filter_bar_ancestors: list[str] | None = None
        self.brief_seen = False
        self.script_ids: list[str] = []
        self.remote_srcs: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        ident, cls = a.get("id", ""), a.get("class", "") or ""
        if tag == "script":
            if ident:
                self.script_ids.append(ident)
            src = a.get("src", "")
            if src and re.match(r"^(https?:)?//", src):
                self.remote_srcs.append(src)
        if tag == "link" and re.match(r"^(https?:)?//", a.get("href", "")):
            self.remote_srcs.append(a["href"])
        if ident == "brief":
            self.brief_seen = True
        if "bar" in cls.split() and self.filter_bar_ancestors is None:
            self.filter_bar_ancestors = [i for (_, i) in self.stack]
        if tag not in ("br", "img", "input", "meta", "link", "hr", "source"):
            self.stack.append((tag, ident))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break


def json_block(html: str, tag_id: str):
    m = re.search(r'<script\s+id="%s"\s+type="application/json"\s*>(.*?)</script>' % tag_id,
                  html, re.S)
    if not m:
        return None, f'no <script id="{tag_id}" type="application/json"> block'
    try:
        return json.loads(m.group(1)), None
    except json.JSONDecodeError as exc:
        return None, f"{tag_id} block is not valid JSON: {exc}"


def check(path: str, decisions_path: str | None) -> list[tuple[str, str, str]]:
    """Returns [(severity, label, detail)]."""
    out: list[tuple[str, str, str]] = []

    def add(sev, label, detail=""):
        out.append((sev, label, detail))

    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        raw = fh.read()

    # Strip HTML comments before checking ANYTHING. Two reasons, both learned the hard way:
    # the template documents its own fill-in blocks inside a comment, which the JSON-block
    # regex happily matched instead of the real one; and a hook that exists only in a
    # comment must not count as present.
    html = re.sub(r"<!--.*?-->", "", raw, flags=re.S)

    tree = Ancestry()
    try:
        tree.feed(html)
    except Exception as exc:                              # noqa: BLE001 - parser is best effort
        add(WARN, "HTML did not parse cleanly", str(exc))

    # ── 1. the brief folds, is bounded, and does not take the filters with it ─────────
    has_fold_btn = re.search(r'id="fold"', html) is not None
    has_fold_css = re.search(r'\.folded\s*#brief|#brief[^{]*\{[^}]*display\s*:\s*none', html) is not None
    add(FAIL if not (has_fold_btn and has_fold_css) else OK,
        "the brief has a fold toggle",
        "" if has_fold_btn and has_fold_css else
        'need an id="fold" control and a body.folded #brief rule — '
        '"the top instructions are persistent and block the screen"')

    m = re.search(r'#brief\s*\{[^}]*max-height\s*:\s*([^;}]+)', html)
    add(FAIL if not m else OK, "the brief's height is BOUNDED",
        "" if m else "#brief needs a max-height. Folding alone is not enough: an open, "
                     "unbounded brief still owns the screen, which is the actual complaint")
    if m:
        add(OK, "  brief max-height", m.group(1).strip())

    persists = re.search(r"(localStorage|LS\.set)[^\n]*fold", html, re.I) is not None
    add(WARN if not persists else OK, "the fold is remembered",
        "" if persists else "re-collapsing on every visit is the same annoyance in a new hat")

    if tree.filter_bar_ancestors is None:
        add(WARN, "could not find a filter bar", "expected an element with class 'bar'")
    else:
        inside = "brief" in tree.filter_bar_ancestors
        add(FAIL if inside else OK, "the filter bar is OUTSIDE the folding region",
            "the search box is inside #brief — folding the brief to see the rows would "
            "hide the filters, a worse trade than the one being fixed" if inside else "")

    # ── 2. the save path is present and copyable ─────────────────────────────────────
    has_copy = re.search(r"data-copy=|clipboard\.writeText", html) is not None
    add(FAIL if not has_copy else OK, "a copy button exists for the save path",
        "" if has_copy else "a path the human retypes is a path they get wrong")
    fallback = re.search(r"execCommand\('copy'\)|selectNode|press ⌘", html) is not None
    add(WARN if not fallback else OK, "clipboard has a fallback",
        "" if fallback else "the clipboard API is refused on some file:// pages")

    if "showSaveFilePicker" in html and "showOpenFilePicker" not in html:
        add(WARN, "uses showSaveFilePicker only",
            "Save-As cannot be given a folder, so the human must paste a path. Pre-create "
            "the decisions file and use showOpenFilePicker (or the sidecar) instead")

    # ── 3. the group label follows, and does not sit on top of a one-row group ────────
    sticky = re.search(r"\.gh\s*\{[^}]*position\s*:\s*sticky", html) is not None
    add(FAIL if not sticky else OK, "group labels are sticky",
        "" if sticky else '"I really like when the different blocks have a persistent name '
                          'that follows along with you while you scroll"')
    nostick = "nostick" in html
    add(FAIL if not nostick else OK, "short groups are de-stuck",
        "" if nostick else "a sticky label covers the only row in a group of one — "
                           "unreadable and unclickable")
    measured = re.search(r"offsetHeight[^\n]*\n?[^\n]*\.top|\.top\s*=\s*h\s*\+", html) is not None
    add(FAIL if not measured else OK, "sticky offset comes from the MEASURED header height",
        "" if measured else "a hardcoded top leaves labels floating or buried once the "
                            "brief folds and the header changes height")
    remeasure = html.count("measure()") >= 3
    add(WARN if not remeasure else OK, "measure() is re-run after render and on resize",
        "" if remeasure else "new group nodes have no top until you measure again")

    # ── 4. storage keys are namespaced (the shared file:// origin) ────────────────────
    raw_ls = re.findall(r"localStorage\.(?:set|get)Item\(\s*['\"]([^'\"]+)['\"]", html)
    bare = [k for k in raw_ls if not k.startswith(("rs:", "NS"))]
    add(FAIL if bare else OK, "localStorage keys are namespaced per sheet",
        f"bare keys: {bare} — every file:// page shares ONE storage origin, so two sheets "
        f"opened from disk collide and one review silently eats the other" if bare else "")
    if "indexedDB" in html:
        ns_handle = re.search(r"(NS\s*\+\s*['\"]handle|['\"]\s*\+\s*sheetId)", html) is not None
        add(FAIL if not ns_handle else OK, "IndexedDB handle key is namespaced",
            "" if ns_handle else "a shared handle key means sheet B auto-writes into sheet "
                                 "A's FILE while reporting 'saved'")

    # ── 5. self-contained ────────────────────────────────────────────────────────────
    add(FAIL if tree.remote_srcs else OK, "no CDN or remote assets",
        f"remote: {tree.remote_srcs[:3]}" if tree.remote_srcs else
        "these are opened from disk, often offline")

    # ── 6. the data ──────────────────────────────────────────────────────────────────
    cfg, err = json_block(html, "CONFIG")
    if err:
        add(FAIL, "CONFIG block", err)
        cfg = {}
    items, err = json_block(html, "ITEMS")
    if err:
        add(FAIL, "ITEMS block", err)
        items = []

    if isinstance(items, list) and items:
        add(OK, "rows", str(len(items)))
        ids = [it.get("id") for it in items]
        dupes = {i for i in ids if ids.count(i) > 1}
        add(FAIL if dupes else OK, "row ids are unique",
            f"{len(dupes)} duplicated: {sorted(dupes)[:5]}" if dupes else "")
        add(FAIL if not all(ids) else OK, "every row has an id",
            "" if all(ids) else "rows without an id cannot be recorded")

        no_group = [i for i, it in zip(ids, items) if not it.get("group")]
        add(WARN if no_group else OK, "every row has a group",
            f"{len(no_group)} without one — grouping is what makes bulk judgement possible"
            if no_group else "")

        # pre-filled? A blank sheet is a chore handed back.
        pre = sum(1 for it in items if it.get("prefill") not in (None, ""))
        pct = 100 * pre // len(items)
        add(FAIL if pct == 0 else (WARN if pct < 90 else OK),
            "rows are pre-filled", f"{pre}/{len(items)} ({pct}%)"
            + ("" if pct >= 90 else " — the agent decides, the human disagrees"))

        # A label is not a decision aid. A row is only decidable if it carries a consequence
        # line OR an image — for a sprite the picture IS the consequence, so demanding prose
        # there would be noise. A row with neither is a name, and a name is not decidable.
        blind = sum(1 for it in items
                    if not str(it.get("effect") or "").strip() and not it.get("thumb"))
        pct_blind = 100 * blind // len(items)
        add(FAIL if pct_blind >= 25 else (WARN if blind else OK),
            "every row says what it DOES",
            f"{blind}/{len(items)} rows ({pct_blind}%) have neither an effect line nor an "
            f'image — "a headwater is where a river begins" is not decidable' if blind else "")

        opt_keys = {o.get("key") for o in (cfg.get("options") or [])}
        bad_pre = {it.get("prefill") for it in items
                   if it.get("prefill") not in (None, "") and it.get("prefill") not in opt_keys}
        add(FAIL if bad_pre else OK, "pre-fill values are valid options",
            f"unknown: {sorted(bad_pre)} not in {sorted(opt_keys)}" if bad_pre else "")

        if any(it.get("thumb") for it in items):
            missing = []
            base = os.path.dirname(os.path.abspath(path))
            for it in items:
                t = it.get("thumb")
                if t and not re.match(r"^(https?:|data:)", t) \
                        and not os.path.exists(os.path.join(base, t)):
                    missing.append(t)
            add(FAIL if missing else OK, "thumbnails resolve on disk",
                f"{len(missing)} missing, e.g. {missing[:3]}" if missing else
                f"{sum(1 for it in items if it.get('thumb'))} images")

    # ── 6b. a decisions file is actually there to review ──────────────────────────────
    # check() used to pass clean whenever it was simply never HANDED a --decisions path —
    # a sheet whose pre-fill generator never ran, or whose file lives somewhere else,
    # shipped with nothing behind the "copy path" button and nobody was told.
    if not decisions_path:
        cfg_name = str((cfg or {}).get("decisionsFile") or "").strip()
        if cfg_name:
            candidate = os.path.join(os.path.dirname(os.path.abspath(path)), cfg_name)
            if os.path.isfile(candidate):
                decisions_path = candidate
    add(FAIL if not decisions_path else OK, "a decisions file exists to review",
        "" if decisions_path else
        "no --decisions given and no file at CONFIG.decisionsFile beside the sheet — "
        "run the pre-fill generator first, or pass --decisions explicitly")

    # ── 7. posture and criterion ─────────────────────────────────────────────────────
    posture = (cfg.get("posture") or {}).get("mode")
    add(FAIL if not posture else OK, "posture is stated in the page",
        "" if posture else "a whitelist and a blacklist are the same UI and opposite meanings")
    if posture:
        add(OK, "  posture", posture)
    add(WARN if not str(cfg.get("criterion") or "").strip() else OK,
        "the ranking criterion is named",
        "" if str(cfg.get("criterion") or "").strip() else
        "a human who can see what you optimised can tell you it was the wrong thing; "
        "one who cannot will assume you knew")
    inv = cfg.get("invented")
    add(WARN if inv is None else OK, "invented rules are declared (even if empty)",
        "" if inv is not None else
        "add \"invented\": [] deliberately — an invented premise presented as a finding is "
        "the most expensive mistake this format makes")

    opts = cfg.get("options") or []
    hot = [o.get("hotkey") for o in opts if o.get("hotkey")]
    add(FAIL if len(hot) != len(set(hot)) else OK, "decision hotkeys are unique",
        f"clash: {hot}" if len(hot) != len(set(hot)) else "")
    add(WARN if not any(o.get("counts") for o in opts) else OK,
        "options say which side of the posture they land on",
        "" if any(o.get("counts") for o in opts) else
        'set "counts":"in"/"out" so the page can show a live kept/stripped counter')

    # ── 8. cross-check the decisions file, if given ──────────────────────────────────
    if decisions_path:
        try:
            with open(decisions_path, "r", encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            add(FAIL, "decisions file readable", str(exc))
        else:
            dec = doc.get("decisions") or {}
            add(OK, "decisions file", f"{len(dec)} rows")
            if isinstance(items, list) and items:
                item_ids = {it.get("id") for it in items}
                orphans = set(dec) - item_ids
                missing = item_ids - set(dec)
                add(WARN if orphans else OK, "no orphaned decisions",
                    f"{len(orphans)} ids in the file are not in the sheet" if orphans else "")
                add(WARN if missing else OK, "every row has a pre-fill entry",
                    f"{len(missing)} rows missing from the file" if missing else "")
            if doc.get("savedBy"):
                add(WARN, "this decisions file has ALREADY been reviewed",
                    f"savedBy={doc['savedBy']} writeCount={doc.get('writeCount')} — "
                    f"regenerating the pre-fill would overwrite a human's decisions")
            if doc.get("frozen"):
                add(WARN, "this decisions file is FROZEN", "the sheet should be read-only")

    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify a generated review sheet is usable.")
    ap.add_argument("sheet")
    ap.add_argument("--decisions", help="cross-check the pre-fill file too")
    ap.add_argument("--quiet", action="store_true", help="only print WARN and FAIL")
    args = ap.parse_args()

    if not os.path.isfile(args.sheet):
        print(f"no such sheet: {args.sheet}", file=sys.stderr)
        return 2

    try:
        results = check(args.sheet, args.decisions)
    except OSError as exc:
        print(f"cannot read: {exc}", file=sys.stderr)
        return 2

    width = max(len(label) for _, label, _ in results) + 2
    print()
    for sev, label, detail in results:
        if args.quiet and sev == OK:
            continue
        tag = {FAIL: "FAIL", WARN: "WARN", OK: "  ok"}[sev]
        line = f"  {tag}  {label.ljust(width)}"
        if detail:
            line += detail if len(line) + len(detail) < 110 else "\n" + " " * (width + 8) + detail
        print(line)

    fails = [r for r in results if r[0] == FAIL]
    warns = [r for r in results if r[0] == WARN]
    print(f"\n  {len(fails)} FAIL · {len(warns)} WARN · {len(results) - len(fails) - len(warns)} ok")
    if fails:
        print("\n  Do NOT hand this sheet over. Every FAIL above is a defect a real person hit.")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
