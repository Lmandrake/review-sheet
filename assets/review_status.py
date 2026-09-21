#!/usr/bin/env python3
"""review_status.py — the one place that answers "has a human ruled on this sheet?"

Every *.decisions.json sidecar has grown its own home-grown way of saying whether a
human has actually looked at it: `reviewed_by`/`owner_said`, `approvedBy`/`approvedAt`/
`approvedSaid`, `savedBy`+`writeCount` alone, `decidedCount`, `generatedBy`, a sentence
buried in the free-text `criterion`, or nothing at all — 7 shapes measured across 13
sheets on 2026-09-21. A consumer that checks one of those keys is right for a handful
of sheets and silently wrong for the rest. That is exactly how the RSW_MossBeetle
contradiction happened: a prefill sheet nobody had opened was read as owner-approved.
See `SHEET_REVIEWED_FLAG_UNIFORM_1`.

The fix is ONE required top-level key, `reviewStatus`, and ONE reader function that
every consumer calls instead of poking at provenance keys itself:

    "reviewStatus": {
        "state":    "ruled" | "prefill" | "unknown",
        "by":       "<who ruled — a name, or null>",
        "at":       "<ISO 8601 date or datetime it was ruled, or null>",
        "evidence": "<one line: which fact makes this classification true>"
    }

Rules for whoever writes it:

- A GENERATOR that pre-fills a sheet writes this key at birth with
  state="prefill" — never "ruled", and never omits the key. "I forgot to write it"
  and "nobody has reviewed this" must be indistinguishable to a consumer, so both
  read the same way: UNREVIEWED.
- Whoever records that a human actually ruled (a sidecar review session, a verbal
  ruling transcribed by an agent, a freeze) updates state to "ruled" and fills in
  by/at/evidence. A blanket ruling ("yes, replace everything") is still "ruled" —
  it does not need to be row-by-row to count, but say so in `evidence`.
- If the provenance genuinely does not say — no name, no quote, no unambiguous
  signal — write state="unknown" rather than guessing "ruled". Guessing "ruled"
  from row content (e.g. every row happens to read the same) is explicitly
  forbidden: a human who agrees with every prefill produces a file byte-identical
  to one nobody opened.
- A sidecar with NO `reviewStatus` key at all is UNREVIEWED, full stop — never
  read as neutral or as an implicit "ruled".

get_review_status() is the call every consumer should make. It returns "ruled" or
"prefill" and RAISES UnreviewedSheetError for "unknown" (explicit, or via a missing/
malformed reviewStatus key). It never returns the string "unknown" for a caller to
forget to check — the refusal on read is the deliverable, not a nice-to-have.

    from review_status import get_review_status, UnreviewedSheetError
    try:
        state = get_review_status("Transient/some_sheet.decisions.json")
    except UnreviewedSheetError as exc:
        ...refuse to treat this sheet's rows as decisions, and say why...

CLI: `./review_status.py path/to/*.decisions.json` prints one line per file.
"""

from __future__ import annotations

import json
import os

_VALID_STATES = {"ruled", "prefill", "unknown"}


class UnreviewedSheetError(Exception):
    """Raised by get_review_status() when a sidecar cannot prove a human ruled on it.

    This is the refusal the spec calls the deliverable: a reader that defaults to
    "probably ruled" on missing or ambiguous provenance rebuilds the exact defect
    this module exists to close.
    """


def _load(doc_or_path) -> dict:
    if isinstance(doc_or_path, dict):
        return doc_or_path
    path = os.fspath(doc_or_path)
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def read_review_status(doc_or_path) -> dict:
    """Return the raw {"state", "by", "at", "evidence"} block. Never raises.

    Use this when you want to DISPLAY the status (e.g. a dashboard, `--status`
    output). Use get_review_status() when you want the refuse-on-unknown contract.
    An absent or malformed `reviewStatus` key comes back as state="unknown" with an
    `evidence` string explaining why — it is never silently promoted to "prefill"
    or "ruled".
    """
    doc = _load(doc_or_path)
    rs = doc.get("reviewStatus")
    if not isinstance(rs, dict) or "state" not in rs:
        return {
            "state": "unknown", "by": None, "at": None,
            "evidence": "no reviewStatus key on this sidecar — treated as "
                        "UNREVIEWED, never as neutral (SHEET_REVIEWED_FLAG_UNIFORM_1)",
        }
    state = rs.get("state")
    if state not in _VALID_STATES:
        return {
            "state": "unknown", "by": rs.get("by"), "at": rs.get("at"),
            "evidence": f"reviewStatus.state={state!r} is not one of "
                        f"{sorted(_VALID_STATES)}",
        }
    return {
        "state": state,
        "by": rs.get("by"),
        "at": rs.get("at"),
        "evidence": rs.get("evidence"),
    }


def get_review_status(doc_or_path) -> str:
    """The call every consumer makes. Returns "ruled" or "prefill" — nothing else.

    Raises UnreviewedSheetError on "unknown" (explicit, or implied by a missing or
    malformed `reviewStatus` key). A caller MUST catch this and refuse to treat the
    sheet's rows as decisions rather than let the exception propagate as a generic
    crash — but it must not be swallowed into a default "proceed anyway".
    """
    rs = read_review_status(doc_or_path)
    if rs["state"] == "unknown":
        raise UnreviewedSheetError(
            "refusing: review status is UNKNOWN/unreviewed for this sidecar "
            f"({rs['evidence']}). A human must rule on it, or an agent must record "
            "why it is genuinely unknown, before any consumer may treat its rows as "
            "decisions. See SHEET_REVIEWED_FLAG_UNIFORM_1."
        )
    return rs["state"]


def _main(argv: list[str]) -> int:
    if not argv:
        print("usage: review_status.py <decisions.json> [...]")
        return 2
    rc = 0
    for p in argv:
        try:
            rs = read_review_status(p)
            state = get_review_status(p)
            print(f"{p}: {state}  (by={rs['by']!r} at={rs['at']!r})")
        except UnreviewedSheetError as exc:
            rc = 1
            print(f"{p}: REFUSED — {exc}")
        except (OSError, json.JSONDecodeError) as exc:
            rc = 2
            print(f"{p}: could not read — {exc}")
    return rc


if __name__ == "__main__":
    import sys
    sys.exit(_main(sys.argv[1:]))
