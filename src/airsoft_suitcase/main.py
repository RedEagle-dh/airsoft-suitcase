import logging
import threading
import time
import tkinter as tk
from typing import List, Optional

from .game_utils import (
    CONFIG_PATH,
    EXIT_CODE,
    VALID_KEYS,
    generate_code,
    initialize_audio,
    play_audio,
    read_audio_setting,
)
from .hardware.led import Led

logger = logging.getLogger(__name__)


class LogicWindow:
    def __init__(self, use_audio: bool) -> None:
        self.extra_input: List[str] = []
        self.use_audio = bool(use_audio and initialize_audio())
        self.led = Led()

        self.blue_counting = False
        self.red_counting = False
        self.blue_counter: Optional[threading.Thread] = None
        self.red_counter: Optional[threading.Thread] = None
        self.red_amount = 0
        self.blue_amount = 0
        self.red_time_label: Optional[tk.Label] = None
        self.blue_time_label: Optional[tk.Label] = None

        self.audio_thread: Optional[threading.Thread] = None
        self.input_lock_thread: Optional[threading.Thread] = None
        self.blinker: Optional[threading.Thread] = None

        # Threading events (replace module-level globals)
        self._stop_event = threading.Event()
        self._stop_lock_event = threading.Event()
        self._stop_red_event = threading.Event()
        self._stop_blue_event = threading.Event()

        # Bomb state
        self.timer_label: Optional[tk.Label] = None
        self.armed = False
        self.info_label: Optional[tk.Label] = None
        self.arm_code: Optional[str] = None
        self.def_code: Optional[str] = None
        self.arm_tries = 3
        self.outer_blinker = False
        self.bomb_tries = 3
        self.input_lock = False
        self.versuche_label: Optional[tk.Label] = None
        self.input_label: Optional[tk.Label] = None

        self.input: List[str] = []

        # Selection logic
        self.pressed_keys: List[str] = []
        self.heights = [120, 220, 320]
        self.modes = ["Bombe", "Bunker", "Flagge"]
        self.diffs = ["Easy", "Medium", "Hard"]
        self.times = [5, 10, 15]
        self.selected_game: Optional[str] = None
        self.selected_diff: Optional[str] = None
        self.selected_time: Optional[int] = None
        self.current = 0
        self.selection = -1
        self.game: Optional[str] = None
        self.is_in_game = False

        self.root = tk.Tk()
        self.root.attributes("-fullscreen", True)
        self.root.focus_force()
        self.root.bind("<KeyPress>", self.keydown)
        self.root.bind("<KeyRelease>", self.keyup)
        self.root.title("Foxys Bombe")
        self.root.geometry("800x480")
        self.root.configure(background="black")

        self.select_label: Optional[tk.Label] = None
        self.render_main_menu()

        self.root.mainloop()

    def render_main_menu(self) -> None:
        self.render_menu("Spielauswahl:", ["Bombe", "Bunker", "Flagge"])

    def render_menu(self, title: str, options: List[str]) -> None:
        self.clear_frame()
        tk.Label(self.root, name="text", text=title, bg="black", fg="green", font=("Ubuntu", 50)).pack()

        for index, option in enumerate(options, start=1):
            tk.Label(
                self.root,
                name=f"lable{index}",
                text=f"{index}:{option}",
                bg="black",
                fg="green",
                font=("Ubuntu", 45),
            ).place(x=150, y=self.heights[index - 1])

        self.render_navigation_hints()
        self.select_label = tk.Label(self.root, text="<--", bg="black", fg="green", font=("calibri light", 40))

    def render_navigation_hints(self) -> None:
        tk.Label(self.root, name="dont1", text="Rot: Zurück", fg="green", bg="black", font=("Ubuntu", 30)).place(
            relx=0.0, rely=1.0, anchor="sw"
        )
        tk.Label(self.root, name="dont2", text="Blau: Bestätigen", fg="green", bg="black", font=("Ubuntu", 30)).place(
            relx=1.0, rely=1.0, anchor="se"
        )

    def reset(self) -> None:
        self.extra_input = []

        self._stop_event.set()
        self.join_thread(self.audio_thread)

        self.led.stop_all_blinkers()
        self.led.turn_off_all()
        self.blue_counting = False
        self.red_counting = False
        self.outer_blinker = False

        self._stop_lock_event.set()
        self.join_thread(self.input_lock_thread)
        self._stop_lock_event.clear()

        self._stop_red_event.set()
        self.join_thread(self.red_counter)
        self._stop_red_event.clear()

        self._stop_blue_event.set()
        self.join_thread(self.blue_counter)
        self._stop_blue_event.clear()

        self.clear_frame()
        self.red_amount = 0
        self.blue_amount = 0
        self.armed = False
        self.audio_thread = None
        self._stop_event.clear()

        self.input_lock = False
        self.selected_game = None
        self.selected_diff = None
        self.selected_time = None
        self.is_in_game = False
        self.input = []
        self.current = 0
        self.selection = -1
        self.arm_tries = 3
        self.bomb_tries = 3

        self.render_main_menu()
        self.root.attributes("-fullscreen", True)
        self.led.turn_off_all()

    def join_thread(self, thread: Optional[threading.Thread]) -> None:
        if thread is None:
            return
        if thread is threading.current_thread():
            return
        try:
            thread.join(timeout=2)
        except Exception:
            logger.warning("Thread join failed", exc_info=True)

    def keydown(self, key: "tk.Event[tk.Misc]") -> None:
        if key.keysym not in self.pressed_keys:
            self.pressed_keys.append(key.keysym)
            self.game_select_input(key)

    def keyup(self, key: "tk.Event[tk.Misc]") -> None:
        if key.keysym in self.pressed_keys:
            self.pressed_keys.remove(key.keysym)

    def game_select_input(self, key: "tk.Event[tk.Misc]") -> None:
        if self.input_lock:
            return

        if not self.is_in_game:
            self.handle_selection_input(key)
            return

        if self.selected_game == "Bombe":
            self.handle_bomb_input(key)
        elif self.selected_game == "Flagge":
            self.handle_flag_input(key)
        elif self.selected_game == "Bunker":
            self.handle_bunker_input(key)

    def handle_selection_input(self, key: "tk.Event[tk.Misc]") -> None:
        if key.keysym in ["1", "2", "3"]:
            self.selection = int(key.keysym) - 1
            if self.select_label is not None:
                self.select_label.configure(text="<--")
                width, _height = self.get_label_width(key.keysym)
                self.select_label.place(x=160 + width, y=self.heights[self.selection])
            return

        if key.keysym == "Return" and self.selection in range(0, 3):
            self.confirm_selection()
            return

        if key.keysym == "Delete":
            self.back_selection()

    def confirm_selection(self) -> None:
        if self.current == 0:
            self.selected_game = self.modes[self.selection]
            self.current = 1
            self.selection = -1
            self.render_menu("Schwierigkeit:", ["Easy", "Medium", "Hard"])
        elif self.current == 1:
            self.selected_diff = self.diffs[self.selection]
            self.current = 2
            self.selection = -1
            self.render_menu("Zeit:", ["5Min", "10Min", "15Min"])
        elif self.current == 2:
            self.selected_time = self.times[self.selection]
            self.clear_frame()
            self.start_game()

    def back_selection(self) -> None:
        if self.current == 1:
            self.selected_game = None
            self.current = 0
            self.selection = -1
            self.render_main_menu()
        elif self.current == 2:
            self.selected_diff = None
            self.current = 1
            self.selection = -1
            self.render_menu("Schwierigkeit:", ["Easy", "Medium", "Hard"])

    def handle_bomb_input(self, key: "tk.Event[tk.Misc]") -> None:
        if key.keysym == "Delete":
            self.clear_input()
            return

        if key.keysym == "Return":
            candidate = "".join(self.input)
            if not self.armed:
                if candidate == self.arm_code:
                    self.armed = True
                    self.clear_input()
                    self.defuse_bomb()
                else:
                    self.reduce_tries()
            else:
                if candidate == self.def_code:
                    self.clear_input()
                    self.bomb_defused()
                else:
                    self.reduce_tries()
            return

        self.append_input(key.keysym, 16)

    def handle_flag_input(self, key: "tk.Event[tk.Misc]") -> None:
        if key.keysym == "Delete":
            self.clear_input()
            self.led.pixel_fill((255, 0, 0))
            self.led.turn_red_on()
            self.led.turn_off_blue()
            if self.info_label is not None:
                self.info_label.configure(text="RED")
            return

        if key.keysym == "Return":
            if self.is_exit_code_entered():
                self.reset()
                return
            self.clear_input()
            if self.info_label is not None:
                self.info_label.configure(text="BLUE")
            self.led.turn_off_red()
            self.led.turn_blue_on()
            self.led.pixel_fill((0, 0, 255))
            return

        self.append_input(key.keysym, len(EXIT_CODE))

    def handle_bunker_input(self, key: "tk.Event[tk.Misc]") -> None:
        if key.keysym == "Delete":
            self.clear_input()
            self.led.turn_red_on()
            self.led.turn_off_blue()
            self.led.pixel_fill((255, 0, 0))

            self._stop_blue_event.set()
            self.join_thread(self.blue_counter)
            self._stop_blue_event.clear()

            if not self.red_counting:
                self.red_counter = threading.Thread(target=self.red_timer, daemon=True)
                self.red_counter.start()
            return

        if key.keysym == "Return":
            if self.is_exit_code_entered():
                self.led.turn_off_blue()
                self.reset()
                return

            self.clear_input()
            self._stop_red_event.set()
            self.join_thread(self.red_counter)
            self._stop_red_event.clear()

            if not self.blue_counting:
                self.blue_counter = threading.Thread(target=self.blue_timer, daemon=True)
                self.blue_counter.start()

            self.led.turn_off_red()
            self.led.turn_blue_on()
            self.led.pixel_fill((0, 0, 255))
            return

        self.append_input(key.keysym, len(EXIT_CODE))

    def append_input(self, key: str, max_length: int) -> None:
        if key not in VALID_KEYS:
            return
        if len(self.input) >= max_length:
            return
        self.input.append(key)
        if self.input_label is not None:
            self.input_label.configure(text="".join(self.input))

    def clear_input(self) -> None:
        self.input = []
        if self.input_label is not None:
            self.input_label.configure(text="")

    def is_exit_code_entered(self) -> bool:
        return "".join(self.input) == EXIT_CODE

    def play_audio_async(self, name: str) -> None:
        threading.Thread(target=play_audio, args=(name, self.use_audio), daemon=True).start()

    def start_game(self) -> None:
        if self.selected_game == "Bombe":
            self.is_in_game = True
            self.arm_code = generate_code(16)
            self.def_code = generate_code(16)
            self.arm_bomb()
            self.arm_tries = 3
        elif self.selected_game == "Bunker":
            self.is_in_game = True
            self.bunker()
        elif self.selected_game == "Flagge":
            self.is_in_game = True
            self.flag()

    def clear_frame(self) -> None:
        for wi in self.root.winfo_children():
            wi.destroy()

    def set_labels(self, values: List[str]) -> None:
        for wi in self.root.winfo_children():
            if str(wi) == ".lable1":
                wi.configure(text=values[0])
            elif str(wi) == ".lable2":
                wi.configure(text=values[1])
            elif str(wi) == ".lable3":
                wi.configure(text=values[2])
            elif str(wi) == ".text":
                wi.configure(text=values[3])

    def get_label_width(self, key: str) -> List[int]:
        label_name = {
            "1": ".lable1",
            "2": ".lable2",
            "3": ".lable3",
        }.get(key)

        if label_name is None:
            return [0, 0]

        for wi in self.root.winfo_children():
            if str(wi) == label_name:
                return [wi.winfo_width(), wi.winfo_height()]
        return [0, 0]

    def arm_bomb(self) -> None:
        self.clear_frame()
        self.led.turn_blue_on()
        tk.Label(self.root, fg="green", bg="black", text="Bombe legen", font=("Ubuntu", 50)).pack()
        tk.Label(self.root, fg="green", bg="black", text="Code:", font=("Ubuntu", 15)).place(x=20, y=160)
        tk.Label(self.root, fg="green", bg="black", text=self.arm_code, font=("Ubuntu", 15)).place(x=100, y=160)
        tk.Label(self.root, fg="green", bg="black", text="Eingabe:", font=("Ubuntu", 30)).place(x=10, y=220)
        tk.Label(self.root, fg="green", bg="black", text="Versuche:", font=("Ubuntu", 30)).place(x=10, y=280)
        self.versuche_label = tk.Label(
            self.root, fg="green", bg="black", text=str(self.bomb_tries), font=("Ubuntu", 30)
        )
        self.versuche_label.place(x=210, y=280)
        self.input_label = tk.Label(self.root, fg="green", bg="black", text="", font=("Ubuntu", 30))
        self.input_label.place(x=180, y=220)
        self.info_label = tk.Label(self.root, fg="green", bg="black", text="", font=("Ubuntu", 30))
        self.info_label.place(x=10, y=350)
        self.root.update()

    def defuse_bomb(self) -> None:
        self.led.stop_all_blinkers()
        self.led.turn_off_all()

        self.led.start_blue_blinker()

        self.led.set_rgb((0, 255, 0))
        self.play_audio_async("Arm")
        self.clear_frame()
        self.timer_label = tk.Label(self.root, fg="green", bg="black", text="", font=("Ubuntu", 50))
        self.timer_label.pack()
        tk.Label(self.root, fg="green", bg="black", text="Code:", font=("Ubuntu", 15)).place(x=20, y=160)
        tk.Label(self.root, fg="green", bg="black", text=self.def_code, font=("Ubuntu", 15)).place(x=100, y=160)
        tk.Label(self.root, fg="green", bg="black", text="Eingabe:", font=("Ubuntu", 30)).place(x=10, y=220)
        tk.Label(self.root, fg="green", bg="black", text="Versuche:", font=("Ubuntu", 30)).place(x=10, y=280)
        self.versuche_label = tk.Label(
            self.root, fg="green", bg="black", text=str(self.arm_tries), font=("Ubuntu", 30)
        )
        self.versuche_label.place(x=210, y=280)
        self.input_label = tk.Label(self.root, fg="green", bg="black", text="", font=("Ubuntu", 30))
        self.input_label.place(x=180, y=220)
        self.info_label = tk.Label(self.root, fg="green", bg="black", text="", font=("Ubuntu", 30))
        self.info_label.place(x=10, y=350)
        self.audio_thread = threading.Thread(target=self.timer, daemon=True)
        self.audio_thread.start()
        self.led.start_stripe_blinker(True)

    def timer(self) -> None:
        if self.selected_time is None:
            return

        ctime = self.selected_time * 60
        while ctime and not self._stop_event.is_set():
            if ctime == (self.selected_time * 60) / 2:
                self.outer_blinker = True
                self.led.start_red_blinker()
                self.led.stop_blue_blinker()
                if not self.led.get_red_is_alive():
                    self.led.start_red_blinker()

            mins, secs = divmod(ctime, 60)
            timeformat = f"{mins:02d}:{secs:02d}"
            if self.timer_label is not None:
                self.timer_label.configure(text=timeformat)
            time.sleep(1)
            ctime -= 1

        if ctime == 0:
            if self.timer_label is not None:
                self.timer_label.configure(text="00:00")
            self.root.update()
            self.explosion()

    def explosion(self) -> None:
        self.led.stop_all_blinkers()
        self.led.turn_off_all()
        self.led.turn_red_on()
        self.led.pixel_fill((255, 0, 0))
        if self.info_label is not None:
            self.info_label.configure(text="Bombe ist explodiert")
        self.root.update()
        self.input_lock = True
        self._stop_event.set()
        self._stop_lock_event.set()

        self.join_thread(self.input_lock_thread)
        self._stop_lock_event.clear()

        self.join_thread(self.audio_thread)
        self.root.update()

        self.play_audio_async("Boom")
        time.sleep(20)
        self.reset()

    def reduce_tries(self) -> None:
        if not self.armed:
            if self.bomb_tries - 1 > 0:
                self.bomb_tries -= 1
                lock_time = self.calculate_lock_time(self.bomb_tries)
                if self.versuche_label is not None:
                    self.versuche_label.configure(text=self.bomb_tries)
                if self.info_label is not None:
                    self.info_label.configure(text=f"Falsche eingabe\nEingabe für: {lock_time} sekunden gesperrt")
                self.clear_input()
                self.input_lock_thread = threading.Thread(target=self.lock_input, args=(lock_time,), daemon=True)
                self.input_lock_thread.start()
            else:
                if self.info_label is not None:
                    self.info_label.configure(text="Zu viele versuche\nBombe ist deaktiviert")
        else:
            if self.arm_tries - 1 > 0:
                self.arm_tries -= 1
                lock_time = self.calculate_lock_time(self.arm_tries)
                if self.versuche_label is not None:
                    self.versuche_label.configure(text=self.arm_tries)
                if self.info_label is not None:
                    self.info_label.configure(text=f"Falsche eingabe\nEingabe für: {lock_time} sekunden gesperrt")
                self.clear_input()
                self.input_lock_thread = threading.Thread(target=self.lock_input, args=(lock_time,), daemon=True)
                self.input_lock_thread.start()
            else:
                if self.info_label is not None:
                    self.info_label.configure(text="Zu viele versuche\nBombe ist explodiert")
                self.explosion()

    def calculate_lock_time(self, tries_left: int) -> int:
        return 10 * (4 - tries_left)

    def lock_input(self, ctime: int) -> None:
        self.input_lock = True
        if not self.led.get_red_is_alive():
            self.led.start_red_blinker()

        elapsed = 0
        while elapsed < ctime and not self._stop_lock_event.is_set():
            time.sleep(1)
            elapsed += 1

        self.input_lock = False
        if not self.outer_blinker:
            self.led.stop_red_blinker()
        if not self._stop_lock_event.is_set() and self.info_label is not None:
            self.info_label.configure(text="")

    def flag(self) -> None:
        tk.Label(self.root, fg="green", bg="black", text="Flagge", font=("Ubuntu", 50)).pack()
        self.info_label = tk.Label(self.root, fg="green", bg="black", text="", font=("Ubuntu", 90))
        self.info_label.place(x=200, y=200)

    def bomb_defused(self) -> None:
        if self.info_label is not None:
            self.info_label.configure(text="Die Bombe wurde entschärft")
        self.led.set_rgb((0, 255, 0))
        self.led.pixel_fill((0, 255, 0))

        self._stop_event.set()
        self.join_thread(self.audio_thread)
        self.root.update()

        self.play_audio_async("Defuse")
        time.sleep(20)
        self.reset()

    def red_timer(self) -> None:
        ctime = self.red_amount
        self.red_counting = True
        while True:
            if self._stop_red_event.is_set():
                self.red_amount = ctime
                self.red_counting = False
                break
            mins, secs = divmod(ctime, 60)
            timeformat = f"{mins:02d}:{secs:02d}"
            if self.red_time_label is not None:
                self.red_time_label.configure(text=timeformat)
            time.sleep(1)
            ctime += 1

    def blue_timer(self) -> None:
        self.blue_counting = True
        ctime = self.blue_amount
        while True:
            if self._stop_blue_event.is_set():
                self.blue_counting = False
                self.blue_amount = ctime
                break
            mins, secs = divmod(ctime, 60)
            timeformat = f"{mins:02d}:{secs:02d}"
            if self.blue_time_label is not None:
                self.blue_time_label.configure(text=timeformat)
            time.sleep(1)
            ctime += 1

    def bunker(self) -> None:
        self.clear_frame()
        tk.Label(self.root, fg="green", bg="black", text="Bunker:", font=("Ubuntu", 50)).pack()
        tk.Label(self.root, fg="green", bg="black", text="Blue:", font=("Ubuntu", 90)).place(x=10, y=180)
        tk.Label(self.root, fg="green", bg="black", text="Red:", font=("Ubuntu", 90)).place(x=25, y=340)

        self.blue_time_label = tk.Label(self.root, fg="green", bg="black", text="00:00", font=("Ubuntu", 90))
        self.blue_time_label.place(x=320, y=180)

        self.red_time_label = tk.Label(self.root, fg="green", bg="black", text="00:00", font=("Ubuntu", 90))
        self.red_time_label.place(x=320, y=340)

        self.info_label = tk.Label(self.root, fg="green", bg="black", text="", font=("Ubuntu", 30))
        self.info_label.place(x=10, y=350)
        self.root.update()


def main() -> None:
    audio_enabled = read_audio_setting(CONFIG_PATH, default=True)
    LogicWindow(audio_enabled)


if __name__ == "__main__":
    main()
