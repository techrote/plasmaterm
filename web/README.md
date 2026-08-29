# PlasmaTerm web-v0.1a

This directory is the experimental browser derivative of the frozen
PlasmaTerm `v0.1a` release. It runs the repository's Python renderer and
configuration generator in Pyodide, presents their ANSI output through
xterm.js, and intentionally does not include PlasmaTerm's later TCP control
architecture.

## Run locally

From the repository root, start any static HTTP server, then open
`http://localhost:8000/web/`:

```powershell
python -m http.server 8000
```

Publish the repository root unchanged to GitHub Pages or any static HTTP(S)
host, then link to `/web/`; the worker intentionally fetches the two shared
Python files from the repository root. Opening `index.html` via `file://` is
not supported.

## Controls

The v0.1a controls are unchanged: `0–9` loads presets, `Ctrl+0–9` loads LUTs,
`Alt+S` saves, and `Q/A` through `O/L` adjust parameters. `Shift` applies a
10× step and `Ctrl` a 100× step. Bare `P` regenerates the complete config bank
from a nondeterministically selected slot; it fires once per press.

Browser focus/visibility loss clears held state. The small generated config is
saved to `localStorage`, so presets, randomization, and parameter changes
normally survive a page reload on the same browser profile.

## Runtime and limitations

Tested dependency pins:

- Pyodide `0.28.2`
- xterm.js `6.0.0`
- xterm FitAddon `0.11.0`

Pyodide runs in a Web Worker. Complete ANSI frames are coalesced on the host so
at most one unpresented frame is retained; the default browser path omits DEC
2026 delimiters and performs one xterm write per presented frame. Add `?sync=1`
to compare xterm.js synchronized output. The default DOM renderer is used;
WebGL is intentionally not enabled for this unusually high-churn workload.

Performance depends on viewport size and device. No backend, account, network
control, WebSocket, or external controller is included.

## Browser validation

On 2026-08-29 the Chromium-based Codex in-app browser passed startup, true-
colour rendering, all control families, Randomize, local persistence, focus
reset, and resize testing from 61×21 through 141×43 cells. Python sustained
about 39.8 produced FPS. At 140×43, the bounded host presented roughly 14–16
FPS, coalesced obsolete worker frames, and accumulated no main-thread frame
queue. DEC 2026 and browser-side atomic writes performed similarly; the atomic
path remains the default because it is simpler and does not depend on continuous
synchronized-output support. Three random slots produced byte-for-byte identical
configuration SHA-256 hashes in native Python and Pyodide.

A 10-minute 15-second default-path run with controls, Randomize, and resizing
held 39.7 produced FPS, presented 17,458 frames, coalesced 6,947 obsolete worker
frames, and recorded zero main-thread queue drops or fresh browser errors. The
Chromium heap returned near its warmed baseline after normal collection cycles
(about +2.7 MB from start to finish), with no progressive slowdown or terminal
corruption observed.

Firefox was not available on the test host and remains an explicit validation
gap before declaring this a permanent cross-browser demo. Safari was not tested.
