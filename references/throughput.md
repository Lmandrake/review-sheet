# Throughput — reviewing hundreds of items without it becoming a slog

Read this when the sheet will carry more than ~100 rows, when the items are images, or when a
human has said a review is taking too long.

At 40 rows the judgement is the work. At 600 the *interface* is the work, and the bottleneck
moves to the mouse. All of this is implemented in `assets/sheet_template.html`.

---

## 1. Keyboard first — one key per row

Mouse-only across 600 rows means 600 aim-and-click cycles. The convention below is borrowed from
annotation tools (Prodigy's whole thesis is that removing friction is what gets data looked at)
and from mail triage:

| Key | Action |
|---|---|
| `j` / `k` (or ↓/↑) | next / previous row |
| `1`…`9` | set the decision **and advance** — this is the one that matters |
| `⇧`+`1`…`9` | apply to the whole visible group |
| `n` / `Enter` | jump into the note / leave it |
| `u` / `⇧U` | undo / redo |
| `g` | next undecided row |
| `c` | next contested row |
| `/` | search |
| `v` | list / grid |
| `z` | zoom the focused thumbnail |
| `?` | the keymap itself |

⭐ **Decide-and-advance is the whole win.** It turns review into a rhythm: look, press, look,
press. Without the advance the human still has to move the mouse or press `j` between every
decision, which doubles the work.

⚠️ **Ignore keys while a note is focused**, and let `Esc` blur. A human typing *"keep"* in a note
must not set three decisions.

⚠️ **Scroll the focused row clear of the sticky header AND the sticky group label**, or the row
they are deciding on sits under the chrome.

## 2. Undo, because bulk actions are terrifying without it

**Bulk-apply to a group of 80 with no undo is a feature nobody dares use.** Give undo and redo a
**single uniform entry shape** so one row and eighty behave identically.

🔴 Measured bug worth not repeating: an earlier build pushed a separate `{batch}` shape that
`undo()` did not understand, so after a 37-row bulk apply `u` silently did nothing. It looked like
the keystroke was being ignored. **One shape, `{entries: [{id, before}]}`, for every action.**

## 3. Grid / contact-sheet mode, when the items are images

A vertical list is the wrong instrument for judging art. Side by side at a consistent scale, the
comparisons make themselves.

* Toggle list ⇄ grid; hide the toggle entirely when the sheet has no images (`CONFIG.media`).
* **Consistent box size with a density slider.** A 16×16 sprite and a 96×96 one shown at their
  natural sizes cannot be compared; shown in equal boxes, the resolution difference is instantly
  visible — which is often the decision.
* **Checkerboard behind every thumbnail** — transparency is invisible on a flat dark field.
* **Decision as a border colour plus a chip**, so a screenful of decisions is readable at a glance.
* **Click-to-zoom** at 3× on a checkerboard. Judging a sprite at 64px is judging nothing.
* `image-rendering: pixelated` for sprite art; the browser's default smoothing hides exactly the
  defects you are asking about.

Measured: 18 sprites visible at once versus 9 list rows on the same viewport.

## 4. Performance, and which half actually matters

Two different problems, and the smaller-sounding one is the important one.

**Per-row DOM patching (the important one).** Never re-render the list to update one row.
Measured at 400 rows: **0.2ms patched vs 6.3ms rebuilt**, a 32× difference — but the real cost of
rebuilding is that it **drops the caret out of the note field** mid-sentence. That is a
correctness bug, not a performance one.

**`content-visibility` (the nice one).** `content-visibility: auto` with
`contain-intrinsic-size: auto <rowheight>` on each row lets the browser skip layout and paint for
off-screen content. Measured at 400 rows: **22.6ms → 6.3ms** median render, 3.6×. The win grows
with row count; below a couple of hundred rows it is not worth reasoning about. Both properties
verified supported.

⚠️ **`contain-intrinsic-size` is not optional.** Without it, off-screen rows measure as
zero-height and the scrollbar jumps around as you scroll.

Also: `loading="lazy" decoding="async"` on every thumbnail, and re-measure sticky offsets after
each render.

## 5. Progress and resumption

A human who cannot see the end does not start.

* **A live counter**: `142/449 decided · 307 left · 18 overruled · 8 noted`, plus the live
  kept/stripped split from the posture.
* **`g` / "next undecided"** — the queue, without making them scroll to find it.
* **Persist the filters** (namespaced per sheet) so closing the tab does not lose their place.
* **Show render time** while you are developing the sheet; it is how you notice you have
  reintroduced a full rebuild.

## 6. What was deliberately left out

**An auto-prompt for "why?" on every override.** It was built and rejected: grabbing focus to
demand a reason reads as nagging, and a control that fights the human gets worked around rather
than used. The passive equivalents — marking the row, an overrides-only filter, and
`serve_sheet.py --overrides` for reading them as a group — get the same information without the
fight. If you find yourself adding a modal that blocks progress until the human justifies
themselves, this is the precedent for not doing it.
