import logging
import os
import threading
import time
from typing import Optional, Tuple

from ..game_utils import is_truthy

logger = logging.getLogger(__name__)


class _NoopGPIO:
    BCM = 0
    OUT = 0

    @staticmethod
    def setwarnings(*_args: object, **_kwargs: object) -> None:
        return None

    @staticmethod
    def setmode(*_args: object, **_kwargs: object) -> None:
        return None

    @staticmethod
    def setup(*_args: object, **_kwargs: object) -> None:
        return None

    @staticmethod
    def output(*_args: object, **_kwargs: object) -> None:
        return None


class _NoopBoard:
    D18 = None


class _NoopNeoPixel:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        pass

    def fill(self, _rgb: Tuple[int, int, int]) -> None:
        pass


class _NoopNeopixelModule:
    NeoPixel = _NoopNeoPixel


try:
    import board
except (ImportError, NotImplementedError):
    board = _NoopBoard()  # type: ignore[assignment]

try:
    import neopixel
except (ImportError, NotImplementedError):
    neopixel = _NoopNeopixelModule()  # type: ignore[assignment]

try:
    import RPi.GPIO as GPIO
except (ImportError, NotImplementedError):
    GPIO = _NoopGPIO()  # type: ignore[assignment]


class Led:
    RED_PIN = 20
    BLUE_PIN = 23
    STRIPE_PIXEL_PIN = getattr(board, "D18", None)
    STRIPE_PIXEL_COUNT = 55

    def __init__(self) -> None:
        force_simulation = is_truthy(os.getenv("AIRSOFT_SIMULATE_GPIO"))
        board_missing = isinstance(board, _NoopBoard)
        gpio_missing = isinstance(GPIO, _NoopGPIO)

        self._simulate_gpio = force_simulation or board_missing or gpio_missing
        self._log_gpio = self._simulate_gpio or is_truthy(os.getenv("AIRSOFT_LOG_GPIO"))
        self._simulation_reason = self._build_simulation_reason(force_simulation, board_missing, gpio_missing)

        self._gpio = _NoopGPIO() if self._simulate_gpio else GPIO
        self._pixel: object = _NoopNeoPixel()

        self._gpio.setwarnings(False)
        self._gpio.setmode(self._gpio.BCM)
        self._gpio.setup(self.RED_PIN, self._gpio.OUT)
        self._gpio.setup(self.BLUE_PIN, self._gpio.OUT)

        if not self._simulate_gpio:
            try:
                self._pixel = neopixel.NeoPixel(self.STRIPE_PIXEL_PIN, self.STRIPE_PIXEL_COUNT, brightness=1)
            except Exception as exc:
                self._simulate_gpio = True
                self._log_gpio = True
                self._simulation_reason = f"NeoPixel init failed: {exc}"
                self._gpio = _NoopGPIO()
                self._pixel = _NoopNeoPixel()
        else:
            self._pixel = _NoopNeoPixel()

        self._state_lock = threading.Lock()

        # Stripe blinker state
        self._stripe_blinker_thread: Optional[threading.Thread] = None
        self._stripe_rgb: Tuple[int, int, int] = (0, 0, 0)
        self._stripe_blinker_stop = False
        self._stripe_interval = 1.0
        self._stripe_blinker_is_alive = False

        # Blue blinker state
        self._blue_blinker_thread: Optional[threading.Thread] = None
        self._blue_blinker_stop = False
        self._blue_blinker_interval = 1.0
        self._blue_blinker_is_alive = False

        # Red blinker state
        self._red_blinker_thread: Optional[threading.Thread] = None
        self._red_blinker_stop = False
        self._red_blinker_interval = 1.0
        self._red_blinker_is_alive = False

        if self._simulate_gpio:
            self._log(f"Simulation mode active ({self._simulation_reason}).")
            self._log("GPIO and LED operations are printed; no hardware is controlled.")

    def _build_simulation_reason(
        self, force_simulation: bool, board_missing: bool, gpio_missing: bool
    ) -> str:
        if force_simulation:
            return "forced by AIRSOFT_SIMULATE_GPIO"
        reasons = []
        if board_missing:
            reasons.append("board backend unavailable")
        if gpio_missing:
            reasons.append("RPi.GPIO unavailable")
        if not reasons:
            return "unknown"
        return ", ".join(reasons)

    def _log(self, message: str) -> None:
        if self._log_gpio:
            print(f"[GPIO-SIM] {message}")

    # Simple controls

    def stop_all_blinkers(self) -> None:
        self._log("Stop all blinkers")
        self.stop_red_blinker()
        self.stop_blue_blinker()
        self.stop_stripe_blinker()

    def turn_off_all(self) -> None:
        self._log("Turn off all outputs")
        self.turn_off_red()
        self.pixel_fill((0, 0, 0))
        self.turn_off_blue()

    def turn_red_on(self) -> None:
        self._gpio.output(self.RED_PIN, True)
        self._log(f"Pin {self.RED_PIN} (RED) -> ON")

    def turn_blue_on(self) -> None:
        self._gpio.output(self.BLUE_PIN, True)
        self._log(f"Pin {self.BLUE_PIN} (BLUE) -> ON")

    def turn_off_blue(self) -> None:
        self._gpio.output(self.BLUE_PIN, False)
        self._log(f"Pin {self.BLUE_PIN} (BLUE) -> OFF")

    def turn_off_red(self) -> None:
        self._gpio.output(self.RED_PIN, False)
        self._log(f"Pin {self.RED_PIN} (RED) -> OFF")

    def stripe_off(self) -> None:
        self._pixel.fill((0, 0, 0))
        self._log("LED stripe -> OFF")

    def pixel_fill(self, rgb: Tuple[int, int, int]) -> None:
        color = self._normalize_rgb(rgb)
        self._pixel.fill(color)
        self._stripe_rgb = color
        self._log(f"LED stripe fill -> {color}")

    # Blue blinker

    def get_blue_is_alive(self) -> bool:
        return self._blue_blinker_is_alive

    def get_red_is_alive(self) -> bool:
        return self._red_blinker_is_alive

    def set_blue_interval(self, interval: float) -> None:
        self._blue_blinker_interval = max(float(interval), 0.01)
        self._log(f"Blue blinker interval -> {self._blue_blinker_interval:.2f}s")

    def start_blue_blinker(self) -> None:
        with self._state_lock:
            if self._blue_blinker_is_alive:
                self._log("Blue blinker already running")
                return
            self._blue_blinker_stop = False
            self._blue_blinker_thread = threading.Thread(target=self._blue_blinker, daemon=True)
            self._blue_blinker_thread.start()
            self._blue_blinker_is_alive = True
            self._log(f"Blue blinker started (interval {self._blue_blinker_interval:.2f}s)")

    def _blue_blinker(self) -> None:
        while not self._blue_blinker_stop:
            self._gpio.output(self.BLUE_PIN, True)
            time.sleep(self._blue_blinker_interval / 2)
            self._gpio.output(self.BLUE_PIN, False)
            time.sleep(self._blue_blinker_interval / 2)

    def stop_blue_blinker(self) -> None:
        self._blue_blinker_stop = True
        self._safe_join(self._blue_blinker_thread)
        self._blue_blinker_is_alive = False
        self._blue_blinker_stop = False
        self._log("Blue blinker stopped")

    # Red blinker

    def set_red_interval(self, interval: float) -> None:
        self._red_blinker_interval = max(float(interval), 0.01)
        self._log(f"Red blinker interval -> {self._red_blinker_interval:.2f}s")

    def start_red_blinker(self) -> None:
        with self._state_lock:
            if self._red_blinker_is_alive:
                self._log("Red blinker already running")
                return
            self._red_blinker_stop = False
            self._red_blinker_thread = threading.Thread(target=self._red_blinker, daemon=True)
            self._red_blinker_thread.start()
            self._red_blinker_is_alive = True
            self._log(f"Red blinker started (interval {self._red_blinker_interval:.2f}s)")

    def _red_blinker(self) -> None:
        while not self._red_blinker_stop:
            self._gpio.output(self.RED_PIN, True)
            time.sleep(self._red_blinker_interval / 2)
            self._gpio.output(self.RED_PIN, False)
            time.sleep(self._red_blinker_interval / 2)

    def stop_red_blinker(self) -> None:
        self._red_blinker_stop = True
        self._safe_join(self._red_blinker_thread)
        self._red_blinker_stop = False
        self._red_blinker_is_alive = False
        self._log("Red blinker stopped")

    # Stripe blinker

    def get_stripe_blinker_alive(self) -> bool:
        return self._stripe_blinker_is_alive

    def set_rgb(self, rgb: Tuple[int, int, int]) -> None:
        self._stripe_rgb = self._normalize_rgb(rgb)
        self._log(f"Stripe base RGB -> {self._stripe_rgb}")

    def set_stripe_interval(self, interval: float) -> None:
        self._stripe_interval = max(float(interval), 0.01)
        self._log(f"Stripe blinker interval -> {self._stripe_interval:.2f}s")

    def start_stripe_blinker(self, pulse: bool) -> None:
        with self._state_lock:
            if self._stripe_blinker_is_alive:
                self._log("Stripe blinker already running")
                return
            self._stripe_blinker_stop = False
            target = self._pulse_stripe if pulse else self._stripe_blinker
            self._stripe_blinker_thread = threading.Thread(target=target, daemon=True)
            self._stripe_blinker_thread.start()
            self._stripe_blinker_is_alive = True
            mode = "pulse" if pulse else "blink"
            self._log(f"Stripe blinker started (mode={mode}, interval {self._stripe_interval:.2f}s)")

    def _pulse_stripe(self) -> None:
        intensity = 1.0
        direction = -1
        while not self._stripe_blinker_stop:
            color = tuple(int(channel * intensity) for channel in self._stripe_rgb)
            self._pixel.fill(color)
            time.sleep(0.1)

            intensity += direction * 0.1
            if intensity <= 0.1:
                intensity = 0.1
                direction = 1
            elif intensity >= 1.0:
                intensity = 1.0
                direction = -1

    def stop_stripe_blinker(self) -> None:
        self._stripe_blinker_stop = True
        self._safe_join(self._stripe_blinker_thread)
        self._stripe_blinker_stop = False
        self._stripe_blinker_is_alive = False
        self._log("Stripe blinker stopped")

    def _stripe_blinker(self) -> None:
        while not self._stripe_blinker_stop:
            self._pixel.fill(self._stripe_rgb)
            time.sleep(self._stripe_interval / 2)
            self._pixel.fill((0, 0, 0))
            time.sleep(self._stripe_interval / 2)

    def _safe_join(self, thread: Optional[threading.Thread]) -> None:
        if thread is None:
            return
        if thread is threading.current_thread():
            return
        try:
            thread.join(timeout=2)
        except Exception:
            logger.warning("Thread join failed", exc_info=True)

    def _normalize_rgb(self, rgb: Tuple[int, int, int]) -> Tuple[int, int, int]:
        if len(rgb) != 3:
            raise ValueError("rgb must contain exactly 3 values")
        return tuple(max(0, min(int(channel), 255)) for channel in rgb)  # type: ignore[return-value]

    def __del__(self) -> None:
        try:
            self.stop_all_blinkers()
            self.turn_off_all()
        except Exception:
            pass
