from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from airsoft_suitcase.hardware import keypad_adapter

if __name__ == "__main__":
    try:
        keypad_adapter.run()
    except KeyboardInterrupt:
        keypad_adapter.GPIO.cleanup()
