# Changelog

## Unreleased

- Macros: text steps follow the computer's keyboard layout (detected, or
  `--layout us|tr` / "Text layout" in the GUI); Turkish Q types ı/i, İ, ğ ü ş ö ç,
  punctuation and AltGr characters correctly
- Macros: fixed long macros getting corrupted: the firmware overwrites bytes
  126-127 of the macro store, so macros are now laid out around them

## 0.3.0 – 2026-10-10

- Macros: key combos, typed text and delays; run once, N times, while held or
  until another key is pressed (`aula macro …` and a Macros page in the GUI)
- Deleting a macro gives its key the factory function back and renumbers the
  keys of later macros
- GUI: an unexpected error no longer stops the background worker silently;
  it is shown in the status bar and every later action keeps working

## 0.2.0 – 2026-10-10

- Bluetooth verified: effects, per-key colors, remapping, status
- Reads collect reply packets across attempts (Bluetooth drops many), with a
  random delay per attempt and a short pause after writes
- Picks the connection the keyboard actually answers on when several exist
  (e.g. dongle plugged in while the keyboard is on Bluetooth)
- Key-release guard understands Bluetooth key reports

## 0.1.0 – 2026-10-10

First public version. Verified on an AULA F75 over the 2.4G dongle.

- Lighting: 15 firmware effects with color, brightness and speed
- Per-key RGB (custom effect) and built-in themes (`synthwave`)
- Key remapping on the base and Fn layers, with read-back verification
- Side light, knob mode, OS mode (Windows / Android / Mac) and Windows key lock
- Battery level (experimental)
- Backup and restore, including the factory settings
- GTK 3 interface with animated effect previews
- Waits for all keys to be released before talking to the keyboard, avoiding
  stuck, auto-repeating keys
