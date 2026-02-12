# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Interactive airsoft game system for Raspberry Pi. Python application with three game modes (Bombe/Bomb, Bunker, Flagge/Flag) controlled via a 4x4 matrix keypad with NeoPixel LED and GPIO feedback. Supports Tkinter GUI, web preview, and headless console modes.

## Commands

```bash
# Install in dev mode
pip install -e ".[dev]"

# Run the application (auto-detects UI mode)
python -m airsoft_suitcase

# Lint
ruff check src tests scripts
ruff format --check src tests scripts

# Run all tests
pytest

# Run a single test file or class
pytest tests/test_game_utils.py
pytest tests/test_led.py::TestLedSimulation::test_pixel_fill
```

## Environment Variables

| Variable | Purpose |
|---|---|
| `AIRSOFT_UI` | UI mode: `tk`, `web`, `console`, `auto` |
| `AIRSOFT_HEADLESS` | Force console mode |
| `AIRSOFT_SIMULATE_GPIO` | Simulate GPIO (no Raspberry Pi hardware needed) |
| `AIRSOFT_LOG_GPIO` | Log GPIO operations |
| `AIRSOFT_DISABLE_AUDIO` | Disable audio playback |
| `AIRSOFT_ENABLE_AUDIO_IN_SIM` | Enable audio even in simulation mode |
| `AIRSOFT_WEB_PORT` | Web server port (default 4311) |
| `AIRSOFT_NO_BROWSER` | Don't auto-open browser in web mode |
| `AIRSOFT_NFC_AUTO_UNLOCK` | Auto-unlock bomb in hard mode |

Tests automatically set `AIRSOFT_SIMULATE_GPIO=1`.

## Architecture

- **`src/airsoft_suitcase/main.py`** — Tkinter GUI (`LogicWindow` class). State machine driving all three game modes with `_start_*()`, `_tick_*()`, `_finish_*()` method patterns.
- **`src/airsoft_suitcase/console_main.py`** — Headless/console mode alternative.
- **`src/airsoft_suitcase/game_utils.py`** — Shared utilities: code generation, audio playback, config reading, constants.
- **`src/airsoft_suitcase/hardware/led.py`** — GPIO LED + NeoPixel stripe control with thread-based blinkers. Gracefully falls back to simulation stubs (`_NoopGPIO`, `_NoopNeoPixel`) when hardware is unavailable.
- **`src/airsoft_suitcase/hardware/keypad_adapter.py`** — 4x4 matrix keypad scanner, translates GPIO reads into keyboard events via pynput.
- **`web/`** — Browser-based preview that mirrors the Python game logic in JavaScript (`app.js`).
- **`config/config.csv`** — Runtime config (colon-separated key:value pairs, currently just `Audio:True`).

## Key Patterns

- **State machine game modes**: Bombe uses states `idle → await_nfc → await_code → countdown → await_reentry → locked → ended`. Bunker and Flagge have simpler flows.
- **GPIO simulation**: All hardware access is behind an abstraction that auto-detects whether real GPIO is available and falls back to no-op stubs.
- **Threading**: LED blinkers and audio run in daemon threads with stop flags for cleanup.
- **UI text is in German** ("Spielauswahl", "Bombe", "Bunker", "Flagge", etc.).
- **Input mapping**: Blue key = Return/KP_Enter (confirm), Red key = Delete/BackSpace (cancel), Hash (#) held 3s = return to menu, Star (*) = bunker signal.

## Code Style

- Python 3.9+, line length 120, ruff for linting/formatting.
- Ruff rules: E, F, W, I, N, UP, B, SIM (ignores UP006, UP035; scripts/ ignores E402, I001).
- Type annotations on all functions. Avoid `any` types — use proper types, `Optional`, `Union`, or `object` where semantically appropriate.
