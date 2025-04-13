# ========================================
# 文件名: PowerAgent/constants.py
# (No structural changes needed, ensure 'ai_command' color exists)
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
    # --- Added color for keyboard actions ---
    "keyboard_action": QColor(255, 165, 0), # orange
    # --- Added background color for keyboard actions ---
    "keyboard_action_bg": QColor(65, 65, 65), # Slightly lighter dark gray
    # <<< ADDED: Color for AI command echo in chat >>>
    "ai_command": QColor(0, 255, 255), # Cyan <<<< ENSURE THIS EXISTS
    # --- Deprecated colors ---
    "ai_cmd_echo": QColor(255, 165, 0), # orange (DEPRECATED)
    "cli_cmd_echo": QColor(173, 216, 230), # lightblue (DEPRECATED)
    # --- CLI Colors ---
    "cli_output": QColor("white"),
    "cli_error": QColor(255, 100, 100), # light red
    "cli_bg": QColor(40, 40, 40), # dark gray
    # --- Other UI Colors ---
    "status_label": QColor("lightgrey"),
    "cwd_label": QColor("lightgrey"),
    "border": QColor(60, 60, 60),
    "text_main": QColor(235, 235, 235),
    # --- Added color for timestamp ---
    "timestamp_color": QColor(160, 160, 160), # Gray
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
    # --- Added color for keyboard actions ---
    "keyboard_action": QColor(200, 100, 0), # Darker Orange/Brown
    # --- Added background color for keyboard actions ---
    "keyboard_action_bg": QColor(225, 225, 225), # Light gray background
    # <<< ADDED: Color for AI command echo in chat >>>
    "ai_command": QColor(0, 139, 139), # Dark Cyan <<<< ENSURE THIS EXISTS
    # --- Deprecated colors ---
    "ai_cmd_echo": QColor(200, 100, 0), # Darker Orange (DEPRECATED)
    "cli_cmd_echo": QColor(0, 0, 150),   # Dark Blue (DEPRECATED)
    # --- CLI Colors ---
    "cli_output": QColor("black"),
    "cli_error": QColor(200, 0, 0),   # Dark Red (same as error color)
    "cli_bg": QColor(245, 245, 245), # Very light gray
    # --- Other UI Colors ---
    "status_label": QColor("darkslategrey"),
    "cwd_label": QColor("darkslategrey"),
    "border": QColor(190, 190, 190),
    "text_main": QColor(0, 0, 0),
    # --- Added color for timestamp ---
    "timestamp_color": QColor(105, 105, 105), # DimGray
}

def get_color(color_name: str, theme: str = "dark") -> QColor:
    """
    Gets the QColor for a specific element based on the current theme.

    Args:
        color_name: The name of the color element (e.g., 'user', 'cli_bg', 'keyboard_action', 'ai_command').
        theme: The current theme ('dark' or 'light').

    Returns:
        The corresponding QColor. Defaults to the theme's main text color if name/theme invalid.
    """
    theme_dict = _LIGHT if theme == "light" else _DARK
    # Define the default text color based on the theme
    default_text_color = _LIGHT.get("text_main", QColor("black")) if theme == "light" else _DARK.get("text_main", QColor("white"))
    # Get the color, falling back to the default text color if the name isn't found
    return theme_dict.get(color_name, default_text_color)