# Changelog

## 3.0.2 — 2026-10-20

- Prepare the realtime desktop helper for public source distribution.
- Add a version-locked local installer that never overwrites the original game.
- Remove machine-specific paths; add `BUCKSHOT_MEMORY_GAME` for custom installs.
- Add portable build instructions, MIT license and regression tests.
- Keep inactive cached states inactive; tolerate short partial JSON writes with a bounded grace period.

## 3.0.1

- Redraw the shell sequence only when visible state changes, fixing repeated widget recreation.

## 3.0.0

- Replace experimental manual/OCR tracking with a single-player local state bridge.
