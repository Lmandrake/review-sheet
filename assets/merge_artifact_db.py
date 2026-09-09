#!/usr/bin/env python3
"""merge_artifact_db.py — fold a remote sitting's artifact-db verdicts back
into the sheet's sidecar decisions.json.

The remote flow: a sheet is published as a claude.ai artifact whose DbBackend
writes one db document per touched row ({rowId, rec:{decision,note,...},
savedAt, savedBy}). The agent dumps those documents to a directory with the
Artifact tool's read_db out_dir (one <docid>.json per row, meta/state ignored),
then runs this to merge them into the repo's decisions file.

Rules carried over from serve_sheet.py's own write contract:
  - merge PER ROW: only rows the human actually touched in the artifact are
    written; every other row in the file is left byte-for-byte alone.
  - unknown top-level keys ride through untouched.
  - REFUSED outright when the dump holds zero row documents — an empty merge
    means the review never landed, which must never read as "reviewed"
    (the 71-row localStorage incident, remote edition).
  - provenance is stamped honestly: savedBy 'artifact-db-merge', never the
    sidecar's own stamp; touchedBySheet true only because real rows merged.

    python3 merge_artifact_db.py --dump DIR --decisions FILE          # report
    python3 merge_artifact_db.py --dump DIR --decisions FILE --apply # write
"""
import argparse
import json
import os
import sys
import time


def load_rows(dump_dir):
    """-> {rowId: rec} from every row document in the dump directory.
    Skips meta/state and anything that doesn't carry rowId+rec; a document
    that LOOKS like a row but is malformed is a hard error, not a skip."""
    rows, skipped = {}, 0
    root = os.path.join(dump_dir, "decisions")
    if not os.path.isdir(root):
        root = dump_dir  # tolerate a flat dump
    for name in sorted(os.listdir(root)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(root, name)
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        if not isinstance(doc, dict) or "rowId" not in doc:
            skipped += 1
            continue
        rec = doc.get("rec")
        if not isinstance(rec, dict) or "decision" not in rec:
            sys.exit(f"REFUSED: {path} carries rowId {doc.get('rowId')!r} but a "
                     f"malformed rec ({type(rec).__name__}) — will not guess.")
        rows[str(doc["rowId"])] = rec
    return rows, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True,
                    help="directory the Artifact read_db out_dir produced")
    ap.add_argument("--decisions", required=True,
                    help="the sheet's sidecar decisions.json to merge into")
    ap.add_argument("--apply", action="store_true",
                    help="write the merge; default is report-only")
    args = ap.parse_args()

    rows, skipped = load_rows(args.dump)
    if not rows:
        sys.exit("REFUSED: the dump holds zero row documents — the remote "
                 "review never landed; merging nothing must not read as "
                 "'reviewed'.")

    with open(args.decisions, encoding="utf-8") as fh:
        doc = json.load(fh)
    if not isinstance(doc, dict):
        sys.exit(f"REFUSED: {args.decisions} top level is "
                 f"{type(doc).__name__}, not an object.")
    dec = doc.get("decisions")
    if dec is None:
        dec = doc["decisions"] = {}
    if not isinstance(dec, dict):
        sys.exit("REFUSED: existing 'decisions' key is not an object — fix the "
                 "file first; replacing it wholesale is how reviews get eaten.")

    merged = overridden = cleared = new = agreed = 0
    for row_id, rec in sorted(rows.items()):
        before = dec.get(row_id)
        merged += 1
        if rec.get("decision", "") == "":
            cleared += 1
        elif before is None:
            new += 1
        elif before.get("decision") != rec.get("decision"):
            overridden += 1
        else:
            agreed += 1
        dec[row_id] = rec

    decided = sum(1 for v in dec.values()
                  if isinstance(v, dict) and v.get("decision"))
    print(f"rows in dump: {len(rows)} (skipped non-row docs: {skipped})")
    print(f"merge: {new} newly decided, {overridden} changed, "
          f"{agreed} re-affirmed, {cleared} cleared")
    print(f"file after merge: {decided} decided of {len(dec)} rows")

    if not args.apply:
        print("\nreport only — re-run with --apply to write.")
        return

    doc["savedBy"] = "artifact-db-merge"
    doc["savedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    doc["writeCount"] = int(doc.get("writeCount") or 0) + 1
    doc["touchedBySheet"] = True  # true in fact: rows above are human acts
    doc["decidedCount"] = decided
    doc["mergedFromArtifactDb"] = {"rows": len(rows), "at": doc["savedAt"]}

    tmp = f"{args.decisions}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, args.decisions)
    print(f"written: {args.decisions}")


if __name__ == "__main__":
    main()
