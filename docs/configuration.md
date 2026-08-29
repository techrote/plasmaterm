# Configuration

`plasma.conf` is an INI file beside `plasma.py`. It contains current runtime
state, ten complete presets, and ten stored colour lookup tables (LUTs).

## Sections

| Section | Meaning |
|---|---|
| `[config]` | Values the running application loads and updates |
| `[preset-0]` … `[preset-9]` | Exact saved parameter sets |
| `[lut-0]` … `[lut-9]` | Fixed 256-entry RGB lookup tables |

Loading a preset copies all of its resolved values into the running state and
then writes them to `[config]`. Presets therefore remain usable without the
generator, its seed, or their original procedural slot.

## Parameters

| Config key | Runtime name | Meaning | Validation |
|---|---|---|---|
| `speed` | `speed` | Plasma geometry time multiplier; zero freezes geometry and negative values reverse it | Any finite number |
| `hue-shift` | `hue_shift` | Palette-index phase speed in degrees per second; not a literal RGB hue rotation | Any finite number |
| `freq-x` | `fx` | Horizontal sine spatial frequency | Any finite number |
| `freq-y` | `fy` | Vertical sine spatial frequency | Any finite number |
| `radius` | `rad` | Radial sine spatial frequency | Any finite number |
| `palette-size` | `palette_size` | Procedural LUT length | Integer 2–1024 |
| `hue-start` | `hue_start` | Procedural palette starting hue, in degrees | Any finite number; interpreted modulo 360 |
| `hue-end` | `hue_end` | Procedural palette ending hue, in degrees | Any finite number; interpreted cyclically |
| `fps` | `fps` | Maximum target frame rate | 1–240 |
| `active-lut` | `active_lut` | `none` for procedural colour, otherwise stored LUT `0`–`9` | `none` or one digit |

The runtime deliberately validates safety-critical structure, not an aesthetic
range for every wave parameter. The deterministic generator uses a narrower
visual envelope; hand-edited configs may go beyond it.

## Procedural hue range

The procedural palette travels forward around the hue circle from start to
end. For example, `330` to `30` crosses red. Equal endpoints mean one complete
360-degree palette, not a single colour. Full-circle generation omits a
duplicate last colour; partial ranges include both endpoints.

These settings are ignored for colour selection while a stored LUT is active.
They remain in the config and take effect again when `active-lut = none`.

## Stored LUT format

Each `[lut-N]` section has one `colors` value containing exactly 256 six-digit
RGB hex entries:

```ini
[lut-0]
colors =
    020008 04000C 070011 0A0017 0E001D 120024 16002B 1B0032
    ...
```

Whitespace or commas may separate entries. A leading `#` is not used because
INI parsers treat it as a comment. Values are validated before use and
normalized to uppercase internally.

Stored LUTs stay at 256 entries. The 2–1024 `palette-size` range applies only
to procedural palettes. The code contains a nearest-neighbour resampler for
turning another palette length into a 256-entry stored LUT.

## Reload and failure behaviour

Once per frame, PlasmaTerm compares the config file's modification time and
size with the last successfully loaded signature. A change triggers one
transactional parse of `[config]` and its active LUT.

- A valid save becomes active on the next frame.
- An invalid, missing, or partly written section leaves the last valid runtime
  state intact.
- A failed load is retried because its file signature is not accepted.
- Runtime writes use a temporary file, flush and `fsync`, then `os.replace`.
- Section updates preserve unrelated sections and hand-written comments.

This mechanism is intentionally simple and is best suited to human edits and
low-rate external control.
