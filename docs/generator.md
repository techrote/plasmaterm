# Deterministic configuration generator

`plasma_config_gen.py` creates a complete `plasma.conf` without using system
time, OS entropy, Python's randomized `hash()`, or previous PRNG state.

## Identity and determinism

The generated family is identified by:

```python
GENERATOR_VERSION = 1
MASTER_SEED = "PlasmaTerm/default-family/2026-08-29"
DEFAULT_SLOT = 0
```

For each non-negative slot, the generator hashes an explicit UTF-8 record of
version, master seed and slot with SHA-256. The first 64 digest bits seed a
locally implemented SplitMix64 generator. This makes every slot direct and
order-independent: generating slot 17 never requires slots 0–16.

Changing the generation algorithm in a way that defines a new procedural
family should normally increment `GENERATOR_VERSION`. Previous algorithms are
not retained in this release.

## Config-bank generation

`generate_config_text(base_slot)` creates:

- `[config]` and `[preset-0]` from `base_slot`;
- `[preset-1]` … `[preset-9]` from the next nine independent slots;
- `[lut-0]` … `[lut-9]`, one for each corresponding profile; and
- provenance comments containing version, master seed and base slot.

The file stores fully resolved values. Provenance is documentary; runtime
loading and later preset saves never reconstruct values from a seed.

## Aesthetic envelope

Profiles use correlated and bounded generation rather than independent noise.

| Property | Generation rule |
|---|---|
| X/Y frequency | Shared detail scale, jittered separation, clamped to 0.16–0.68 with about 0.04 minimum separation |
| Speed | Correlated with activity/detail, clamped to 0.35–1.45 |
| Radius | Correlated with detail, clamped to 0.28–0.95 |
| Hue span | Weighted families: commonly 70–145°, sometimes 145–245°, rarely 245–330° |
| Hue movement | Signed phase speed up to 60°/s, with a 10% chance of zero |
| Palette/FPS | Fixed generated defaults of 256 colours and 40 FPS |

Each LUT is a smooth, closed HSV curve built from a small set of randomized
hue, saturation and value anchors. Smoothstep interpolation expands those
anchors into 256 RGB entries. This produces structured ramps with a continuous
wrap instead of unrelated random colours.

## API and CLI

```python
from plasma_config_gen import generate_config

generate_config(slot=12, output_path="plasma.conf")
```

```powershell
python plasma_config_gen.py
python plasma_config_gen.py 12
python plasma_config_gen.py 12 --output another.conf
```

The CLI defaults to slot 0 and `plasma.conf` beside the generator. Output is
assembled completely, written to a temporary file in the destination
directory, flushed, and atomically replaced. A missing destination directory
or generation error fails clearly without leaving a partial config.
