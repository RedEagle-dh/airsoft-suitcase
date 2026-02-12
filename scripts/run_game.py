import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from airsoft_suitcase.game_utils import is_truthy  # noqa: E402


def _tk_runtime_available():
    check = subprocess.run(
        [
            sys.executable,
            "-c",
            "import tkinter as tk; root = tk.Tk(); root.withdraw(); root.destroy()",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=5,
        check=False,
    )
    return check.returncode == 0

if __name__ == "__main__":
    ui_mode = os.getenv("AIRSOFT_UI", "auto").strip().lower()
    force_headless = is_truthy(os.getenv("AIRSOFT_HEADLESS"))
    if ui_mode == "tk":
        from airsoft_suitcase.main import main

        main()
    elif ui_mode == "web":
        from airsoft_suitcase.web_preview import main as web_main

        web_main()
    elif ui_mode == "console" or force_headless:
        os.environ.setdefault("AIRSOFT_DISABLE_AUDIO", "1")
        from airsoft_suitcase.console_main import main as console_main

        console_main()
    elif _tk_runtime_available():
        from airsoft_suitcase.main import main

        main()
    else:
        print("[BOOT] Tk GUI is not usable on this Python/macOS runtime.")
        print("[BOOT] Falling back to web preview renderer.")
        from airsoft_suitcase.web_preview import main as web_main

        web_main()
