#!/usr/bin/env python3
"""make_demo.py — build a worked review sheet from the template.

This is the end-to-end example: it shows a generator's whole job, which is to produce
CONFIG, ITEMS, and a pre-filled decisions file — and to touch nothing else in the
template, because the chrome is not the generator's to author.

The dataset deliberately mixes the two things people actually review: ~200 sprites
(judged by eye, so they need thumbnails and a grid) and ~200 text defs (judged by their
consequence line). Sprites are real PNGs with transparency, written with zlib + struct so
there is no Pillow dependency on a machine where you cannot pip install.

    ./make_demo.py && ../assets/serve_sheet.py --sheet sheet.html --decisions decisions.json
"""

from __future__ import annotations

import json
import os
import random
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "..", "assets", "sheet_template.html")
SPRITES = os.path.join(HERE, "sprites")
RNG = random.Random(20260831)          # deterministic: a demo that changes every run is untestable


# ─────────────────────────────────────────────────────────────────────────────
# a PNG writer in 20 lines of stdlib
# ─────────────────────────────────────────────────────────────────────────────

def png_bytes(w: int, h: int, rows: list[list[tuple[int, int, int, int]]]) -> bytes:
    raw = b"".join(b"\x00" + bytes(v for px in row for v in px) for row in rows)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b""))


