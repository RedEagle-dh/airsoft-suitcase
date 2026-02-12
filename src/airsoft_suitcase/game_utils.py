import csv
import logging
import os
import random
import shutil
import subprocess
from contextlib import suppress
from pathlib import Path
from typing import Iterable, Optional, Tuple, Union

try:
    import pygame
except ImportError:
    pygame = None

logger = logging.getLogger(__name__)

KEYPAD_CHARACTERS: Tuple[str, ...] = tuple("0123456789ABCD")
EXIT_CODE: str = "6969"

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
ASSETS_DIR: Path = PROJECT_ROOT / "assets"
CONFIG_PATH: Path = PROJECT_ROOT / "config" / "config.csv"

AUDIO_FILES = {
    "Boom": ASSETS_DIR / "audio" / "boom.mp3",
    "Arm": ASSETS_DIR / "audio" / "arm.mp3",
    "Defuse": ASSETS_DIR / "audio" / "defuse.mp3",
}

VALID_KEYS = set(KEYPAD_CHARACTERS)
_AUDIO_BACKEND = "none"


def is_truthy(value: Optional[str]) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def initialize_audio() -> bool:
    global _AUDIO_BACKEND
    _AUDIO_BACKEND = "none"

    if pygame is None:
        if shutil.which("mpg123"):
            _AUDIO_BACKEND = "mpg123"
            return True
        return False
    if is_truthy(os.getenv("AIRSOFT_DISABLE_AUDIO")):
        return False
    if is_truthy(os.getenv("AIRSOFT_SIMULATE_GPIO")) and not is_truthy(
        os.getenv("AIRSOFT_ENABLE_AUDIO_IN_SIM")
    ):
        return False

    try:
        pygame.init()
    except Exception:
        logger.warning("pygame.init() failed", exc_info=True)
        return False

    configured_device = (os.getenv("AIRSOFT_AUDIO_DEVICE") or "").strip()
    attempts = []
    if configured_device:
        attempts.append({"devicename": configured_device})
    attempts.append({})
    attempts.append({"devicename": "default"})
    attempts.append({"devicename": "0"})

    for kwargs in attempts:
        try:
            with suppress(Exception):
                if pygame.mixer.get_init():
                    pygame.mixer.quit()
            pygame.mixer.init(**kwargs)
            _AUDIO_BACKEND = "pygame"
            return True
        except TypeError:
            # Older pygame builds may not support the devicename kwarg.
            if kwargs:
                continue
            logger.warning("pygame.mixer.init() failed", exc_info=True)
            return False
        except Exception:
            logger.warning("pygame.mixer.init() attempt failed (%s)", kwargs or "default", exc_info=True)

    if shutil.which("mpg123"):
        logger.warning("pygame mixer unavailable; falling back to mpg123")
        _AUDIO_BACKEND = "mpg123"
        return True

    return False


def play_audio(name: str, enabled: bool) -> None:
    if not enabled:
        return
    audio_file = AUDIO_FILES.get(name)
    if audio_file is None:
        return

    if _AUDIO_BACKEND == "pygame" and pygame is not None:
        try:
            pygame.mixer.music.load(str(audio_file))
            pygame.mixer.music.play()
        except Exception:
            logger.warning("Audio playback failed for %s", name, exc_info=True)
        return

    if _AUDIO_BACKEND == "mpg123":
        try:
            subprocess.Popen(
                ["mpg123", "-q", str(audio_file)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            logger.warning("mpg123 playback failed for %s", name, exc_info=True)


def generate_code(length: int, charset: Iterable[str] = KEYPAD_CHARACTERS) -> str:
    if length <= 0:
        return ""
    values = tuple(charset)
    if not values:
        raise ValueError("charset must contain at least one character")
    return "".join(random.choice(values) for _ in range(length))


def read_audio_setting(config_path: Union[str, Path], default: bool = True) -> bool:
    path = Path(config_path)
    if not path.exists():
        return default

    try:
        with path.open(newline="") as csv_file:
            csv_reader = csv.reader(csv_file, delimiter=",")
            for row in csv_reader:
                for column in row:
                    key, separator, value = column.partition(":")
                    if separator and key.strip().lower() == "audio":
                        return value.strip().lower() not in {"false", "0", "no", "off"}
    except Exception:
        logger.warning("Failed to read config from %s", config_path, exc_info=True)
        return default

    return default
