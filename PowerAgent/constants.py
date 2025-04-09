# ========================================
# 文件名: PowerAgent/constants.py
# -----------------------------------------------------------------------
# constants.py
# -*- coding: utf-8 -*-

from PySide6.QtGui import QColor

# --- Application Constants ---
APP_NAME = "PowerAgent"
ORG_NAME = "YourOrgName" # Change if desired
SETTINGS_APP_NAME = "PowerAgent" # Used for QSettings and auto-start identifiers

# --- UI Colors (Static Definitions) ---

# Dark Theme Colors
_DARK = {
    # ============================================================= #
    # <<< User 改为绿色，Model 改为浅蓝色 >>>
    "user": QColor(144, 238, 144),  # LightGreen
    "model": QColor(173, 216, 230), # lightblue
    # ============================================================= #
    "system": QColor("lightGray"),
    "error": QColor("red"),
    "help": QColor(173, 216, 230), # lightblue
    "prompt": QColor("magenta"),
    "ai_cmd_echo": QColor(255, 165, 0), # orange (DEPRECATED in favor of model color for AI echo)
    "cli_cmd_echo": QColor(173, 216, 230), # lightblue (DEPRECATED in favor of user color for manual echo)
    "cli_output": QColor("white"),
    "cli_error": QColor(255, 100, 100), # light red
    "cli_bg": QColor(40, 40, 40), # dark gray
    "status_label": QColor("lightgrey"),
    "cwd_label": QColor("lightgrey"),
    "border": QColor(60, 60, 60),
    "text_main": QColor(235, 235, 235),
}

# Light Theme Colors
_LIGHT = {
    # ============================================================= #
    # <<< User 改为绿色，Model 改为浅蓝色 (选择对比度合适的颜色) >>>
    "user": QColor("green"),          # Dark Green for contrast
    "model": QColor("blue"),          # Blue for contrast
    # ============================================================= #
    "system": QColor(80, 80, 80),     # Darker Gray for better contrast
    "error": QColor(200, 0, 0),       # Dark Red
    "help": QColor(0, 0, 150),        # Dark Blue
    "prompt": QColor(150, 0, 150),    # Dark Magenta
    "ai_cmd_echo": QColor(200, 100, 0), # Darker Orange (DEPRECATED)
    "cli_cmd_echo": QColor(0, 0, 150),   # Dark Blue (DEPRECATED)
    "cli_output": QColor("black"),
    "cli_error": QColor(200, 0, 0),   # Dark Red (same as error color)
    "cli_bg": QColor(245, 245, 245), # Very light gray
    "status_label": QColor("darkslategrey"),
    "cwd_label": QColor("darkslategrey"),
    "border": QColor(190, 190, 190),
    "text_main": QColor(0, 0, 0),
}

def get_color(color_name: str, theme: str = "dark") -> QColor:
    """
    Gets the QColor for a specific element based on the current theme.

    Args:
        color_name: The name of the color element (e.g., 'user', 'cli_bg').
        theme: The current theme ('dark' or 'light').

    Returns:
        The corresponding QColor. Defaults to black if name/theme invalid.
    """
    theme_dict = _LIGHT if theme == "light" else _DARK
    default_color = _LIGHT.get("text_main") if theme == "light" else _DARK.get("text_main", QColor("white"))
    return theme_dict.get(color_name, default_color)