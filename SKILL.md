---
name: review-sheets
description: Use when a curation or review task is too large for conversation — someone must pick keep/cut, rank, grade, or assign across dozens to hundreds of items (sprites, defs, rows, files, images, records) — and whenever you are about to hand a human a generated HTML page they must WORK in rather than read. Also use when a decision needs capturing as data rather than prose, when a review's result must outlive the conversation, when a human reports a generated page is unusable (instructions block the screen, nowhere obvious to save, loses track of which group they are in), or when a decisions file may contain an agent's guesses rather than a human's choices.
---

# Sheets a human can actually decide with

**The problem:** a curation pass over 449 defs cannot happen in chat. Asking 449 questions is
absurd; deciding all 449 alone and presenting a wall of prose is worse, because the human
cannot see what he is agreeing to. The sheet is the middle: **the agent decides, the human
disagrees.**

Nine of these exist in the project this was extracted from — `anomaly_register`,
`biome_register`, `genome_register`, `species_register`, `mech_register`,
`xenotype_art_selector`, `faction_religions_spec`, `anomaly_assignment`,
`worldmap_elements`. Every lesson below was paid for in a real one.

---

## Build it like this. Do not hand-roll the page.

```bash
cp assets/sheet_template.html mysheet.html     # a COMPLETE sheet. Fill in two JSON blocks.
python3 make_prefill.py                        # your generator: writes decisions.json
python3 assets/check_sheet.py mysheet.html --decisions decisions.json   # the gate
python3 assets/serve_sheet.py --sheet mysheet.html --decisions decisions.json
```

`assets/sheet_template.html` is a whole working sheet. **You fill in exactly two things** —
`<script id="CONFIG">` (brief, posture, criterion, options) and `<script id="ITEMS">` (the
rows) — plus an optional `window.itemBody` if the default row is wrong for your data.

🔴 **Do not write the chrome yourself.** The previous version of this asset was a ~100-line
fragment saying "wire the three marked hooks", and agents rebuilt the page from scratch and
dropped one every time. That is why the chrome is no longer yours to author, and why
`check_sheet.py` exists.

⛔ **Hard gate: `check_sheet.py` must exit 0 before you hand the sheet over.** Every FAIL it
reports is a defect a real person hit and complained about. `assets/test_check_sheet.py`
proves the gate bites — 17/17 historical defects caught.

Details: **`references/chrome-and-layout.md`** (what the chrome must do and why),
**`references/persistence.md`** (how the file gets written), **`references/throughput.md`**
(reviewing hundreds of items quickly), **`references/cross-platform.md`** (macOS and
WSL-to-Windows-browser).

---

## 1. 🔴 Pre-fill it. A blank sheet is a chore you handed back.

Do not ship 449 empty rows. Decide every one against the project's brief, then let the human
overrule you. Owner, on being handed a pre-filled sheet: *"I'll just review."*

* **State the brief IN the page**, not just in chat. The sheet outlives the conversation, and
  six weeks later nobody remembers what "serious tone" meant.
* 🔴 **Flag any rule you INVENTED.** On the world-map sheet an agent decided the planet's
  volcanism was extinct — coherent, defensible, and never asked for. Stated plainly in a
  header panel, the owner overturned it in one line with better physics. Buried, it would
  have silently shaped the planet. **An invented premise presented as a finding is the most
  expensive mistake this format makes.** `CONFIG.invented` is a required key; set it to `[]`
  deliberately, never by omission.
* **Mark contested calls** — the ones defensible both ways — with a marker and their own
  filter. 18 flagged rows out of 449 carried nearly all the real judgement.
* **Leave genuinely open calls undecided ON PURPOSE**, with the note saying why, so they stand
  out from the ones you simply worked through.

## 2. 🔑 Say what each entry DOES, not what it is

Owner: *"'headwater' for a river... so what? I can see where that is on the map... what does
it mean if it has this particular mutator?"*

A label is not a decision aid. **Mine the actual data for the consequence.** RimWorld's
`TileMutatorDef` carries `animalDensityFactor`, `plantDensityFactor`, `junkDensityFactor`,
`extraGenSteps`, `blacklistedRaidStrategies` — so the line becomes *"Halves plants, doubles
junk, blocks siege raids"*. That is decidable; *"a headwater is where a river begins"* is not.

* **Lead with the consequence**, under ~20 words.
* ⚠️ **Mark inferences.** If a def has empty fields and you are guessing from its name, prefix
  it and give it a filter. 45 of 449 were guesses; presenting them as fact would have poisoned
  decisions made on them.
* ✅ **"No mechanical effect — appearance only" is a real answer** and it changes calls.
* For an image, **the picture IS the consequence** — a thumbnail earns the row its place, and
  demanding a prose line there is noise. `check_sheet.py` fails a sheet only on rows carrying
  neither.

