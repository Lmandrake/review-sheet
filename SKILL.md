---
name: review-sheets
description: Build an interactive HTML sheet so a human can review, curate and record decisions over hundreds of items — sprites, defs, biomes, species, rows of any kind — instead of answering hundreds of questions in chat. Covers the three things that decide whether the sheet is usable at all (a COLLAPSIBLE brief that does not eat a sticky header, the save path PRESENT and copyable on a button press, and a sticky group label that follows while scrolling), plus pre-filling decisions so the human only disagrees, showing what each entry DOES rather than its name, auto-saving to a real file rather than localStorage, and freezing the result. Use whenever a curation or review task is too large for conversation, when someone must pick keep/cut across many items, when a decision needs capturing as data rather than prose, and whenever you are about to hand a human a generated HTML page they must WORK in — even a small one, because these three defects are what make such pages unusable.
---

# Sheets a human can actually decide with

Nine of these now exist in this repo — `anomaly_register`, `biome_register`,
`genome_register`, `species_register`, `mech_register`, `xenotype_art_selector`,
`faction_religions_spec`, `anomaly_assignment`, `worldmap_elements`. Every lesson below
was paid for in a real one.

**The problem they solve:** a curation pass over 449 defs cannot happen in chat. Asking
449 questions is absurd; deciding all 449 alone and presenting a wall of prose is worse,
because the human cannot see what he is agreeing to. The sheet is the middle: **the agent
decides, the human disagrees.**

Related: `rimworld-content-moderation` covers WHAT to keep in a RimWorld stack and how to
cut it. This skill is about the instrument.

---

## 1. 🔴 Pre-fill it. A blank sheet is a chore you handed back.

Do not ship 449 empty rows. Decide every one against the project's brief, then let the
human overrule you. Owner, on being handed a pre-filled sheet: *"I'll just review."*

* **State the brief IN the page**, not just in chat. The sheet outlives the conversation,
  and six weeks later nobody remembers what "serious tone" meant.
* 🔴 **Flag any rule you INVENTED.** On the world-map sheet an agent decided the planet's
  volcanism was extinct — coherent, defensible, and never asked for. Stated plainly in a
  header panel, the owner overturned it in one line with better physics. Buried, it would
  have silently shaped the planet. **An invented premise presented as a finding is the
  most expensive mistake this format makes.**
* **Mark contested calls** — the ones defensible both ways — with a marker and give them
  their own filter. 18 flagged rows out of 449 carried nearly all the real judgement.
* **Leave genuinely open calls undecided ON PURPOSE**, with the note saying why, so they
  stand out from the ones you simply worked through.

## 2. 🔑 Say what each entry DOES, not what it is

Owner: *"'headwater' for a river... so what? I can see where that is on the map... what
does it mean if it has this particular mutator?"*

A label is not a decision aid. **Mine the actual data for the consequence.** RimWorld's
`TileMutatorDef` carries `animalDensityFactor`, `plantDensityFactor`, `junkDensityFactor`,
`extraGenSteps`, `blacklistedRaidStrategies` — so the line becomes *"Halves plants,
doubles junk, blocks siege raids"*. That is decidable; "a headwater is where a river
begins" is not.

* **Lead with the consequence**, under ~20 words.
* ⚠️ **Mark inferences.** If a def has empty fields and you are guessing from its name,
  prefix it and give it a filter. 45 of 449 were guesses; presenting them as fact would
  have poisoned decisions made on them.
* ✅ **"No mechanical effect — appearance only" is a real answer** and it changes calls.

## 3. Make the list tractable before asking for judgement

* ⭐ **Show what actually occurs.** Of 449 world-map defs, only **144 appeared in the
  real world**. That one column turns an impossible list into a short one.
* **Group by source** (mod, author, pack) — not alphabetically. Whole groups get decided
  in one motion because they share a character.
* **Bulk actions per group**, filters by state/source/type, and a text search that also
  matches the effect line.

