# Changelog

## Unreleased

- Platform code split out into `aula/backends/` (groundwork for Windows and
  macOS); no change in behavior on Linux
- Sleep time "never" (0) verified on hardware
- Any RGB color for single-color effects: `aula effect NAME --rgb RRGGBB`,
  `aula palette [NAME] [--reset]`, and a color button plus "Factory colors" on
  the GUI's Lighting page. Each effect has its own 7-color palette (command 0x09),
  verified on hardware; the GUI preview and `aula info` show the real color
- Backups now include the effect palettes and the macro store, so a restore
  also brings back the macros
- GUI: no more "Gdk was imported without specifying a version" warning
- GUI: fits any window size. The window no longer insists on 980×820, so it works
  in tiling window managers and on small screens; text and controls scale with the
  window, the board and the settings share the height (drag the divider to
  change it), and long pages scroll
- GUI: a Themes page with a gallery of previews instead of a row of buttons
- Animations played from the computer over the keyboard's real-time channel
  (command 0x88, worked out from the official app and tuned on hardware): wave,
  breathe, sparkle, rainbow, fire and blaze. `aula animate` and an Animations page
  in the GUI with live previews on its cards; the drawing shows the frames the
  keyboard gets. Nothing is stored on the keyboard
- Animations that react to the keys you press, in any window: ripple, afterglow
  and heatmap (`aula animate ripple`, and their own row on the Animations page,
  whose cards preview them with pretend typing). The keys come from the
  keyboard's own key reports (boot and NKRO), read only while one plays
- GUI: one look for the whole window instead of the desktop theme below the board:
  a dark desk whose only color is the keyboard's current light (buttons, sliders
  and the chosen cards take on the color the board shows)
- Fourteen more themes: rainbow, ocean, fire, forest, sakura, frost, vaporwave,
  galaxy, supernova, nord, tokyo-night, catppuccin, gruvbox and royal. Themes can
  now run top to bottom, on the diagonal or out from the center

## 0.4.0 – 2026-10-10

- GUI: record macros from the keyboard (Record / Stop on the Macros page). Typed
  characters become text: steps for your layout, shortcuts become combos, fast
  typing with overlapping keys is handled; optional "Keep pauses"
- Macros: `down:KEY` / `up:KEY` steps for keys that stay held across other steps
- Sleep timer: `aula sleep 5m` / `off` and "Sleep after" on the Device page
  (LED block byte 24, 30 s units, timed on hardware); shown by `aula info`

## 0.3.1 – 2026-10-10

- Eight more themes: cyberpunk, dracula, matrix, sunset, volcano, aurora,
  miami-vice and toxic
- Macros: text steps follow the computer's keyboard layout (detected, or
  `--layout us|tr` / "Text layout" in the GUI); Turkish Q types ı/i, İ, ğ ü ş ö ç,
  punctuation and AltGr characters correctly
- Macros: fixed long macros getting corrupted: the firmware overwrites bytes
  126-127 of the macro store, so macros are now laid out around them
- `aula keys` also lists the key names for remap targets and macro steps
- README: a full guide to macros and a list of the themes

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