## 3. 🔴 Your ranking criterion is probably not theirs — say so, and make disagreeing cheap

**The most valuable thing a sheet produces is not the rows the human agreed with. It is the
rows they overruled**, because those are where the machine's criterion and the human's differ
— and you cannot find that out by thinking harder about the criterion.

A measured case worth generalising. A sheet ranked 621 creature sprites for *art quality*
using what was measurable: resolution, contrast, fill, saturation. The human reviewed it,
overruled 8 rows, and his notes showed he had been judging something else entirely:

> *"Fascinating profile shape, so keep in and make smaller"* — weak art KEPT, for its outline.
> *"terrestrial, not wanted"* — good art CUT, for being recognisably from Earth.
> *"It's familiar outline is also a negative"* — familiarity itself as a defect.
> *"I can't even see what this thing is"* — legibility, which no sharpness measure captures.

The decisive row scored **2,850 px at contrast 0.30** — comfortably fine, pre-filled *keep*.
He ruled *redraw*: **"So alien and bizarre I want to honor it."**

🔑 **A metric can rank QUALITY. It cannot rank WORTH.** The sort order was still useful — it
put the weakest art in front of him first — but it was never the decision, and a sheet that
presents it as one collects agreement instead of judgement.

**So build for the disagreement:**

- ⭐ **Name your criterion in the page, in one line, next to the counts** (`CONFIG.criterion`).
  *"Ranked by sprite resolution — which ranks quality, not worth."* A human who can see what
  you optimised can tell you it was the wrong thing; one who cannot will assume you knew.
- **Make the note field the most inviting control on the row**, not an afterthought beside the
  dropdown. The 12 notes in that review were worth more than the 588 agreements, because each
  one carried a criterion nobody had written down.
- ⚠️ **Read the overrides as a GROUP before acting on them individually** —
  `serve_sheet.py --decisions f.json --overrides` prints them together with their reasons.
  Eight scattered disagreements looked like noise; read together they were one coherent rule
  the sheet did not know. Row-by-row you implement eight exceptions and miss the rule.
- ⚠️ **Do not make the sheet nag for a reason.** An earlier build grabbed focus and demanded
  *"why?"* on every disagreement. A control that fights the human gets worked around rather
  than used. Mark the override, filter for it, and read the notes that come freely.
- 🔴 **Report the override rate back honestly, and let it change what you build next.** A sheet
  with zero overrides has either nailed the criterion or failed to make disagreeing easy — and
  **those two look identical in the output file.** Compare against your other sheets before
  treating it as success.

## 4. Make the list tractable before asking for judgement

* ⭐ **Show what actually occurs.** Of 449 world-map defs, only **144 appeared in the real
  world**. That one column turns an impossible list into a short one.
* **Group by source** (mod, author, pack) — not alphabetically. Whole groups get decided in one
  motion because they share a character.
* **Bulk actions per group**, filters by state/source/type, and a text search that also matches
  the effect line. All of these are in the template.
* At hundreds of rows the bottleneck becomes the mouse, not the judgement — see
  **`references/throughput.md`**.

### ⭐ Count a marker against the real data BEFORE you add it

A badge, glyph, chip or highlight is worth adding only if it is **rare**. Measured on a real
board of 137 items, four candidate markers came out like this:

| candidate | rows | verdict |
|---|---|---|
| a draft is ready | 1 | ship it — high signal |
| an offer exists | 12 (9%) | ship it |
| material on disk | 29 (21%) | ship it |
| message body present | 33 (24%) | ship it |
| *who/what this involves* | **105 (77%)** | **cut it — wallpaper** |

A marker on three-quarters of the rows teaches the eye to skip that position, which quietly
destroys the *other* markers sharing it. Run the count first; it takes one query and it is the
difference between a signal and a decoration.

Two corollaries worth keeping:

- 🔴 **Never mark a field that is never populated.** Four more candidates on that same board
  looked perfect in the schema and were filled on **0 of 137** rows. A marker there is invisible
  forever, and worse, its *absence* reads as "none of these rows have that problem" when the truth
  is "nobody ever recorded one." Absence of data is not absence of the thing.
- **Distinguish a FLAG from a CATEGORY.** "A draft is ready" is a flag: absence is normal, so
  sparsity is the whole test. "Where this came from" is a category: every row has exactly one, so
  100% coverage is *correct* there and the sparsity rule does not apply. They need separate
  positions on the row — sharing one collapses two meanings into a glyph that means neither.

## 5. 🔴 Posture must be explicit, in the page AND in the export

A whitelist and a blacklist are the same UI and opposite meanings.

