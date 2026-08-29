# User guide

## Requirements and startup

This release is intended for Python 3 on Windows, running in Windows Terminal.
It has no third-party Python dependencies.

```powershell
python plasma.py
```

`plasma.py` looks for `plasma.conf` beside the script. If the file is missing,
it imports `generate_config()` from `plasma_config_gen.py`, creates a complete
configuration atomically, then loads it through the normal config path. An
existing config is never regenerated or replaced at startup.

The renderer enters the terminal's alternate screen, hides the cursor, and
restores both on `Ctrl+C` or normal cleanup.

## Controls

| Key | Action |
|---|---|
| `0`–`9` | Load the corresponding full preset immediately |
| `Alt+S` | Save exact current values to the last selected preset; slot 0 initially |
| `Ctrl+0`–`Ctrl+9` | Load the corresponding stored LUT immediately |
| `Q` / `A` | Increase / decrease vertical frequency |
| `W` / `S` | Increase / decrease horizontal frequency |
| `E` / `D` | Increase / decrease procedural hue start |
| `R` / `F` | Increase / decrease procedural hue end |
| `T` / `G` | Increase / decrease animation speed |
| `Y` / `H` | Increase / decrease palette phase speed |
| `U` / `J` | Increase / decrease radial frequency |
| `I` / `K` | Increase / decrease procedural palette size |
| `O` / `L` | Increase / decrease FPS limit |

Adjustment modifiers:

- No modifier: fine step.
- `Shift`: 10× step.
- `Ctrl`: 100× step.
- Holding an adjustment key repeats after a short delay.

Each successful adjustment or load updates `[config]` in `plasma.conf` using an
atomic file replacement. Preset saves update only the selected preset section.

## Palette modes

`active-lut` determines where displayed colours come from:

- `none`: build a procedural palette from `palette-size`, `hue-start`, and
  `hue-end`.
- `0`–`9`: use the corresponding fixed 256-colour `[lut-N]` section.

Consequently, the `E/D`, `R/F`, and `I/K` controls do not visibly change a
stored LUT. Set `active-lut = none` before using those controls to shape the
procedural palette. `hue-shift` remains active in either mode because it moves
the lookup phase through whichever palette is selected.

## Keyboard ownership

Commands are accepted only while the PlasmaTerm terminal document is focused
and the viewport owns keyboard input. Alt-Tab, a Windows Terminal tab change,
or a future UI owner revokes dispatch and clears held/repeat state. Returning
focus starts from neutral input: a fresh key press is required.

Keyboard polling is Windows-specific in this release. The ANSI renderer may be
portable to other terminals, but non-Windows platforms do not receive these
controls and are not a supported interactive target.

## Command-line options

`python plasma.py --help` lists initial values for speed, frequencies, radius,
palette and FPS. In this release, `plasma.conf` is the runtime authority and is
loaded on the first frame, so an existing or newly generated config supersedes
those initial command-line values. Treat config editing and presets as the
normal control interface.
