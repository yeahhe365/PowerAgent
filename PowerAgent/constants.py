# ========================================
# 文件名: PowerAgent/constants.py
# -----------------------------------------------------------------------
# constants.py
# -*- coding: utf-8 -*-

from PySide6.QtGui import QColor

# --- Application Constants ---
APP_NAME = "PowerAgent"  # <<< MODIFIED
ORG_NAME = "YourOrgName" # Change if desired
SETTINGS_APP_NAME = "PowerAgent" # <<< MODIFIED - Used for QSettings and auto-start identifiers

# --- UI Colors (Static Definitions) ---

# Dark Theme Colors
_DARK = {
    "user": QColor("cyan"),
    "model": QColor("yellow"),
    "system": QColor("lightGray"),
    "error": QColor("red"),
    "help": QColor(173, 216, 230), # lightblue
    "prompt": QColor("magenta"),
    "ai_cmd_echo": QColor(255, 165, 0), # orange
    "cli_cmd_echo": QColor(173, 216, 230), # lightblue
    "cli_output": QColor("white"),
    "cli_error": QColor(255, 100, 100), # light red
    # ============================================================= #
    # <<< 修改这里: 将 CLI 背景色从深蓝色改为深灰色 >>>
    # 原来的值: QColor(1, 36, 86), # dark blue
    "cli_bg": QColor(40, 40, 40), # dark gray (changed from blue)
    # ============================================================= #
    "status_label": QColor("lightgrey"),
    "cwd_label": QColor("lightgrey"),
    "border": QColor(60, 60, 60),
    "text_main": QColor(235, 235, 235),
}

# Light Theme Colors
_LIGHT = {
    "user": QColor(0, 100, 150),      # Dark Blue/Teal
    "model": QColor(0, 128, 0),       # Dark Green
    "system": QColor(80, 80, 80),     # Darker Gray for better contrast
    "error": QColor(200, 0, 0),       # Dark Red
    "help": QColor(0, 0, 150),        # Dark Blue
    "prompt": QColor(150, 0, 150),    # Dark Magenta
    "ai_cmd_echo": QColor(200, 100, 0), # Darker Orange
    "cli_cmd_echo": QColor(0, 0, 150),   # Dark Blue
    "cli_output": QColor("black"),
    "cli_error": QColor(200, 0, 0),   # Dark Red (same as error color)
    "cli_bg": QColor(245, 245, 245), # Very light gray
    "status_label": QColor("darkslategrey"),
    "cwd_label": QColor("darkslategrey"),
    "border": QColor(190, 190, 190),
    "text_main": QColor(0, 0, 0),
}

# <<< GUI OPTIMIZATION: Central function to get theme-specific colors >>>
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

# No more dynamic global color variables here.
# UI elements will call get_color() when they need a color.