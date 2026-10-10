# Changelog

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
