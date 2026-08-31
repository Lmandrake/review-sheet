#!/usr/bin/env python3
"""serve_sheet.py — the sidecar that owns a review sheet's decisions file.

Why a server at all, when the File System Access API exists? Because moving the
write out of the page relocates four of this skill's hardest-won rules from
"the agent must remember" to "the plumbing enforces":

  * merge per row, never all-or-nothing   -> the server merges per key
  * carry unknown top-level keys through  -> the server reads, merges, re-emits
  * refuse a truncating write             -> the server returns 409
  * stamp a key only the page could write -> the SERVER stamps it, so a
                                             pre-fill generator physically
                                             cannot forge it

It also deletes the picker dance: no showSaveFilePicker, no path to paste, no
permission to re-grant after a browser restart, and it works in Firefox and
Safari, which the File System Access API does not.

Runs on macOS and on WSL with the browser over on Windows. Stdlib only, because
a review sheet is often opened on a machine where you cannot pip install.

    ./serve_sheet.py --sheet demo/sheet.html --decisions demo/decisions.json
    ./serve_sheet.py --decisions demo/decisions.json --status
    ./serve_sheet.py --selftest

WSL notes, which are the whole reason this file is more than 50 lines:
  * The browser is a Windows process, so every path shown to the human must be
    a Windows path. `wslpath -w` does that; printing /mnt/d/... gives them a
    path Windows cannot open.
  * WSL2's localhost relay has been unreliable for services bound only to
    127.0.0.1, so on WSL we bind 0.0.0.0 and gate every request on a
    per-session token instead of relying on the interface for safety.
  * os.replace() on a /mnt/ DrvFs path fails when a Windows process holds the
    file open (editor, antivirus). It gets retried, then falls back to an
    in-place write that keeps a .bak, because losing the human's decisions to
    an unlucky rename is the one outcome worse than a non-atomic write.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

STAMP_BY = "review-sheet-sidecar"
MAX_BODY = 64 * 1024 * 1024


# ─────────────────────────────────────────────────────────────────────────────
# platform: the parts that differ between macOS and WSL-with-a-Windows-browser
# ─────────────────────────────────────────────────────────────────────────────

def is_wsl() -> bool:
    if os.environ.get("SHEET_FAKE_WSL") == "1":       # so the WSL paths are testable off-WSL
        return True
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    try:
        with open("/proc/version", "r", encoding="utf-8", errors="replace") as fh:
            return "microsoft" in fh.read().lower()
    except OSError:
        return False


def native_path(path: str) -> str:
    """The path as the HUMAN's browser sees it.

    On WSL the browser is a Windows process: /mnt/d/x is meaningless to it and
    D:\\x is what belongs in the pathbar. Falls back to the POSIX path rather
    than failing, since a slightly wrong label beats no sheet.
    """
    abspath = os.path.abspath(path)
    if not is_wsl():
        return abspath
    try:
        out = subprocess.run(["wslpath", "-w", abspath], capture_output=True,
                             timeout=5, check=True).stdout.decode().strip()
        return out or abspath
    except (OSError, subprocess.SubprocessError):
        return wsl_to_windows(abspath)


def wsl_to_windows(abspath: str) -> str:
    """Translate without wslpath. Pure logic, so it is testable off WSL.

    Two cases matter. A project on a Windows drive (/mnt/d/...) becomes D:\\...,
    and a project inside the distro's own filesystem (/home/...) becomes a
    \\\\wsl.localhost\\<distro>\\... UNC path — which Windows can open, and which
    the naive answer (printing the POSIX path) cannot.
    """
    m = re.match(r"^/mnt/([a-zA-Z])(/.*)?$", abspath)
    if m:
        rest = (m.group(2) or "/").replace("/", "\\")
        return f"{m.group(1).upper()}:{rest}"
    distro = os.environ.get("WSL_DISTRO_NAME")
    if distro:
        return f"\\\\wsl.localhost\\{distro}" + abspath.replace("/", "\\")
    return abspath


def default_host() -> str:
    # See module docstring: 127.0.0.1 has been unreliable through WSL2's relay.
    return "0.0.0.0" if is_wsl() else "127.0.0.1"


def open_browser(url: str) -> str:
    """Best effort. Returns the launcher used, or '' if the human must click."""
    if is_wsl():
        for cmd in (["wslview", url],
                    ["explorer.exe", url],
                    ["powershell.exe", "-NoProfile", "-Command", f"Start-Process '{url}'"],
                    ["cmd.exe", "/c", "start", "", url]):
            try:
                subprocess.run(cmd, timeout=10, check=False,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return cmd[0]
            except (OSError, subprocess.SubprocessError):
                continue
        return ""
    launcher = "open" if platform.system() == "Darwin" else "xdg-open"
    try:
        subprocess.run([launcher, url], timeout=10, check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return launcher
    except (OSError, subprocess.SubprocessError):
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# the decisions file — one class, because every rule about it lives together
# ─────────────────────────────────────────────────────────────────────────────

class DecisionsFile:
    """Owns the JSON on disk. Every write goes through write_ops()."""

    def __init__(self, path: str):
        self.path = os.path.abspath(path)
        self.lock = threading.Lock()
        self.rev = 0
        self._last_hash = ""

    # ---- reading

    def read(self) -> dict:
        try:
            with open(self.path, "rb") as fh:
                raw = fh.read()
        except FileNotFoundError:
            return {}
        except OSError as exc:
            raise RuntimeError(f"cannot read {self.path}: {exc}") from exc
        self._last_hash = hashlib.sha256(raw).hexdigest()
        if not raw.strip():
            return {}
        try:
            doc = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            # Refuse rather than overwrite something we failed to understand.
            raise RuntimeError(
                f"{self.path} is not valid JSON ({exc}). Refusing to touch it — "
                f"fix or move the file, so a parse error cannot cost the human "
                f"their decisions.") from exc
        if not isinstance(doc, dict):
            raise RuntimeError(f"{self.path} must hold a JSON object, got {type(doc).__name__}")
        return doc

    def on_disk_hash(self) -> str:
        try:
            with open(self.path, "rb") as fh:
                return hashlib.sha256(fh.read()).hexdigest()
        except OSError:
            return ""

    # ---- writing

    def write_ops(self, ops: dict, force: bool = False) -> dict:
        """Merge `ops` into doc["decisions"] and persist.

        ops is {itemId: decisionObject|None}. Only the mentioned keys are
        touched, so a client bug cannot empty the file — the failure mode that
        section 6 of the skill was written about.
        """
        if not isinstance(ops, dict):
            raise ValueError("ops must be an object of {itemId: decision}")

        with self.lock:
            doc = self.read()                       # always re-read: another tab
            external = bool(self._last_hash and self._last_hash != getattr(self, "_ours", ""))
            if doc.get("frozen") is True:
                raise Frozen(doc.get("frozenOn"), doc.get("frozenMeaning"))

            decisions = doc.get("decisions")
            if not isinstance(decisions, dict):
                decisions = {}

            before_decided = sum(1 for v in decisions.values() if _is_decided(v))

            # Truncation guard. Ops cannot empty the file wholesale, but a
            # client bug could still clear a swathe of rows in one batch.
            clearing = sum(1 for k, v in ops.items()
                           if not _is_decided(v) and _is_decided(decisions.get(k)))
            limit = max(10, int(before_decided * 0.2))
            if not force and before_decided >= 20 and clearing > limit:
                raise Truncating(clearing, before_decided, limit)

            for key, value in ops.items():
                if value is None:
                    decisions.pop(key, None)
                else:
                    decisions[key] = value

            after_decided = sum(1 for v in decisions.values() if _is_decided(v))

            doc["decisions"] = decisions
            # Provenance. A pre-fill generator must never emit these keys; a
            # consumer that cannot find them is looking at guesses, not
            # decisions. The server stamps them so the page cannot forget to.
            doc["savedBy"] = STAMP_BY
            doc["savedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            doc["writeCount"] = int(doc.get("writeCount") or 0) + 1
            doc["decidedCount"] = after_decided

            payload = (json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
            how = _durable_write(self.path, payload)
            self._ours = hashlib.sha256(payload).hexdigest()
            self._last_hash = self._ours
            self.rev += 1

            return {
                "ok": True, "rev": self.rev, "writeCount": doc["writeCount"],
                "savedAt": doc["savedAt"], "decidedCount": after_decided,
                "applied": len(ops), "externalChange": external, "writeMode": how,
            }


class Frozen(Exception):
    def __init__(self, on=None, meaning=None):
        super().__init__("decisions file is frozen")
        self.on, self.meaning = on, meaning


class Truncating(Exception):
    def __init__(self, clearing, before, limit):
        super().__init__("refusing a write that clears too many decided rows")
        self.clearing, self.before, self.limit = clearing, before, limit


def _is_decided(value) -> bool:
    if not isinstance(value, dict):
        return bool(value)
    d = value.get("decision")
    return d is not None and d != "" and d != "undecided"


def _durable_write(path: str, payload: bytes) -> str:
    """Atomic where the filesystem allows it; never lossy where it does not.

    os.replace() is atomic on APFS and on ext4. On a WSL /mnt/ DrvFs path it
    raises PermissionError when a Windows process holds the target open, so it
    is retried, and only then downgraded to an in-place write that keeps a .bak.
    Returns which path was taken, so the page can say so out loud.
    """
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)

    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".sheet-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        last: Exception | None = None
        for attempt in range(5):
            try:
                os.replace(tmp, path)
                return "atomic" if attempt == 0 else f"atomic-retry-{attempt}"
            except OSError as exc:                    # DrvFs: file held by Windows
                last = exc
                time.sleep(0.1 * (attempt + 1))
        # Fall back rather than lose the write. Keep a .bak first: an in-place
        # write that dies halfway is the one way to truncate the human's file.
        try:
            if os.path.exists(path):
                shutil.copy2(path, path + ".bak")
        except OSError:
            pass
        with open(path, "wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        return f"in-place (os.replace failed: {type(last).__name__})"
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def status_of(store: DecisionsFile, sheet: str | None = None) -> dict:
    """What a shell can ask instead of asking the human whether they saved."""
    try:
        doc = store.read()
    except RuntimeError as exc:
        return {"file": native_path(store.path), "error": str(exc)}
    decisions = doc.get("decisions") if isinstance(doc.get("decisions"), dict) else {}
    decided = [v for v in decisions.values() if _is_decided(v)]
    overrides = [v for v in decisions.values()
                 if isinstance(v, dict) and v.get("prefill") not in (None, "")
                 and v.get("decision") != v.get("prefill")]
    noted = [v for v in decisions.values()
             if isinstance(v, dict) and str(v.get("note") or "").strip()]
    return {
        "file": native_path(store.path),
        "posixFile": store.path,
        "exists": os.path.exists(store.path),
        "sheet": native_path(sheet) if sheet else None,
        # savedBy/writeCount are the unforgeable part: absent means the human's
        # session never reached disk, whatever they said in chat.
        "touchedBySheet": doc.get("savedBy") == STAMP_BY,
        "savedBy": doc.get("savedBy"),
        "savedAt": doc.get("savedAt"),
        "writeCount": doc.get("writeCount"),
        "rows": len(decisions),
        "decided": len(decided),
        "undecided": len(decisions) - len(decided),
        "overrides": len(overrides),
        "notes": len(noted),
        "frozen": doc.get("frozen") is True,
        "unknownTopLevelKeys": sorted(k for k in doc
                                      if k not in {"decisions", "savedBy", "savedAt",
                                                   "writeCount", "decidedCount"}),
    }


# ─────────────────────────────────────────────────────────────────────────────
# HTTP
# ─────────────────────────────────────────────────────────────────────────────

class Ctx:
    sheet = ""
    root = ""
    store: DecisionsFile
    token = ""
    quiet = False


def _guess_type(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return {".html": "text/html; charset=utf-8", ".htm": "text/html; charset=utf-8",
            ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
            ".json": "application/json; charset=utf-8", ".png": "image/png",
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
            ".svg": "image/svg+xml", ".webp": "image/webp", ".ico": "image/x-icon",
            ".woff2": "font/woff2", ".txt": "text/plain; charset=utf-8"}.get(ext, "application/octet-stream")


def inject_sidecar(html: bytes, cfg: dict) -> bytes:
    """Hand the page its runtime config without the page needing a placeholder.

    Any sheet works, template or not — which matters because the fallback flow
    (open the .html straight off disk) must keep working when nobody runs this.
    """
    tag = ("<script>window.__SIDECAR__=" + json.dumps(cfg) + ";</script>").encode("utf-8")
    lowered = html.lower()
    for marker in (b"</head>", b"<body>", b"<html>"):
        idx = lowered.find(marker)
        if idx != -1:
            at = idx if marker == b"</head>" else idx + len(marker)
            return html[:at] + tag + html[at:]
    return tag + html


class Handler(BaseHTTPRequestHandler):
    server_version = "review-sheet-sidecar/1.0"
    protocol_version = "HTTP/1.1"

    # ---- plumbing

    def log_message(self, fmt, *args):
        if not Ctx.quiet:
            sys.stderr.write("  %s\n" % (fmt % args))

    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code: int, obj: dict, extra: dict | None = None):
        self._send(code, (json.dumps(obj) + "\n").encode("utf-8"),
                   "application/json; charset=utf-8", extra)

    def _authed(self, query: dict) -> bool:
        """Token via query, header or cookie.

        On WSL we are bound to 0.0.0.0 because the loopback relay cannot be
        relied on, so the token — not the interface — is what keeps anything
        else on the network out of the human's decisions.
        """
        if not Ctx.token:
            return True
        supplied = (query.get("t", [None])[0]
                    or self.headers.get("X-Sheet-Token")
                    or _cookie(self.headers.get("Cookie", "")).get("sheet_token"))
        return bool(supplied) and secrets.compare_digest(str(supplied), Ctx.token)

    # ---- routes

    def do_GET(self):        # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        path = unquote(parsed.path)

        if not self._authed(query):
            return self._send(403, b"Bad or missing session token. Use the URL this "
                                   b"server printed; it carries ?t=<token>.\n",
                              "text/plain; charset=utf-8")

        cookie = {}
        if query.get("t"):
            cookie = {"Set-Cookie": f"sheet_token={Ctx.token}; Path=/; SameSite=Strict"}

        if path in ("/", "/index.html", "/sheet.html"):
            try:
                with open(Ctx.sheet, "rb") as fh:
                    html = fh.read()
            except OSError as exc:
                return self._send(500, f"cannot read sheet: {exc}\n".encode(),
                                  "text/plain; charset=utf-8")
            cfg = {
                "mode": "server",
                "token": Ctx.token,
                "decisionsPath": native_path(Ctx.store.path),
                "sheetPath": native_path(Ctx.sheet),
                "platform": "wsl" if is_wsl() else platform.system().lower(),
                "endpoints": {"get": "/decisions", "post": "/decisions", "status": "/status"},
            }
            return self._send(200, inject_sidecar(html, cfg), "text/html; charset=utf-8", cookie)

        if path == "/decisions":
            try:
                doc = Ctx.store.read()
            except RuntimeError as exc:
                return self._json(500, {"error": str(exc)}, cookie)
            doc["_rev"] = Ctx.store.rev
            return self._json(200, doc, cookie)

        if path == "/status":
            return self._json(200, status_of(Ctx.store, Ctx.sheet), cookie)

        if path == "/favicon.ico":
            # A 404 here puts a red error in the console of an otherwise healthy sheet,
            # and a human who opens devtools then distrusts the whole page.
            return self._send(204, b"", "image/x-icon")

        return self._static(path, cookie)

    def do_HEAD(self):       # noqa: N802
        self.do_GET()

    def do_POST(self):       # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if not self._authed(query):
            return self._json(403, {"error": "bad or missing session token"})
        if unquote(parsed.path) != "/decisions":
            return self._json(404, {"error": "no such endpoint"})

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._json(400, {"error": "bad Content-Length"})
        if length <= 0 or length > MAX_BODY:
            return self._json(400, {"error": "empty or oversized body"})

        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return self._json(400, {"error": f"bad JSON: {exc}"})
        if not isinstance(body, dict) or not isinstance(body.get("ops"), dict):
            return self._json(400, {"error": 'expected {"ops": {itemId: decision}}'})

        force = bool(body.get("force")) or query.get("force", ["0"])[0] == "1"
        try:
            return self._json(200, Ctx.store.write_ops(body["ops"], force=force))
        except Frozen as exc:
            return self._json(423, {"error": "frozen", "frozenOn": exc.on,
                                    "frozenMeaning": exc.meaning,
                                    "hint": "the decisions file is frozen; the sheet is read-only"})
        except Truncating as exc:
            return self._json(409, {"error": "truncating-write", "clearing": exc.clearing,
                                    "wasDecided": exc.before, "limit": exc.limit,
                                    "hint": "refused: this batch clears an implausible number of "
                                            "decided rows. Re-send with force:true only if you "
                                            "meant it."})
        except (ValueError, RuntimeError, OSError) as exc:
            return self._json(500, {"error": str(exc)})

    def _static(self, path: str, extra: dict):
        rel = path.lstrip("/")
        target = os.path.abspath(os.path.join(Ctx.root, rel))
        if not (target == Ctx.root or target.startswith(Ctx.root + os.sep)):
            return self._send(403, b"outside the sheet's directory\n", "text/plain; charset=utf-8")
        if not os.path.isfile(target):
            return self._send(404, b"not found\n", "text/plain; charset=utf-8")
        try:
            with open(target, "rb") as fh:
                return self._send(200, fh.read(), _guess_type(target), extra)
        except OSError as exc:
            return self._send(500, f"{exc}\n".encode(), "text/plain; charset=utf-8")


def _cookie(raw: str) -> dict:
    out = {}
    for part in raw.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


# ─────────────────────────────────────────────────────────────────────────────
# selftest — run this on WSL, because I could only measure the macOS half
# ─────────────────────────────────────────────────────────────────────────────

def selftest() -> int:
    import urllib.error
    import urllib.request

    results: list[tuple[bool, str]] = []

    def check(ok: bool, label: str, detail: str = ""):
        results.append((bool(ok), label + (f" — {detail}" if detail else "")))

    tmp = tempfile.mkdtemp(prefix="sheet-selftest-")
    dpath = os.path.join(tmp, "decisions.json")
    spath = os.path.join(tmp, "sheet.html")
    with open(spath, "w", encoding="utf-8") as fh:
        fh.write("<html><head><title>t</title></head><body>sheet</body></html>")

    check(True, f"platform: {'WSL' if is_wsl() else platform.system()}")

    # Path translation is pure logic, so assert it on EVERY platform. A sheet
    # served from WSL is read by a browser on Windows, and a pathbar showing
    # /mnt/d/... is a path that browser cannot open.
    os.environ.setdefault("WSL_DISTRO_NAME", "Ubuntu") if is_wsl() else None
    cases = [("/mnt/d/Luke/dev/review-sheets/decisions.json", r"D:\Luke\dev\review-sheets\decisions.json"),
             ("/mnt/c/Users/x/a b/c.json", r"C:\Users\x\a b\c.json")]
    for posix, expected in cases:
        got = wsl_to_windows(posix)
        check(got == expected, f"wsl_to_windows({posix})", got)
    distro_case = wsl_to_windows("/home/luke/proj/decisions.json")
    check(distro_case.startswith("\\\\wsl.localhost\\") or not os.environ.get("WSL_DISTRO_NAME"),
          "a path inside the distro becomes a UNC path Windows can open", distro_case)

    nat = native_path(dpath)
    if is_wsl():
        check("\\" in nat, "native_path hands the browser a Windows path", nat)
    else:
        check(nat == os.path.abspath(dpath), "native_path is the POSIX path off WSL", nat)

    # a pre-fill written by a generator: no provenance keys, plus a key the
    # sheet knows nothing about, which must survive every write
    seed = {"posture": "whitelist", "criterion": "resolution, which ranks quality not worth",
            "someOtherToolsKey": {"keep": "me"},
            "decisions": {f"i{n}": {"decision": "keep", "prefill": "keep"} for n in range(40)}}
    with open(dpath, "w", encoding="utf-8") as fh:
        json.dump(seed, fh, indent=2)

    store = DecisionsFile(dpath)
    st = status_of(store)
    check(st["touchedBySheet"] is False, "a fresh pre-fill is correctly reported as NOT reviewed")
    check(st["decided"] == 40, "counts read back", f"decided={st['decided']}")

    res = store.write_ops({"i0": {"decision": "cut", "prefill": "keep", "note": "terrestrial"}})
    doc = store.read()
    check(res["ok"] and doc["decisions"]["i0"]["decision"] == "cut", "op applied")
    check(doc.get("someOtherToolsKey") == {"keep": "me"},
          "unknown top-level key survived the write")
    check(len(doc["decisions"]) == 40, "merge touched only the named row",
          f"rows={len(doc['decisions'])}")
    check(doc.get("savedBy") == STAMP_BY and doc.get("writeCount") == 1,
          "server stamped provenance", f"writeCount={doc.get('writeCount')}")
    check(status_of(store)["touchedBySheet"] is True, "status now reports a real review")
    check(status_of(store)["overrides"] == 1, "override detected against prefill")
    check(res["writeMode"].startswith("atomic") or res["writeMode"].startswith("in-place"),
          "write mode reported", res["writeMode"])

    try:
        store.write_ops({f"i{n}": {"decision": ""} for n in range(30)})
        check(False, "truncation guard refuses a mass clear")
    except Truncating as exc:
        check(True, "truncation guard refuses a mass clear",
              f"clearing={exc.clearing} limit={exc.limit}")
    check(len(store.read()["decisions"]) == 40, "file intact after the refusal")
    store.write_ops({f"i{n}": {"decision": ""} for n in range(30)}, force=True)
    check(status_of(store)["decided"] == 10, "force:true still allows a deliberate mass clear")

    doc = store.read(); doc["frozen"] = True
    with open(dpath, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
    try:
        store.write_ops({"i0": {"decision": "keep"}})
        check(False, "freeze locks the file against further writes")
    except Frozen:
        check(True, "freeze locks the file against further writes")
    doc = store.read(); del doc["frozen"]
    with open(dpath, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)

    # end to end over HTTP, including the token gate and the browser-visible path
    Ctx.sheet, Ctx.root, Ctx.store = spath, os.path.abspath(tmp), DecisionsFile(dpath)
    Ctx.token, Ctx.quiet = secrets.token_urlsafe(8), True
    httpd = ThreadingHTTPServer((default_host(), 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]
    base = f"http://127.0.0.1:{port}"
    try:
        try:
            urllib.request.urlopen(base + "/status", timeout=5)
            check(False, "an untokened request is refused")
        except urllib.error.HTTPError as exc:
            check(exc.code == 403, "an untokened request is refused", f"HTTP {exc.code}")

        with urllib.request.urlopen(f"{base}/?t={Ctx.token}", timeout=5) as r:
            html = r.read().decode()
        check("window.__SIDECAR__" in html, "sidecar config injected into the sheet")
        check('"mode": "server"' in html or '"mode":"server"' in html, "page is told it has a server")

        req = urllib.request.Request(
            f"{base}/decisions?t={Ctx.token}",
            data=json.dumps({"ops": {"i5": {"decision": "redraw", "prefill": "keep",
                                            "note": "so alien I want to honour it"}}}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            posted = json.loads(r.read())
        check(posted["ok"] and posted["applied"] == 1, "POST /decisions round-trips")
        check(store.read()["decisions"]["i5"]["decision"] == "redraw", "POST landed on disk")

        with urllib.request.urlopen(f"{base}/status?t={Ctx.token}", timeout=5) as r:
            st = json.loads(r.read())
        check(st["touchedBySheet"] and st["writeCount"] >= 1, "GET /status proves the write")
        check("someOtherToolsKey" in st["unknownTopLevelKeys"],
              "status names the keys this sheet does not own")

        try:
            urllib.request.urlopen(f"{base}/../../etc/passwd?t={Ctx.token}", timeout=5)
            check(False, "path traversal blocked")
        except urllib.error.HTTPError as exc:
            check(exc.code in (403, 404), "path traversal blocked", f"HTTP {exc.code}")
    finally:
        httpd.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    for ok, label in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    failed = [r for r in results if not r[0]]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed"
          + (f" — {len(failed)} FAILED" if failed else ""))
    if failed and is_wsl():
        print("\nOn WSL, a failure here is worth reporting: the Windows-path and DrvFs\n"
              "behaviours are the parts that cannot be measured from macOS.")
    return 1 if failed else 0


# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Serve a review sheet and own its decisions file.")
    ap.add_argument("--sheet", help="the generated .html to serve")
    ap.add_argument("--decisions", help="the decisions .json this sheet owns")
    ap.add_argument("--port", type=int, default=0, help="0 picks a free port (default)")
    ap.add_argument("--host", default=None, help="default: 127.0.0.1, or 0.0.0.0 on WSL")
    ap.add_argument("--no-token", action="store_true", help="disable the session token (not on WSL)")
    ap.add_argument("--no-open", action="store_true", help="do not launch a browser")
    ap.add_argument("--status", action="store_true", help="print the decisions file's status and exit")
    ap.add_argument("--selftest", action="store_true", help="verify this machine's behaviour and exit")
    args = ap.parse_args()

    # Line-buffer: the URL and the token are the whole point of the banner, and Python
    # block-buffers stdout when it is a pipe, so `serve_sheet.py > log &` otherwise shows
    # nothing at all until the process exits.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except (AttributeError, OSError):
        pass

    if args.selftest:
        return selftest()

    if not args.decisions:
        ap.error("--decisions is required")
    store = DecisionsFile(args.decisions)

    if args.status:
        print(json.dumps(status_of(store, args.sheet), indent=2))
        return 0

    if not args.sheet:
        ap.error("--sheet is required unless --status or --selftest")
    if not os.path.isfile(args.sheet):
        print(f"no such sheet: {args.sheet}", file=sys.stderr)
        return 2

    Ctx.sheet = os.path.abspath(args.sheet)
    Ctx.root = os.path.dirname(Ctx.sheet) or os.path.abspath(".")
    Ctx.store = store
    Ctx.token = "" if args.no_token else secrets.token_urlsafe(16)

    host = args.host or default_host()
    try:
        httpd = ThreadingHTTPServer((host, args.port), Handler)
    except OSError as exc:
        print(f"cannot bind {host}:{args.port} — {exc}", file=sys.stderr)
        return 2
    port = httpd.server_address[1]
    url = f"http://localhost:{port}/" + (f"?t={Ctx.token}" if Ctx.token else "")

    print(f"\n  sheet      {native_path(Ctx.sheet)}")
    print(f"  decisions  {native_path(store.path)}")
    st = status_of(store)
    print(f"             {st['rows']} rows · {st['decided']} decided · "
          f"{'reviewed' if st['touchedBySheet'] else 'NEVER reviewed (pre-fill only)'}"
          + (" · FROZEN" if st["frozen"] else ""))
    print(f"  serving    {url}")
    if is_wsl():
        print("             (WSL: bound 0.0.0.0 because the WSL2 loopback relay is unreliable;\n"
              "              the ?t= token is what gates writes. Windows browser uses localhost.)")
    print("  stop       Ctrl-C\n")

    if not args.no_open:
        used = open_browser(url)
        print(f"  opened with {used}\n" if used else "  could not launch a browser — open the URL above\n")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.shutdown()
        final = status_of(store)
        print(f"\n  wrote {final['writeCount'] or 0} time(s) · {final['decided']} decided · "
              f"{final['overrides']} overrides · {final['notes']} notes")
        if not final["touchedBySheet"]:
            print("  ⚠️  this file was never written by the sheet — it is still the pre-fill.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
