# ========================================
# 文件名: PowerAgent/main.py
# (No changes needed in this file for this feature)
# -----------------------------------------------------------------------
# main.py
# -*- coding: utf-8 -*-

import sys
import os
import platform
import ctypes

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QFont # <<< GUI OPTIMIZATION: For setting default font

# --- 这些导入语句本身是正确的 ---
# 如果 Pylance 报错，请检查 VS Code 工作区设置和 Python 解释器
from constants import APP_NAME, ORG_NAME, SETTINGS_APP_NAME, get_color
from gui.main_window import MainWindow
from gui.palette import setup_palette
from core import config
# ---------------------------------

# --- Determine Application Base Directory ---
# (Logic remains the same)
if getattr(sys, 'frozen', False):
    application_base_dir = os.path.dirname(sys.executable)
else:
    try:
        main_script_path = os.path.abspath(sys.argv[0])
        application_base_dir = os.path.dirname(main_script_path)
    except Exception:
        application_base_dir = os.path.dirname(os.path.abspath(__file__))
print(f"[Main] Application Base Directory: {application_base_dir}")

# --- Main Execution ---
if __name__ == "__main__":

    # --- Platform Specific Setup ---
    # (Logic remains the same)
    if platform.system() == "Windows":
        myappid = f"{ORG_NAME}.{APP_NAME}.{SETTINGS_APP_NAME}.1.0"
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
            print(f"[Main] AppUserModelID set to: {myappid}")
        except AttributeError:
            print("[Main] Warning: Could not set AppUserModelID (ctypes or shell32 not found).")
        except Exception as e:
            print(f"[Main] Warning: Could not set AppUserModelID: {e}")

    # Set Organization and Application name EARLY
    QCoreApplication.setOrganizationName(ORG_NAME)
    QCoreApplication.setApplicationName(SETTINGS_APP_NAME)
    print(f"[Main] OrgName: {QCoreApplication.organizationName()}, AppName: {QCoreApplication.applicationName()}")

    # --- Load Configuration EARLY (includes theme) ---
    print("[Main] Loading configuration...")
    # 假设 core.config 模块加载成功 (Pylance 错误解决后)
    load_success, load_message = config.load_config()
    print(f"[Main] Config load status: {load_success} - {load_message}")
    # config.APP_THEME is now set

    # --- Application Setup ---
    app = QApplication(sys.argv)

    # <<< GUI OPTIMIZATION: Set a default application font for consistency >>>
    default_font = QFont()
    default_font.setPointSize(10) # Adjust point size as desired
    app.setFont(default_font)
    print(f"[Main] Default application font set.")

    # --- Apply Initial Theme/Style ---
    # 假设 config.APP_THEME 和 setup_palette 加载成功 (Pylance 错误解决后)
    print(f"[Main] Applying initial theme: {config.APP_THEME}")
    setup_palette(app, config.APP_THEME) # Apply loaded theme's global palette

    # --- Create and Show Main Window ---
    print("[Main] Creating MainWindow...")
    # Pass the application base directory if needed, or let MainWindow determine it
    # 假设 MainWindow 加载成功 (Pylance 错误解决后)
    main_window = MainWindow(application_base_dir=application_base_dir)
    print("[Main] Showing MainWindow...")
    main_window.show()

    # --- Start Event Loop ---
    print("[Main] Starting application event loop...")
    sys.exit(app.exec())