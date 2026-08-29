# Architecture

This release keeps application and generation responsibilities separate.

| Component | Responsibilities |
|---|---|
| `plasma.py` | Startup, config loading/saving, keyboard ownership, controls, palette selection, rendering and frame pacing |
| `plasma_config_gen.py` | Stable seed derivation, constrained profile/LUT generation, complete config formatting and atomic creation |
| `plasma.conf` | Exact mutable runtime state and user-owned presets/LUTs |

There is no circular dependency. `plasma.py` imports the generator only when
the config is absent; the generator does not import the application.

## Startup and frame loop

1. Ensure `plasma.conf` exists, generating it only when absent.
2. Parse command-line initial values.
3. Compile an initial procedural palette.
4. Bind keyboard ownership to the current Windows Terminal document.
5. Enter the alternate screen and enable terminal focus reports.
6. Each frame: load a changed config, dispatch owned keyboard input, advance
   plasma time, render, flush once, and sleep to the configured FPS limit.
7. On exit: revoke input, clear transient state, restore the terminal, and
   release the Windows 1 ms timer period if acquired.

Because config checking occurs at the start of the first frame, `plasma.conf`
is the practical runtime authority over command-line initial values.

## Keyboard boundary

`ViewportKeyboardOwnership` is the single authority for command dispatch. Its
decision combines:

- native foreground-window identity;
- Windows Terminal DECSET 1004 document/tab focus reports; and
- a logical owner, currently `viewport`.

`poll_hotkeys()` exits before any command handler unless that authority grants
ownership. `set_keyboard_input_owner()` is the small future-facing hook for a
text field, modal, browser, or other component to claim input.

Every loss or regain boundary clears pressed and repeat maps, then latches keys
that are still physically held until their release. This prevents a missing
`keyup` during Alt-Tab from producing stuck movement or resuming a held action
when focus returns.

## Plasma field

For each terminal cell, the renderer averages four deterministic waves:

- a horizontal sine wave;
- a vertical sine wave with a different time rate;
- a fixed diagonal sine wave; and
- a radial sine wave centred on the current terminal dimensions.

The result is normalized to 0–1, quantized to a palette index, offset by the
current palette phase, and rendered as a true-colour background space.

## Terminal output

The palette is compiled once into ANSI `48;2;r;g;b` background sequences.
Within each row, a new colour escape is emitted only when the quantized index
changes; adjacent equal cells therefore form compact runs. One encoded frame
is written and flushed per loop.

Frames are wrapped in DEC synchronized-update mode (`?2026`) so Windows
Terminal 1.23 and later can present a parsed frame atomically. The application
also uses the alternate screen (`?1049`), hidden cursor (`?25`) and focus
reporting (`?1004`).

The renderer queries terminal dimensions every frame, so resizing needs no
separate layout state.
