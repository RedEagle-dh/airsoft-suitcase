import logging
import os
import random
import threading
import tkinter as tk
from contextlib import suppress
from typing import Dict, List, Optional

from .game_utils import (
    CONFIG_PATH,
    VALID_KEYS,
    generate_code,
    initialize_audio,
    is_truthy,
    play_audio,
    read_audio_setting,
)
from .hardware.led import Led
from .hardware.nfc_reader import NfcReader
from .theme import (
    BG_PANEL,
    BG_PRIMARY,
    BG_SCREEN,
    BORDER_COLOR,
    FONT_BODY,
    FONT_CODE,
    FONT_FLAG_TEAM,
    FONT_FOOTER,
    FONT_HINT,
    FONT_INPUT,
    FONT_MENU_OPTION,
    FONT_SUBTITLE,
    FONT_TIMER,
    FONT_TIMER_LARGE,
    FOOTER_BAR_HEIGHT,
    HEADER_BAR_HEIGHT,
    OUTER_PAD,
    PANEL_BORDER_WIDTH,
    PANEL_PADX,
    TEXT_ALERT,
    TEXT_DIM,
    TEXT_HEADER,
    TEXT_PRIMARY,
)

logger = logging.getLogger(__name__)


class LogicWindow:
    BOMB_DURATION_SECONDS = 10 * 60
    BOMB_CODE_LENGTH = 20
    BOMB_LOCK_SECONDS = (30, 60)

    BUNKER_TARGET_SECONDS = 600

    HASH_HOLD_MILLISECONDS = 3000

    def __init__(self, use_audio: bool) -> None:
        self.use_audio = bool(use_audio and initialize_audio())
        self.led = Led()
        self.nfc = NfcReader()

        self.modes = ["Bombe", "Bunker", "Flagge"]
        self.bomb_difficulties = ["Einfach", "Mittel", "Schwer"]

        self.pressed_keys: List[str] = []

        self.phase = "menu"
        self.menu_level = "game"
        self.selection = -1
        self.is_in_game = False

        self.selected_game: Optional[str] = None
        self.selected_diff: Optional[str] = None

        # Timed callbacks
        self.hash_hold_job: Optional[str] = None
        self.hash_key_down = False
        self.bomb_tick_job: Optional[str] = None
        self.bomb_lock_job: Optional[str] = None
        self.bomb_beep_job: Optional[str] = None
        self.bunker_tick_job: Optional[str] = None
        self.bunker_signal_job: Optional[str] = None
        self.game_end_job: Optional[str] = None

        # Bomb state
        self.bomb_stage = "idle"
        self.bomb_expected_code = ""
        self.bomb_defuse_code = ""
        self._beep_suppressed = False
        self.bomb_input: List[str] = []
        self.bomb_remaining = self.BOMB_DURATION_SECONDS
        self.bomb_reentry_targets: List[int] = []
        self.bomb_attempt = 0
        self.bomb_lock_remaining = 0
        self.bomb_resume_stage = ""
        self.bomb_end_message = ""

        # Bunker state
        self.bunker_blue_seconds = 0
        self.bunker_red_seconds = 0
        self.bunker_active_team: Optional[str] = None
        self.bunker_winner: Optional[str] = None
        self.bunker_signal_active = False

        # Flag state
        self.flag_team: Optional[str] = None

        # View cache to avoid full widget tear-down on every state tick.
        self._active_view_key = ""
        self._menu_widgets: Dict[str, object] = {}
        self._bomb_widgets: Dict[str, tk.Label] = {}
        self._bunker_widgets: Dict[str, tk.Label] = {}
        self._flag_widgets: Dict[str, tk.Label] = {}

        self.root = tk.Tk()
        self.root.title("Foxys Bombe")
        self.root.geometry("800x480+0+0")
        self.root.attributes("-fullscreen", True)
        self.root.attributes("-topmost", True)
        self.root.configure(background=BG_PRIMARY, cursor="none")
        self.root.focus_force()
        self.root.bind("<KeyPress>", self.keydown)
        self.root.bind("<KeyRelease>", self.keyup)
        self.root.bind("<FocusOut>", lambda _: self.root.after(100, self.root.focus_force))

        self.reset_to_menu()
        self.root.mainloop()

    # ----------------------------
    # General helpers
    # ----------------------------

    def _cancel_job(self, job_name: str) -> None:
        job = getattr(self, job_name)
        if job is None:
            return
        with suppress(Exception):
            self.root.after_cancel(job)
        setattr(self, job_name, None)

    def _cancel_all_jobs(self) -> None:
        for job_name in (
            "hash_hold_job",
            "bomb_tick_job",
            "bomb_lock_job",
            "bomb_beep_job",
            "bunker_tick_job",
            "bunker_signal_job",
            "game_end_job",
        ):
            self._cancel_job(job_name)

    def clear_frame(self) -> None:
        for child in self.root.winfo_children():
            child.destroy()

    def _switch_view(self, view_key: str) -> bool:
        if self._active_view_key == view_key:
            return False
        self.clear_frame()
        self._active_view_key = view_key
        return True

    def _set_label_text(self, label: tk.Label, text: str) -> None:
        if label.cget("text") != text:
            label.configure(text=text)

    def format_time(self, seconds: int) -> str:
        mins, secs = divmod(max(seconds, 0), 60)
        return f"{mins:02d}:{secs:02d}"

    def play_audio_async(self, name: str) -> None:
        threading.Thread(target=play_audio, args=(name, self.use_audio), daemon=True).start()

    def _beep_once(self) -> None:
        self.play_audio_async("beep")

    def _extract_keypad_char(self, key: "tk.Event[tk.Misc]") -> str:
        char = (getattr(key, "char", "") or "").upper()
        if char in VALID_KEYS or char in {"#", "*"}:
            return char

        if key.keysym in {"numbersign", "KP_Hash"}:
            return "#"
        if key.keysym in {"asterisk", "KP_Multiply", "parenleft"} or char == "(":
            return "*"

        if key.keysym in VALID_KEYS:
            return key.keysym

        return ""

    def _is_blue_key(self, key: "tk.Event[tk.Misc]") -> bool:
        return key.keysym in {"Return", "KP_Enter"}

    def _is_red_key(self, key: "tk.Event[tk.Misc]") -> bool:
        return key.keysym in {"Delete", "BackSpace"}

    def _is_hash_key(self, key: "tk.Event[tk.Misc]") -> bool:
        return self._extract_keypad_char(key) == "#"

    def _is_star_key(self, key: "tk.Event[tk.Misc]") -> bool:
        return self._extract_keypad_char(key) == "*"

    def _is_selection_digit(self, key: "tk.Event[tk.Misc]") -> Optional[int]:
        char = self._extract_keypad_char(key)
        if char in {"1", "2", "3"}:
            return int(char) - 1
        return None

    # ----------------------------
    # Layout helpers (tactical panel structure)
    # ----------------------------

    def _create_layout(self) -> tuple:
        """Create the three-zone tactical layout. Returns (header, content, footer)."""
        outer = tk.Frame(self.root, bg=BORDER_COLOR, padx=PANEL_BORDER_WIDTH, pady=PANEL_BORDER_WIDTH)
        outer.pack(fill="both", expand=True, padx=OUTER_PAD, pady=OUTER_PAD)

        header = tk.Frame(outer, bg=BG_PANEL, height=HEADER_BAR_HEIGHT)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        tk.Frame(outer, bg=BORDER_COLOR, height=1).pack(fill="x")

        content = tk.Frame(outer, bg=BG_SCREEN)
        content.pack(fill="both", expand=True)

        tk.Frame(outer, bg=BORDER_COLOR, height=1).pack(fill="x", side="bottom")

        footer = tk.Frame(outer, bg=BG_PANEL, height=FOOTER_BAR_HEIGHT)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        return header, content, footer

    def _add_header_title(self, header: tk.Frame, title: str) -> tk.Label:
        """Add a left-aligned title label to the header bar."""
        label = tk.Label(header, text=title, fg=TEXT_HEADER, bg=BG_PANEL, font=FONT_SUBTITLE, anchor="w")
        label.pack(side="left", padx=PANEL_PADX, fill="y")
        return label

    def _add_header_status(self, header: tk.Frame, text: str = "") -> tk.Label:
        """Add a right-aligned status label to the header bar."""
        label = tk.Label(header, text=text, fg=TEXT_PRIMARY, bg=BG_PANEL, font=FONT_FOOTER, anchor="e")
        label.pack(side="right", padx=PANEL_PADX, fill="y")
        return label

    def _add_footer_hints(self, footer: tk.Frame, left: str = "", right: str = "") -> tuple:
        """Add left/right hint labels to the footer bar. Returns (left_label, right_label)."""
        left_label = tk.Label(footer, text=left, fg=TEXT_DIM, bg=BG_PANEL, font=FONT_HINT, anchor="w")
        left_label.pack(side="left", padx=PANEL_PADX, fill="y")
        right_label = tk.Label(footer, text=right, fg=TEXT_DIM, bg=BG_PANEL, font=FONT_HINT, anchor="e")
        right_label.pack(side="right", padx=PANEL_PADX, fill="y")
        return left_label, right_label

    # ----------------------------
    # Global reset/menu
    # ----------------------------

    def reset_to_menu(self) -> None:
        self._cancel_all_jobs()
        self.nfc.stop_polling()

        self.pressed_keys = []
        self.hash_key_down = False

        self.phase = "menu"
        self.menu_level = "game"
        self.selection = -1
        self.is_in_game = False

        self.selected_game = None
        self.selected_diff = None

        self.bomb_stage = "idle"
        self.bomb_expected_code = ""
        self.bomb_defuse_code = ""
        self.bomb_input = []
        self.bomb_remaining = self.BOMB_DURATION_SECONDS
        self.bomb_reentry_targets = []
        self.bomb_attempt = 0
        self.bomb_lock_remaining = 0
        self.bomb_resume_stage = ""
        self.bomb_end_message = ""

        self.bunker_blue_seconds = 0
        self.bunker_red_seconds = 0
        self.bunker_active_team = None
        self.bunker_winner = None
        self.bunker_signal_active = False

        self.flag_team = None

        self.led.stop_all_blinkers()
        self.led.turn_off_all()
        self.led.pixel_fill((0, 0, 0))
        self.led.turn_red_on()
        self.led.turn_blue_on()

        self.render_menu()

    def render_menu(self) -> None:
        rebuilt = self._switch_view(f"menu:{self.menu_level}")
        title = "SPIELAUSWAHL" if self.menu_level == "game" else "BOMBE: SCHWIERIGKEIT"
        options = self.modes if self.menu_level == "game" else self.bomb_difficulties

        if rebuilt:
            header, content, footer = self._create_layout()
            title_label = self._add_header_title(header, title)

            option_labels: List[tk.Label] = []
            for _ in range(3):
                opt = tk.Label(content, bg=BG_SCREEN, fg=TEXT_PRIMARY, font=FONT_MENU_OPTION, anchor="w")
                opt.pack(padx=80, pady=(18, 0), anchor="w")
                option_labels.append(opt)

            self._add_footer_hints(footer, left="Rot: Zurück", right="Blau: Bestätigen")

            self._menu_widgets = {
                "title": title_label,
                "options": option_labels,
            }

        title_label = self._menu_widgets["title"]
        option_labels = self._menu_widgets["options"]
        self._set_label_text(title_label, title)  # type: ignore[arg-type]

        for idx, option in enumerate(options):
            prefix = "> " if self.selection == idx else "  "
            self._set_label_text(option_labels[idx], f"{prefix}{idx + 1}: {option}")  # type: ignore[index]

    # ----------------------------
    # Key handling
    # ----------------------------

    def keydown(self, key: "tk.Event[tk.Misc]") -> None:
        if key.keysym in self.pressed_keys:
            return
        self.pressed_keys.append(key.keysym)

        if self.is_in_game and key.keysym == "Escape":
            self.reset_to_menu()
            return

        if self._is_hash_key(key):
            self.hash_key_down = True
            if self.is_in_game:
                self._start_hash_hold()
            return

        if self._is_star_key(key):
            self._handle_star_press()
            return

        if not self.is_in_game:
            self.handle_menu_input(key)
            return

        if self.phase == "bomb":
            self.handle_bomb_input(key)
        elif self.phase == "bunker":
            self.handle_bunker_input(key)
        elif self.phase == "flag":
            self.handle_flag_input(key)

    def keyup(self, key: "tk.Event[tk.Misc]") -> None:
        if key.keysym in self.pressed_keys:
            self.pressed_keys.remove(key.keysym)

        if self._is_hash_key(key):
            self.hash_key_down = False
            self._cancel_job("hash_hold_job")
            return

        if self._is_star_key(key):
            self._handle_star_release()

    def _start_hash_hold(self) -> None:
        if self.hash_hold_job is not None:
            return
        self.hash_hold_job = self.root.after(self.HASH_HOLD_MILLISECONDS, self._finish_hash_hold)

    def _finish_hash_hold(self) -> None:
        self.hash_hold_job = None
        if self.hash_key_down and self.is_in_game:
            self.reset_to_menu()

    # ----------------------------
    # Menu flow
    # ----------------------------

    def handle_menu_input(self, key: "tk.Event[tk.Misc]") -> None:
        selection = self._is_selection_digit(key)
        if selection is not None:
            self.selection = selection
            self.render_menu()
            return

        if self._is_blue_key(key) and self.selection in {0, 1, 2}:
            if self.menu_level == "game":
                self.selected_game = self.modes[self.selection]
                self.selection = -1
                if self.selected_game == "Bombe":
                    self.menu_level = "bomb_diff"
                    self.render_menu()
                    return
                self.start_selected_game()
                return

            self.selected_diff = self.bomb_difficulties[self.selection]
            self.start_selected_game()
            return

        if self._is_red_key(key) and self.menu_level == "bomb_diff":
            self.menu_level = "game"
            self.selection = -1
            self.selected_game = None
            self.render_menu()

    def start_selected_game(self) -> None:
        if self.selected_game == "Bombe":
            self.start_bomb_game()
        elif self.selected_game == "Bunker":
            self.start_bunker_game()
        elif self.selected_game == "Flagge":
            self.start_flag_game()

    # ----------------------------
    # Bomb mode
    # ----------------------------

    def _build_reentry_targets(self, difficulty: str) -> List[int]:
        if difficulty == "Einfach":
            return []
        if difficulty == "Mittel":
            return [random.randint(180, 420)]

        # Schwer: zwei stop-points zwischen Minute 3 und 7.
        values = random.sample(range(180, 421), 2)
        values.sort(reverse=True)
        return values

    def start_bomb_game(self) -> None:
        self.is_in_game = True
        self.phase = "bomb"

        diff = self.selected_diff or "Einfach"
        self.bomb_stage = "await_nfc" if diff == "Schwer" else "await_code"
        if diff == "Schwer" and is_truthy(os.getenv("AIRSOFT_NFC_AUTO_UNLOCK")):
            self.bomb_stage = "await_code"

        self.bomb_expected_code = generate_code(self.BOMB_CODE_LENGTH)
        self.bomb_defuse_code = generate_code(self.BOMB_CODE_LENGTH)
        self.bomb_input = []
        self.bomb_remaining = self.BOMB_DURATION_SECONDS
        self.bomb_reentry_targets = self._build_reentry_targets(diff)
        self.bomb_attempt = 0
        self.bomb_lock_remaining = 0
        self.bomb_resume_stage = ""
        self.bomb_end_message = ""

        if self.bomb_stage == "await_nfc":
            self._start_nfc_polling()

        self._prepare_bomb_idle_leds()
        self.render_bomb()

    def _start_nfc_polling(self) -> None:
        """Begin polling the NFC reader; advances to await_code when a card is detected."""
        self.nfc.start_polling(lambda: self.root.after(0, self._on_nfc_card_detected))

    def _on_nfc_card_detected(self) -> None:
        """Called on the Tk main thread when a card is scanned."""
        if self.bomb_stage != "await_nfc":
            return
        logger.info("NFC card accepted – advancing to code entry")
        self.bomb_stage = "await_code"
        self.bomb_input = []
        self.bomb_attempt = 0
        self.render_bomb()

    # Skip targets for dev testing: 7:10, 4:10, 1:10, 0:10
    _BOMB_SKIP_TARGETS = [430, 250, 70, 10]

    def _bomb_blue_interval(self) -> float:
        if self.bomb_remaining <= 60:
            return 0.25
        if self.bomb_remaining <= 240:
            return 0.333
        if self.bomb_remaining <= 420:
            return 0.50
        return 1.0

    def _bomb_tank_interval(self) -> float:
        if self.bomb_remaining <= 60:
            return 0.05
        if self.bomb_remaining <= 300:
            return 0.10
        return 0.16

    def _bomb_beeps_per_second(self) -> int:
        if self.bomb_remaining <= 60:
            return 4
        if self.bomb_remaining <= 240:
            return 3
        if self.bomb_remaining <= 420:
            return 2
        return 1

    def _fire_synced_beeps(self) -> None:
        """Fire beeps for the current second, synced to the timer tick."""
        if self._beep_suppressed:
            return
        count = self._bomb_beeps_per_second()
        self._beep_once()
        if count > 1:
            interval = 1000 // count
            for i in range(1, count):
                self.root.after(interval * i, self._beep_once)

    def _end_beep_suppression(self) -> None:
        self._beep_suppressed = False

    def _prepare_bomb_idle_leds(self) -> None:
        self.led.stop_all_blinkers()
        self.led.turn_off_all()
        self.led.pixel_fill((0, 0, 0))
        self.led.turn_blue_on()

    def _prepare_bomb_countdown_leds(self) -> None:
        self.led.stop_all_blinkers()
        self.led.turn_off_all()

        self.led.set_blue_interval(self._bomb_blue_interval())
        self.led.start_blue_blinker()

        self.led.set_rgb((0, 255, 0))
        self.led.set_stripe_interval(self._bomb_tank_interval())
        self.led.start_stripe_blinker(True)

    def _update_bomb_countdown_leds(self) -> None:
        self.led.set_blue_interval(self._bomb_blue_interval())
        self.led.set_stripe_interval(self._bomb_tank_interval())

    def _schedule_bomb_tick(self) -> None:
        if self.bomb_tick_job is not None:
            return
        self.bomb_tick_job = self.root.after(1000, self._tick_bomb)

    def _tick_bomb(self) -> None:
        self.bomb_tick_job = None
        if self.phase != "bomb" or self.bomb_stage != "countdown":
            return

        self.bomb_remaining -= 1
        if self.bomb_remaining <= 0:
            self._finish_bomb_timer_elapsed()
            return

        if self.bomb_reentry_targets and self.bomb_remaining == self.bomb_reentry_targets[0]:
            self.bomb_reentry_targets.pop(0)
            self._pause_bomb_for_reentry()
            return

        self._update_bomb_countdown_leds()
        self._fire_synced_beeps()
        self.render_bomb()
        self._schedule_bomb_tick()

    _ARM_SOUND_DURATION_MS = 2600

    def _start_bomb_countdown(self, play_arm_sound: bool) -> None:
        self.bomb_stage = "countdown"
        self.bomb_input = []

        if play_arm_sound:
            self.play_audio_async("Arm")
            self._beep_suppressed = True
            self.root.after(self._ARM_SOUND_DURATION_MS, self._end_beep_suppression)
        else:
            self._beep_suppressed = False

        self._prepare_bomb_countdown_leds()
        self.render_bomb()
        self._schedule_bomb_tick()

    def _pause_bomb_for_reentry(self) -> None:
        self._cancel_job("bomb_tick_job")
        self._cancel_job("bomb_beep_job")

        self.bomb_stage = "await_reentry"
        self.bomb_expected_code = generate_code(self.BOMB_CODE_LENGTH)
        self.bomb_input = []
        self.bomb_attempt = 0

        self._prepare_bomb_idle_leds()
        self.render_bomb()

    def _start_bomb_lock(self, seconds: int) -> None:
        self._cancel_job("bomb_tick_job")
        self._cancel_job("bomb_beep_job")

        self.bomb_resume_stage = self.bomb_stage
        self.bomb_stage = "locked"
        self.bomb_lock_remaining = seconds
        self.bomb_input = []

        self.led.stop_all_blinkers()
        self.led.turn_off_all()
        self.led.pixel_fill((0, 0, 0))
        self.led.set_red_interval(0.25)
        self.led.start_red_blinker()

        self.render_bomb()
        self.bomb_lock_job = self.root.after(1000, self._tick_bomb_lock)

    def _tick_bomb_lock(self) -> None:
        self.bomb_lock_job = None
        if self.phase != "bomb" or self.bomb_stage != "locked":
            return

        self.bomb_lock_remaining -= 1
        if self.bomb_lock_remaining <= 0:
            self.bomb_stage = self.bomb_resume_stage or "await_code"
            self.bomb_resume_stage = ""
            self.bomb_input = []
            self.led.stop_red_blinker()
            if self.bomb_stage == "countdown":
                self._prepare_bomb_countdown_leds()
                self.render_bomb()
                self._schedule_bomb_tick()
            else:
                self._prepare_bomb_idle_leds()
                self.render_bomb()
            return

        self.render_bomb()
        self.bomb_lock_job = self.root.after(1000, self._tick_bomb_lock)

    def _handle_wrong_bomb_code(self) -> None:
        self.bomb_attempt += 1
        if self.bomb_attempt <= len(self.BOMB_LOCK_SECONDS):
            self._start_bomb_lock(self.BOMB_LOCK_SECONDS[self.bomb_attempt - 1])
            return

        self._finish_bomb_failed_input()

    def _finish_bomb_failed_input(self) -> None:
        self.bomb_stage = "ended"
        self.bomb_end_message = "Zu viele Fehlversuche. Platzierer-Team verliert."

        self._cancel_job("bomb_tick_job")
        self._cancel_job("bomb_lock_job")
        self._cancel_job("bomb_beep_job")

        self.led.stop_all_blinkers()
        self.led.turn_off_all()
        self.led.turn_red_on()
        self.led.pixel_fill((255, 0, 0))

        self.play_audio_async("Defuse")
        self.render_bomb()

    def _finish_bomb_timer_elapsed(self) -> None:
        self.bomb_stage = "ended"
        self.bomb_end_message = "Zeit abgelaufen. Platzierer-Team gewinnt."

        self._cancel_job("bomb_tick_job")
        self._cancel_job("bomb_lock_job")
        self._cancel_job("bomb_beep_job")

        self.led.stop_all_blinkers()
        self.led.turn_off_all()
        self.led.turn_red_on()
        self.led.pixel_fill((255, 0, 0))

        self.play_audio_async("Arm")
        self.root.after(self._ARM_SOUND_DURATION_MS, lambda: self.play_audio_async("Boom"))
        self.render_bomb()

    def _dev_skip_bomb_timer(self) -> None:
        """Dev helper: skip countdown to the next phase boundary."""
        if self.bomb_stage != "countdown":
            return
        for target in self._BOMB_SKIP_TARGETS:
            if self.bomb_remaining > target:
                self.bomb_remaining = target
                self._beep_suppressed = False
                self._update_bomb_countdown_leds()
                self.render_bomb()
                return

    def _finish_bomb_defused(self) -> None:
        self.bomb_stage = "ended"
        self.bomb_end_message = "Bombe entschärft! Platzierer-Team verliert."

        self._cancel_job("bomb_tick_job")
        self._cancel_job("bomb_lock_job")
        self._cancel_job("bomb_beep_job")

        self.led.stop_all_blinkers()
        self.led.turn_off_all()
        self.led.turn_blue_on()
        self.led.pixel_fill((0, 0, 255))

        self.play_audio_async("Defuse")
        self.render_bomb()

    def handle_bomb_input(self, key: "tk.Event[tk.Misc]") -> None:
        if self.bomb_stage in {"ended", "locked"}:
            return

        if self._is_star_key(key) and self.bomb_stage == "countdown":
            self._dev_skip_bomb_timer()
            return

        if self._is_red_key(key):
            self.bomb_input = []
            self.render_bomb()
            return

        if self._is_blue_key(key):
            candidate = "".join(self.bomb_input)
            if not candidate:
                return

            self.bomb_input = []

            if self.bomb_stage == "countdown":
                if candidate == self.bomb_defuse_code:
                    self._finish_bomb_defused()
                else:
                    self._handle_wrong_bomb_code()
                return

            if self.bomb_stage not in {"await_code", "await_reentry"}:
                self.render_bomb()
                return

            if candidate == self.bomb_expected_code:
                self.bomb_attempt = 0
                if self.bomb_stage == "await_code":
                    self._start_bomb_countdown(play_arm_sound=True)
                else:
                    self._start_bomb_countdown(play_arm_sound=False)
                return

            self._handle_wrong_bomb_code()
            return

        char = self._extract_keypad_char(key)
        if self.bomb_stage == "await_nfc":
            if char == "A":
                self.bomb_stage = "await_code"
                self.bomb_input = []
                self.bomb_attempt = 0
                self.render_bomb()
            return

        if self.bomb_stage not in {"await_code", "await_reentry", "countdown"}:
            return

        if char not in VALID_KEYS:
            return

        if len(self.bomb_input) >= self.BOMB_CODE_LENGTH:
            return

        self.bomb_input.append(char)
        self.render_bomb()

    def render_bomb(self) -> None:
        rebuilt = self._switch_view(f"bomb:{self.bomb_stage}")

        if rebuilt:
            self._bomb_widgets = {}
            header, content, footer = self._create_layout()

            self._bomb_widgets["header_title"] = self._add_header_title(header, "BOMBE")
            self._bomb_widgets["timer"] = self._add_header_status(header)

            if self.bomb_stage == "await_nfc":
                tk.Label(content, fg=TEXT_PRIMARY, bg=BG_SCREEN, text="SCHWER-MODUS", font=FONT_SUBTITLE).pack(
                    pady=(40, 8)
                )
                tk.Label(content, fg=TEXT_PRIMARY, bg=BG_SCREEN, text="NFC-Karte scannen", font=FONT_BODY).pack(pady=4)
                nfc_hint = "Karte an Leser halten..." if self.nfc.available else "Kein Leser \u2013 Taste A"
                tk.Label(content, fg=TEXT_DIM, bg=BG_SCREEN, text=nfc_hint, font=FONT_HINT).pack(pady=(20, 0))
                self._add_footer_hints(footer, left="# 3s = Menu")

            elif self.bomb_stage in {"await_code", "await_reentry"}:
                self._bomb_widgets["prompt"] = tk.Label(content, fg=TEXT_PRIMARY, bg=BG_SCREEN, font=FONT_SUBTITLE)
                self._bomb_widgets["prompt"].pack(pady=(16, 4))
                self._bomb_widgets["code"] = tk.Label(content, fg=TEXT_DIM, bg=BG_SCREEN, font=FONT_CODE)
                self._bomb_widgets["code"].pack(pady=2)
                self._bomb_widgets["input"] = tk.Label(content, fg=TEXT_PRIMARY, bg=BG_SCREEN, font=FONT_INPUT)
                self._bomb_widgets["input"].pack(pady=(12, 4))
                self._bomb_widgets["attempts"] = tk.Label(content, fg=TEXT_DIM, bg=BG_SCREEN, font=FONT_BODY)
                self._bomb_widgets["attempts"].pack(pady=4)
                self._add_footer_hints(footer, left="# 3s = Menu")

            elif self.bomb_stage == "countdown":
                self._bomb_widgets["big_timer"] = tk.Label(
                    content, fg=TEXT_PRIMARY, bg=BG_SCREEN, font=FONT_TIMER
                )
                self._bomb_widgets["big_timer"].pack(pady=(12, 4))
                self._bomb_widgets["defuse_code"] = tk.Label(
                    content, fg=TEXT_DIM, bg=BG_SCREEN, font=FONT_CODE
                )
                self._bomb_widgets["defuse_code"].pack(pady=(4, 2))
                self._bomb_widgets["input"] = tk.Label(
                    content, fg=TEXT_PRIMARY, bg=BG_SCREEN, font=FONT_INPUT
                )
                self._bomb_widgets["input"].pack(pady=(4, 2))
                self._bomb_widgets["attempts"] = tk.Label(
                    content, fg=TEXT_DIM, bg=BG_SCREEN, font=FONT_HINT
                )
                self._bomb_widgets["attempts"].pack(pady=2)
                self._add_footer_hints(footer, left="# 3s = Menu")

            elif self.bomb_stage == "locked":
                self._bomb_widgets["locked"] = tk.Label(content, fg=TEXT_ALERT, bg=BG_SCREEN, font=FONT_TIMER)
                self._bomb_widgets["locked"].pack(pady=(60, 0))
                tk.Label(content, fg=TEXT_ALERT, bg=BG_SCREEN, text="EINGABE GESPERRT", font=FONT_SUBTITLE).pack(pady=8)
                self._add_footer_hints(footer, left="# 3s = Menu")

            elif self.bomb_stage == "ended":
                self._bomb_widgets["ended"] = tk.Label(
                    content, fg=TEXT_ALERT, bg=BG_SCREEN, font=FONT_BODY, wraplength=700
                )
                self._bomb_widgets["ended"].pack(pady=(60, 12))
                self._add_footer_hints(footer, left="# 3s = Menu")

        self._set_label_text(self._bomb_widgets["timer"], f"Zeit: {self.format_time(self.bomb_remaining)}")

        if self.bomb_stage == "countdown" and "big_timer" in self._bomb_widgets:
            self._set_label_text(self._bomb_widgets["big_timer"], self.format_time(self.bomb_remaining))
            self._set_label_text(self._bomb_widgets["defuse_code"], f"Entschärfen: {self.bomb_defuse_code}")
            self._set_label_text(self._bomb_widgets["input"], f"Eingabe: {''.join(self.bomb_input)}")
            self._set_label_text(self._bomb_widgets["attempts"], f"Fehlversuche: {self.bomb_attempt}/3")
        elif self.bomb_stage in {"await_code", "await_reentry"}:
            prompt = "Code zum Start:" if self.bomb_stage == "await_code" else "Neuer Code erforderlich:"
            self._set_label_text(self._bomb_widgets["prompt"], prompt)
            self._set_label_text(self._bomb_widgets["code"], self.bomb_expected_code)
            self._set_label_text(self._bomb_widgets["input"], f"Eingabe: {''.join(self.bomb_input)}")
            self._set_label_text(self._bomb_widgets["attempts"], f"Fehlversuche: {self.bomb_attempt}/3")
        elif self.bomb_stage == "locked":
            self._set_label_text(self._bomb_widgets["locked"], f"{self.bomb_lock_remaining}s")
        elif self.bomb_stage == "ended":
            self._set_label_text(self._bomb_widgets["ended"], self.bomb_end_message)

    # ----------------------------
    # Bunker mode
    # ----------------------------

    def start_bunker_game(self) -> None:
        self.is_in_game = True
        self.phase = "bunker"

        self.bunker_blue_seconds = 0
        self.bunker_red_seconds = 0
        self.bunker_active_team = None
        self.bunker_winner = None
        self.bunker_signal_active = False

        self.led.stop_all_blinkers()
        self.led.turn_off_all()
        self.led.pixel_fill((0, 0, 0))

        self.render_bunker()
        self._schedule_bunker_tick()

    def _set_bunker_team(self, team: str) -> None:
        if self.bunker_winner is not None:
            return

        self.bunker_active_team = team

        self.led.stop_all_blinkers()
        self.led.turn_off_all()

        if team == "red":
            self.led.turn_red_on()
            self.led.set_rgb((255, 0, 0))
        else:
            self.led.turn_blue_on()
            self.led.set_rgb((0, 0, 255))

        self.led.set_stripe_interval(0.28)
        self.led.start_stripe_blinker(True)

        self.render_bunker()

    def _schedule_bunker_tick(self) -> None:
        if self.bunker_tick_job is not None:
            return
        self.bunker_tick_job = self.root.after(1000, self._tick_bunker)

    def _tick_bunker(self) -> None:
        self.bunker_tick_job = None
        if self.phase != "bunker":
            return

        if self.bunker_winner is None:
            if self.bunker_active_team == "blue":
                self.bunker_blue_seconds += 1
            elif self.bunker_active_team == "red":
                self.bunker_red_seconds += 1

            if self.bunker_blue_seconds >= self.BUNKER_TARGET_SECONDS:
                self.bunker_winner = "blue"
                self.bunker_active_team = "blue"
            elif self.bunker_red_seconds >= self.BUNKER_TARGET_SECONDS:
                self.bunker_winner = "red"
                self.bunker_active_team = "red"

        self.render_bunker()
        if self.bunker_winner is None:
            self._schedule_bunker_tick()

    def _schedule_bunker_signal(self) -> None:
        if self.bunker_signal_job is not None:
            return
        self.bunker_signal_job = self.root.after(220, self._tick_bunker_signal)

    def _tick_bunker_signal(self) -> None:
        self.bunker_signal_job = None
        if self.phase != "bunker" or not self.bunker_signal_active:
            return
        self._beep_once()
        self._schedule_bunker_signal()

    def _handle_star_press(self) -> None:
        if self.phase == "bunker" and self.bunker_winner is not None and not self.bunker_signal_active:
            self.bunker_signal_active = True
            self.render_bunker()
            self._schedule_bunker_signal()

    def _handle_star_release(self) -> None:
        if self.phase == "bunker" and self.bunker_signal_active:
            self.bunker_signal_active = False
            self._cancel_job("bunker_signal_job")
            self.reset_to_menu()

    def handle_bunker_input(self, key: "tk.Event[tk.Misc]") -> None:
        if self._is_red_key(key):
            self._set_bunker_team("red")
            return
        if self._is_blue_key(key):
            self._set_bunker_team("blue")

    def render_bunker(self) -> None:
        rebuilt = self._switch_view("bunker")

        if rebuilt:
            self._bunker_widgets = {}
            header, content, footer = self._create_layout()

            self._add_header_title(header, "BUNKER")
            self._bunker_widgets["header_status"] = self._add_header_status(
                header, f"Ziel: {self.BUNKER_TARGET_SECONDS}s"
            )

            self._bunker_widgets["status"] = tk.Label(content, fg=TEXT_PRIMARY, bg=BG_SCREEN)
            self._bunker_widgets["status"].pack(pady=(24, 8))
            self._bunker_widgets["times"] = tk.Label(content, fg=TEXT_DIM, bg=BG_SCREEN, font=FONT_BODY)
            self._bunker_widgets["times"].pack(pady=8)

            fl, fr = self._add_footer_hints(footer, left="# 3s = Menu")
            self._bunker_widgets["footer_left"] = fl
            self._bunker_widgets["footer_right"] = fr

        status_label = self._bunker_widgets["status"]
        if self.bunker_active_team is None:
            status_text = "Warte auf Team..."
            status_label.configure(font=FONT_SUBTITLE, fg=TEXT_DIM)
        else:
            active_secs = self.bunker_blue_seconds if self.bunker_active_team == "blue" else self.bunker_red_seconds
            active_name = "BLUE" if self.bunker_active_team == "blue" else "RED"
            status_text = f"{active_name} {self.format_time(active_secs)}"
            status_label.configure(font=FONT_TIMER_LARGE, fg=TEXT_PRIMARY)
        self._set_label_text(status_label, status_text)

        blue_t = self.format_time(self.bunker_blue_seconds)
        red_t = self.format_time(self.bunker_red_seconds)
        self._set_label_text(self._bunker_widgets["times"], f"Blue: {blue_t}   Red: {red_t}")

        footer_right = self._bunker_widgets["footer_right"]
        if self.bunker_winner is None:
            footer_right.configure(fg=TEXT_DIM)
            self._set_label_text(footer_right, "")
        else:
            winner_name = "BLUE" if self.bunker_winner == "blue" else "RED"
            footer_right.configure(fg=TEXT_ALERT)
            if self.bunker_signal_active:
                self._set_label_text(footer_right, f"{winner_name} gewonnen - Signal aktiv")
            else:
                self._set_label_text(footer_right, f"{winner_name} bei 600s - * halten")

    # ----------------------------
    # Flag mode
    # ----------------------------

    def start_flag_game(self) -> None:
        self.is_in_game = True
        self.phase = "flag"
        self.flag_team = None

        self.led.stop_all_blinkers()
        self.led.turn_off_all()
        self.led.pixel_fill((0, 0, 0))

        self.render_flag()

    def _set_flag_team(self, team: str) -> None:
        self.flag_team = team

        self.led.stop_all_blinkers()
        self.led.turn_off_all()

        if team == "red":
            self.led.turn_red_on()
            self.led.set_rgb((255, 0, 0))
        else:
            self.led.turn_blue_on()
            self.led.set_rgb((0, 0, 255))

        self.led.set_stripe_interval(0.25)
        self.led.start_stripe_blinker(True)

        self.render_flag()

    def handle_flag_input(self, key: "tk.Event[tk.Misc]") -> None:
        if self._is_red_key(key):
            self._set_flag_team("red")
            return
        if self._is_blue_key(key):
            self._set_flag_team("blue")

    def render_flag(self) -> None:
        rebuilt = self._switch_view("flag")

        if rebuilt:
            self._flag_widgets = {}
            header, content, footer = self._create_layout()

            self._add_header_title(header, "FLAGGE")

            self._flag_widgets["team"] = tk.Label(content, fg=TEXT_PRIMARY, bg=BG_SCREEN, font=FONT_FLAG_TEAM)
            self._flag_widgets["team"].pack(expand=True)

            self._add_footer_hints(footer, left="# 3s = Menu")

        label = "-"
        if self.flag_team == "red":
            label = "ROT"
        elif self.flag_team == "blue":
            label = "BLAU"
        self._set_label_text(self._flag_widgets["team"], label)


def main() -> None:
    audio_enabled = read_audio_setting(CONFIG_PATH, default=True)
    LogicWindow(audio_enabled)


if __name__ == "__main__":
    main()
