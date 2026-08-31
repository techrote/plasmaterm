# PlasmaTerm web-v0.101a

This directory is the bounded browser presentation of the frozen PlasmaTerm
`v0.1a` release. The page version is `web-v0.101a`; native configuration files
remain compatible. It runs the repository's Python renderer and
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

The page is a no-scroll workspace containing four independent faux-terminal
windows. PlasmaTerm begins at 900×560 on desktop; Keybed and Modulation begin
visible, and LUT begins docked. Windows may overlap, are brought forward when
used, and may be dragged by only the blank part of their compact title bars.
Their positions and stacking order last for the session rather than being
written to storage.

The approximately 24px title bars are blank and titleless, with centred 8px
lights and flush, square-edged fields and buttons. These lights are controls
rather than decoration. Keybed, Modulation, and LUT each have a yellow minimize
control; minimizing adds a labelled restore button to PlasmaTerm's title bar.
Restoring returns the window to its last position, clamps it to the viewport,
and brings it forward. PlasmaTerm's green control toggles between its last good
desktop geometry and a viewport-filling layout. On narrow/mobile layouts,
where PlasmaTerm already fills the viewport, green instead moves it between the
front and back of the stack. PlasmaTerm's red control, or `Esc` anywhere on the
page, restores the 900×560 desktop size, Pt 24, responsive starting positions,
and default stacking: Keybed and Modulation visible at the front, LUT docked.
This global reset changes layout and display scaling only, not the current
plasma or Energy values.

Hover PlasmaTerm to reveal its four centre-anchored resize handles. Their hit
areas sit fully outside the window border so they never cover the title-bar
controls. A resize pauses frame production, changes only the shell during the
drag, and performs one xterm fit and worker resize on release. The title bar
exposes three editable display controls:

- **Pt** changes xterm font size and therefore the rendered character
  resolution. Its presets are 12, 16, 24, 36, 46, and 64; direct entry accepts
  6–200, and the two jog buttons to its left step by one. The default is 24.
- **Bg** accepts a LUT-style `RRGGBB` value (an optional leading `#` is also
  accepted). Enter or focus loss applies it to the page and terminal
  background, Modulation highlights, and docked-window tabs with automatic
  contrasting text. This appearance setting resets on reload.
- **FPS** presets are 24, 30, 60, 120, 144, and 240; direct entry accepts
  1–1000. The default is 24, and the chosen value persists through presets,
  Randomize, and Randomize Undo.

The Keybed pairs `Q/A`, `W/S`, `T/G`, `Y/H`, `U/J`, `I/K`, and
Randomize/Undo in a compact two-row layout. Pointer press, hold, release,
cancellation, and physical keyboard input share one worker path and light the
same keycaps. `I/K` cycle stored LUTs with 0↔9 wrapping; `T/G` use a 0.03 base
speed step; and Randomize has a two-entry, session-only Undo stack.

The latching **+** and **++** controls replace Shift/Ctrl parameter scaling in
the web keybed. For speed and radius they apply 3× and 6×; for Y/X frequency
and hue shift they apply 1.5× and 3×. Both can be active, combining to 18× or
4.5× respectively. Keybed Reset releases held keys, clears both latches, and
returns those five parameters to the most recent startup, preset, Randomize,
or Randomize-Undo anchor while preserving LUT and FPS. It does not move the
window. Native PlasmaTerm retains its existing Shift 10× and Ctrl 100×
modifier behavior.

The compact **Modulation** window places its five parameter toggles vertically
at the far left, followed by a full-height dual-ended Width control and the
vertical Energy and Rate controls. Offset sits directly beneath Energy/Rate
with its label above it; the bottom row contains the prominent On/Off control
and the unlabeled waveform selector. Energy and Rate have editable values;
Rate's slider spans −3…+3 while its field accepts −6…+6. The waveform menu
provides sine, smoothed triangle, seamless loop noise, and deterministic wander
noise.

Energy remains transient and never rewrites the base configuration. Frequency
Y/X use 30% of their keybed fine step, hue shift uses a 0.005 step (half the
previous Energy sensitivity), radius uses 50%, and speed is unchanged. The
Modulation Reset button leaves the window in place and restores Off, Energy
25, Rate 1, Width −100…+100%, Offset 0, Sine, and Speed as the sole target.

Browser keyboard controls also include `0–9` for presets, `Ctrl+0–9` for direct
LUT loads, `Alt+S` to save, and bare `P` to regenerate the complete config bank
once per press. Physical `E/D` and `R/F` retain procedural hue-range
adjustments but are intentionally absent from the mouse keybed. `O/L` do not
change FPS.

## LUT editor

Restore **LUT** from PlasmaTerm's title bar to edit the active 256-colour
palette as `RRGGBB` fields. The grid is 16×16 on wide/landscape layouts and
8×32 in narrow portrait layouts. Every field uses its represented colour as
its background, automatically selects legible light or dark text, and follows
normal Tab order. A valid edit is committed and persisted as focus advances;
the visualization updates immediately. Editing a procedural palette first
materializes its 256-colour resampling into LUT slot 0.

To replace the complete LUT, focus the first field and paste exactly 256 valid
values. Commas or whitespace may separate values, and brackets, quotes, and an
optional leading `#` are accepted. The replacement is atomic: an invalid value
or count leaves the current LUT unchanged. **Export** copies uppercase values
as 32 lines of eight comma-and-space-separated entries, which can be pasted
back into the same first field. Manual LUT edits do not consume or create
Randomize undo history.

The LUT title bar also provides **Randomise** and a synchronized 0–100
**Scale** field/slider, defaulting to 25. Randomise builds a smooth cyclic
eight-anchor palette and blends the current LUT toward it by the selected
percentage: 0 leaves the LUT unchanged, 25 makes a restrained variation, and
100 replaces it with a fully new coherent palette. It uses the same atomic LUT
write path as manual editing and does not affect Randomize undo history.

The entire workspace stays at `100vw × 100dvh` with no document scrolling.
On narrow displays PlasmaTerm fills the viewport behind the floating windows;
portrait defaults stack them, while short landscape defaults place them side
by side. Overlap is allowed when space is limited. Pinch over the terminal to
change Pt and rendered resolution.

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

Performance depends on viewport and character size. The bounded desktop
default prevents rendering from automatically expanding to the entire browser
window; larger characters reduce the number of rendered cells. No backend, account, network
control, WebSocket, or external controller is included.

## Browser validation

On 2026-08-31 the Chromium-based Codex in-app browser passed startup, true-
colour rendering, all control families, Randomize, local persistence, focus
reset, centre-anchored zigzag resize recovery, draggable positioning, two-level
Undo, LUT cycling, signed/noise Energy modulation, and no-scroll responsive layouts.
The original performance pass tested cells from 61×21 through 141×43. Python sustained
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
