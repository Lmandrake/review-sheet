# review-sheets

A Claude skill for building an **interactive HTML sheet a human can actually
decide with** — so a curation pass over hundreds of items (sprites, defs, biomes,
species, rows of any kind) happens in a page the human works in, instead of
hundreds of questions in chat.

The shape it enforces: **the agent decides, the human disagrees.** Pre-fill every
row, show what each entry *does* rather than what it is called, let a sidecar own
the decisions file, and freeze the result when it is done.

It was extracted from the RimWorld project on 2026-08-23 because none of it is
RimWorld-specific — nine real sheets paid for every lesson in it, but the lessons
are about the instrument, not the domain.

## What is here

```
SKILL.md                      the skill itself — judgement and the hard gates. start here
references/
  persistence.md              how the human's decisions reach disk, and the file:// origin trap
  chrome-and-layout.md        the three complaints that make a sheet unusable
  throughput.md               keyboard, grid mode and performance at hundreds of rows
  cross-platform.md           macOS and WSL-with-a-Windows-browser
assets/
  sheet_template.html         a COMPLETE sheet. fill in two JSON blocks, author no chrome
  serve_sheet.py              the sidecar: owns the decisions file, stdlib only
  check_sheet.py              the gate. must exit 0 before you hand a sheet over
  test_check_sheet.py         proves the gate bites — 17/17 historical defects caught
demo/
  make_demo.py                worked example: 400 rows, 200 real PNG sprites, no deps
```

## Try it

```bash
cd demo && python3 make_demo.py
python3 ../assets/check_sheet.py sheet.html --decisions decisions.json
python3 ../assets/serve_sheet.py --sheet sheet.html --decisions decisions.json
```

Then, once a human has been through it:

```bash
python3 ../assets/serve_sheet.py --decisions decisions.json --status      # did they actually save?
python3 ../assets/serve_sheet.py --decisions decisions.json --overrides   # where were you wrong?
```

Verify the tooling on a machine before trusting it — particularly on WSL, where the
Windows-path and DrvFs behaviour lives:

```bash
python3 assets/serve_sheet.py --selftest
python3 assets/test_check_sheet.py
```

## Install

```bash
mkdir -p ~/.claude/skills
ln -s "$(pwd)" ~/.claude/skills/review-sheets
```

Per-project discovery is the same symlink under that project's `.claude/skills/`.

## Design in one line

A blank sheet is a chore you handed back; a pre-filled one is a decision the
human only has to disagree with.
