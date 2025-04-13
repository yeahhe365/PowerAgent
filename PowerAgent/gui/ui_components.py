# ========================================
# 文件名: PowerAgent/gui/ui_components.py
# (MODIFIED - Implemented IME bypass via custom widgets)
# WARNING: This approach is experimental and likely to break standard text editing features.
# ---------------------------------------
# gui/ui_components.py
# -*- coding: utf-8 -*-

"""
Creates and lays out the UI elements for the MainWindow.
Includes custom widgets to attempt bypassing IME for English input.
"""
from typing import TYPE_CHECKING # To avoid circular import for type hinting

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QPushButton, QSplitter, QLabel, QFrame,
    QSizePolicy, QToolBar, QCompleter, QComboBox
)
from PySide6.QtCore import Qt, QSize, QStringListModel, QRect, Signal, QEvent
from PySide6.QtGui import QAction, QIcon, QPainter, QColor, QBrush, QPen, QKeyEvent # Added QKeyEvent

# Import config only if absolutely necessary
from core import config

# Type hinting for MainWindow without causing circular import at runtime
if TYPE_CHECKING:
    from .main_window import MainWindow

# ====================================================================== #
# <<< Original Custom QTextEdit Subclass >>>
# ====================================================================== #
class ChatInputEdit(QTextEdit):
    """Custom QTextEdit that emits a signal on Enter press (without Shift)."""
    sendMessageRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

    def keyPressEvent(self, event: QKeyEvent): # Changed type hint
        """Override keyPressEvent to handle Enter key."""
        key = event.key()
        modifiers = event.modifiers()

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if not (modifiers & Qt.KeyboardModifier.ShiftModifier):
                self.sendMessageRequested.emit() # Emit signal on Enter
                event.accept()
                return
            else:
                # Allow Shift+Enter for new lines
                super().keyPressEvent(event)
                return
        super().keyPressEvent(event)
# ====================================================================== #
# <<< END >>>
# ====================================================================== #


# ====================================================================== #
# <<< NEW: Custom QLineEdit to Bypass IME >>>
# WARNING: Experimental and potentially buggy
# ====================================================================== #
class ImeBypassLineEdit(QLineEdit):
    """
    Attempts to bypass IME for basic English input by intercepting keys
    and inserting characters programmatically.
    """
    def __init__(self, parent=None):
        super().__init__(parent)

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        modifiers = event.modifiers()
        text = event.text()

        # --- Condition for Direct Insert ---
        # 1. Text is not empty and is a single character.
        # 2. The character is a basic printable ASCII character (Space to ~).
        # 3. No Ctrl, Alt, or Meta modifiers are pressed (allowing only Shift or none).
        is_direct_insert_candidate = (
            text and len(text) == 1 and
            32 <= ord(text[0]) <= 126 and
            not (modifiers & Qt.KeyboardModifier.ControlModifier) and
            not (modifiers & Qt.KeyboardModifier.AltModifier) and
            not (modifiers & Qt.KeyboardModifier.MetaModifier)
        )

        if is_direct_insert_candidate:
            # print(f"ImeBypassLineEdit: Intercepted '{text}'") # Debug
            event.accept()  # Consume the event, prevent IME/default handling
            self.insert(text) # Insert the character directly
        else:
            # print(f"ImeBypassLineEdit: Passing key {key} / text '{text}' to super") # Debug
            # Let the base class handle other keys (Enter, Backspace, Arrows, Ctrl+C, etc.)
            super().keyPressEvent(event)

# ====================================================================== #
# <<< NEW: Custom QTextEdit to Bypass IME >>>
# WARNING: Experimental and potentially buggy
# Inherits from ChatInputEdit to keep Enter key functionality
# ====================================================================== #
class ImeBypassTextEdit(ChatInputEdit):
    """
    Attempts to bypass IME for basic English input by intercepting keys
    and inserting characters programmatically. Inherits ChatInputEdit features.
    """
    def __init__(self, parent=None):
        super().__init__(parent)

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        modifiers = event.modifiers()
        text = event.text()

        # --- Check for Enter/Shift+Enter first (from base class logic) ---
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if not (modifiers & Qt.KeyboardModifier.ShiftModifier):
                self.sendMessageRequested.emit() # Emit signal on Enter
                event.accept()
                return
            else:
                # Allow Shift+Enter for new lines - pass to base QTextEdit behavior
                # Need to call the grandparent's method directly if ChatInputEdit
                # doesn't handle Shift+Enter itself in its super call. Let's assume
                # QTextEdit's default handles Shift+Enter correctly.
                QTextEdit.keyPressEvent(self, event) # Call QTextEdit's implementation
                return

        # --- Condition for Direct Insert (same as LineEdit) ---
        is_direct_insert_candidate = (
            text and len(text) == 1 and
            32 <= ord(text[0]) <= 126 and
            not (modifiers & Qt.KeyboardModifier.ControlModifier) and
            not (modifiers & Qt.KeyboardModifier.AltModifier) and
            not (modifiers & Qt.KeyboardModifier.MetaModifier)
        )

        if is_direct_insert_candidate:
            # print(f"ImeBypassTextEdit: Intercepted '{text}'") # Debug
            event.accept()  # Consume the event
            cursor = self.textCursor()
            cursor.insertText(text) # Insert the character directly
            self.ensureCursorVisible()
        else:
            # print(f"ImeBypassTextEdit: Passing key {key} / text '{text}' to super") # Debug
            # Let the base class (ChatInputEdit -> QTextEdit) handle others
            super().keyPressEvent(event)

