# AULA F75 wireless configuration protocol

Source: `OemDrv.exe` (MFC, class `CDev3632`) from the official
`AULA F75 Setup v2.0 20240509.exe`, disassembled without running it, plus the
`Dev/kb/*/KB.ini` files and live tests. Wired mode (`CDevG5KB`, 258A:010C, Usage
Page 0xFF00, 520-byte feature report) uses the same data formats over a different
transport and is not implemented yet.

## Devices

| Mode | VID:PID | Channel |
|---|---|---|
| 2.4G dongle | 3554:FA09 | interface 1, Usage Page 0xFF02, report 0x13, 19-byte in/out |
| Bluetooth | 3554:FA07 | same channel (via uhid); keyboard reports: id 1 boot-style, id 2 NKRO |
| Wired | 258A:010C | Usage Page 0xFF00, feature report 0x208 bytes (not implemented) |

## Packet (20 bytes including report id)

```
[0] 0x13
[1] command              read = write | 0x40
[2] packet count         bit 7 set in a reply = error
[3] packet index (0..)
[4] (sub << 4) | payload_length (≤14)
[5..18] payload
[19] sum([0..18]) & 0xFF
```

- **Write:** data is split into 14-byte chunks. The keyboard **echoes every packet
  back** as an acknowledgement. Commands with bit 7 set, and 0x06, get no reply. The
  official app waits ~15 ms between packets.
- **Read:** send `[0x13, cmd|0x40, 1, 0, sub<<4, 0…, sum]`. The reply arrives in
  several packets, which have to be reassembled by their index `[3]`. Packets do get
  lost, so a reader has to reassemble by index and retry when a chunk is missing.

### Bluetooth packet loss

Over Bluetooth, multi-packet replies lose packets: the first three arrive, then
roughly every other one is dropped, depending on timing (the keyboard sends faster
than the radio link carries). The keyboard ignores the index field of a read
request and always resends the whole reply, so a reader has to repeat the request
and collect the parts across attempts. Adding a random 0-50 ms delay before each
attempt spreads the losses; right after a write the keyboard is busy saving and
loses even more, so reads wait 0.5 s after a write. Writes are unaffected: each
packet is acknowledged before the next one is sent.

### Dropped key releases

While the keyboard answers configuration traffic it can drop the **key release**
report of a key pressed at that moment (typically the Enter that launched the
command). The OS then auto-repeats that key until another key is pressed. To avoid
this, `Keyboard` watches the normal key reports (boot interface: 8-byte reports;
NKRO report id 4) and only sends a command once all keys are up and the keyboard has
been idle for 0.4 s.

The boot interface also sends three `00 00 01 00…` (ErrorRollOver) reports after
every key release. This is a firmware quirk and harmless.

## Commands

| Write | Read | Length | Content |
|---|---|---|---|
| 0x01 | 0x41 | 504 | Keymap, sub = layer (0 base, 1 Fn, 2-3 empty) |
| 0x02 | 0x42 | 378 | Per-key RGB (effect 32), planar: R[126] G[126] B[126] |
| 0x03 | 0x43 | 512-byte blocks | Macro storage, sub = block number (see "Macros") |
| 0x04 | 0x44 | 128 | LED config block |
| 0x06 | – | 1 | Factory reset (untested) |
| 0x07 | – | 1 | Read through a separate helper; probably battery/link status |
| 0x09 | 0x49 | 490 | Effect palettes: 7 colors × RGB per effect (writing untested) |
| 0x0A | 0x4A | 1-2 | Profile per the app. The reply `64 01`: first byte is probably the **battery %** (read 100 while the Fn+B gauge showed 10/10; unconfirmed at lower charge) |
| 0x0B | – | ? | Screen parameters (the F75 has no screen) |
| 0x88 / 0x8E | – | – | Real-time lighting / music data (no ack, untested) |

## LED config block (0x44, 128 bytes)

| Offset | Meaning |
|---|---|
| 9 | (in the app) flag for whether a special effect is selected |
| 10 | **Hardware number of the active effect** |
| 11 | ? (0x20) |
| 15 | **Windows key lock** (Fn+Win): 0 off, 1 locked |
| 18 | **Side light mode** (white bar next to Esc, Fn+Left Shift): 0 off, 1 fill top to bottom, 2 breathing, 3 static |
| 26 | **Knob mode** (long-press the knob to toggle): 0 media (turn = volume, press = mute; Shift/Win blink blue), 1 lighting (turn = brightness, press = next effect; Shift/Win blink green) |
| 27 | **OS mode**: 0 Windows (Fn+W), 1 Android (Fn+Q), 2 Mac (Fn+E). The keymap itself doesn't change |
| 24 | **Sleep timer** (2.4G / Bluetooth) in units of 30 s. Factory value 2 = 1 minute; 2 and 4 timed on hardware (lights went off after 1 and 2 minutes). The app offers 60-1200 s (KB.ini `SleepUI` / `SleepHW`, the latter being seconds / 30) and writes 0 when sleep is turned off: verified, with 0 the lights stayed on overnight |
| 19-21 | side light color / brightness / speed according to the app; no visible effect on the F75 (its side LEDs are white only: color values 0-7 all showed white) |
| 56-57 | ? (`81 f0`) |
| 58 + 2·(hw−1) | settings for effect hw: `[brightness 0-9, (speed 0-4 << 4) \| color]` |
| 126-127 | `5A A5` signature |

