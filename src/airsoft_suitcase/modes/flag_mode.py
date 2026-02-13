import tkinter as tk

from ..theme import BG_SCREEN, FONT_FLAG_TEAM, TEXT_PRIMARY
from .led_utils import reset_leds, start_team_pulse


class FlagModeMixin:
    def _init_flag_state(self) -> None:
        self.flag_team = None
        self._flag_widgets: dict[str, tk.Label] = {}

    def _reset_flag_state(self) -> None:
        self.flag_team = None

    def start_flag_game(self) -> None:
        self.is_in_game = True
        self.phase = "flag"
        self._reset_flag_state()

        reset_leds(self.led)

        self.render_flag()

    def _set_flag_team(self, team: str) -> None:
        self.flag_team = team
        start_team_pulse(self.led, team, stripe_interval=0.25)
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
