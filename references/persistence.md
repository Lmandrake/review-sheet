# Persistence — getting the human's decisions onto disk

Read this when wiring a sheet's save path, when a review's work has gone missing, or when
deciding between the sidecar and the browser file APIs.

**The short version: run `assets/serve_sheet.py` and stop thinking about it.** The rest of this
file is why, and what to do when you cannot.

---

## Why the sidecar rather than the File System Access API

Not convenience. Four rules in the skill are rules an agent has to *remember*, and each one has
already been forgotten once in a real sheet. Moving the write to a server turns each into
something the plumbing enforces:

| Rule | Failure it prevents |
|---|---|
| **Merge per key** — only the rows in the request are touched | A page that seeds its pre-fill only when storage is empty. Measured: the human clicked two rows, came back, and **all 350 pre-filled rows were suppressed** — the sheet looked broken and empty. With the sidecar the page never seeds at all; it loads what is on disk. |
| **Carry unknown top-level keys through** | A whole-file auto-writer deletes keys it does not know about. Measured: the file had gained `frozen`/`frozenOn`/`frozenBy`/`frozenMeaning` from a different commit, and the first keystroke would have erased the freeze marker. |
| **Refuse a truncating write** | An auto-writer that empties the human's file over a transient bug is worse than the clumsy manual flow it replaced. The server returns **409** and the page shows it. |
| **Stamp a key only the plumbing writes** | Committing the agent's guesses under the human's name — see SKILL.md §8. A pre-fill generator physically cannot emit `savedBy`, because it is the *server* that writes it. |

Secondary wins that matter in practice: it works in Firefox and Safari (the File System Access
API does not), there is no permission to re-grant after a browser restart, the origin is a real
`http://localhost:PORT` rather than the shared `file://` bucket, and `--status` lets you answer
*"did the human actually save?"* from a shell instead of asking them.

## The protocol

```
GET  /                 the sheet, with window.__SIDECAR__ injected (token, native paths)
GET  /decisions        the file as-is, plus _rev
POST /decisions        {"ops": {itemId: decisionObject|null}, "force": false}
GET  /status           counts, provenance, frozen, unknown top-level keys
```

`ops` carries **only the rows that changed**. That is the structural part: a client bug cannot
empty a file it never mentions. `null` deletes a row's entry.

Responses that are not 200 and what the page must do:

| Code | Meaning | Page behaviour |
|---|---|---|
| 409 | truncating write refused | show the message, keep the ops pending, do not clear them |
| 423 | file is frozen | go read-only, say so in the header |
| 403 | bad or missing session token | tell them to use the printed URL |
| 500 | the file is unreadable or not JSON | refuse to write; never overwrite what you failed to parse |

The write itself: temp file in the same directory → `fsync` → `os.replace`. On failure it
retries five times with backoff, then falls back to an in-place write **after copying a
`.bak`**, and reports which path it took. See `references/cross-platform.md` for why the
fallback exists.

## Useful invocations

```bash
# serve
serve_sheet.py --sheet sheet.html --decisions decisions.json

# did a human actually review this, or is it still my guesses?
serve_sheet.py --decisions decisions.json --status

# read the disagreements as a group, before acting on any one of them
serve_sheet.py --decisions decisions.json --overrides

# verify this machine behaves — run it on WSL, where the interesting parts live
serve_sheet.py --selftest
```

## 🔴 The measured hazard: every `file://` page shares ONE storage origin

Measured 2026-08-31, Chrome on macOS. A page at `/tmp/a.html` wrote a `localStorage` key; a page
at `/tmp/probe2/other.html` read it back. `location.origin` is the literal string `"file://"`
for both. `navigator.storage.persisted()` is `false`, so the whole bucket is evictable.

Consequences, in ascending order of how bad they are:

1. A fold-state key called `sheet_folded` is **global** — folding one sheet folds all of them.
2. An unnamespaced decisions key means **sheet B silently eats sheet A's review**.
3. An unnamespaced IndexedDB *file handle* means **sheet B auto-writes its decisions into sheet
   A's file** — while reporting *saved*. This is the worst outcome the format can produce,
   because both sheets look healthy.

⇒ **Namespace every storage key by a sheet id** (`rs:<sheetId>:<key>`), and **verify a recalled
handle before writing a byte** — compare `handle.name` against the filename this sheet owns and
refuse if it differs. The template does both; `check_sheet.py` fails a sheet that does not.

This alone is a reason to prefer the sidecar: `http://localhost:8731` is a real origin, isolated
per port, with durable storage.

## The `file://` fallback, when nothing can be running

The sheet must still work opened straight off disk. What is measured to be available there
(Chrome, macOS, 2026-08-31): `showOpenFilePicker`, `showSaveFilePicker`, `showDirectoryPicker`,
IndexedDB, `navigator.clipboard.writeText`, `DataTransferItem.getAsFileSystemHandle`, and
`isSecureContext === true`. Presence is not function — see the origin hazard above — but the
APIs are there.

**Use the right picker.** The historical clumsiness came from reaching for Save-As:

| Approach | What the human does | Verdict |
|---|---|---|
| `showSaveFilePicker` | copies a path, pastes it into the filename box | ❌ The picker **cannot be given a folder** — a browser rule you cannot code around. A path they retype is a path they get wrong, and a decisions file in the wrong folder is invisible in the worst way: the sheet says *saved* and the generator quietly finds nothing. |
| `showOpenFilePicker` on a **pre-created** file | double-clicks the file that is already there | ✅ Nothing to type. The agent has already written the pre-fill, so the file exists. Pass `id: 'review-sheets'` and the picker reopens in the same folder next session. |
| `showDirectoryPicker` + `getFileHandle(name, {create:true})` | picks the folder once; the page owns the filename | ✅ Also fine. Costs write access to the whole folder. |
| drag the file onto the page | one drag from the file manager | ✅ Lovely as a secondary affordance. `getAsFileSystemHandle()` returns a writable handle. Chromium only. |

**Permissions.** Store the handle in IndexedDB and call `requestPermission()` on it: from Chrome
122 that triggers the three-way prompt with **"Allow on every visit"**, which is what makes the
link survive a browser restart. Without a stored handle you only get the one-shot prompt. Three
denials reverts to the old behaviour.

**Read-modify-write, always.** Your page is not the only author of its own file. Read the
existing JSON, carry unknown top-level keys through verbatim, then re-emit.

✅ **Verify byte identity before trusting a new writer.** Simulate the write and diff it against
what is on disk — the first auto-write should produce a **zero-line `git diff`**. Anything else
means the format drifted and every future diff is noise.

## localStorage is a cache, not storage

Keep it as the last resort, keep the export/copy-JSON fallback beside it, and **say so loudly in
the page** when that is where the work is living. Be honest when an API is absent rather than
pretending. The 71-row incident in SKILL.md §8 is what a quiet fallback costs.
