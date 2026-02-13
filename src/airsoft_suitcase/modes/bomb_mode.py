import logging
import os
import random
import tkinter as tk
from typing import List, Optional

from ..game_utils import VALID_KEYS, generate_code, is_truthy
from ..theme import (
    BG_SCREEN,
    FONT_BODY,
    FONT_CODE,
    FONT_HINT,
    FONT_INPUT,
    FONT_SUBTITLE,
    FONT_TIMER,
    TEXT_ALERT,
    TEXT_DIM,
    TEXT_PRIMARY,
)
from .led_utils import reset_leds, show_team_static

logger = logging.getLogger(__name__)


class BombModeMixin:
    BOMB_DURATION_SECONDS = 10 * 60
    BOMB_CODE_LENGTH = 20
    BOMB_LOCK_SECONDS = (30, 60)

    # Skip targets for dev testing: 7:10, 4:10, 1:10, 0:10
    _BOMB_SKIP_TARGETS = [430, 250, 70, 10]
    _ARM_SOUND_DURATION_MS = 2600

    def _init_bomb_state(self) -> None:
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
        self._bomb_widgets: dict[str, tk.Label] = {}

    def _reset_bomb_state(self) -> None:
        self.bomb_stage = "idle"
        self.bomb_expected_code = ""
        self.bomb_defuse_code = ""
        self._beep_suppressed = False
        self.bomb_input = []
        self.bomb_remaining = self.BOMB_DURATION_SECONDS
        self.bomb_reentry_targets = []
        self.bomb_attempt = 0
        self.bomb_lock_remaining = 0
        self.bomb_resume_stage = ""
        self.bomb_end_message = ""

    def _build_reentry_targets(self, difficulty: str) -> List[int]:
        if difficulty == "Einfach":
            return []
        if difficulty == "Mittel":
            return [random.randint(180, 420)]

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
        self.nfc.start_polling(lambda: self.root.after(0, self._on_nfc_card_detected))

    def _on_nfc_card_detected(self) -> None:
        if self.bomb_stage != "await_nfc":
            return
        logger.info("NFC card accepted - advancing to code entry")
        self.bomb_stage = "await_code"
        self.bomb_input = []
        self.bomb_attempt = 0
        self.render_bomb()

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
        if self._beep_suppressed:
            return
        count = self._bomb_beeps_per_second()
        self._beep_once()
        if count > 1:
            interval = 1000 // count
            for idx in range(1, count):
                self.root.after(interval * idx, self._beep_once)

    def _end_beep_suppression(self) -> None:
        self._beep_suppressed = False

    def _prepare_bomb_idle_leds(self) -> None:
        reset_leds(self.led)
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

        reset_leds(self.led)
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
        self._enter_bomb_end_state(
            message="Zu viele Fehlversuche. Platzierer-Team verliert.",
            team="red",
            audio_name="Defuse",
        )

    def _finish_bomb_timer_elapsed(self) -> None:
        self._enter_bomb_end_state(
            message="Zeit abgelaufen. Platzierer-Team gewinnt.",
            team="red",
            audio_name="Arm",
            delayed_audio_name="Boom",
            delayed_ms=self._ARM_SOUND_DURATION_MS,
        )

    def _dev_skip_bomb_timer(self) -> None:
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
        self._enter_bomb_end_state(
            message="Bombe entschärft! Platzierer-Team verliert.",
            team="blue",
            audio_name="Defuse",
        )

    def _enter_bomb_end_state(
        self,
        *,
        message: str,
        team: str,
        audio_name: str,
        delayed_audio_name: Optional[str] = None,
        delayed_ms: int = 0,
    ) -> None:
        self.bomb_stage = "ended"
        self.bomb_end_message = message

        self._cancel_job("bomb_tick_job")
        self._cancel_job("bomb_lock_job")
        self._cancel_job("bomb_beep_job")

        show_team_static(self.led, team)

        self.play_audio_async(audio_name)
        if delayed_audio_name is not None:
            self.root.after(delayed_ms, lambda: self.play_audio_async(delayed_audio_name))

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
                tk.Label(content, fg=TEXT_PRIMARY, bg=BG_SCREEN, text="NFC-Karte scannen", font=FONT_BODY).pack(
                    pady=4
                )
                nfc_hint = "Karte an Leser halten..." if self.nfc.available else "Kein Leser - Taste A"
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
                self._bomb_widgets["big_timer"] = tk.Label(content, fg=TEXT_PRIMARY, bg=BG_SCREEN, font=FONT_TIMER)
                self._bomb_widgets["big_timer"].pack(pady=(12, 4))
                self._bomb_widgets["defuse_code"] = tk.Label(content, fg=TEXT_DIM, bg=BG_SCREEN, font=FONT_CODE)
                self._bomb_widgets["defuse_code"].pack(pady=(4, 2))
                self._bomb_widgets["input"] = tk.Label(content, fg=TEXT_PRIMARY, bg=BG_SCREEN, font=FONT_INPUT)
                self._bomb_widgets["input"].pack(pady=(4, 2))
                self._bomb_widgets["attempts"] = tk.Label(content, fg=TEXT_DIM, bg=BG_SCREEN, font=FONT_HINT)
                self._bomb_widgets["attempts"].pack(pady=2)
                self._add_footer_hints(footer, left="# 3s = Menu")

            elif self.bomb_stage == "locked":
                self._bomb_widgets["locked"] = tk.Label(content, fg=TEXT_ALERT, bg=BG_SCREEN, font=FONT_TIMER)
                self._bomb_widgets["locked"].pack(pady=(60, 0))
                tk.Label(content, fg=TEXT_ALERT, bg=BG_SCREEN, text="EINGABE GESPERRT", font=FONT_SUBTITLE).pack(
                    pady=8
                )
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