## 4. 🔴 Posture must be explicit, in the page AND in the export

A whitelist and a blacklist are the same UI and opposite meanings.

* Say it in the header: *"Default is EXCLUDE. Anything not whitelisted will be stripped."*
* Show a live counter of both sides — `whitelisted 296 · will be stripped 54`.
* 🔴 **Put the posture IN the exported JSON** (`{"posture": "whitelist", ...}`). A sparse
  file is otherwise ambiguous: a consumer cannot tell "strip these few" from "keep only
  these few", and will eventually guess wrong.
* Distinguish **rejected** (looked, said no) from **undecided** (never looked) even when
  both strip — the human needs to know which rows he has actually seen.

## 5. 🔴 Persistence — localStorage is where work goes to die

* **Auto-save on every keystroke.** No save button.
* ⚠️ `localStorage` is per-browser, per-profile, wiped by "clear browsing data", and
  weakest of all on `file://` pages. It is a cache, not storage.
* ⭐ **Link the page to the real file** with the File System Access API:
  `showSaveFilePicker` once, keep the handle in **IndexedDB** so it survives reloads,
  then auto-write debounced (~1s — the human types notes per keystroke). Chrome needs a
  gesture to re-grant after restart, so show a reconnect affordance rather than failing
  quietly.
* **Always show link state and last-write time.** He must never wonder if his work is safe.
* Keep export/clipboard/textarea as the fallback, and say honestly when the API is absent
  (Firefox) rather than pretending.
* 🔴 **A whole-file auto-writer DELETES keys it does not know about.** Measured: the
  sheet auto-saves by rewriting the entire JSON, and the file had meanwhile gained
  `frozen` / `frozenOn` / `frozenBy` / `frozenMeaning` from a different commit. The first
  keystroke would have silently erased the freeze marker. ⇒ **Read the existing file,
  carry unknown top-level keys through verbatim, and re-emit them.** Never assume your
  page is the only author of its own file.
* ✅ **Verify byte identity before trusting the writer.** Simulate the write and diff it
  against what is on disk — the first auto-write should produce a ZERO-line `git diff`.
  Anything else means the format drifted and every future diff is noise.
* 🔴 **Guard against a truncating write.** If in-memory state has implausibly few decided
  rows, REFUSE and say so. An auto-writer that empties the human's file over a transient
  bug is worse than the clumsy manual flow it replaced.

## 6. 🔴 Merge the pre-fill per row — never all-or-nothing

The bug worth the whole section. The sheet seeded its pre-fill **only when localStorage
was completely empty**, to avoid clobbering the human's work. He clicked two rows, came
back, and **all 350 pre-filled rows were suppressed** — the sheet looked broken and empty.

⇒ **Merge per key.** A row the human has touched is left exactly alone; every untouched
row takes the pre-fill. Then say which happened: *"Filled in 348 rows from the prefill,
and kept your 2 existing decisions untouched."* A vague banner gives him no way to tell a
deliberate state from a broken one.

## 7. Freeze the result, and make the freeze real

When the human says he is done:

* Commit his export as the source of truth.
* Write a `"frozen": true` flag with the date and what it means.
* 🔴 **Make the generator that produced YOUR guesses refuse to run.** It would silently
  overwrite his decisions with the agent's. Require an explicit
  `--i-know-this-overwrites-the-owners-decisions`. A comment saying "do not run this" is
  not a guard.
* Regenerating the SHEET stays safe — it reads the frozen file. Only the decision
  generator is locked.
* ⚠️ **Say what freezing costs.** Under whitelist posture, rows left undecided are
  *stripped*. Name them at freeze time; the human may not realise he is cutting them.

## 8. 🔴 The chrome: three things that decide whether the sheet is usable at all

**Every one of these is a complaint from a human who could not work in a sheet that had it
wrong.** They are cheap to build and they are the difference between a page someone reviews and
a page someone abandons. ⭐ **A ready-made, dependency-free implementation is
`assets/sheet_chrome.html` — copy it rather than rebuilding it.**

