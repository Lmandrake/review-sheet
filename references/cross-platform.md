# Cross-platform — macOS, and WSL with the browser on Windows

Read this before printing a path, binding a port, or launching a browser. These sheets get
reviewed on both, and the WSL case breaks in ways that look like the sheet is fine.

**The trap in one sentence: on WSL the tooling runs in Linux and the human's browser is a Windows
process, so anything you hand across that boundary needs translating.**

`assets/serve_sheet.py --selftest` verifies all of it on the machine it runs on. Run it on WSL;
the macOS half is already measured (26/26), and the interesting failures live over there.

---

## 1. Paths shown to the human must be Windows paths

A pathbar reading `/mnt/d/Luke/dev/review-sheets/decisions.json` is a path the Windows file picker
cannot open. Translate with `wslpath -w`, and keep a pure-logic fallback for when it is missing:

| POSIX (what the tool sees) | Windows (what the browser needs) |
|---|---|
| `/mnt/d/Luke/dev/x/decisions.json` | `D:\Luke\dev\x\decisions.json` |
| `/home/luke/proj/decisions.json` | `\\wsl.localhost\Ubuntu\home\luke\proj\decisions.json` |

⚠️ **The second row is the one people miss.** A project inside the distro's own filesystem still
needs a UNC path; printing the POSIX path there is just as broken as printing `/mnt/d/...`, and
quieter, because it looks like a plausible path.

The path translation is pure logic, so `--selftest` asserts it on **every** platform, not just on
WSL. A check that only runs where you cannot run it is not a check.

## 2. Binding: use `0.0.0.0` on WSL, and let the token do the securing

WSL2 forwards `localhost` from Windows into the distro, so a server in WSL is reachable at
`http://localhost:PORT` from the Windows browser. But services bound **only** to `127.0.0.1` have
historically been unreliable through that relay, depending on Windows build and networking mode
(NAT vs mirrored).

⇒ On WSL, bind `0.0.0.0`, and gate every request on a per-session token carried in the URL and
then a cookie. **The token, not the interface, is what keeps anything else on the network out of
the human's decisions.** On macOS, bind `127.0.0.1` and keep the token anyway — it costs nothing.

Print both URLs and say which is which. Pick the port by binding `0`, so nothing collides with
Windows' Hyper-V reserved port ranges.

## 3. Launching the browser

| Platform | What works |
|---|---|
| WSL | `wslview`, then `explorer.exe <url>`, then `powershell.exe Start-Process`, then `cmd.exe /c start` |
| macOS | `open <url>` |
| Linux | `xdg-open <url>` |

Try them in order and **fall back to printing the URL** rather than failing. `xdg-open` on WSL
does not reach the Windows browser, which is the mistake that makes a sidecar look broken.

## 4. 🔴 `os.replace` is not reliably atomic on `/mnt/` (DrvFs)

The standard safe-write recipe — write a temp file, `fsync`, `os.replace` over the target — is
atomic on APFS and ext4. On a WSL `/mnt/c` or `/mnt/d` path it raises `PermissionError` when a
Windows process holds the target open: an editor with the JSON loaded, a syncing client, or
antivirus mid-scan.

⇒ **Retry with backoff, then downgrade — but copy a `.bak` first.** An in-place write that dies
halfway is the one way to truncate the human's decisions, which is precisely the outcome the
atomic write was protecting against. Report which path was taken so the page can say so.

## 5. Detect external change by hash, not mtime

DrvFs mtime granularity is too coarse to trust, and the `/mnt/` filesystems cache aggressively. If
you need to know whether the file changed under you, hash the contents. The sidecar re-reads and
re-hashes before every write, which is cheap at these file sizes and correct on both platforms.

## 6. Line buffering, when the sidecar is backgrounded

Python block-buffers stdout when it is a pipe, so `serve_sheet.py > log &` prints **nothing** —
including the URL and the token, which are the entire point of the banner. Call
`sys.stdout.reconfigure(line_buffering=True)`. Measured: without it, an empty log file and a
server that is running fine but unreachable because nobody knows the token.

## 7. Things that are the same on both, and worth not re-testing

Measured Chrome, macOS, 2026-08-31 — on a `file://` page: `isSecureContext` is `true`, all three
file pickers exist, IndexedDB works with a ~10GB quota, `navigator.clipboard.writeText` succeeds,
and `DataTransferItem.getAsFileSystemHandle` exists. `content-visibility: auto` and
`contain-intrinsic-size` are both supported.

⚠️ And the one that is the same on both and is a hazard on both: **every `file://` page shares one
storage origin.** See `references/persistence.md` — it is the reason storage keys must be
namespaced per sheet regardless of platform.
