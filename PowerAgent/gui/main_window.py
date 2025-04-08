# ========================================
# 文件名: PowerAgent/gui/main_window.py
# -----------------------------------------------------------------------
# gui/main_window.py
# -*- coding: utf-8 -*-

import sys
import os
import json
import platform
import re
from collections import deque

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QPushButton, QSplitter, QLabel, QDialog, QApplication, QFrame,
    QSpacerItem, QSizePolicy, QStatusBar, QToolBar, QCompleter # Keep QCompleter import for now if you plan to add it elsewhere
)
from PySide6.QtCore import Qt, Slot, QSettings, QCoreApplication, QStandardPaths, QSize, QStringListModel, QEvent
from PySide6.QtGui import (
    QTextCursor, QPalette, QFont, QIcon, QColor,
    QAction, QKeySequence, QTextCharFormat
)


# Import from other modules
from constants import APP_NAME, get_color
from core import config # <<< Needs access to config
from core.workers import ApiWorkerThread, ManualCommandThread
from .settings_dialog import SettingsDialog
from .palette import setup_palette
# Import the helper function for decoding subprocess output
from core.workers import _decode_output

# Stylesheet template (Re-added CliPromptLabel styling)
STYLESHEET_TEMPLATE = """
    /* General */
    QMainWindow {{ }}
    QWidget {{
        color: {text_main};
    }}
    QToolBar {{
        border: none;
        padding: 2px;
        spacing: 5px;
    }}
    /* Toolbar Labels */
    QToolBar QLabel#ToolbarCwdLabel,
    QToolBar QLabel#ModelIdLabel,
    QToolBar QLabel#ModeLabel {{
        padding: 0px 5px; /* Same padding for all */
        font-size: 9pt;
        color: {status_label_color};
    }}
    /* Specific Toolbar CWD Label color */
    QToolBar QLabel#ToolbarCwdLabel {{
        color: {cwd_label_color};
    }}
    /* Separator Styling */
    QToolBar QFrame {{
        margin-left: 3px;
        margin-right: 3px;
    }}
    /* Settings Button Padding */
    QToolBar QToolButton {{
        padding-left: 3px;
        padding-right: 5px;
        padding-top: 2px;
        padding-bottom: 2px;
    }}
    /* Status indicator styling is done directly in the code */

    QStatusBar {{
        border-top: 1px solid {border};
    }}

    /* CLI Area Specifics */
    #CliOutput {{
        background-color: {cli_bg};
        color: {cli_output};
        border: 1px solid {border};
        padding: 3px;
        font-family: {mono_font_family};
        font-size: {mono_font_size}pt;
    }}
    #CliInput {{
        background-color: {cli_bg};
        color: {cli_output};
        border: none; /* Input field has no border itself */
        padding: 4px;
        font-family: {mono_font_family};
        font-size: {mono_font_size}pt;
    }}
    #CliInputContainer {{
       border: 1px solid {border};
       background-color: {cli_bg};
       border-radius: 3px;
       /* Container provides the border for the input */
    }}
    #CliInputContainer:focus-within {{
        border: 1px solid {highlight_bg};
    }}
    /* Styling for the Prompt Label inside the container */
    #CliPromptLabel {{
        color: {prompt_color}; /* Use the prompt color */
        padding: 4px 0px 4px 5px; /* Top/Bottom/Left padding like input, NO right padding */
        margin-right: 0px; /* No margin between label and input */
        background-color: {cli_bg}; /* Match container background */
        font-family: {mono_font_family};
        font-size: {mono_font_size}pt;
        font-weight: bold; /* Make prompt stand out slightly */
    }}

    /* Chat Area Specifics */
    #ChatHistoryDisplay {{
        border: 1px solid {border};
        padding: 3px;
    }}
     #ChatInput {{
        border: 1px solid {border};
        padding: 4px;
        border-radius: 3px;
    }}
    #ChatInput:focus {{
         border: 1px solid {highlight_bg};
    }}

    /* Other Widgets */
    QPushButton {{
        padding: 5px 10px;
        border-radius: 3px;
        min-height: 26px;
        background-color: {button_bg};
        color: {button_text};
        border: 1px solid {border};
    }}
    QPushButton:hover {{
        background-color: {highlight_bg};
        color: {highlighted_text};
        border: 1px solid {highlight_bg};
    }}
    QPushButton:pressed {{
        background-color: {button_pressed_bg};
    }}
    QPushButton:disabled {{
        background-color: {button_disabled_bg};
        color: {text_disabled};
        border: 1px solid {border_disabled};
        padding: 5px 10px;
        min-height: 26px;
    }}
    QLabel#StatusLabel {{
        color: {status_label_color};
        font-size: {label_font_size}pt;
        margin-left: 5px;
    }}
    QSplitter::handle {{
        background-color: transparent;
        border: none;
    }}
    QSplitter::handle:horizontal {{
        width: 5px;
        margin: 0 1px;
    }}
    QSplitter::handle:vertical {{
        height: 5px;
        margin: 1px 0;
    }}
    QSplitter::handle:pressed {{
         background-color: {highlight_bg};
    }}
    QToolTip {{
        border: 1px solid {border};
        padding: 3px;
        background-color: {tooltip_bg};
        color: {tooltip_text};
    }}
    #ClearChatButton {{ }}
    #ClearChatButton:hover {{ }}
"""

# Minimal stylesheet (Re-added CliPromptLabel font styling)
MINIMAL_STYLESHEET_SYSTEM_THEME = """
    #CliOutput, #CliInput, #CliPromptLabel {{
        font-family: {mono_font_family};
        font-size: {mono_font_size}pt;
    }}
    #CliInputContainer {{
       border: 1px solid {border};
       border-radius: 3px;
    }}
    #CliInput {{
        border: none;
        padding: 4px;
    }}
     #CliOutput {{
        border: 1px solid {border};
        padding: 3px;
    }}
     #ChatHistoryDisplay {{
        border: 1px solid {border};
        padding: 3px;
    }}
     #ChatInput {{
        border: 1px solid {border};
        padding: 4px;
        border-radius: 3px;
    }}
    QSplitter::handle {{ }}
     QToolTip {{
        border: 1px solid {border};
        padding: 3px;
     }}
    /* Toolbar Labels */
    QToolBar QLabel#ToolbarCwdLabel,
    QToolBar QLabel#ModelIdLabel,
    QToolBar QLabel#ModeLabel {{
        padding: 0px 5px;
        font-size: 9pt;
    }}
    /* Separator Styling */
    QToolBar QFrame {{
        margin-left: 3px;
        margin-right: 3px;
    }}
    QToolBar QToolButton {{
        padding-left: 3px;
        padding-right: 5px;
        padding-top: 2px;
        padding-bottom: 2px;
    }}
    QPushButton {{
        padding: 5px 10px;
        min-height: 26px;
    }}
    QPushButton:disabled {{
        padding: 5px 10px;
        min-height: 26px;
    }}
"""