### 8a. The brief FOLDS, and remembers

> *"the top instructions are persistent and block the screen"*

The header must be sticky, because the filters have to stay reachable. That makes an always-open
brief a permanent hole in the screen — on a 600-row list the human scrolls past it hundreds of
times. So give it a fold toggle, and **persist the fold**: re-collapsing it on every visit is the
same annoyance wearing a different hat.

⚠️ **Keep the filter bar OUTSIDE the folding region.** Folding away the search box to see the rows
is a worse trade than the one you were fixing.

### 8b. The save path is PRESENT, and copies on a button

> *"It MUST have the file to link to already present and easily copied (with a button press)"*

🔑 **`showSaveFilePicker()` accepts a filename and not a folder** — a browser rule you cannot code
around — so the human must put the file in the right place themselves. **A path they have to
retype is a path they will get wrong**, and a decisions file written to the wrong folder is
invisible in the worst way: the sheet says *saved*, and the generator quietly finds nothing.

So print the **full native path** in the page and put a **copy** button on it. Print the sheet's
own path too — it is what they need to reopen it. Give the button a fallback that selects the text
when the clipboard API is refused, which happens on `file://` pages.

### 8c. The group name FOLLOWS while scrolling

> *"I really like when the different blocks have a persistent name that follows along with you
> while you scroll"*

Scroll into a long list and the question is always *"what am I looking at now?"*. A sticky group
label answers it continuously — and it is what makes bulk judgement possible, because whole groups
share a character and get decided in one motion.

⚠️ **Set `top` from the MEASURED header height, never a constant.** The header changes height when
the brief folds, and a stale offset leaves labels floating in mid-page or buried under the bar.
Re-measure at the end of every render and on resize.
⚠️ **De-stick groups of ≤3** — see 9a below; this is the same bug and it is easy to reintroduce.

---

## 9. Layout traps that cost real time

* 🔴 **(9a) Sticky group headers cover short groups.** Two mods had exactly ONE def each and
  the sticky header sat on top of the only row — unreadable, unclickable. Disable
  stickiness for groups of ≤3.
* Make the note field visually distinct from the effect line and the label, or the human
  cannot tell his own words from generated text.
* Dark, dense, single self-contained `.html`, no CDN — these are opened from disk, often
  offline. Inline the CSS and JS.

## 10. What to ask the human, and when

* Ask for the **posture** before generating (whitelist vs blacklist changes everything).
* Ask for a **ruling on invented rules** — do not bury them.
* Do NOT ask for the 400 routine calls. That is the whole point.

## 11. 🔴 Prove the sheet actually wrote before you consume its file

Measured 2026-08-17, and it nearly deployed an agent's guesses as the owner's decisions.

The owner filled in a 71-row matrix, said "assignments are complete", and asked for it to be
committed. The decisions file on disk was **byte-identical to the generated pre-fill**: the
File System Access link had never been established, so every choice was sitting in
`localStorage` and the file had never been touched. Committing it would have recorded the
agent's own guesses under the owner's name, and the applier would then have written them
into the game.

**Three cheap checks, in order of strength:**

1. ⭐ **Have the page stamp a key only IT writes** — `placedCount`, `savedAt`, anything — and
   make the consumer **refuse to run** if that key is absent. A pre-fill generator must
   never emit it. This is the only check that cannot be fooled.
2. `git diff` the decisions file. No diff after a review session means no review landed.
3. Compare the decision count against the pre-fill's. Identical totals are suspicious.

⚠️ **"The owner said they finished" is not evidence that the file changed.** They finished;
the plumbing did not. Say so plainly and hand back the recovery — the work is still in
`localStorage`, so *"reopen the sheet, click copy JSON or link the file"* recovers it in
seconds, and it is destroyed only by clearing browsing data.

⇒ Build the guard into the tool, not the conversation: a consumer that cannot tell the
human's decisions from its own suggestions will eventually ship the wrong ones silently.
