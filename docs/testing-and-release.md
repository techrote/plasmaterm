# Testing and release notes

These notes describe commit
`1d83f7c0973ae58cf6375e068b40f351c2385fde`, before the planned high-rate
control refactor.

## Automated validation

From the repository root:

```powershell
python -m py_compile plasma.py plasma_config_gen.py test_plasma_config_gen.py
python -m unittest -v test_plasma_config_gen.py
```

The release snapshot passes all nine tests. They cover:

- byte-identical output for the same slot;
- different output for different slots;
- slot order independence;
- identical generation across fresh Python processes;
- constraints and LUT structure across 128 generated slots;
- ten complete presets and LUTs per generated config;
- missing-config bootstrap and normal config loading;
- preservation of an existing config; and
- exact preset persistence without generator access.

## Manual release checks

1. Start without `plasma.conf`; confirm one is generated and animation begins.
2. Start with an existing config; confirm it is not regenerated.
3. Exercise preset load/save, LUT loads and all adjustment pairs.
4. Edit a valid config while running; confirm it applies on the next frame.
5. Save an invalid/partial config; confirm the last valid display remains.
6. Hold a control, Alt-Tab before release, then return; confirm no repeat or
   held action resumes and a fresh press works.
7. Change Windows Terminal tabs repeatedly; confirm no stale or duplicate
   input dispatch.
8. Resize the terminal and interrupt with `Ctrl+C`; confirm screen and cursor
   restoration.

## Release constraints

- Windows Terminal on Windows is the supported interactive target.
- Keyboard polling uses Windows APIs; non-Windows keyboard controls are inert.
- Synchronized frames target Windows Terminal 1.23 or later.
- Stored LUT sections are exactly 256 RGB entries; procedural palettes support
  2–1024 entries.
- The file watcher is intended for low-rate edits, not continuous high-rate
  modulation.
- `plasma.conf` is user/runtime state and is intentionally ignored by Git;
  `plasma.conf.example` is the versioned reference.
- Command-line values are initial state only; the config loaded on the first
  frame becomes authoritative.

The repository contains no published GitHub release at the time represented by
this documentation bundle.
