# review-sheets

A Claude skill for building an **interactive HTML sheet a human can actually
decide with** — so a curation pass over hundreds of items (sprites, defs, biomes,
species, rows of any kind) happens in a page the human works in, instead of
hundreds of questions in chat.

The shape it enforces: **the agent decides, the human disagrees.** Pre-fill every
row, show what each entry *does* rather than what it is called, auto-save to a
real file rather than `localStorage`, and freeze the result when it is done.

It was extracted from the RimWorld project on 2026-08-23 because none of it is
RimWorld-specific — nine real sheets paid for every lesson in it, but the lessons
are about the instrument, not the domain.

## What is here

```
SKILL.md                   the skill itself — start here
assets/sheet_chrome.html   the three things that decide whether a sheet is usable
                           at all: the folding brief, the copy-path button, and
                           the sticky group label
```

## Install

```bash
mkdir -p ~/.claude/skills
ln -s /mnt/d/Luke/dev/review-sheets ~/.claude/skills/review-sheets
```

Per-project discovery is the same symlink under that project's `.claude/skills/`.

## Design in one line

A blank sheet is a chore you handed back; a pre-filled one is a decision the
human only has to disagree with.
