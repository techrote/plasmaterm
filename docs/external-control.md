# External control in this release

The current external-control interface is the watched `plasma.conf` file. It
was chosen for simplicity, transparency and interoperability with small
scripts—not as a high-rate modulation protocol.

## Contract

An external tool should:

1. Read the current file rather than assuming default values.
2. Preserve sections and keys it does not own.
3. Write a complete valid INI document.
4. Prefer a temporary file plus atomic replacement in the same directory.
5. Allow PlasmaTerm to validate and adopt the change on a subsequent frame.

`[config]` and its selected `[lut-N]` are loaded together. If either is invalid,
the whole update is rejected and the previous valid state keeps running. This
transactional rule prevents a new parameter set from being displayed with a
half-written palette.

PlasmaTerm detects changes using `(mtime_ns, file_size)`. A successful load
records that signature; a failed load does not, so it is retried. File events,
IPC, sockets and global hotkeys are not used.

## Appropriate uses

The watched file is a good fit for occasional state changes such as status,
notifications, time-of-day themes, or manual tuning. Rewriting and parsing an
INI file every frame is not appropriate for smooth, high-rate control.

## Refactor boundary

A future high-rate interface should deliver control values through a dedicated
in-process or IPC path while preserving these release contracts:

- `plasma.conf` remains exact persisted user state;
- presets continue to store resolved values, not generator references;
- the deterministic generator remains an optional source of initial profiles;
- keyboard commands still pass through viewport ownership; and
- rendering remains independent of where control values originate.

This document records the boundary only. It does not prescribe the later
transport, event model or tuning UI.
