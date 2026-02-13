import tkinter as tk

from ..theme import BG_SCREEN, FONT_BODY, FONT_SUBTITLE, FONT_TIMER_LARGE, TEXT_ALERT, TEXT_DIM, TEXT_PRIMARY
from .led_utils import reset_leds, start_team_pulse


class BunkerModeMixin:
    BUNKER_TARGET_SECONDS = 600

    def _init_bunker_state(self) -> None:
        self.bunker_blue_seconds = 0
        self.bunker_red_seconds = 0
        self.bunker_active_team = None
        self.bunker_winner = None
        self.bunker_signal_active = False
        self._bunker_widgets: dict[str, tk.Label] = {}

    def _reset_bunker_state(self) -> None:
        self.bunker_blue_seconds = 0
        self.bunker_red_seconds = 0
        self.bunker_active_team = None
        self.bunker_winner = None
        self.bunker_signal_active = False

    def start_bunker_game(self) -> None:
        self.is_in_game = True
        self.phase = "bunker"
        self._reset_bunker_state()

        reset_leds(self.led)

        self.render_bunker()
        self._schedule_bunker_tick()

    def _set_bunker_team(self, team: str) -> None:
        if self.bunker_winner is not None:
            return

        self.bunker_active_team = team
        start_team_pulse(self.led, team, stripe_interval=0.28)
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
                self._set_label_text(footer_right, f"{winner_name} bei {self.BUNKER_TARGET_SECONDS}s - * halten")
