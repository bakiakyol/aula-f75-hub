"""Step through firmware effects one by one and record what the user sees.

Usage: python3 tools/effect_tour.py [start] [end]   (notes go to effect-notes.txt)
"""

import sys
import termios
import time
import traceback

sys.path.insert(0, __file__.rsplit("/tools/", 1)[0])
from aula import protocol as P  # noqa: E402
from aula.device import Keyboard  # noqa: E402

start = int(sys.argv[1]) if len(sys.argv) > 1 else 1
end = int(sys.argv[2]) if len(sys.argv) > 2 else P.LED_SLOTS

with Keyboard() as kb, open("effect-notes.txt", "a") as notes:
    for hw in range(start, end + 1):
        try:
            led = kb.get_led()
            led.effect = hw
            led.set_slot(hw, P.EffectSlot(9, 2, 0))
            kb.set_led(led)
        except Exception:
            print(f">>> ERROR: could not set effect {hw}:")
            traceback.print_exc()
            notes.write(f"{hw}: [WRITE ERROR]\n")
            notes.flush()
            continue
        time.sleep(0.5)
        termios.tcflush(sys.stdin, termios.TCIFLUSH)  # discard keys typed while switching
        note = ""
        while not note:
            try:
                note = input(f"Effect {hw} - what do you see? (press a few keys too): ").strip()
            except EOFError:
                print("\n(exiting)")
                sys.exit(0)
        notes.write(f"{hw}: {note}\n")
        notes.flush()
    led = kb.get_led()
    led.effect = 1
    kb.set_led(led)
    print("Done, keyboard is back on the static effect.")
