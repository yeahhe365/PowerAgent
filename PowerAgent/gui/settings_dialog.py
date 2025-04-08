# ========================================
# 文件名: PowerAgent/gui/settings_dialog.py
# -----------------------------------------------------------------------
# gui/settings_dialog.py
# -*- coding: utf-8 -*-

import platform
import os
from PySide6.QtWidgets import (
    QDialog, QLineEdit, QPushButton, QVBoxLayout, QFormLayout,
    QDialogButtonBox, QCheckBox, QLabel, QHBoxLayout,
    QComboBox, QSizePolicy, QSpacerItem, QGroupBox, QMessageBox # <<< ADDED QMessageBox
)
from PySide6.QtCore import QStandardPaths, QCoreApplication, Qt, QSize
from PySide6.QtGui import QIcon

# Import constants needed for tooltips/paths
from constants import SETTINGS_APP_NAME, ORG_NAME
# Import config functions/state
from core import config # To get initial values AND call reset function <<< MODIFIED

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("应用程序设置")
        self.setModal(True)
        self.setMinimumWidth(500)

        # Load current global settings initially to populate fields
        self.load_initial_values()

        # --- Widgets ---
        # (API Inputs, Theme, Autostart - unchanged creation, just populated by load_initial_values)
        self.url_input = QLineEdit(self._current_api_url)
        self.url_input.setPlaceholderText("例如: https://api.openai.com")
        self.url_input.setToolTip("输入您的 AI 服务 API 端点 URL")

        self.key_input = QLineEdit(self._current_api_key)
        self.key_input.setPlaceholderText("输入您的 API 密钥")
        self.key_input.setToolTip("输入您的 AI 服务 API 密钥 (保密)")
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)

        self.model_input = QLineEdit(self._current_model_id)
        self.model_input.setPlaceholderText("例如: gpt-4-turbo")
        self.model_input.setToolTip("输入要使用的 AI 模型 ID")

        self.show_hide_button = QPushButton()
        self.show_hide_button.setCheckable(True); self.show_hide_button.setChecked(False)
        self.show_hide_button.setToolTip("显示/隐藏 API 密钥"); self.show_hide_button.setFlat(True)
        self.show_hide_button.setIconSize(QSize(16, 16)); self._update_visibility_icon(False)
        self.show_hide_button.clicked.connect(self.toggle_api_key_visibility)

        key_layout = QHBoxLayout(); key_layout.setContentsMargins(0, 0, 0, 0); key_layout.setSpacing(3)
        key_layout.addWidget(self.key_input, 1); key_layout.addWidget(self.show_hide_button)

        self.theme_combobox = QComboBox()
        self.theme_combobox.addItem("系统默认 (System)", "system"); self.theme_combobox.addItem("暗色 (Dark)", "dark"); self.theme_combobox.addItem("亮色 (Light)", "light")
        self.theme_combobox.setToolTip("选择应用程序界面主题。\n更改后需要应用设置。")
        current_theme_index = self.theme_combobox.findData(self._current_theme)
        self.theme_combobox.setCurrentIndex(current_theme_index if current_theme_index != -1 else 0)

        self.auto_startup_checkbox = QCheckBox("系统登录时启动")
        self.auto_startup_checkbox.setChecked(self._current_auto_startup)
        self.auto_startup_checkbox.setToolTip(self._get_autostart_tooltip())

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: red; padding-top: 5px;"); self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setWordWrap(True); self.error_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.error_label.setVisible(False)

        # --- Layout ---
        api_groupbox = QGroupBox("API 配置"); api_layout = QFormLayout(api_groupbox)
        api_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows); api_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight); api_layout.setSpacing(10)
        api_layout.addRow("API URL:", self.url_input); api_layout.addRow("API 密钥:", key_layout); api_layout.addRow("模型 ID:", self.model_input)

        ui_groupbox = QGroupBox("界面与行为"); ui_layout = QFormLayout(ui_groupbox)
        ui_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows); ui_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight); ui_layout.setSpacing(10)
        ui_layout.addRow("界面主题:", self.theme_combobox); ui_layout.addRow(self.auto_startup_checkbox)

        # --- Reset Button ---
        # <<< ADDED Reset Button >>>
        self.reset_button = QPushButton("恢复默认设置并清除缓存")
        self.reset_button.setToolTip("将所有设置恢复为默认值，并清除聊天历史、命令历史和保存的工作目录。\n此操作无法撤销，需要确认。")
        self.reset_button.clicked.connect(self.handle_reset_settings)
        # Put reset button in its own layout, aligned left
        reset_layout = QHBoxLayout()
        reset_layout.addWidget(self.reset_button)
        reset_layout.addStretch(1) # Pushes button to the left

        # --- Standard Buttons ---
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.button(QDialogButtonBox.StandardButton.Ok).setText("确定")
        button_box.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        button_box.accepted.connect(self.validate_and_accept)
        button_box.rejected.connect(self.reject)

        # --- Main Layout ---
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(api_groupbox); main_layout.addWidget(ui_groupbox)
        main_layout.addLayout(reset_layout) # <<< ADDED Reset button layout >>>
        main_layout.addWidget(self.error_label)
        main_layout.addSpacerItem(QSpacerItem(20, 10, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))
        main_layout.addWidget(button_box)

    def load_initial_values(self):
        """Loads current config values into internal variables for UI population."""
        current_config_values = config.get_current_config()
        self._current_api_key = current_config_values.get("api_key", "")
        self._current_api_url = current_config_values.get("api_url", "")
        self._current_model_id = current_config_values.get("model_id", "")
        self._current_auto_startup = current_config_values.get("auto_startup", False)
        self._current_theme = current_config_values.get("theme", "system")

    def update_fields_from_config(self):
        """Updates the UI fields based on the current config module state."""
        # Reload values from the config module (might have been reset)
        self.load_initial_values()
        # Update UI elements
        self.url_input.setText(self._current_api_url)
        self.key_input.setText(self._current_api_key)
        self.model_input.setText(self._current_model_id)
        self.auto_startup_checkbox.setChecked(self._current_auto_startup)
        current_theme_index = self.theme_combobox.findData(self._current_theme)
        self.theme_combobox.setCurrentIndex(current_theme_index if current_theme_index != -1 else 0)
        # Ensure password visibility is reset if key was cleared
        if not self._current_api_key:
            self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.show_hide_button.setChecked(False)
            self._update_visibility_icon(False)


    def _update_visibility_icon(self, visible: bool):
        # Logic remains the same
        icon_name_on = "visibility"; icon_name_off = "visibility_off"
        icon = QIcon.fromTheme(icon_name_off if not visible else icon_name_on)
        if icon.isNull(): self.show_hide_button.setText("👁️" if not visible else "🚫"); self.show_hide_button.setIcon(QIcon())
        else: self.show_hide_button.setIcon(icon); self.show_hide_button.setText("")

    def _get_autostart_tooltip(self) -> str:
        # Logic remains the same
        startup_tooltip = "启用/禁用在您登录时自动启动应用程序。\n更改可能需要重启应用程序或重新登录才能完全生效。\n\n实现机制:\n"
        try:
            if platform.system() == "Windows": key_path = f"HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\\{SETTINGS_APP_NAME}"; startup_tooltip += f"- Windows 注册表: {key_path}"
            elif platform.system() == "Linux":
                autostart_dir_base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.ConfigLocation); autostart_path = os.path.join(autostart_dir_base, "autostart", f"{SETTINGS_APP_NAME}.desktop") if autostart_dir_base else ""
                startup_tooltip += f"- Linux 桌面条目: {autostart_path}" if autostart_path else "- Linux 桌面条目: (~/.config/autostart/...)"
            elif platform.system() == "Darwin": plist_path = os.path.expanduser(f"~/Library/LaunchAgents/com.{ORG_NAME}.{SETTINGS_APP_NAME}.plist"); startup_tooltip += f"- macOS 启动代理: {plist_path}"
            else: startup_tooltip += f"- 未为 {platform.system()} 实现"
        except Exception as e: print(f"Error generating autostart tooltip details: {e}"); startup_tooltip += "- 无法确定具体路径。"
        return startup_tooltip

    def toggle_api_key_visibility(self, checked):
        # Logic remains the same
        if checked: self.key_input.setEchoMode(QLineEdit.EchoMode.Normal); self.show_hide_button.setToolTip("隐藏 API 密钥")
        else: self.key_input.setEchoMode(QLineEdit.EchoMode.Password); self.show_hide_button.setToolTip("显示 API 密钥")
        self._update_visibility_icon(checked)

    # <<< ADDED Reset Handler >>>
    def handle_reset_settings(self):
        """Handles the reset button click."""
        reply = QMessageBox.warning(
            self,
            "确认重置",
            "您确定要将所有设置恢复为默认值并清除所有缓存数据（包括API密钥、聊天记录、命令历史和保存的目录）吗？\n\n此操作无法撤销！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel # Default button
        )

        if reply == QMessageBox.StandardButton.Yes:
            print("User confirmed reset. Resetting settings and clearing cache...")
            try:
                # Call the reset function in the config module
                config.reset_to_defaults_and_clear_cache()
                print("Config module reset executed.")

                # Update the fields in this dialog to reflect the reset
                self.update_fields_from_config()
                print("Settings dialog fields updated to reflect reset.")

                # Inform the user
                QMessageBox.information(
                    self,
                    "重置完成",
                    "设置已恢复为默认值，缓存已清除。\n您可能需要重新配置API密钥才能使用AI功能。"
                )
                # We don't automatically accept/reject here. The user might still want
                # to Cancel the dialog or make further changes before clicking OK.
                # The main window will handle the update based on whether OK is clicked.

            except Exception as e:
                 print(f"Error during reset process: {e}")
                 QMessageBox.critical(
                    self,
                    "重置错误",
                    f"恢复默认设置时发生错误:\n{e}"
                )
        else:
            print("User cancelled reset.")


    def validate_and_accept(self):
        """Validate inputs before accepting the dialog."""
        api_key = self.key_input.text().strip(); api_url = self.url_input.text().strip(); model_id = self.model_input.text().strip()
        self.error_label.setText(""); self.error_label.setVisible(False)
        default_style = ""; self.url_input.setStyleSheet(default_style); self.key_input.setStyleSheet(default_style); self.model_input.setStyleSheet(default_style)
        errors = []
        if not api_url: errors.append("API URL")
        if not api_key: errors.append("API 密钥")
        if not model_id: errors.append("模型 ID")

        if errors:
            error_msg = "以下必填字段不能为空:\n- " + "\n- ".join(errors); self.error_label.setText(error_msg); self.error_label.setVisible(True)
            error_style = "border: 1px solid red;"; first_error_field = None
            if "API URL" in errors: self.url_input.setStyleSheet(error_style); first_error_field = first_error_field or self.url_input
            if "API 密钥" in errors: self.key_input.setStyleSheet(error_style); first_error_field = first_error_field or self.key_input
            if "模型 ID" in errors: self.model_input.setStyleSheet(error_style); first_error_field = first_error_field or self.model_input
            if first_error_field: first_error_field.setFocus()
            print(f"Settings validation failed: {error_msg}")
            return
        self.accept()

    def get_values(self):
        # Logic remains the same
        selected_theme = self.theme_combobox.currentData()
        valid_themes = ["dark", "light", "system"]; selected_theme = selected_theme if selected_theme in valid_themes else "system"
        return (
            self.key_input.text().strip(), self.url_input.text().strip(), self.model_input.text().strip(),
            self.auto_startup_checkbox.isChecked(), selected_theme
        )