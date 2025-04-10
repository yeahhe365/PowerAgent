# ========================================
# 文件名: PowerAgent/gui/ui_components.py
# (MODIFIED - Introduced ChatInputEdit subclass, removed event filter install, added signal connection)
# ---------------------------------------
# gui/ui_components.py
# -*- coding: utf-8 -*-

"""
Creates and lays out the UI elements for the MainWindow.
"""
from typing import TYPE_CHECKING # To avoid circular import for type hinting

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QPushButton, QSplitter, QLabel, QFrame,
    QSizePolicy, QToolBar, QCompleter, QComboBox
)
# <<< MODIFICATION: Import Signal, Qt, QEvent >>>
from PySide6.QtCore import Qt, QSize, QStringListModel, QRect, Signal, QEvent
from PySide6.QtGui import QAction, QIcon, QPainter, QColor, QBrush, QPen

# Import config only if absolutely necessary
from core import config

# Type hinting for MainWindow without causing circular import at runtime
if TYPE_CHECKING:
    from .main_window import MainWindow

# ====================================================================== #
# <<< ADDED: Custom QTextEdit Subclass >>>
# ====================================================================== #
class ChatInputEdit(QTextEdit):
    """Custom QTextEdit that emits a signal on Enter press (without Shift)."""
    sendMessageRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

    def keyPressEvent(self, event: QEvent):
        """Override keyPressEvent to handle Enter key."""
        key = event.key()
        modifiers = event.modifiers()

        # Debug print inside the overridden method
        print(f"[ChatInputEdit.keyPressEvent] Key={key}, Modifiers={modifiers}, ShiftPressed={bool(modifiers & Qt.KeyboardModifier.ShiftModifier)}")

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if not (modifiers & Qt.KeyboardModifier.ShiftModifier):
                print("[ChatInputEdit.keyPressEvent] Enter without Shift detected. Emitting sendMessageRequested.")
                self.sendMessageRequested.emit()
                # Consume the event to prevent newline insertion
                event.accept()
                return # Don't call super().keyPressEvent for this case
            else:
                # Shift+Enter: fall through to default behavior (insert newline)
                print("[ChatInputEdit.keyPressEvent] Shift+Enter detected. Calling super().keyPressEvent.")
                # Explicitly call super() here for clarity, though falling through works too
                super().keyPressEvent(event)
                return
        # For keys other than Enter/Return call the default implementation
        super().keyPressEvent(event)

# ====================================================================== #
# <<< END ADDED >>>
# ====================================================================== #


# ====================================================================== #
# <<< 自定义状态指示灯控件 (No changes here) >>>
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
# <<< 自定义控件结束 >>>
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

    # --- Left Pane (CLI) (No changes here) ---
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

    main_window.cli_input = QLineEdit()
    main_window.cli_input.setObjectName("CliInput")
    main_window.cli_input.setPlaceholderText("输入 Shell 命令 (↑/↓ 历史)...")
    main_window.cli_input.returnPressed.connect(main_window.handle_manual_command)

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

    # <<< MODIFICATION: Instantiate ChatInputEdit instead of QTextEdit >>>
    main_window.chat_input = ChatInputEdit()
    main_window.chat_input.setObjectName("ChatInput")
    main_window.chat_input.setPlaceholderText("询问 AI 或输入 /help... (Shift+Enter 换行)")
    main_window.chat_input.setMaximumHeight(80)
    main_window.chat_input.setAcceptRichText(False)
    # <<< REMOVED: Event filter installation is no longer needed >>>
    # main_window.chat_input.installEventFilter(main_window)

    # --- Button Layout (No changes here) ---
    button_layout = QHBoxLayout()
    button_layout.setContentsMargins(0, 0, 0, 0)
    button_layout.setSpacing(5)

    main_window.send_button = QPushButton("发送")
    main_window.send_button.clicked.connect(main_window.handle_send_message)
    main_window.send_button.setIconSize(QSize(16, 16))
    send_icon = main_window._get_icon("mail-send", "send.png", None)
    main_window.send_button.setIcon(send_icon if not send_icon.isNull() else QIcon())
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
    # <<< ADDED: Connect the new signal from ChatInputEdit >>>
    if main_window.chat_input:
        main_window.chat_input.sendMessageRequested.connect(main_window.handle_send_message)
    # <<< END ADDED >>>

    # --- Status Bar (No changes here) ---
    main_window.status_bar = main_window.statusBar()
    main_window.status_bar.hide()