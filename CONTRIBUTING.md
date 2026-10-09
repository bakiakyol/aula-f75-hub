# Contributing

Thanks for helping! Bug reports, device reports and pull requests are all welcome.
Issues may be written in English or Turkish.

## Reporting your keyboard

The protocol was worked out on one AULA F75 over the 2.4G dongle. Reports from
other versions and connections (Bluetooth, F75 Pro, F87, F99, …) are the most
useful contribution right now: open a **Device / firmware report** issue.

`tools/effect_tour.py` steps through every firmware effect number and records what
you see, which is how the effect list in `aula/protocol.py` was made:

```bash
python3 tools/effect_tour.py 1 34
```

## Development

- Plain Python 3.10+, no dependencies for the CLI; the GUI uses GTK 3 (PyGObject).
- Run the tests: `python3 -m unittest -v`. They don't need a keyboard.
- Protocol notes live in [docs/protocol.md](docs/protocol.md); please update them
  when you find something new.
- Only send commands whose effect you understand. Never send firmware-update or
  bootloader commands. Back up first: `./aula.sh backup ~/aula-backup`.
- Code, comments and commit messages are in English.

## Katkı (Türkçe)

Hata bildirimleri ve öneriler Türkçe de yazılabilir. En faydalı katkı, farklı AULA
modelleri ve bağlantı türlerinde (Bluetooth, kablo) aracın nasıl çalıştığını
**Device / firmware report** ile bildirmek.
