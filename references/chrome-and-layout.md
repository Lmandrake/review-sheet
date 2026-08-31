# The chrome — three things that decide whether the sheet is usable at all

Read this when a human says a generated page is unusable, when `check_sheet.py` fails a chrome
check, or when you are tempted to build the page yourself.

**Every item here is a verbatim complaint from a human who could not work in a sheet that had it
wrong.** They are cheap to build and they are the difference between a page someone reviews and
a page someone abandons. All of it is already implemented in `assets/sheet_template.html`.

---

## 1. The brief folds, is BOUNDED, and gets out of the way

> *"the top instructions are persistent and block the screen"*

The header must be sticky, because the filters have to stay reachable. That makes an always-open
brief a permanent hole in the screen — on a 600-row list the human scrolls past it hundreds of
times.

🔴 **A fold toggle alone is not the fix, and this is where the earlier version was wrong.** An
*open* brief with no height limit still owns the screen, which is what the complaint was actually
about. Three things together:

1. **`max-height` on the brief** (`26vh`, with `overflow:auto`). The worst case becomes "the
   brief scrolls inside itself", never "the rows are off-screen".
2. **A fold toggle whose state persists.** Re-collapsing on every visit is the same annoyance
   wearing a different hat.
3. **Auto-fold on the first real scroll**, once, if the human has never made their own fold
   choice — then flash the toggle so they can see where it went. The brief *must* be seen (it
   carries the posture and any rule you invented), and it must not be in the way once they start
   working. Auto-folding is what resolves those two.

Measured on a 900px viewport, 400 rows: header **362px (40% of the screen) → 128px (14%)** on
first scroll. Five visible rows became nine.

⚠️ **Keep the filter bar OUTSIDE the folding region.** Folding away the search box to see the
rows is a worse trade than the one you were fixing. `check_sheet.py` walks the DOM to confirm the
filter bar is not a descendant of `#brief`.

## 2. The save path is present and copyable

> *"It MUST have the file to link to already present and easily copied (with a button press)"*

With the sidecar running there is no picker and no path to paste, so this is now a **fallback** —
but it still has to be right, because the sheet must work opened straight off disk.

* Print the **full native path** and put a **copy** button on it. On WSL that means the *Windows*
  path — see `references/cross-platform.md`.
* Print the sheet's own path too; it is what they need to reopen it.
* Give the copy button a fallback that selects the text when the clipboard API is refused.
* Use `showOpenFilePicker` on a pre-created file, not `showSaveFilePicker` — see
  `references/persistence.md` for why that one choice removes the whole paste dance.

## 3. The group name FOLLOWS while scrolling

> *"I really like when the different blocks have a persistent name that follows along with you
> while you scroll"*

Scroll into a long list and the question is always *"what am I looking at now?"*. A sticky group
label answers it continuously — and it is what makes bulk judgement possible, because whole
groups share a character and get decided in one motion.

⚠️ **Set `top` from the MEASURED header height, never a constant.** The header changes height
when the brief folds, and a stale offset leaves labels floating in mid-page or buried under the
bar. Re-measure at the end of **every** render and on resize — new group nodes have no `top`
until you do.

⚠️ **De-stick groups of ≤3.** Two mods had exactly ONE def each and the sticky header sat on top
of the only row — unreadable, unclickable. `.gh.nostick { position: static }`.

---

## Layout traps that cost real time

* **Make the note field visually distinct** from the effect line and the label, or the human
  cannot tell his own words from generated text. It should be the most *inviting* control on the
  row — the notes are worth more than the agreements.
* **Let notes auto-grow.** A one-line box that hides what the human just wrote makes the most
  valuable field on the row look like the least important one.
* **Never rebuild the whole list to update one row.** Patch the row. A full `innerHTML` rebuild
  on every keystroke drops the caret out of the note field and feels broken — measured **0.2ms
  patched vs 6.3ms rebuilt** at 400 rows, and the caret survives.
* **Dark, dense, single self-contained `.html`, no CDN.** These are opened from disk, often
  offline. Inline the CSS and JS.
* **Show transparency honestly.** A sprite with an alpha channel is unjudgeable on a flat dark
  field — put a checkerboard behind every thumbnail.
* **Serve a favicon** (or a 204). A 404 in the console of an otherwise healthy sheet makes a
  human who opens devtools distrust the whole page.
* **Warn on unload if writes are pending.** `beforeunload` when the dirty set is non-empty.

## What `check_sheet.py` enforces here

Chrome checks that **FAIL** (block handover): fold toggle present, brief height bounded, filter
bar outside the fold, copy button for the save path, group labels sticky, short groups de-stuck,
sticky offset measured rather than hardcoded, storage keys namespaced, no CDN assets.

Checks that **WARN** (read them out loud to the human): fold not persisted, no clipboard
fallback, `measure()` not re-run, `showSaveFilePicker` used without `showOpenFilePicker`.

`assets/test_check_sheet.py` breaks a working sheet in each of these ways and asserts the
matching check flips to FAIL — 17/17. A gate nobody has tested is a gate that turns "nobody
checked" into "it was checked and it's fine".