def make_sprite(size: int, contrast: float, sat: float, fill: float, seed: int) -> bytes:
    """A mirrored blob creature. Varying size/contrast/saturation/fill is the point: it
    reproduces the real case this skill was written from, where sprites were ranked by
    exactly those measurables — which rank quality, not worth."""
    r = random.Random(seed)
    hue = r.random()
    # cheap HSV->RGB at full value
    i, f = int(hue * 6) % 6, hue * 6 - int(hue * 6)
    v, p, q, t = 235, int(235 * (1 - sat)), int(235 * (1 - sat * f)), int(235 * (1 - sat * (1 - f)))
    base = [(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)][i]

    cx, cy = size / 2, size / 2
    lobes = [(r.uniform(-0.18, 0.18), r.uniform(-0.35, 0.35),
              r.uniform(0.16, 0.34) * fill, r.uniform(0.16, 0.40) * fill)
             for _ in range(r.randint(3, 6))]

    rows = []
    for y in range(size):
        row = []
        for x in range(size):
            nx, ny = (x - cx) / size, (y - cy) / size
            inside, depth = False, 0.0
            for (ox, oy, rx, ry) in lobes:
                for sx in (nx, -nx):                       # mirror: bilateral symmetry
                    d = ((sx - ox) / rx) ** 2 + ((ny - oy) / ry) ** 2
                    if d <= 1.0:
                        inside = True
                        depth = max(depth, 1.0 - d)
            if not inside:
                row.append((0, 0, 0, 0))
                continue
            shade = (1 - contrast) + contrast * (0.45 + 0.55 * depth)
            px = tuple(min(255, int(c * shade)) for c in base)
            row.append((px[0], px[1], px[2], 255))
        rows.append(row)

    # eyes, so the thing reads as a creature and legibility becomes judgeable
    eye_y = int(size * 0.36)
    for dx in (int(size * 0.30), int(size * 0.70)):
        for yy in range(max(0, eye_y - size // 14), min(size, eye_y + size // 14 + 1)):
            for xx in range(max(0, dx - size // 14), min(size, dx + size // 14 + 1)):
                if rows[yy][xx][3]:
                    rows[yy][xx] = (18, 16, 20, 255)
    return png_bytes(size, size, rows)


# ─────────────────────────────────────────────────────────────────────────────
# items
# ─────────────────────────────────────────────────────────────────────────────

SPRITE_PACKS = ["Vanilla Expanded – Insectoids", "Alpha Animals", "Megafauna",
                "Xenobiology Overhaul", "Cosmic Horrors", "Anima Bestiary"]
DEF_PACKS = ["Geological Landforms", "Vanilla Expanded – Biomes", "Map Designer",
             "Terrain Overhaul", "Tile Mutators Plus"]

CREATURE = ["Thrumbo", "Chitinid", "Vaultworm", "Sporeling", "Glasswing", "Mirestrider",
            "Duneback", "Hollow Ox", "Voidmoth", "Crystalback", "Ashcrawler", "Gloomcalf",
            "Riftling", "Boneshrike", "Pallid Hare", "Tunnelmaw", "Silt Eel", "Lumen Doe"]
SUFFIX = ["", " (juvenile)", " (alpha)", " drone", " queen", " nymph", " hulk", " runt"]

EFFECTS = [
    ("Halves plants, doubles junk, blocks siege raids", False),
    ("Triples animal density; no effect on terrain", False),
    ("Adds a river crossing; raids arrive from the south only", False),
    ("No mechanical effect — appearance only", False),
    ("Removes all trees; +30% mineral nodes", False),
    ("Blocks drop pods over 40% of the tile", False),
    ("Halves growing period, adds geothermal vents", False),
    ("Spawns 2–4 ancient structures; doubles mech clusters", False),
    ("Reduces raid pathing options to two chokepoints", False),
    ("Probably raises ambient temperature", True),
    ("Likely adds swamp terrain — fields are empty, judging by the name", True),
    ("Presumably cosmetic; no fields set", True),
]
FEATURE = ["Headwater", "Oxbow", "Caldera", "Karst Sink", "Basalt Flats", "Mesa Rim",
           "Tidal Shelf", "Glacial Moraine", "Salt Pan", "Fumarole Field", "Sea Arch",
           "Dry Wash", "Cinder Cone", "Talus Slope", "Estuary", "Butte", "Sinkhole"]


def build() -> tuple[list[dict], dict]:
    items: list[dict] = []
    os.makedirs(SPRITES, exist_ok=True)
    for old in os.listdir(SPRITES):
        if old.endswith(".png"):
            os.unlink(os.path.join(SPRITES, old))

    # ── sprites: judged by eye
    for n in range(200):
        size = RNG.choice([16, 20, 24, 32, 32, 40, 48, 64, 64, 96])
        contrast = round(RNG.uniform(0.10, 0.95), 2)
        sat = round(RNG.uniform(0.15, 1.0), 2)
        fill = round(RNG.uniform(0.55, 1.35), 2)
        name = RNG.choice(CREATURE) + RNG.choice(SUFFIX)
        ident = f"sprite_{n:03d}"
        with open(os.path.join(SPRITES, ident + ".png"), "wb") as fh:
            fh.write(make_sprite(size, contrast, sat, fill, seed=n * 7919))

        # The measurable score: resolution, contrast, saturation. It ranks QUALITY.
        score = (size * size) * (0.35 + contrast) * (0.5 + sat * 0.5)
        prefill = "keep" if score > 2600 else ("redraw" if score > 900 else "cut")
        contested = 900 < score < 3400 and RNG.random() < 0.12
        items.append({
            "id": ident, "label": name, "group": RNG.choice(SPRITE_PACKS),
            "thumb": f"sprites/{ident}.png",
            "effect": f"{size}×{size} px · contrast {contrast:.2f} · saturation {sat:.2f}"
                      f" · fill {fill:.2f} — measured score {score:,.0f}",
            "meta": {"px": f"{size}×{size}"},
            "prefill": prefill, "contested": contested,
        })

    # ── text defs: judged by their consequence line
    for n in range(200):
        effect, inferred = RNG.choice(EFFECTS)
        occurs = RNG.random() < 0.34            # only a third actually appear in the world
        label = f"{RNG.choice(FEATURE)} {RNG.choice(['', 'Minor ', 'Major ', 'Ancient '])}".strip()
        ident = f"mutator_{n:03d}"
        prefill = "keep" if (occurs and "No mechanical effect" not in effect) else "cut"
        items.append({
            "id": ident, "label": label, "group": RNG.choice(DEF_PACKS),
            "effect": effect,
            "occurs": occurs,
            "meta": {"tier": RNG.choice(["common", "uncommon", "rare"])},
            "prefill": prefill,
            "inferred": inferred,
            "contested": RNG.random() < 0.06,
        })

    RNG.shuffle(items)

    # A pre-fill file as a GENERATOR writes it: no savedBy, no writeCount — so a consumer
    # can tell these are guesses. Plus a key this sheet knows nothing about, which every
    # write must carry through verbatim.
    decisions = {
        "posture": "whitelist",
        "criterion": "sprite resolution x contrast x saturation — which ranks quality, not worth",
        "generatedBy": "make_demo.py",
        "someOtherToolsKey": {"do not": "lose me"},
        "decisions": {it["id"]: {"decision": it["prefill"], "prefill": it["prefill"], "note": ""}
                      for it in items},
    }
    return items, decisions


CONFIG = {
    "sheetId": "demo_review",
    "title": "Creature sprites + tile mutators",
    "subtitle": "400 rows · worked example",
    "briefHtml": """
      <p><b>The brief.</b> Cut this stack down to what belongs in a serious, grounded
      playthrough. Sprites must read clearly at 1&times; on a dark tile; defs must have a
      mechanical consequence worth the load order slot.</p>
      <p>Every row is <b>already decided</b>. Your job is to <b>disagree</b> — and when you
      do, say why in the note, because that is the only place the sheet learns something it
      could not compute.</p>""",
    "criterion": "sprite resolution × contrast × saturation — which ranks quality, not worth",
    "invented": [
        "I assumed 'serious tone' rules out anything recognisably terrestrial. Nobody asked for that.",
        "I treated a 16×16 sprite as automatically cut. A distinctive silhouette might survive at that size.",
        "I scored legibility as contrast. Legibility is not contrast, and I could not measure the real thing.",
    ],
    "posture": {"mode": "whitelist",
                "explain": "Default is EXCLUDE. Anything not marked Keep will be stripped from the build, "
                           "including rows left undecided."},
    "options": [
        {"key": "keep",   "label": "Keep",   "hotkey": "1", "color": "#5ac37f", "counts": "in"},
        {"key": "redraw", "label": "Redraw", "hotkey": "2", "color": "#e8b64c", "counts": "in"},
        {"key": "cut",    "label": "Cut",    "hotkey": "3", "color": "#e06c6c", "counts": "out"},
    ],
    "groupLabel": "pack",
    "media": True,
    "decisionsFile": "decisions.json",
}


def main() -> int:
    # §7: the generator that produced the GUESSES must refuse to run once a human has
    # reviewed. The tell is a key only the sidecar writes — a pre-fill cannot forge it.
    # A comment saying "do not run this" is not a guard; this is.
    dpath = os.path.join(HERE, "decisions.json")
    if os.path.exists(dpath) and "--i-know-this-overwrites-the-owners-decisions" not in sys.argv:
        try:
            with open(dpath, "r", encoding="utf-8") as fh:
                existing = json.load(fh)
        except (OSError, json.JSONDecodeError):
            existing = {}
        if existing.get("savedBy"):
            print(f"REFUSING to run: {dpath} was written by the sheet "
                  f"({existing.get('savedAt')}, {existing.get('writeCount')} writes, "
                  f"{existing.get('decidedCount')} decided).\n"
                  f"Re-running would replace a human's decisions with this script's guesses.\n"
                  f"Pass --i-know-this-overwrites-the-owners-decisions if you truly mean it.",
                  file=sys.stderr)
            return 3
        if existing.get("frozen"):
            print(f"REFUSING to run: {dpath} is FROZEN.", file=sys.stderr)
            return 3

    items, decisions = build()

    with open(TEMPLATE, "r", encoding="utf-8") as fh:
        html = fh.read()

    # A generator fills in exactly two blocks. Anything else it edits is chrome it should
    # not be touching — which is why check_sheet.py exists.
    def swap(doc: str, tag_id: str, payload: str) -> str:
        start = doc.index(f'<script id="{tag_id}" type="application/json">')
        start = doc.index(">", start) + 1
        end = doc.index("</script>", start)
        return doc[:start] + "\n" + payload + "\n" + doc[end:]

    cfg = dict(CONFIG)
    cfg["decisionsPath"] = os.path.join(HERE, "decisions.json")
    cfg["sheetPath"] = os.path.join(HERE, "sheet.html")
    html = swap(html, "CONFIG", json.dumps(cfg, indent=2))
    html = swap(html, "ITEMS", json.dumps(items, indent=1))

    out = os.path.join(HERE, "sheet.html")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)
    # Regenerating the SHEET is always safe — it reads the decisions file. Only the
    # decision generator is locked, which is why the guard above is on this write.
    with open(dpath, "w", encoding="utf-8") as fh:
        json.dump(decisions, fh, indent=2)

    sprites = len([i for i in items if i.get("thumb")])
    print(f"  sheet      {out}  ({len(html) / 1024:.0f} KB)")
    print(f"  decisions  {dpath}  ({len(decisions['decisions'])} pre-filled)")
    print(f"  sprites    {SPRITES}  ({sprites} PNGs)")
    print(f"  rows       {len(items)}  ·  {sprites} sprite · {len(items) - sprites} text")
    print(f"\n  ../assets/serve_sheet.py --sheet {os.path.relpath(out)} "
          f"--decisions {os.path.relpath(dpath)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
