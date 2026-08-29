# PlasmaTerm release documentation

These notes describe the pre-refactor PlasmaTerm release at commit
`1d83f7c0973ae58cf6375e068b40f351c2385fde`.

PlasmaTerm is a Windows Terminal plasma renderer with invisible, viewport-owned
keyboard controls. Runtime state is kept in `plasma.conf`; the application
watches that file so valid external edits can be applied while it runs. This
watched-file interface is suitable for human edits and low-rate automation.
High-rate control is intentionally left for a later control-path refactor.

## Documents

- [User guide](user-guide.md): requirements, startup, controls and normal use.
- [Configuration](configuration.md): parameters, presets, LUTs and persistence.
- [Architecture](architecture.md): runtime, input and rendering boundaries.
- [Deterministic generator](generator.md): seeds, slots, constraints and CLI.
- [External control](external-control.md): the current watched-file contract.
- [Testing and release notes](testing-and-release.md): validation and limits.

## Repository files

| Path | Purpose |
|---|---|
| `plasma.py` | Application, renderer, keyboard input and config persistence |
| `plasma_config_gen.py` | Deterministic config, preset and LUT generation |
| `plasma.conf` | Local runtime state; generated when absent and ignored by Git |
| `plasma.conf.example` | Versioned example configuration |
| `test_plasma_config_gen.py` | Generator, bootstrap and persistence tests |
| `images/` | README imagery |

The repository contains the GNU Affero General Public License version 3 text.