class MainWindow(QMainWindow):

    def __init__(self, application_base_dir=None, parent=None):
        super().__init__(parent)

        # Determine Application Base Directory
        if application_base_dir: self.application_base_dir = application_base_dir
        elif getattr(sys, 'frozen', False): self.application_base_dir = os.path.dirname(sys.executable)
        else:
            try: main_script_path = os.path.abspath(sys.argv[0]); self.application_base_dir = os.path.dirname(main_script_path)
            except Exception: self.application_base_dir = os.path.dirname(os.path.abspath(__file__))
        print(f"[MainWindow] Using Application Base Directory: {self.application_base_dir}")

        # Set initial CWD based on application dir FIRST
        self.initial_directory = self.application_base_dir
        self.current_directory = self.initial_directory

        # Initialize State Variables
        self.conversation_history = deque(maxlen=50)
        self.current_mode = "suggest"
        self.api_worker_thread = None
        self.manual_cmd_thread = None
        self.settings_dialog_open = False
        self.cli_command_history = deque(maxlen=100)
        self.cli_history_index = -1
        self.toolbar_cwd_label = None; self.model_id_label = None
        self.mode_label = None; self.status_indicator = None
        self.cli_prompt_label = None # Instance variable for the prompt label

        # Load state AFTER setting initial CWD
        try:
            self.load_state() # Tries to load saved CWD, history, etc.
            if os.path.isdir(self.current_directory):
                os.chdir(self.current_directory)
                print(f"Successfully set initial process working directory to: {self.current_directory}")
            else:
                print(f"Warning: Current directory '{self.current_directory}' (loaded or initial) not found. Falling back to CWD.")
                self.current_directory = os.getcwd()
                os.chdir(self.current_directory)
                print(f"Using current working directory as fallback: {self.current_directory}")
        except Exception as e:
            print(f"Warning: Could not change process directory to '{self.current_directory}': {e}")
            self.current_directory = os.getcwd() # Last resort
            print(f"Using fallback process working directory: {self.current_directory}")


        # Basic Window Setup
        self.setWindowTitle(APP_NAME)
        self.setGeometry(100, 100, 850, 585)
        self.set_window_icon()

        # Setup UI Elements
        self.setup_ui()

        # Post-UI Setup
        self.apply_theme_specific_styles() # Applies theme + initial styles
        self.load_and_apply_state() # Applies loaded history to display

        # Set initial mode and status display
        self.update_mode_display()
        self.update_status_indicator(False) # Start idle
        self.update_model_id_display() # Ensure model ID shown initially

        # Add welcome message
        if not self.conversation_history:
             self.add_chat_message("System", f"欢迎使用 {APP_NAME}！输入 '/help' 查看命令。")
             print("[MainWindow] Added initial welcome message as history was empty.")
        else:
             print("[MainWindow] Skipping initial welcome message as history was loaded.")


        # Update CWD label (toolbar) and CLI prompt
        self.update_cwd_label() # Updates toolbar CWD label
        self.update_prompt()    # Updates CLI prompt
        self.cli_input.setFocus()

    def eventFilter(self, watched, event):
        # Handles Shift+Enter in chat input
        if watched == self.chat_input and event.type() == QEvent.Type.KeyPress:
            key = event.key(); modifiers = event.modifiers()
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if not (modifiers & Qt.KeyboardModifier.ShiftModifier):
                    self.handle_send_message()
                    return True # Prevent default newline insertion
                else:
                    pass # Allow default behavior (newline) for Shift+Enter
        return super().eventFilter(watched, event)

    def _get_icon(self, theme_name: str, fallback_filename: str, text_fallback: str = None) -> QIcon:
        # Helper to get themed icons or fallbacks
        icon = QIcon.fromTheme(theme_name)
        if icon.isNull():
            assets_dir = os.path.join(self.application_base_dir, "assets"); icon_path = os.path.join(assets_dir, fallback_filename)
            if os.path.exists(icon_path): icon = QIcon(icon_path);
            if icon.isNull(): print(f"Warning: Icon theme '{theme_name}' not found and fallback '{fallback_filename}' does not exist in {assets_dir}.")
        return icon

    def set_window_icon(self):
        # Sets the main application window icon
        try:
            icon = self._get_icon(APP_NAME.lower(), "icon.png", None) # Try app name first
            if icon.isNull(): icon = self._get_icon("utilities-terminal", "app.ico", None) # Generic terminal icon as fallback
            if not icon.isNull(): self.setWindowIcon(icon)
            else: print("Could not find a suitable window icon via theme or fallback.")
        except Exception as e: print(f"Error setting window icon: {e}")

    def setup_ui(self):
        """Creates and arranges all UI widgets."""
        central_widget = QWidget(); self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget); main_layout.setContentsMargins(5, 5, 5, 5); main_layout.setSpacing(5)

        # --- Toolbar Setup ---
        toolbar = self.addToolBar("Main Toolbar"); toolbar.setObjectName("MainToolBar"); toolbar.setMovable(False); toolbar.setIconSize(QSize(16, 16)); toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        settings_icon = self._get_icon("preferences-system", "settings.png", "⚙️"); settings_action = QAction(settings_icon, "设置", self); settings_action.setToolTip("配置 API、主题、自动启动及其他设置"); settings_action.triggered.connect(self.open_settings_dialog); toolbar.addAction(settings_action)
        spacer = QWidget(); spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred); toolbar.addWidget(spacer)
        self.toolbar_cwd_label = QLabel("..."); self.toolbar_cwd_label.setObjectName("ToolbarCwdLabel"); self.toolbar_cwd_label.setToolTip("当前工作目录"); toolbar.addWidget(self.toolbar_cwd_label)
        cwd_separator = QFrame(); cwd_separator.setFrameShape(QFrame.Shape.VLine); cwd_separator.setFrameShadow(QFrame.Shadow.Sunken); toolbar.addWidget(cwd_separator)
        self.model_id_label = QLabel(f"模型: {config.MODEL_ID or '未配置'}"); self.model_id_label.setObjectName("ModelIdLabel"); self.model_id_label.setToolTip(f"当前使用的 AI 模型 ID: {config.MODEL_ID or '未配置'}"); toolbar.addWidget(self.model_id_label)
        model_separator = QFrame(); model_separator.setFrameShape(QFrame.Shape.VLine); model_separator.setFrameShadow(QFrame.Shadow.Sunken); toolbar.addWidget(model_separator)
        self.mode_label = QLabel(f"模式: {self.current_mode}"); self.mode_label.setObjectName("ModeLabel"); self.mode_label.setToolTip("当前的 AI 命令模式"); toolbar.addWidget(self.mode_label)
        # Status Indicator Label (styled in update_status_indicator)
        self.status_indicator = QLabel(); self.status_indicator.setObjectName("StatusIndicator"); self.status_indicator.setFixedSize(16, 16); self.status_indicator.setToolTip("状态: 空闲"); toolbar.addWidget(self.status_indicator)

        # --- Splitter Setup ---
        splitter = QSplitter(Qt.Orientation.Horizontal); splitter.setObjectName("MainSplitter"); main_layout.addWidget(splitter, 1)

        # --- Left Pane (CLI) ---
        left_widget = QWidget(); left_layout = QVBoxLayout(left_widget); left_layout.setContentsMargins(0, 0, 5, 0); left_layout.setSpacing(3)
        self.cli_output_display = QTextEdit(); self.cli_output_display.setObjectName("CliOutput"); self.cli_output_display.setReadOnly(True); self.cli_output_display.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)

        # Container for CLI Prompt Label and Input LineEdit
        cli_input_container = QWidget(); cli_input_container.setObjectName("CliInputContainer"); cli_input_layout = QHBoxLayout(cli_input_container); cli_input_layout.setContentsMargins(0, 0, 0, 0); cli_input_layout.setSpacing(0) # No space between prompt and input
        # Create the prompt label instance
        self.cli_prompt_label = QLabel("PS>"); self.cli_prompt_label.setObjectName("CliPromptLabel") # Default prompt
        self.cli_input = QLineEdit(); self.cli_input.setObjectName("CliInput"); self.cli_input.setPlaceholderText("输入 Shell 命令 (↑/↓ 历史)..."); self.cli_input.returnPressed.connect(self.handle_manual_command)
        # Add the prompt label *before* the input field
        cli_input_layout.addWidget(self.cli_prompt_label)
        cli_input_layout.addWidget(self.cli_input, 1) # Input field takes remaining space

        left_layout.addWidget(self.cli_output_display, 1); left_layout.addWidget(cli_input_container); splitter.addWidget(left_widget)

        # --- Right Pane (Chat) ---
        right_widget = QWidget(); right_layout = QVBoxLayout(right_widget); right_layout.setContentsMargins(5, 0, 0, 0); right_layout.setSpacing(3)
        self.chat_history_display = QTextEdit(); self.chat_history_display.setObjectName("ChatHistoryDisplay"); self.chat_history_display.setReadOnly(True); self.chat_history_display.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.chat_input = QTextEdit(); self.chat_input.setObjectName("ChatInput"); self.chat_input.setPlaceholderText("询问 AI 或输入 /help... (Shift+Enter 换行)"); self.chat_input.setMaximumHeight(80); self.chat_input.setAcceptRichText(False); self.chat_input.installEventFilter(self)
        button_layout = QHBoxLayout(); button_layout.setContentsMargins(0, 0, 0, 0); button_layout.setSpacing(5)
        self.send_button = QPushButton("发送"); self.send_button.setToolTip("发送消息给 AI (Enter)"); self.send_button.clicked.connect(self.handle_send_message); self.send_button.setIconSize(QSize(16, 16)); send_icon = self._get_icon("mail-send", "send.png", None); self.send_button.setIcon(send_icon if not send_icon.isNull() else QIcon())
        button_layout.addWidget(self.send_button)
        self.clear_chat_button = QPushButton("清除聊天"); self.clear_chat_button.setObjectName("ClearChatButton"); self.clear_chat_button.setToolTip("清除聊天显示和历史记录"); self.clear_chat_button.setIconSize(QSize(16, 16)); clear_icon = self._get_icon("edit-clear", "clear.png", None); clear_icon = clear_icon if not clear_icon.isNull() else self._get_icon("user-trash", "trash.png", "🗑️"); self.clear_chat_button.setIcon(clear_icon if not clear_icon.isNull() else QIcon()); self.clear_chat_button.clicked.connect(self.handle_clear_chat)
        button_layout.addWidget(self.clear_chat_button)
        right_layout.addWidget(self.chat_history_display, 1); right_layout.addWidget(self.chat_input); right_layout.addLayout(button_layout); splitter.addWidget(right_widget)

        # --- Slash Command Completer ---
        # <<< MODIFICATION START >>>
        # QCompleter is not directly compatible with QTextEdit.
        # Remove or comment out the completer setup for chat_input.
        # If you need completion, it requires a custom implementation.
        # ---
        # self.slash_commands = ["/help", "/mode suggest", "/clear", "/clear_cli", "/clear_all", "/settings", "/save", "/cwd", "/exit"]
        # completer_model = QStringListModel(self.slash_commands)
        # self.completer = QCompleter(completer_model, self)
        # self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        # self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        # self.completer.setFilterMode(Qt.MatchFlag.MatchStartsWith)
        # self.chat_input.setCompleter(self.completer) # <<< THIS LINE IS REMOVED/COMMENTED >>>
        # ---
        # <<< MODIFICATION END >>>


        # --- Initial Splitter Sizes ---
        try:
            settings = config.get_settings(); splitter_state = settings.value("ui/splitter_state"); default_width = self.geometry().width()
            if splitter_state and isinstance(splitter_state, (bytes, bytearray)): splitter.restoreState(splitter_state); print("Restored splitter state from settings.")
            else: cli_width = int(default_width * 0.55); chat_width = default_width - cli_width; splitter.setSizes([cli_width, chat_width]); print("Set default splitter sizes (55%/45%).")
        except Exception as e: print(f"Could not set initial splitter sizes: {e}"); default_width = 850; splitter.setSizes([int(default_width*0.55), int(default_width*0.45)])

        # --- Status Bar ---
        self.status_bar = self.statusBar(); self.status_bar.hide()


    # --- UI Update and Helper Methods ---

    def _get_os_fonts(self):
        # Helper to get platform-specific monospace fonts
        mono_font_family = "Monospace"; mono_font_size = 10; label_font_size = 9
        if platform.system() == "Windows": mono_font_family, mono_font_size, label_font_size = "Consolas, Courier New", 10, 9
        elif platform.system() == "Darwin": mono_font_family, mono_font_size, label_font_size = "Menlo", 11, 9
        elif platform.system() == "Linux": mono_font_family, mono_font_size, label_font_size = "Monospace", 10, 9
        return mono_font_family, mono_font_size, label_font_size

    def apply_theme_specific_styles(self):
        # Applies the QSS stylesheet based on the current theme
        theme = config.APP_THEME
        print(f"Applying styles for theme: {theme}")
        mono_font_family, mono_font_size, label_font_size = self._get_os_fonts()
        qss = ""
        palette = QApplication.instance().palette() # Get the current global palette
        border_color_role = QPalette.ColorRole.Mid; border_color = palette.color(border_color_role)
        if not border_color.isValid(): border_color = palette.color(QPalette.ColorRole.Dark)
        if not border_color.isValid(): border_color = QColor(180, 180, 180) # Fallback
        border_color_name = border_color.name()

        if theme == "system":
            qss = MINIMAL_STYLESHEET_SYSTEM_THEME.format(
                mono_font_family=mono_font_family, mono_font_size=mono_font_size,
                label_font_size=label_font_size, border=border_color_name
            )
            print("Applied system theme (minimal QSS). Relies on global palette.")
        else: # "dark" or "light"
            # Get theme-specific colors from constants
            cli_bg=get_color("cli_bg", theme); cli_output_color=get_color("cli_output", theme); prompt_color=get_color("prompt", theme); border_color_const=get_color("border", theme)
            text_main_color=get_color("text_main", theme); status_label_color=get_color("status_label", theme); cwd_label_color=get_color("cwd_label", theme)
            # Get palette colors for general UI elements
            window_bg=palette.color(QPalette.ColorRole.Window).name(); base_bg=palette.color(QPalette.ColorRole.Base).name(); highlight_bg=palette.color(QPalette.ColorRole.Highlight).name(); highlighted_text=palette.color(QPalette.ColorRole.HighlightedText).name()
            button_bg=palette.color(QPalette.ColorRole.Button).name(); button_text_color=palette.color(QPalette.ColorRole.ButtonText).name(); tooltip_bg=palette.color(QPalette.ColorRole.ToolTipBase).name(); tooltip_text=palette.color(QPalette.ColorRole.ToolTipText).name()
            text_disabled=palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text).name(); button_disabled_bg=palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button).name()
            border_disabled=palette.color(QPalette.ColorGroup.Disabled, border_color_role).name(); button_pressed_bg=QColor(button_bg).darker(115).name()
            # Format the full QSS template
            qss = STYLESHEET_TEMPLATE.format(
                window_bg=window_bg, base_bg=base_bg, text_main=text_main_color.name(), cli_bg=cli_bg.name(), cli_output=cli_output_color.name(), prompt_color=prompt_color.name(),
                cwd_label_color=cwd_label_color.name(), border=border_color_const.name(), highlight_bg=highlight_bg, splitter_handle_bg=button_bg,
                mono_font_family=mono_font_family, mono_font_size=mono_font_size, label_font_size=label_font_size, button_bg=button_bg, button_text=button_text_color,
                highlighted_text=highlighted_text, button_pressed_bg=button_pressed_bg, button_disabled_bg=button_disabled_bg, text_disabled=text_disabled,
                border_disabled=border_disabled, tooltip_bg=tooltip_bg, tooltip_text=tooltip_text, status_label_color=status_label_color.name()
            )
            print(f"Theme '{theme}' styles applied via full QSS.")

        self.setStyleSheet(qss)
        self.update_status_indicator(self.is_busy()) # Refresh indicator style
        self.update() # Force widget repaint
        # Update dynamic labels that might depend on theme colors/fonts
        self.update_cwd_label() # Ensure toolbar CWD updates
        self.update_prompt()    # Ensure CLI prompt updates

    def load_and_apply_state(self):
        """Applies loaded history to the display. Called after load_state."""
        print(f"Applying {len(self.conversation_history)} loaded history items to display...")
        history_copy = list(self.conversation_history); self.chat_history_display.clear(); self.conversation_history.clear() # Clear display and internal before reapplying
        for role, message in history_copy: self.add_chat_message(role, message, add_to_internal_history=True)
        print("History applied to display and internal deque.")
        # Ensure other UI elements reflect loaded state
        self.update_mode_display()
        self.update_model_id_display()
        self.update_cwd_label() # Make sure CWD label reflects loaded CWD
        self.update_prompt()    # Make sure prompt label reflects loaded CWD


    def get_short_cwd(self, max_len=35):
         # Shortens the CWD for display in the toolbar
         display_cwd = self.current_directory
         try:
             home_dir = os.path.expanduser("~")
             if display_cwd.startswith(home_dir):
                 if display_cwd == home_dir: display_cwd = "~"
                 elif display_cwd.startswith(home_dir + os.path.sep): display_cwd = "~" + display_cwd[len(home_dir):]
             if len(display_cwd) > max_len:
                 parts = display_cwd.split(os.path.sep); num_parts = len(parts)
                 is_windows_drive_root = platform.system() == "Windows" and len(parts) == 2 and parts[1] == '' and parts[0].endswith(':')
                 if not is_windows_drive_root and num_parts > 2:
                    first_part = parts[0] if parts[0] != "~" else "~"
                    if not first_part and len(parts) > 1 and parts[1]: first_part = f"{os.path.sep}{parts[1]}" # Handle root paths like /usr
                    display_cwd_short = f"{first_part}{os.path.sep}...{os.path.sep}{parts[-1]}"
                    # If still too long, try including the last two components
                    if len(display_cwd_short) > max_len and num_parts > 3:
                        display_cwd = f"{first_part}{os.path.sep}...{os.path.sep}{parts[-2]}{os.path.sep}{parts[-1]}"
                    else: display_cwd = display_cwd_short
             # Final hard truncate if still too long
             if len(display_cwd) > max_len: display_cwd = "..." + display_cwd[-(max_len-3):]
         except Exception as e: print(f"Error shortening CWD: {e}"); # Use original on error
         return display_cwd

    def update_cwd_label(self):
        """Updates the CWD label in the toolbar."""
        if self.toolbar_cwd_label:
            short_cwd = self.get_short_cwd(max_len=30); self.toolbar_cwd_label.setText(f"{short_cwd}")
            self.toolbar_cwd_label.setToolTip(f"当前工作目录: {self.current_directory}")
        self.update_prompt() # Also update CLI prompt when CWD changes

    def update_prompt(self):
        """Updates the CLI prompt label to include the current directory."""
        if not self.cli_prompt_label:
            return

        shell_prefix = "PS" if platform.system() == "Windows" else "$"
        display_path = self.current_directory

        # Try to replace home directory with ~ for display
        try:
            home_dir = os.path.expanduser("~")
            if display_path.startswith(home_dir):
                if display_path == home_dir: display_path = "~" # Exactly home
                elif display_path.startswith(home_dir + os.path.sep): display_path = "~" + display_path[len(home_dir):] # Replace prefix
        except Exception as e: print(f"Error processing path for prompt display: {e}") # Use original on error

        # Construct the final prompt text
        prompt_text = f"{shell_prefix} {display_path}> " # Add trailing space
        self.cli_prompt_label.setText(prompt_text)
        # Tooltip *always* shows the full, non-abbreviated path
        self.cli_prompt_label.setToolTip(f"当前工作目录: {self.current_directory}")

    def update_model_id_display(self):
        """Updates the model ID label in the toolbar."""
        if self.model_id_label:
            model_text = config.MODEL_ID or '未配置'; self.model_id_label.setText(f"模型: {model_text}")
            self.model_id_label.setToolTip(f"当前使用的 AI 模型 ID: {model_text}")

    def update_mode_display(self):
        """Updates the mode label in the toolbar."""
        if self.mode_label: self.mode_label.setText(f"模式: {self.current_mode}")

    def update_status_indicator(self, busy: bool):
        """Updates the visual style and tooltip of the status indicator."""
        if self.status_indicator:
            border_color = get_color("border", config.APP_THEME).name()
            # Use red when busy, green when idle
            color = "red" if busy else "limegreen"
            tooltip = f"状态: {'忙碌' if busy else '空闲'}"
            # Apply stylesheet to make it a colored circle
            self.status_indicator.setStyleSheet(
                f"QLabel#StatusIndicator {{ "
                f"border: 1px solid {border_color}; "
                f"border-radius: 8px; " # Makes it circular (half of fixed size 16)
                f"background-color: {color}; "
                f"}}"
            )
            self.status_indicator.setToolTip(tooltip)

    def is_busy(self) -> bool:
        """Checks if any background worker thread is currently running."""
        api_running = self.api_worker_thread and self.api_worker_thread.isRunning()
        manual_running = self.manual_cmd_thread and self.manual_cmd_thread.isRunning()
        return api_running or manual_running

    def add_formatted_text(self, target_widget: QTextEdit, text: str, color: QColor = None):
        # Helper to add text with specific color to a QTextEdit
        if not text: return
        cursor = target_widget.textCursor(); at_end = cursor.atEnd(); cursor.movePosition(QTextCursor.MoveOperation.End)
        char_format = QTextCharFormat(); current_theme = config.APP_THEME
        # Apply color only if specified AND not using system theme (where palette handles it)
        if color is not None and current_theme != "system": char_format.setForeground(color)
        else: # Otherwise, use the widget's default text color from the palette
            default_text_color = target_widget.palette().color(QPalette.ColorRole.Text); char_format.setForeground(default_text_color)
        cursor.setCharFormat(char_format); cursor.insertText(text)
        # Ensure scroll to bottom if cursor was at the end
        if at_end:
            scrollbar = target_widget.verticalScrollBar()
            if scrollbar: QApplication.processEvents(); scrollbar.setValue(scrollbar.maximum()) # Process events before scrolling
            target_widget.ensureCursorVisible()

    def add_chat_message(self, role: str, message: str, add_to_internal_history: bool = True):
        # Adds a message to the chat display with role-based formatting
        role_lower = role.lower(); role_display = role.capitalize()
        prefix_text = f"{role_display}: "; message_text = message.rstrip() + '\n' # Ensure single newline at end
        target_widget = self.chat_history_display; cursor = target_widget.textCursor(); at_end = cursor.atEnd()
        cursor.movePosition(QTextCursor.MoveOperation.End); target_widget.setTextCursor(cursor)

        current_theme = config.APP_THEME; char_format = QTextCharFormat()
        default_text_color = target_widget.palette().color(QPalette.ColorRole.Text) # Get default from palette

        # Simplified coloring - Use constants for non-system themes
        prefix_color = None
        message_color = default_text_color # Default to standard text color

        if current_theme != "system":
            if role_lower == 'user':
                prefix_color = get_color('user', current_theme)
            elif role_lower == 'model':
                prefix_color = get_color('model', current_theme) # Model prefix might be styled differently
                message_color = get_color('model', current_theme) # Model message content color
            elif role_lower in ['system', 'error', 'help', 'prompt']:
                 prefix_color = get_color(role_lower, current_theme)
                 message_color = prefix_color # Usually same color for prefix and message
            else: # Fallback for unknown roles
                 prefix_color = get_color('system', current_theme)
                 message_color = prefix_color
        else: # System theme - rely on palette (use default for now, could customize later)
             prefix_color = default_text_color
             message_color = default_text_color

        # Apply Prefix Color
        char_format.setForeground(prefix_color if prefix_color else default_text_color)
        # Make prefix bold
        prefix_font = char_format.font(); prefix_font.setBold(True); char_format.setFont(prefix_font)
        cursor.setCharFormat(char_format); cursor.insertText(prefix_text)

        # Apply Message Color (and reset font)
        char_format.setForeground(message_color)
        message_font = char_format.font(); message_font.setBold(False); char_format.setFont(message_font) # Reset bold
        cursor.setCharFormat(char_format); cursor.insertText(message_text)

        # Scroll to bottom if needed
        if at_end:
            scrollbar = target_widget.verticalScrollBar()
            if scrollbar: QApplication.processEvents(); scrollbar.setValue(scrollbar.maximum())
            target_widget.ensureCursorVisible()

        # Add to internal history deque if requested
        if add_to_internal_history:
            # Remove timing info before adding to history
            message_for_history = re.sub(r"\s*\([\u0041-\uFFFF]+:\s*[\d.]+\s*[\u0041-\uFFFF]+\)$", "", message).strip()
            # Avoid adding exact duplicates consecutively
            if not self.conversation_history or self.conversation_history[-1] != (role, message_for_history):
                self.conversation_history.append((role, message_for_history))

    def add_cli_output(self, message_bytes: bytes, message_type: str = "output"):
        # Adds decoded output from worker threads to the CLI display
        message = _decode_output(message_bytes); # Decode using helper
        message_to_display = message; current_theme = config.APP_THEME

        # Basic filter for CLIXML progress messages (often sent to stderr)
        is_clixml = message.strip().startswith("#< CLIXML")
        if is_clixml: print("Filtered CLIXML output."); return

        # Prepend stderr tag if it's an error and not CLIXML
        if message_type == "error": message_to_display = f"[stderr] {message}"

        # Determine color based on message type and theme
        color = None
        if current_theme != "system":
            color_key = f"cli_{message_type}" # e.g., cli_output, cli_error
            # Add specific handling for command echoes if needed
            if message_type == "cli_cmd_echo": color_key = "cli_cmd_echo"
            elif message_type == "ai_cmd_echo": color_key = "ai_cmd_echo"
            elif message_type == "system": color_key = "system" # System message in CLI
            color = get_color(color_key, current_theme)

        text_to_insert = message_to_display.rstrip() + '\n' # Ensure single newline
        self.add_formatted_text(self.cli_output_display, text_to_insert, color)

    def show_help(self):
        # Displays help text in the chat window
        help_title = f"--- {APP_NAME} 帮助 ---"; available_commands = "可用命令 (在聊天输入框输入):"; cmd_help = "/help          显示此帮助信息。"
        cmd_mode = f"/mode [suggest] 设置 AI 命令模式。当前: '{self.current_mode}'。"; mode_explanation = "              suggest: AI 在 <cmd> 标签中提出命令, 然后执行。"
        cmd_clear = "/clear         清除聊天显示和历史记录 (同 '清除聊天' 按钮)。"; cmd_clear_cli = "/clear_cli     清除命令行输出显示。"; cmd_clear_all = "/clear_all     清除两个显示区域及聊天历史。"
        cmd_settings = "/settings      打开应用程序设置对话框 (API密钥, 主题等)。"; cmd_save = "/save          手动保存状态 (聊天历史, 当前目录)。重启时自动加载。"
        cmd_cwd = "/cwd           在聊天中显示完整当前工作目录。"; cmd_exit = "/exit          关闭应用程序。"
        gui_elements = "界面元素:"; gui_toolbar = f"- 工具栏: 设置按钮, 当前目录 (短路径), 模型 ID ({config.MODEL_ID or 'N/A'}), 当前模式, 状态指示灯 (绿:空闲, 红:忙碌)。"; gui_clear_btn = "- 清除聊天按钮: 清除聊天显示和历史记录。"; gui_send_btn = "- 发送按钮: 发送消息给 AI。"
        manual_commands_title = "手动命令 (在命令行输入框输入):"; shell_name = "PowerShell" if platform.system() == "Windows" else "Shell";
        # Get current prompt text for example
        example_prompt = self.cli_prompt_label.text() if self.cli_prompt_label else ("PS C:\\Path>" if platform.system() == "Windows" else "$ /path>")
        manual_desc1 = f" - 直接在 {shell_name} 输入框 (形如 {example_prompt}) 输入并按回车。"
        manual_desc2 = f" - 使用 ↑ / ↓ 键浏览已输入的命令历史。"; manual_desc3 = f" - 标准 {shell_name} 命令可用 (例如 'Get-ChildItem', 'cd ..', 'echo hello', 'python script.py')。"; manual_desc4 = " - 使用 'cd <目录>' 更改工作目录。支持相对/绝对路径和 '~' (用户主目录)。"; manual_desc5 = f" - 使用 '{'cls' if platform.system() == 'Windows' else 'clear'}' 清空命令行输出显示。"
        ai_interaction_title = "AI 交互 (在聊天输入框输入):"; ai_desc1 = " - 向 AI 请求任务帮助 (例如 “列出当前目录的 python 文件”, “显示 git 状态”, “创建一个名为 temp 的目录”)" ; ai_desc2 = f" - 在 '{self.current_mode}' 模式下, 如果 AI 通过 <cmd>标签</cmd> 建议命令, 它将在命令行窗口中自动回显并执行。"; ai_desc3 = " - 如果 AI 的响应不包含 <cmd> 标签, 则仅在聊天窗口显示文本回复。"; timing_info = " - 模型回复后会附带本次请求的耗时信息。"
        help_text = f"{help_title}\n\n{available_commands}\n {cmd_help}\n {cmd_mode}\n{mode_explanation}\n {cmd_clear}\n {cmd_clear_cli}\n {cmd_clear_all}\n {cmd_settings}\n {cmd_save}\n {cmd_cwd}\n {cmd_exit}\n\n{gui_elements}\n {gui_toolbar}\n {gui_clear_btn}\n {gui_send_btn}\n\n{manual_commands_title}\n{manual_desc1}\n{manual_desc2}\n{manual_desc3}\n{manual_desc4}\n{manual_desc5}\n\n{ai_interaction_title}\n{ai_desc1}\n{ai_desc2}\n{ai_desc3}\n{timing_info}\n"
        self.add_chat_message("Help", help_text, add_to_internal_history=False) # Don't add help to history

    # --- Event Handling and Slots ---

    @Slot()
    def handle_send_message(self):
        # Handles sending a message from the chat input to the AI
        user_prompt = self.chat_input.toPlainText().strip()
        if not user_prompt: return;
        self.chat_input.clear() # Clear input after getting text

        # Handle slash commands first
        if user_prompt.startswith("/"): self.handle_slash_command(user_prompt); return

        # Check API config before proceeding
        if not config.API_KEY or not config.API_URL or not config.MODEL_ID:
            self.add_chat_message("Error", "API 未配置。请使用“设置”按钮或 /settings 命令进行配置。")
            return

        # Stop any previous API worker if running
        self.stop_api_worker()

        # Add user message to display and history
        self.add_chat_message("User", user_prompt)

        # Set UI to busy state BEFORE starting thread
        self.set_busy_state(True, "api")
        print("Starting ApiWorkerThread...")

        # Create and start the API worker thread
        self.api_worker_thread = ApiWorkerThread(
            api_key=config.API_KEY, api_url=config.API_URL, model_id=config.MODEL_ID,
            history=list(self.conversation_history), prompt=user_prompt,
            mode=self.current_mode, cwd=self.current_directory
        )
        # Connect signals
        self.api_worker_thread.api_result.connect(self.handle_api_result) # Model text reply
        self.api_worker_thread.cli_output_signal.connect(lambda output_bytes: self.add_cli_output(output_bytes, "output")) # Command stdout
        self.api_worker_thread.cli_error_signal.connect(lambda error_bytes: self.add_cli_output(error_bytes, "error"))    # Command stderr
        self.api_worker_thread.directory_changed_signal.connect(self.handle_directory_change) # Directory change
        self.api_worker_thread.task_finished.connect(lambda: self.handle_task_finished("api")) # Task completion
        self.api_worker_thread.start()


    def handle_slash_command(self, command):
        # Processes slash commands entered in the chat input
        command_lower = command.lower(); parts = command.split(maxsplit=1); cmd_base = parts[0].lower(); arg = parts[1].strip() if len(parts) == 2 else None
        print(f"Processing slash command: {command}")

        if cmd_base == "/exit": self.close()
        elif cmd_base == "/clear": self.handle_clear_chat()
        elif cmd_base == "/clear_cli":
            self.cli_output_display.clear()
            self.add_cli_output(f"命令行显示已清除。当前目录: {self.current_directory}".encode(), "system") # Use system type
        elif cmd_base == "/clear_all":
            self.handle_clear_chat() # Clears chat display + history
            self.cli_output_display.clear()
            self.add_chat_message("System", "聊天和命令行显示已清除。", add_to_internal_history=False)
            self.add_cli_output(f"命令行显示已清除。当前目录: {self.current_directory}".encode(), "system")
        elif cmd_base == "/settings": self.open_settings_dialog()
        elif cmd_base == "/save": self.save_state(); self.add_chat_message("System", "当前状态 (历史, CWD) 已保存。")
        elif cmd_base == "/help": self.show_help()
        elif cmd_base == "/mode":
            if arg:
                if arg in ["suggest"]: # Only 'suggest' mode currently
                    self.current_mode = arg
                    self.add_chat_message("System", f"模式已设为: {self.current_mode}")
                    self.update_mode_display()
                else: self.add_chat_message("Error", f"无效模式 '{arg}'。可用模式: suggest")
            else: self.add_chat_message("Error", f"用法: /mode [suggest]。当前模式: '{self.current_mode}'")
        elif cmd_base == "/cwd": self.add_chat_message("System", f"当前工作目录: {self.current_directory}")
        else: self.add_chat_message("Error", f"未知命令: {command}。输入 /help 获取帮助。")


    @Slot()
    def handle_clear_chat(self):
        # Clears the chat display and internal history deque
        print("Clear Chat action triggered.")
        self.chat_history_display.clear(); self.conversation_history.clear()
        # Add a notification message, but don't add it to the (now empty) history
        self.add_chat_message("System", "聊天历史已清除。", add_to_internal_history=False)
        self.save_state(); # Save the cleared state
        print("Chat history display and internal history deque cleared and state saved.")


    @Slot()
    def handle_manual_command(self):
        # Handles executing a command entered in the CLI input
        command = self.cli_input.text().strip();
        if not command: return

        # Add to CLI history (if different from last command)
        if not self.cli_command_history or self.cli_command_history[-1] != command:
            self.cli_command_history.append(command)
        self.cli_history_index = -1 # Reset history navigation index
        self.cli_input.clear() # Clear input field

        # Intercept 'cls' or 'clear' locally for faster clearing
        command_lower = command.lower(); clear_cmd = "cls" if platform.system() == "Windows" else "clear"
        if command_lower == clear_cmd:
            print(f"Intercepted '{command}' command. Clearing CLI display directly."); self.cli_output_display.clear(); self.add_cli_output(f"命令行显示已清除。当前目录: {self.current_directory}".encode(), "system"); return

        # Stop any previous manual command worker if running
        self.stop_manual_worker();

        # Echo the command to the CLI output
        prompt_text = self.cli_prompt_label.text() if self.cli_prompt_label else "> "
        self.add_cli_output(f"{prompt_text}{command}".encode(), "cli_cmd_echo") # Encode echo message

        # Set UI to busy state BEFORE starting thread
        self.set_busy_state(True, "manual")
        print(f"Starting ManualCommandThread for: {command}")

        # Create and start the manual command worker thread
        self.manual_cmd_thread = ManualCommandThread(command, self.current_directory)
        # Connect signals
        self.manual_cmd_thread.cli_output_signal.connect(lambda output_bytes: self.add_cli_output(output_bytes, "output"))
        self.manual_cmd_thread.cli_error_signal.connect(lambda error_bytes: self.add_cli_output(error_bytes, "error"))
        self.manual_cmd_thread.directory_changed_signal.connect(self.handle_directory_change)
        self.manual_cmd_thread.command_finished.connect(lambda: self.handle_task_finished("manual"))
        self.manual_cmd_thread.start()


    def keyPressEvent(self, event: QKeySequence):
        # Handles Up/Down arrow keys in CLI input for history navigation
        focused_widget = QApplication.focusWidget()
        if focused_widget == self.cli_input:
            key = event.key(); modifiers = event.modifiers()
            # Up Arrow
            if key == Qt.Key.Key_Up and not modifiers:
                if not self.cli_command_history: event.accept(); return # No history
                if self.cli_history_index == -1: # Start from the end
                    self.cli_history_index = len(self.cli_command_history) - 1
                elif self.cli_history_index > 0: # Move further back
                    self.cli_history_index -= 1
                else: event.accept(); return # Already at the beginning
                # Display the history item
                if 0 <= self.cli_history_index < len(self.cli_command_history):
                    self.cli_input.setText(self.cli_command_history[self.cli_history_index])
                    self.cli_input.end(False) # Move cursor to end
                event.accept(); return # Consume the event
            # Down Arrow
            elif key == Qt.Key.Key_Down and not modifiers:
                if self.cli_history_index == -1: event.accept(); return # Not navigating history
                if self.cli_history_index < len(self.cli_command_history) - 1: # Move forward
                    self.cli_history_index += 1;
                    self.cli_input.setText(self.cli_command_history[self.cli_history_index]);
                    self.cli_input.end(False)
                else: # Reached the end, clear input and stop navigating
                    self.cli_history_index = -1; self.cli_input.clear()
                event.accept(); return # Consume the event
            # Any other key press while navigating resets the index
            elif self.cli_history_index != -1 and key not in (
                Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta,
                Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_PageUp, Qt.Key.Key_PageDown,
                Qt.Key.Key_Home, Qt.Key.Key_End ):
                 self.cli_history_index = -1 # Stop navigating on other input
        super().keyPressEvent(event) # Pass other key events


    def set_busy_state(self, busy: bool, task_type: str):
        """Updates UI element states (enabled/disabled) and the status indicator."""
        print(f"Setting busy state: {busy} for task type: {task_type}")

        # Enable/Disable input widgets based on task type
        if task_type == "api":
            self.chat_input.setEnabled(not busy)
            self.send_button.setEnabled(not busy)
            self.clear_chat_button.setEnabled(not busy)
        elif task_type == "manual":
            self.cli_input.setEnabled(not busy);

        # Update the status indicator immediately when a task starts or might end
        if busy:
            self.update_status_indicator(True) # Set to red
        else:
            # When a task finishes, *check the overall busy state*
            # Only set to green if NO tasks are running anymore
            QApplication.processEvents() # Process events before potentially changing state
            if not self.is_busy():
                 print("All tasks finished, setting indicator to idle (green).")
                 self.update_status_indicator(False) # Set to green
            else:
                 print("A task finished, but another is still running. Indicator remains busy (red).")


        # Set focus back to the appropriate input field when becoming idle
        if not busy:
            # Prioritize CLI input focus if it was the last thing used?
            # Or just focus the one that became enabled.
            if task_type == "api" and self.chat_input.isEnabled(): self.chat_input.setFocus()
            elif task_type == "manual" and self.cli_input.isEnabled(): self.cli_input.setFocus()


    @Slot(str, float)
    def handle_api_result(self, reply: str, elapsed_time: float):
        # Handles the text reply received from the API worker
        time_str = f" (耗时: {elapsed_time:.2f} 秒)"; message_with_time = f"{reply}{time_str}"
        self.add_chat_message("Model", message_with_time)
        # Note: Worker thread will continue to execute command if present.
        # Status is set back to idle in handle_task_finished.

    @Slot(str, bool)
    def handle_directory_change(self, new_directory: str, is_manual_command: bool):
        # Handles the signal emitted when a 'cd' command changes the directory
        if os.path.isdir(new_directory):
             old_directory = self.current_directory
             self.current_directory = os.path.normpath(new_directory)
             self.update_cwd_label(); # Updates toolbar and CLI prompt
             source = "手动命令" if is_manual_command else "AI 命令"
             print(f"Directory changed from '{old_directory}' to '{self.current_directory}' via {source}")
             self.save_state() # Save the new CWD
        else:
            print(f"Warning: Directory change received for non-existent path '{new_directory}'")
            error_msg = f"Error: Directory not found: '{new_directory}'"
            self.add_cli_output(error_msg.encode(), "error") # Show error in CLI

    @Slot(str)
    def handle_task_finished(self, task_type: str):
        """Handles the finished signal from worker threads."""
        print(f"{task_type.capitalize()}WorkerThread finished.")

        # Clear the reference to the finished thread
        if task_type == "api": self.api_worker_thread = None
        elif task_type == "manual": self.manual_cmd_thread = None

        # Update the busy state. This will check if *any* thread is still running.
        # It enables inputs and sets the indicator to green ONLY if all are finished.
        self.set_busy_state(False, task_type)

    @Slot()
    def open_settings_dialog(self):
        """Opens the settings configuration dialog."""
        if self.settings_dialog_open: return # Prevent multiple dialogs
        self.settings_dialog_open = True
        print("Opening settings dialog...")
        dialog = SettingsDialog(self)
        current_theme_before = config.APP_THEME
        current_model_id_before = config.MODEL_ID
        result = dialog.exec() # Show dialog modally

        if result == QDialog.DialogCode.Accepted:
            print("Settings dialog accepted.")
            api_key, api_url, model_id, auto_startup, new_theme = dialog.get_values()

            # Check if any configuration actually changed
            config_after_dialog_interaction = config.get_current_config()
            config_changed = (
                api_key != config_after_dialog_interaction['api_key'] or
                api_url != config_after_dialog_interaction['api_url'] or
                model_id != config_after_dialog_interaction['model_id'] or
                auto_startup != config_after_dialog_interaction['auto_startup'] or
                new_theme != config_after_dialog_interaction['theme']
            )

            if config_changed:
                print("Configuration change detected, saving...")
                config.save_config(api_key, api_url, model_id, auto_startup, new_theme)
                print(f"Configuration saved. New theme: {new_theme}, AutoStart: {auto_startup}, Model: {model_id}")
            else:
                print("Settings dialog accepted, but no changes detected in values.")

            # Refresh UI elements even if no direct save happened (e.g., after reset)
            self.update_model_id_display() # Always refresh model ID display

            theme_changed = new_theme != current_theme_before
            # Reload state and apply theme if theme changed OR if other settings changed
            # (because reset might have cleared state requiring reload)
            if theme_changed or config_changed:
                print(f"Theme changed: {theme_changed}, Config changed (other): {config_changed and not theme_changed}")
                # Apply theme/palette change *before* potentially reloading history
                if theme_changed:
                    app = QApplication.instance(); setup_palette(app, new_theme); self.apply_theme_specific_styles()

                print("Reloading state (necessary after potential reset or theme change)...")
                self.load_state() # Reload state (might be cleared by reset)
                self.load_and_apply_state() # Apply (potentially cleared) history to display
            else: # If only API key etc changed, just update displays
                 # Re-applying styles might still be good if palette colors changed slightly even within same theme name?
                 self.apply_theme_specific_styles() # Re-apply styles just in case

            # Update CWD and Prompt display after potential reset or load
            self.update_cwd_label() # Will also update prompt
            print("CWD display updated after settings dialog.")

        else:
            print("Settings dialog cancelled.")

        self.settings_dialog_open = False
        self.activateWindow(); self.raise_() # Ensure main window regains focus


    # --- State Management ---
    def save_state(self):
        # Saves conversation history, CWD, CLI history, and splitter state
        try:
            settings = config.get_settings(); history_list = list(self.conversation_history)
            # Save core state
            settings.beginGroup("state"); settings.setValue("conversation_history", json.dumps(history_list)); settings.setValue("current_directory", self.current_directory); settings.setValue("cli_history", json.dumps(list(self.cli_command_history))); settings.endGroup()
            # Save UI state (splitter)
            splitter = self.findChild(QSplitter, "MainSplitter")
            if splitter: settings.beginGroup("ui"); settings.setValue("splitter_state", splitter.saveState()); settings.endGroup()
            settings.sync(); # Ensure changes are written
            print(f"State saved: History({len(history_list)}), CWD, CLI History({len(self.cli_command_history)})")
        except Exception as e: print(f"Error saving state: {e}")


    def load_state(self):
        # Loads state on startup
        print("Loading state (CWD, History, CLI History)...")
        try:
            settings = config.get_settings()
            restored_cwd = self.initial_directory # Default to initial app dir

            # Load from settings, using defaults if missing
            settings.beginGroup("state")
            saved_cwd = settings.value("current_directory")
            history_json = settings.value("conversation_history", "[]")
            cli_history_json = settings.value("cli_history", "[]")
            settings.endGroup()

            # Validate saved CWD
            if saved_cwd and isinstance(saved_cwd, str):
                if os.path.isdir(saved_cwd): restored_cwd = saved_cwd
                else: print(f"Warning: Saved directory '{saved_cwd}' not found or invalid. Using default.")
            else: print("No valid saved directory found. Using default.")
            self.current_directory = os.path.normpath(restored_cwd)
            print(f"Effective CWD after loading: {self.current_directory}")

            # Load and validate conversation history
            loaded_history = []
            try:
                 history_list = json.loads(history_json)
                 # Basic validation of format
                 if isinstance(history_list, list) and all(isinstance(item, (list, tuple)) and len(item) == 2 and isinstance(item[0], str) and isinstance(item[1], str) for item in history_list): loaded_history = history_list; print(f"Loaded {len(loaded_history)} conversation history items.")
                 elif history_json != "[]": print("Warning: Saved conversation history format invalid.")
            except Exception as e: print(f"Error processing saved conversation history: {e}.")
            self.conversation_history = deque(loaded_history, maxlen=self.conversation_history.maxlen)

            # Load and validate CLI command history
            loaded_cli_history = []
            try:
                cli_history_list = json.loads(cli_history_json)
                if isinstance(cli_history_list, list) and all(isinstance(item, str) for item in cli_history_list): loaded_cli_history = cli_history_list; print(f"Loaded {len(loaded_cli_history)} CLI history items.")
                elif cli_history_json != "[]": print("Warning: Saved CLI history format invalid.")
            except Exception as e: print(f"Error processing saved CLI history: {e}.")
            self.cli_command_history = deque(loaded_cli_history, maxlen=self.cli_command_history.maxlen); self.cli_history_index = -1

        except Exception as e:
            print(f"CRITICAL Error loading state: {e}. Resetting state variables.")
            self.conversation_history.clear(); self.cli_command_history.clear(); self.cli_history_index = -1
            self.current_directory = self.initial_directory # Ensure fallback CWD

    # --- Thread Management ---
    def stop_api_worker(self):
        # Stops the API worker thread if running
        if self.api_worker_thread and self.api_worker_thread.isRunning():
            print("Stopping API worker...")
            self.api_worker_thread.stop() # Signal the thread to stop
            self.api_worker_thread = None # Clear reference
            # If stopping this worker makes the app idle, update state
            if not self.is_busy():
                 self.set_busy_state(False, "api") # Update UI elements and potentially indicator

    def stop_manual_worker(self):
        # Stops the manual command worker thread if running
        if self.manual_cmd_thread and self.manual_cmd_thread.isRunning():
            print("Stopping Manual Command worker...")
            self.manual_cmd_thread.stop() # Signal thread and try to terminate process
            self.manual_cmd_thread = None # Clear reference
            # If stopping this worker makes the app idle, update state
            if not self.is_busy():
                 self.set_busy_state(False, "manual") # Update UI elements and potentially indicator


    # --- Window Close Event ---
    def closeEvent(self, event):
        # Handles the window close event
        print("Close event triggered.")
        # Stop any running background tasks cleanly
        self.stop_api_worker(); self.stop_manual_worker()
        print("Saving final state before closing..."); self.save_state()
        print("Exiting application."); event.accept() # Accept the close event