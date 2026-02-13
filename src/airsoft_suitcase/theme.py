"""Military/tactical theme constants for the Tkinter UI."""

from typing import Tuple

# --- Colors (uniform green palette) ---
BG_PRIMARY: str = "#050b05"  # Root background (near-black, green tint)
BG_PANEL: str = "#0e150e"  # Header/footer bar backgrounds
BG_SCREEN: str = "#000000"  # Main content area
BORDER_COLOR: str = "#1e7f2f"  # Panel borders, separator lines
TEXT_PRIMARY: str = "#29ff55"  # Main text
TEXT_DIM: str = "#1a8a35"  # Hints, secondary info
TEXT_HEADER: str = "#3bff6e"  # Title text (slightly brighter)
TEXT_ALERT: str = "#ff2222"  # Locked/ended states

# --- Font family ---
FONT_FAMILY: str = "Liberation Mono"

# --- Font specs (family, size[, weight]) ---
FONT_TITLE: Tuple[str, int, str] = (FONT_FAMILY, 42, "bold")
FONT_SUBTITLE: Tuple[str, int, str] = (FONT_FAMILY, 28, "bold")
FONT_BODY: Tuple[str, int] = (FONT_FAMILY, 24)
FONT_BODY_LARGE: Tuple[str, int] = (FONT_FAMILY, 32)
FONT_TIMER: Tuple[str, int, str] = (FONT_FAMILY, 48, "bold")
FONT_TIMER_LARGE: Tuple[str, int, str] = (FONT_FAMILY, 64, "bold")
FONT_CODE: Tuple[str, int] = (FONT_FAMILY, 16)
FONT_INPUT: Tuple[str, int] = (FONT_FAMILY, 28)
FONT_HINT: Tuple[str, int] = (FONT_FAMILY, 16)
FONT_MENU_OPTION: Tuple[str, int, str] = (FONT_FAMILY, 34, "bold")
FONT_FOOTER: Tuple[str, int] = (FONT_FAMILY, 22)
FONT_FLAG_TEAM: Tuple[str, int, str] = (FONT_FAMILY, 100, "bold")

# --- Layout ---
PANEL_BORDER_WIDTH: int = 2
PANEL_PADX: int = 16
PANEL_PADY: int = 12
HEADER_BAR_HEIGHT: int = 52
FOOTER_BAR_HEIGHT: int = 44
OUTER_PAD: int = 4