* Say it in the header: *"Default is EXCLUDE. Anything not whitelisted will be stripped."*
* Show a live counter of both sides — `whitelisted 296 · will be stripped 54`. Mark each option
  with `"counts": "in"|"out"` so the page can.
* 🔴 **Put the posture IN the decisions file** (`{"posture": "whitelist", ...}`). A sparse file
  is otherwise ambiguous: a consumer cannot tell *"strip these few"* from *"keep only these
  few"*, and will eventually guess wrong.
* Distinguish **rejected** (looked, said no) from **undecided** (never looked) even when both
  strip — the human needs to know which rows he has actually seen.

## 6. 🔴 Persistence — let the sidecar own the file

`localStorage` is where work goes to die. It is per-browser, per-profile, wiped by "clear
browsing data", and — measured — **shared across every `file://` page on the machine**.

⭐ **Run `assets/serve_sheet.py`.** It removes the picker entirely, and it moves four rules out
of "the agent must remember" and into plumbing that enforces them:

| Rule | If the page owns the file | With the sidecar |
|---|---|---|
| Merge per row, never all-or-nothing | page logic you can get wrong | server merges per key |
| Carry unknown top-level keys through | you must remember | server reads, merges, re-emits |
| Refuse a truncating write | you must remember | server returns 409 |
| Stamp a key only the page could write | you must remember, and once forgot | **server** stamps it, so a pre-fill generator cannot forge it |

**Always show link state and last-write time.** He must never wonder if his work is safe.

Full protocol, the `file://` fallback, the shared-origin hazard and the picker options that do
*not* require pasting a path: **`references/persistence.md`**.

⚠️ **If a decision SPAWNS an output, the sheet must be able to show it — or say where it went.**
Measured 2026-09-02: a row offered "draft a reply", he clicked it, the choice persisted correctly,
a generator produced a real validated artifact on disk — and **no surface could read it back.** No
error, no empty state, nothing: from where he sat the button had done nothing, and he would only
ever have found the result by knowing which directory to look in.

A request that persists while its result stays invisible is worse than a button that admits it is
dead, because the work looks *lost* rather than *pending*. Whenever an action produces an
artifact, build the read side in the same change as the write side, and give the row a visible
state — "drafted", with a way to open it. If you genuinely cannot show it yet, say on the row
where it lands.

## 7. Freeze the result, and make the freeze real

When the human says he is done:

* Commit his decisions file as the source of truth.
* Write `"frozen": true` with the date and what it means. The sidecar then refuses every write
  with HTTP 423 and the sheet goes read-only — the freeze is enforced, not announced.
* 🔴 **Make the generator that produced YOUR guesses refuse to run.** It would silently
  overwrite his decisions with the agent's. Require an explicit
  `--i-know-this-overwrites-the-owners-decisions`, and gate it on a key only the sheet writes.
  A comment saying "do not run this" is not a guard. (`demo/make_demo.py` does this — and it
  is worth knowing that it did *not*, until the demo silently ate a reviewed file.)
* ⭐ **Separate the two generators.** Regenerating the SHEET must stay safe — it renders from
  the decisions file, so a fixed renderer can be picked up mid-review. Only the DECISION
  generator is locked. One command that does both is what forces people to reach for the
  override flag and lose their work.
* ⚠️ **Say what freezing costs.** Under whitelist posture, rows left undecided are *stripped*.
  Name them at freeze time; the human may not realise he is cutting them.

## 8. 🔴 Prove the sheet actually wrote before you consume its file

Measured 2026-08-17, and it nearly deployed an agent's guesses as the owner's decisions.

The owner filled in a 71-row matrix, said "assignments are complete", and asked for it to be
committed. The decisions file on disk was **byte-identical to the generated pre-fill**: the
save link had never been established, so every choice was sitting in `localStorage` and the
file had never been touched. Committing it would have recorded the agent's own guesses under
the owner's name, and the applier would then have written them into the game.

```bash
python3 assets/serve_sheet.py --decisions decisions.json --status
# "touchedBySheet": false   ->  this is still the pre-fill. Nothing landed.
```

**Three cheap checks, in order of strength:**

1. ⭐ **A key only the sheet's plumbing writes** — `savedBy`, `writeCount`, `savedAt`. A
   pre-fill generator must never emit them, and with the sidecar it cannot. **Make the consumer
   refuse to run if they are absent.** This is the only check that cannot be fooled.
2. `git diff` the decisions file. No diff after a review session means no review landed.
3. Compare the decision count against the pre-fill's. Identical totals are suspicious.

⚠️ **"The owner said they finished" is not evidence that the file changed.** They finished; the
plumbing did not. Say so plainly and hand back the recovery — the work is usually still in
`localStorage`, so *"reopen the sheet and click copy JSON"* recovers it in seconds, and it is
destroyed only by clearing browsing data.

