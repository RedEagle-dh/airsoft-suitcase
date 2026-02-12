import time
from typing import List

from .game_utils import (
    CONFIG_PATH,
    EXIT_CODE,
    generate_code,
    initialize_audio,
    play_audio,
    read_audio_setting,
)
from .hardware.led import Led


def prompt_choice(title: str, options: List[str]) -> int:
    while True:
        print(f"\n{title}")
        for idx, option in enumerate(options, start=1):
            print(f"  {idx}: {option}")
        value = input("> ").strip()
        if value in {"1", "2", "3"}:
            return int(value) - 1
        print("Invalid input. Choose 1, 2, or 3.")


def run_bomb_mode(led: Led, minutes: int, audio_enabled: bool) -> None:
    print("\n[BOMBE] Starting bomb mode")
    arm_code = generate_code(16)
    def_code = generate_code(16)
    arm_tries = 3
    def_tries = 3

    led.turn_blue_on()
    print(f"[BOMBE] Arm code: {arm_code}")

    while arm_tries > 0:
        value = input("[BOMBE] Enter arm code (or 6969 to exit): ").strip().upper()
        if value == EXIT_CODE:
            print("[BOMBE] Exit requested")
            led.turn_off_all()
            return
        if value == arm_code:
            print("[BOMBE] Bomb armed")
            led.start_blue_blinker()
            led.set_rgb((0, 255, 0))
            led.start_stripe_blinker(True)
            play_audio("Arm", audio_enabled)
            break
        arm_tries -= 1
        if arm_tries == 0:
            print("[BOMBE] Too many attempts. Bomb disabled.")
            led.turn_off_all()
            return
        lock_time = 10 * (4 - arm_tries)
        print(f"[BOMBE] Wrong code. Input lock would be {lock_time}s. Tries left: {arm_tries}")

    deadline = time.time() + (minutes * 60)
    print(f"[BOMBE] Defuse code: {def_code}")

    while def_tries > 0:
        remaining = int(deadline - time.time())
        if remaining <= 0:
            print("[BOMBE] Timer reached 00:00. BOOM.")
            led.stop_all_blinkers()
            led.turn_off_all()
            led.turn_red_on()
            led.pixel_fill((255, 0, 0))
            play_audio("Boom", audio_enabled)
            return

        print(f"[BOMBE] Remaining time: {remaining}s")
        value = input("[BOMBE] Enter defuse code (or 6969 to exit): ").strip().upper()
        if value == EXIT_CODE:
            print("[BOMBE] Exit requested")
            led.turn_off_all()
            return
        if value == def_code:
            print("[BOMBE] Bomb defused")
            led.stop_all_blinkers()
            led.set_rgb((0, 255, 0))
            led.pixel_fill((0, 255, 0))
            play_audio("Defuse", audio_enabled)
            return

        def_tries -= 1
        if def_tries == 0:
            print("[BOMBE] Too many attempts. BOOM.")
            led.stop_all_blinkers()
            led.turn_off_all()
            led.turn_red_on()
            led.pixel_fill((255, 0, 0))
            play_audio("Boom", audio_enabled)
            return

        lock_time = 10 * (4 - def_tries)
        print(f"[BOMBE] Wrong code. Input lock would be {lock_time}s. Tries left: {def_tries}")


def run_bunker_mode(led: Led, minutes: int) -> None:
    print("\n[BUNKER] Starting bunker mode")
    print("[BUNKER] Commands: r, b, tick <seconds>, status, 6969")

    target = minutes * 60
    blue_seconds = 0
    red_seconds = 0
    active = None

    while True:
        command = input("[BUNKER] > ").strip().lower()
        if command == EXIT_CODE:
            print("[BUNKER] Exit requested")
            led.turn_off_all()
            return

        if command == "r":
            active = "red"
            led.turn_red_on()
            led.turn_off_blue()
            led.pixel_fill((255, 0, 0))
            print("[BUNKER] Red is capturing")
            continue

        if command == "b":
            active = "blue"
            led.turn_off_red()
            led.turn_blue_on()
            led.pixel_fill((0, 0, 255))
            print("[BUNKER] Blue is capturing")
            continue

        if command == "status":
            print(f"[BUNKER] Blue={blue_seconds}s Red={red_seconds}s Active={active}")
            continue

        if command.startswith("tick "):
            try:
                seconds = int(command.split()[1])
            except (ValueError, IndexError):
                print("[BUNKER] Invalid tick value")
                continue

            if seconds < 0:
                print("[BUNKER] Tick must be >= 0")
                continue

            if active == "blue":
                blue_seconds += seconds
            elif active == "red":
                red_seconds += seconds

            print(f"[BUNKER] Simulated +{seconds}s (Blue={blue_seconds}s Red={red_seconds}s)")

            if blue_seconds >= target:
                print("[BUNKER] Blue wins")
                led.turn_off_all()
                return
            if red_seconds >= target:
                print("[BUNKER] Red wins")
                led.turn_off_all()
                return
            continue

        print("[BUNKER] Unknown command")


def run_flag_mode(led: Led) -> None:
    print("\n[FLAGGE] Starting flag mode")
    print("[FLAGGE] Commands: r, b, 6969")

    while True:
        command = input("[FLAGGE] > ").strip().lower()
        if command == EXIT_CODE:
            print("[FLAGGE] Exit requested")
            led.turn_off_all()
            return

        if command == "r":
            led.pixel_fill((255, 0, 0))
            led.turn_red_on()
            led.turn_off_blue()
            print("[FLAGGE] RED")
            continue

        if command == "b":
            led.turn_off_red()
            led.turn_blue_on()
            led.pixel_fill((0, 0, 255))
            print("[FLAGGE] BLUE")
            continue

        print("[FLAGGE] Unknown command")


def main() -> None:
    print("[HEADLESS] Running console mode (no Tk GUI).")
    print("[HEADLESS] GPIO activity will be logged if simulation is active.")

    led = Led()

    audio_config = read_audio_setting(CONFIG_PATH, default=True)
    audio_enabled = bool(audio_config and initialize_audio())

    game_idx = prompt_choice("Spielauswahl", ["Bombe", "Bunker", "Flagge"])
    _diff_idx = prompt_choice("Schwierigkeit", ["Easy", "Medium", "Hard"])
    time_idx = prompt_choice("Zeit", ["5 Minuten", "10 Minuten", "15 Minuten"])

    minutes = [5, 10, 15][time_idx]

    if game_idx == 0:
        run_bomb_mode(led, minutes, audio_enabled)
    elif game_idx == 1:
        run_bunker_mode(led, minutes)
    else:
        run_flag_mode(led)


if __name__ == "__main__":
    main()
