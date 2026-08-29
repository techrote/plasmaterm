**PlasmaTerm** is a lightweight real-time generative plasma visualizer with a minimal, keyboard-driven interface. The rendered viewport acts as the primary interaction surface, avoiding conventional menus and persistent UI.

**PlasmaTerm is developed targetting Windows Terminal. And has only been tested in Windows Terminal**

This `web-v0.1a` branch also includes an isolated browser experiment in [`web/`](web/README.md).





Features:

Hue-range and palette-size controls affect only procedural palettes; stored LUTs remain 256 colours.
Config watching is a next-frame, low-rate control and is not intended as instantaneous high-rate modulation (planned in future)

Animated plasma patterns are controlled through a compact set of parameters for spatial frequency, hue range, animation speed, and hue shifting. Keyboard controls allow immediate visual exploration, including saving and recalling configurations.
Unlike Perlin or Simplex noise, the apparent complexity does not come from pseudo-randomness; it emerges deterministically from the interaction of simple mathematical waves.

PlasmaTerm is designed to remain small, extensible and immediate while providing a foundation for richer direct control and generative visual experimentation.
The ability to edit the config file live, is intended to enable external scripts to easily change the visualisation. This could be used for notifications, status representation, sunrise/set clock or any other whimsical use case that would benefit from pretty flowing patterns.

![PlasmaTerm Examples](images/plasmatermexamples.png)


Controls:

| Key       | Action                                       |
| ---------- | -------------------------------------------- |
| `0–9`      | Immediately load preset                      |
| `Alt+S`    | Save to last-loaded preset; slot 0 initially |
| `Ctrl+0–9` | Immediately load corresponding LUT           |
| `Q/A`      | Increase/decrease frequency Y                |
| `W/S`      | Increase/decrease frequency X                |
| `E/D`      | Increase/decrease hue start                  |
| `R/F`      | Increase/decrease hue end                    |
| `T/G`      | Increase/decrease speed                      |
| `Y/H`      | Increase/decrease hue shift                  |
| `U/J`      | Increase/decrease radius                     |
| `I/K`      | Increase/decrease palette size               |
| `O/L`      | Increase/decrease FPS                        |
| `P`        | Randomize the complete config bank once      |

Modifiers:

* No modifier: fine adjustment
* `Shift`: 10× step
* `Ctrl`: 100× step
* Holding an adjustment key repeats it

  ## Command-line usage

Run these commands from the PlasmaTerm repository directory.

### PlasmaTerm

Start PlasmaTerm using:

```powershell
python plasma.py
```

Show the available command-line options:

```powershell
python plasma.py --help
```

Command-line parameters provide initial values, but `plasma.conf` is loaded on the first frame and becomes authoritative. Edit the config or use the keyboard controls for persistent changes. If plasma.conf is not present plasma_config_gen.py will create it.

### Configuration generator

Generate the default configuration using procedural slot 0:

```powershell
python plasma_config_gen.py
```

Generate a configuration beginning with a different slot:

```powershell
python plasma_config_gen.py 12
```

Write the generated configuration to another file:

```powershell
python plasma_config_gen.py 12 --output custom.conf
```

The selected slot becomes preset 0; the following nine deterministic slots populate presets 1–9 and their corresponding LUTs.

### Test suite

Run the complete test suite with verbose results:

```powershell
python -m unittest -v test_plasma_config_gen.py
```

It can also be run directly:

```powershell
python test_plasma_config_gen.py
```


Parameter changes update the "live" config immediately, and external edits to the config file should be applied instantly upon saving.

If config file is absent, plasma.py imports the generator plasma_config_gen.py and creates a complete config atomically.


plasma_config_gen.py details:


GENERATOR_VERSION = 1
* Explicit MASTER_SEED
* SHA-256 slot derivation
* Explicit SplitMix64 PRNG

plasma_config_gen.py Workflow:
* Each requested base slot directly generates ten independent preset/LUT pairs.
* Generated configs contain resolved values; normal saving never depends on seeds or the generator.
* Frequencies, speed, radius, hue movement, and LUTs use constrained/correlated generation.
* LUTs are smooth, cyclic 256-colour curves rather than random colour noise.
* Generated defaults retain 256 colours and 40 FPS.

