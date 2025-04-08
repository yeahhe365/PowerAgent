# ========================================
# 文件名: PowerAgent/gui/palette.py
# -----------------------------------------------------------------------
# gui/palette.py
# -*- coding: utf-8 -*-

from PySide6.QtGui import QPalette, QColor
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

# Import get_color (though it might be less used now for system theme)
from constants import get_color

# --- Dark Theme ---
def setup_dark_palette(app: QApplication):
    """Configures and applies a dark Fusion style palette to the QApplication."""
    app.setStyle("Fusion") # Ensure Fusion style is set for dark theme
    dark_palette = QPalette()
    theme = "dark"

    # Define colors using get_color for consistency with other parts
    COLOR_WINDOW_BG = QColor(53, 53, 53)
    COLOR_BASE_BG = QColor(42, 42, 42)
    COLOR_TEXT = get_color("text_main", theme)
    COLOR_BUTTON_BG = QColor(70, 70, 70)
    COLOR_HIGHLIGHT = QColor(42, 130, 218)
    COLOR_HIGHLIGHTED_TEXT = QColor(255, 255, 255)
    COLOR_DISABLED_TEXT = QColor(127, 127, 127)

    # General Colors
    dark_palette.setColor(QPalette.ColorRole.Window, COLOR_WINDOW_BG)
    dark_palette.setColor(QPalette.ColorRole.WindowText, COLOR_TEXT)
    dark_palette.setColor(QPalette.ColorRole.Base, COLOR_BASE_BG)
    dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(60, 60, 60))
    dark_palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(20, 20, 20))
    dark_palette.setColor(QPalette.ColorRole.ToolTipText, COLOR_TEXT)
    dark_palette.setColor(QPalette.ColorRole.Text, COLOR_TEXT)
    dark_palette.setColor(QPalette.ColorRole.Button, COLOR_BUTTON_BG)
    dark_palette.setColor(QPalette.ColorRole.ButtonText, COLOR_TEXT)
    dark_palette.setColor(QPalette.ColorRole.BrightText, get_color("error", theme))
    dark_palette.setColor(QPalette.ColorRole.Link, COLOR_HIGHLIGHT)
    dark_palette.setColor(QPalette.ColorRole.Highlight, COLOR_HIGHLIGHT)
    dark_palette.setColor(QPalette.ColorRole.HighlightedText, COLOR_HIGHLIGHTED_TEXT)

    # Disabled Colors
    dark_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, COLOR_DISABLED_TEXT)
    dark_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, COLOR_DISABLED_TEXT)
    dark_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, COLOR_DISABLED_TEXT)
    dark_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, COLOR_WINDOW_BG)
    dark_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button, QColor(53,53,53))
    dark_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, QColor(80, 80, 80))
    dark_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.HighlightedText, COLOR_DISABLED_TEXT)

    app.setPalette(dark_palette)
    print("Dark theme global palette applied.")


# --- Light Theme ---
def setup_light_palette(app: QApplication):
    """Configures and applies a light Fusion style palette to the QApplication."""
    app.setStyle("Fusion") # Ensure Fusion style is set for light theme
    light_palette = QPalette()
    theme = "light"

    # Use standard light theme colors or get from constants if needed
    COLOR_WINDOW_BG = QColor(240, 240, 240)
    COLOR_BASE_BG = QColor(240, 240, 240) # Modified light gray base
    COLOR_TEXT = get_color("text_main", theme) # Black
    COLOR_BUTTON_BG = QColor(225, 225, 225)
    COLOR_HIGHLIGHT = QColor(51, 153, 255)
    COLOR_HIGHLIGHTED_TEXT = QColor(255, 255, 255)
    COLOR_DISABLED_TEXT = QColor(160, 160, 160)

    # General Colors
    light_palette.setColor(QPalette.ColorRole.Window, COLOR_WINDOW_BG)
    light_palette.setColor(QPalette.ColorRole.WindowText, COLOR_TEXT)
    light_palette.setColor(QPalette.ColorRole.Base, COLOR_BASE_BG)
    light_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(233, 233, 233))
    light_palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 220))
    light_palette.setColor(QPalette.ColorRole.ToolTipText, COLOR_TEXT)
    light_palette.setColor(QPalette.ColorRole.Text, COLOR_TEXT)
    light_palette.setColor(QPalette.ColorRole.Button, COLOR_BUTTON_BG)
    light_palette.setColor(QPalette.ColorRole.ButtonText, COLOR_TEXT)
    light_palette.setColor(QPalette.ColorRole.BrightText, get_color("error", theme))
    light_palette.setColor(QPalette.ColorRole.Link, COLOR_HIGHLIGHT)
    light_palette.setColor(QPalette.ColorRole.Highlight, COLOR_HIGHLIGHT)
    light_palette.setColor(QPalette.ColorRole.HighlightedText, COLOR_HIGHLIGHTED_TEXT)

    # Disabled Colors
    light_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, COLOR_DISABLED_TEXT)
    light_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, COLOR_DISABLED_TEXT)
    light_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, COLOR_DISABLED_TEXT)
    light_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, COLOR_BASE_BG) # Match modified base
    light_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button, QColor(225, 225, 225))
    light_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, QColor(190, 190, 190))
    light_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.HighlightedText, COLOR_DISABLED_TEXT)

    app.setPalette(light_palette)
    print("Light theme global palette applied (with gray base background).")


# --- Unified Setup Function ---
# <<< 修改: 处理 "system" 主题 >>>
def setup_palette(app: QApplication, theme_name: str = "system"):
    """Applies the specified theme palette (dark, light, or system default)."""
    # Set a consistent style first. Fusion is a good cross-platform choice.
    # Removing this might make it use the *native* system style (e.g., Windows style on Win),
    # which might be desirable for a true "system" feel, but can vary visually.
    # Let's keep Fusion for now for predictable behavior across platforms.
    app.setStyle("Fusion")

    if theme_name == "light":
        setup_light_palette(app)
    elif theme_name == "dark":
        setup_dark_palette(app)
    else: # Handle "system" or any other unknown value
        if theme_name != "system":
            print(f"Warning: Unknown theme '{theme_name}' requested. Using system default palette.")
        # For the system theme, we *don't* call app.setPalette() with our custom one.
        # Qt's default behavior when a style is set but no specific palette is applied
        # is to derive a palette appropriate for that style and the system's settings.
        # We can explicitly reset it to the application's default, but often just not setting it works.
        # app.setPalette(QApplication.style().standardPalette()) # Alternative: Explicit reset
        print("Using system default palette (no custom palette applied).")