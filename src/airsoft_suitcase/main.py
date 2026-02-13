import logging
import threading
import tkinter as tk
from contextlib import suppress
from typing import Dict, List, Optional

from .game_utils import CONFIG_PATH, VALID_KEYS, initialize_audio, play_audio, read_audio_setting
from .hardware.led import Led
from .hardware.nfc_reader import NfcReader
from .modes import BombModeMixin, BunkerModeMixin, FlagModeMixin
from .modes.led_utils import reset_leds
from .theme import (
    BG_PANEL,
    BG_PRIMARY,
    BG_SCREEN,
    BORDER_COLOR,
    FONT_FOOTER,
    FONT_HINT,
    FONT_MENU_OPTION,
    FONT_SUBTITLE,
    FOOTER_BAR_HEIGHT,
    HEADER_BAR_HEIGHT,
    OUTER_PAD,
    PANEL_BORDER_WIDTH,
    PANEL_PADX,
    TEXT_DIM,
    TEXT_HEADER,
    TEXT_PRIMARY,
)

logger = logging.getLogger(__name__)


class LogicWindow(BombModeMixin, BunkerModeMixin, FlagModeMixin):
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

        self._init_bomb_state()
        self._init_bunker_state()
        self._init_flag_state()

        self._active_view_key = ""
        self._menu_widgets: Dict[str, object] = {}

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

    def _create_layout(self) -> tuple[tk.Frame, tk.Frame, tk.Frame]:
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
        label = tk.Label(header, text=title, fg=TEXT_HEADER, bg=BG_PANEL, font=FONT_SUBTITLE, anchor="w")
        label.pack(side="left", padx=PANEL_PADX, fill="y")
        return label

    def _add_header_status(self, header: tk.Frame, text: str = "") -> tk.Label:
        label = tk.Label(header, text=text, fg=TEXT_PRIMARY, bg=BG_PANEL, font=FONT_FOOTER, anchor="e")
        label.pack(side="right", padx=PANEL_PADX, fill="y")
        return label

    def _add_footer_hints(self, footer: tk.Frame, left: str = "", right: str = "") -> tuple[tk.Label, tk.Label]:
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

        self._reset_bomb_state()
        self._reset_bunker_state()
        self._reset_flag_state()

        reset_leds(self.led)
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
                option_label = tk.Label(content, bg=BG_SCREEN, fg=TEXT_PRIMARY, font=FONT_MENU_OPTION, anchor="w")
                option_label.pack(padx=80, pady=(18, 0), anchor="w")
                option_labels.append(option_label)

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


def main() -> None:
    audio_enabled = read_audio_setting(CONFIG_PATH, default=True)
    LogicWindow(audio_enabled)


if __name__ == "__main__":
    main()