# ====================================================================== #
# <<< StatusIndicatorWidget (No changes from original) >>>
# ====================================================================== #
class StatusIndicatorWidget(QWidget):
    """A custom widget that draws a circular status indicator."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._busy = False
        self._color_idle = QColor("limegreen")
        self._color_busy = QColor("red")
        self.setFixedSize(16, 16)

    def setBusy(self, busy: bool):
        """Sets the busy state and triggers a repaint."""
        if self._busy != busy:
            self._busy = busy
            self.update()

    def paintEvent(self, event):
        """Overrides the paint event to draw a circle."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self._color_busy if self._busy else self._color_idle
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        rect = QRect(0, 0, self.width(), self.height())
        painter.drawEllipse(rect)

    def sizeHint(self):
        return QSize(16, 16)
# ====================================================================== #
# <<< END >>>
# ====================================================================== #


def create_ui_elements(main_window: 'MainWindow'):
    """Creates and arranges all UI widgets for the given MainWindow instance."""

    central_widget = QWidget()
    main_window.setCentralWidget(central_widget)
    main_layout = QVBoxLayout(central_widget)
    main_layout.setContentsMargins(5, 5, 5, 5)
    main_layout.setSpacing(5)

    # --- Toolbar Setup (No changes here) ---
    toolbar = main_window.addToolBar("Main Toolbar")
    toolbar.setObjectName("MainToolBar")
    toolbar.setMovable(False)
    toolbar.setIconSize(QSize(16, 16))
    toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

    settings_icon = main_window._get_icon("preferences-system", "settings.png", "⚙️")
    settings_action = QAction(settings_icon, "设置", main_window)
    settings_action.triggered.connect(main_window.open_settings_dialog)
    toolbar.addAction(settings_action)

    spacer = QWidget()
    spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    toolbar.addWidget(spacer)

    main_window.model_selector_combo = QComboBox()
    main_window.model_selector_combo.setObjectName("ModelSelectorCombo")
    main_window.model_selector_combo.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Preferred)
    main_window.model_selector_combo.setMaximumWidth(180)
    toolbar.addWidget(main_window.model_selector_combo)

    status_separator = QFrame()
    status_separator.setFrameShape(QFrame.Shape.VLine)
    status_separator.setFrameShadow(QFrame.Shadow.Sunken)
    toolbar.addWidget(status_separator)

    left_indicator_spacer = QWidget(); left_indicator_spacer.setFixedWidth(5)
    toolbar.addWidget(left_indicator_spacer)
    main_window.status_indicator = StatusIndicatorWidget()
    toolbar.addWidget(main_window.status_indicator)
    right_indicator_spacer = QWidget(); right_indicator_spacer.setFixedWidth(5)
    toolbar.addWidget(right_indicator_spacer)

    # --- Splitter Setup (No changes here) ---
    main_window.splitter = QSplitter(Qt.Orientation.Horizontal)
    main_window.splitter.setObjectName("MainSplitter")
    main_layout.addWidget(main_window.splitter, 1)

    # --- Left Pane (CLI) ---
    left_widget = QWidget()
    left_layout = QVBoxLayout(left_widget)
    left_layout.setContentsMargins(0, 0, 5, 0)
    left_layout.setSpacing(3)

    main_window.cli_output_display = QTextEdit()
    main_window.cli_output_display.setObjectName("CliOutput")
    main_window.cli_output_display.setReadOnly(True)
    main_window.cli_output_display.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)

    cli_input_container = QWidget()
    cli_input_container.setObjectName("CliInputContainer")
    cli_input_layout = QHBoxLayout(cli_input_container)
    cli_input_layout.setContentsMargins(0, 0, 0, 0)
    cli_input_layout.setSpacing(0)

    main_window.cli_prompt_label = QLabel("PS>")
    main_window.cli_prompt_label.setObjectName("CliPromptLabel")

    # <<< MODIFICATION: Use ImeBypassLineEdit >>>
    main_window.cli_input = ImeBypassLineEdit()
    main_window.cli_input.setObjectName("CliInput")
    main_window.cli_input.setPlaceholderText("输入 Shell 命令 (↑/↓ 历史)...")
    # Remove ImhPreferLatin hint, keep NoPredictiveText
    main_window.cli_input.setInputMethodHints(Qt.InputMethodHint.ImhNoPredictiveText)
    # Connect returnPressed signal as before
    main_window.cli_input.returnPressed.connect(main_window.handle_manual_command)
    # <<< END MODIFICATION >>>

    cli_input_layout.addWidget(main_window.cli_prompt_label)
    cli_input_layout.addWidget(main_window.cli_input, 1)

    left_layout.addWidget(main_window.cli_output_display, 1)
    left_layout.addWidget(cli_input_container)
    main_window.splitter.addWidget(left_widget)

    # --- Right Pane (Chat) ---
    right_widget = QWidget()
    right_layout = QVBoxLayout(right_widget)
    right_layout.setContentsMargins(5, 0, 0, 0)
    right_layout.setSpacing(3)

    main_window.chat_history_display = QTextEdit()
    main_window.chat_history_display.setObjectName("ChatHistoryDisplay")
    main_window.chat_history_display.setReadOnly(True)
    main_window.chat_history_display.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)

    # <<< MODIFICATION: Use ImeBypassTextEdit >>>
    main_window.chat_input = ImeBypassTextEdit()
    main_window.chat_input.setObjectName("ChatInput")
    main_window.chat_input.setPlaceholderText("询问 AI 或输入 /help... (Shift+Enter 换行)")
    main_window.chat_input.setMaximumHeight(80)
    main_window.chat_input.setAcceptRichText(False)
    # Remove ImhPreferLatin hint, keep NoPredictiveText
    main_window.chat_input.setInputMethodHints(Qt.InputMethodHint.ImhNoPredictiveText)
    # <<< END MODIFICATION >>>

    # --- Button Layout (No changes here) ---
    button_layout = QHBoxLayout()
    button_layout.setContentsMargins(0, 0, 0, 0)
    button_layout.setSpacing(5)

    main_window.send_button = QPushButton("发送")
    main_window.send_button.setObjectName("SendStopButton")
    main_window.send_button.setIconSize(QSize(16, 16))

    send_icon = main_window._get_icon("mail-send", "send.png", "▶️")
    main_window.send_button.setIcon(send_icon if not send_icon.isNull() else QIcon())
    main_window.send_button.setToolTip("向 AI 发送消息 (Shift+Enter 换行)")
    main_window.send_button.clicked.connect(main_window.handle_send_stop_button_click)

    api_configured = bool(config.API_KEY and config.API_URL and config.MODEL_ID_STRING)
    main_window.send_button.setEnabled(api_configured)

    button_layout.addWidget(main_window.send_button)

    main_window.clear_chat_button = QPushButton("清除聊天")
    main_window.clear_chat_button.setObjectName("ClearChatButton")
    main_window.clear_chat_button.setIconSize(QSize(16, 16))
    clear_icon = main_window._get_icon("edit-clear", "clear.png", None)
    clear_icon = clear_icon if not clear_icon.isNull() else main_window._get_icon("user-trash", "trash.png", "🗑️")
    main_window.clear_chat_button.setIcon(clear_icon if not clear_icon.isNull() else QIcon())
    main_window.clear_chat_button.clicked.connect(main_window.handle_clear_chat)
    button_layout.addWidget(main_window.clear_chat_button)

    main_window.clear_cli_button = QPushButton("清空CLI")
    main_window.clear_cli_button.setObjectName("ClearCliButton")
    main_window.clear_cli_button.setIconSize(QSize(16, 16))
    clear_cli_icon = main_window._get_icon("edit-clear-history", "clear_cli.png", None)
    if clear_cli_icon.isNull():
        clear_cli_icon = main_window._get_icon("edit-clear", "clear.png", None)
    main_window.clear_cli_button.setIcon(clear_cli_icon if not clear_cli_icon.isNull() else QIcon())
    main_window.clear_cli_button.clicked.connect(main_window.handle_clear_cli)
    button_layout.addWidget(main_window.clear_cli_button)

    right_layout.addWidget(main_window.chat_history_display, 1)
    right_layout.addWidget(main_window.chat_input)
    right_layout.addLayout(button_layout)
    main_window.splitter.addWidget(right_widget)

    # --- Connect Signals AFTER UI elements are created ---
    if main_window.model_selector_combo:
        main_window.model_selector_combo.currentTextChanged.connect(main_window.handle_model_selection_changed)
    if main_window.chat_input:
        # Connect Enter press signal (which is defined in ChatInputEdit / ImeBypassTextEdit)
        main_window.chat_input.sendMessageRequested.connect(main_window.handle_send_stop_button_click)

    # --- Status Bar ---
    main_window.status_bar = main_window.statusBar()
    main_window.status_bar.hide()