⇒ Build the guard into the tool, not the conversation: a consumer that cannot tell the human's
decisions from its own suggestions will eventually ship the wrong ones silently.

### 🔴 And one step earlier: prove the CONTROL FIRES. Click one in a real browser.

Measured 2026-09-02, and it is the cheapest bug to ship and the most expensive to notice. A
review board's buttons were wired to the sidecar. Everything a script can check was green:

* the whole unit suite passed — 2,224 tests
* the page was served, the token injected, `POST /decisions` round-tripped to disk
* every row carried its id, every button carried its action
* **the buttons rendered visibly enabled** — 220 of them

Clicking one threw `Cannot read properties of null (reading 'parentNode')` and saved nothing. The
markup named the button container one thing and the script looked for another. Every button on the
page was live-looking and inert, and **no assertion in the suite could see it**, because a
rendering test proves the markup and a protocol test proves the endpoint — neither one executes
the handler between them.

⭐ **So before handing the sheet over: serve it, click one control of each kind, and read the
browser console.** Not the DOM — the *console*. A handler that throws leaves the page looking
perfect.

Then check the whole consequence, not just the write:

```
did the value land on disk?           …and did the row's state change on screen?
did the count in the header follow?   …and does the page still agree with the file after a reload?
```

The follow-on bug that same day: the click *did* save and the row *did* move, and a header still
read "7" above six rows, because the counter refresh sat behind an early return. Saved-but-
contradicted is worse than not-saved, because he has no reason to look again.

⚠️ **Fix it in the seam, then re-introduce the bug to prove the guard bites.** Both defects above
were pinned with tests asserting the contract *from both sides* — the markup's class name and the
script's selector — and each guard was verified by putting the original bug back and watching the
suite go red. A regression test you have never seen fail is a test you are trusting on faith.

## 9. What to ask the human, and when

* Ask for the **posture** before generating — whitelist vs blacklist changes everything.
* Ask for a **ruling on invented rules** — do not bury them.
* Ask **what the decision will drive**, so you know whether "undecided" is safe.
* Do NOT ask for the 400 routine calls. That is the whole point.

---

## Handover checklist

Do not tell the human the sheet is ready until every line is true.

- [ ] `check_sheet.py` exits **0**. Not "only warnings I judged acceptable" — 0 FAILs.
- [ ] Every row is pre-filled, or deliberately undecided with a note saying why.
- [ ] `CONFIG.invented` is set — to a real list, or to `[]` on purpose.
- [ ] `CONFIG.criterion` names what you actually sorted by, including what it cannot rank.
- [ ] Posture is in the page **and** in the decisions file.
- [ ] The sidecar is running, or the fallback path is printed and copyable.
- [ ] You have said, in chat, how many rows you decided and which ones you are least sure of.
- [ ] You have **not** asked the human to paste a path, retype a filename, or hunt for a folder.
- [ ] You **served it and clicked one control of each kind in a real browser**, and read the
      console — not just the DOM. Enabled-and-inert passes every scripted check there is.
- [ ] Every marker you added was **counted against the real data first**, and none of them sits on
      most of the rows.
- [ ] Any action that produces an artifact can be **read back onto the row**, or the row says
      where the artifact went.

## Red flags

| Thought | Reality |
|---|---|
| "This sheet is small, the chrome rules don't apply" | The three complaints came from sheets of every size. Copy the template. |
| "I'll build the page from scratch, it's simpler" | This is exactly how the fold toggle goes missing every time. |
| "check_sheet's warnings are fine, I'll ship it" | FAILs block. Warnings you should still read out loud to the human. |
| "The human said they're done, so I'll commit the file" | Check `touchedBySheet`. They finished; the plumbing may not have. |
| "Zero overrides means I got the criterion right" | It equally means disagreeing was too hard. The file cannot tell you which. |
| "I'll ask them to save it in the right folder" | A path they retype is a path they get wrong. Run the sidecar. |
| "I'll pre-fill nothing so I don't bias them" | A blank sheet is a chore you handed back. Decide, then let them disagree. |
| "The metric ranked these, so the order is the answer" | A metric ranks quality. It cannot rank worth. |
| "The tests pass, so the buttons work" | A rendering test proves markup, a protocol test proves the endpoint. Neither runs the handler between them. Click one. |
| "The button is enabled, so it's wired" | 220 enabled buttons once threw on every click. Enabled is a style; wired is a console with no errors. |
| "It saved, so the row is correct" | It saved and the header still read 7 above six rows. Check the whole consequence, then reload. |
| "This glyph is useful, I'll add it" | Count it against real rows first. At 77% coverage it is wallpaper, and it ruins the markers beside it. |
| "The field is in the schema, so I can mark it" | It was populated on 0 of 137 rows. An invisible marker whose absence reads as "no problems here" is worse than none. |