Colors: 0 red, 1 green, 2 blue, 3 yellow, 4 purple, 5 cyan, 6 white, 7 multicolor.

Firmware effect numbers, observed by trying every value 1-34 on a real F75 (the
official app's `LedOpt` names and numbering do **not** match the firmware):

| # | Effect | # | Effect |
|---|---|---|---|
| 1 | static | 10 | snake |
| 2 | breathing | 11 | stream (left to right) |
| 3 | spectrum (multicolor breathing) | 12 | reactive (pressed key lights) |
| 4 | ripple along the pressed key's row | 13 | center wave (middle → both sides) |
| 5 | raindrops | 15 | rainbow wheel (ignores color) |
| 6 | slow wave, left to right | 16 | waterfall (ignores color) |
| 7 | ripple over the whole board | 17 | fast flicker from the middle |
| 8 | twinkle (random keys) | **32** | **custom: per-key table (0x02), updates live** |

9, 14, 18-31, 33 and 34 show nothing. 21 (the app's "Self-define") and 29 only show
the per-key table after it has been re-sent; 32 shows it immediately.

## Keymap entry (4 bytes)

`[type, modifier_bits, ?, HID_usage]`

- type 0x00: plain key. Modifier bits: 01 LCtrl, 02 LShift, 04 LAlt, 08 LWin,
  10 RCtrl, 20 RShift, 40 RAlt, 80 RWin.
- type 0x07: special function (the `0x09,0x01,0x07xxxxxx` codes in KB.ini, stored
  big-endian, e.g. ESC on the Fn layer = `07 00 00 04`).
- type 0x08: Fn functions (brightness/effect etc., e.g. `08 03 01 00`).
- type 0x0D: the Fn key.
- Matrix indices are in `aula/keymap.py`. On the hardware, 53 = RAlt and 59 = Fn
  (KB.ini has these two labels the wrong way round).

## Macros

From `StMacro_To_HdMacro` in the official app, checked against the factory macro
("M1": Ctrl+\`) and on hardware.

Store (block 0 of command 0x03/0x43, 512 bytes; blocks 1-2 read back as zeros):

```
header   [address u16 LE, size u16 LE] per macro; the first address equals the
         header size, which gives the count
macro    [name length in bytes] [name] [event × n]
event    [ (kind << 4) | delay bits 19..16 | 0x80 if release,  delay bits 15..8,
           delay bits 7..0,  code ]
         kind 0 key (HID usage), 1 modifier (E0-E7), 2 mouse button,
         3 / 4 mouse move X / Y, 5 wheel; delay in ms until the next event
```

The app writes names as UTF-16LE; the factory macro uses plain ASCII.

The firmware writes `5A A5` over bytes 126-127 of the store (the same marker as at
the end of the 128-byte LED block), corrupting whatever event is there; bytes
254-255, 382-383 and 510-511 are left alone. Seen on hardware with a macro whose
22nd event landed on 124-127 (read back as `00 00 5A A5`). When those bytes are
written as zeros they read back as zeros. Since every macro has its own address in
the header, a macro that would cross them can simply start at byte 128.

Keymap entry of a key that runs a macro: `[03, mode, count, macro index]` with
mode 1 = run `count` times, 2 = repeat while held, 4 = repeat until any key is
pressed. A plain key entry is `[00, modifiers, key 2, key 1]`, so two-key combos
can also be assigned without a macro.

## Default Fn layer (layer 1)

From KB.ini `[FN1]` and the keyboard's layer-1 table; behavior notes from the owner.

| Key | Entry | Function |
|---|---|---|
| \` | `07 00 00 08` | 2.4G (the back switch decides the connection type) |
| 1 / 2 / 3 | `07 00 00 05/06/07` | Bluetooth device slot 1 / 2 / 3 |
| W / E | `07 00 00 18` / `07 00 00 1A` | Windows / Mac mode |
| Q | `07 00 00 19` | Android mode |
| B | `07 00 00 11` | battery gauge on 1…0 (green, 10 % per key) while held |
| G | `07 00 00 0A` | ? (no visible effect, changes no stored setting) |
| LWin | `07 00 00 01` | Windows key lock |
| Esc | `07 00 00 04` | factory reset when held |
| \\ | `08 00 00 00` | cycle lighting effect |
| Left Shift | `08 00 00 01` | cycle side light mode |
| Tab | `08 02 00 00` | cycle effect color |
| ↑ / ↓ | `08 03 01 00` / `08 03 02 00` | brightness up / down |
| → / ← | `08 04 01 00` / `08 04 02 00` | speed up / down |
| F1 / F2 | `02 00 02 23` / `02 00 01 8A` | consumer: browser home / mail |
| F3 | `00 04 00 2B` | Alt+Tab |
| F4 | `00 08 00 08` | Win+E |
| F7 … F12 | `02 00 00 B6/CD/B5/E2/EA/E9` | prev / play / next / mute / vol− / vol+ |

The connection type is chosen with the 3-position switch on the back of the
keyboard (2.4G / wired / Bluetooth); in Bluetooth mode Fn+1/2/3 picks which paired
device to connect to.

Holding Fn alone lights the key of the active connection (\` for 2.4G, 1-3 for
Bluetooth) and of the OS mode (W or E) in white, on top of the running effect.

## Open questions

- Wired transport (`CDevG5KB::AccessData`, around `0x48b350`).
