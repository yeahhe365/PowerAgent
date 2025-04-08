# core/autostart.py
# -*- coding: utf-8 -*-

import sys
import os
import platform
import ctypes # For checking admin rights on Windows
from PySide6.QtCore import QSettings, QStandardPaths, QCoreApplication

# Import constants needed for paths/names
from constants import SETTINGS_APP_NAME, ORG_NAME

# --- Auto-Startup Management ---
def is_admin():
    """Check if the script is running with administrator privileges on Windows."""
    if platform.system() == "Windows":
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception as e:
            print(f"Error checking admin status: {e}")
            return False
    # On non-Windows, this check is typically not needed for user-level autostart
    return False

def get_script_path():
    """Gets the absolute path to the currently running script or executable."""
    if getattr(sys, 'frozen', False): # Check if running as a bundled executable (PyInstaller)
        # sys.executable is the path to the bundled .exe or app
        return sys.executable
    else: # Running as a script
        # sys.argv[0] is generally the path of the script that was initially run
        return os.path.abspath(sys.argv[0])

def get_python_executable():
    """Gets the path to the pythonw executable if possible, otherwise python."""
    # sys.executable is the path to the Python interpreter running the script
    python_exe = sys.executable
    if platform.system() == "Windows" and not getattr(sys, 'frozen', False):
        # Prefer pythonw.exe for scripts to avoid console window on startup
        pythonw_exe = python_exe.replace("python.exe", "pythonw.exe")
        if os.path.exists(pythonw_exe):
            return pythonw_exe
    return python_exe # Fallback for non-windows, bundled apps, or if pythonw not found

def set_auto_startup(enable):
    """Enable or disable auto-startup for the application."""
    # Ensure app/org names are set for QSettings/paths if not already
    if not QCoreApplication.organizationName():
        QCoreApplication.setOrganizationName(ORG_NAME)
    if not QCoreApplication.applicationName():
        QCoreApplication.setApplicationName(SETTINGS_APP_NAME)

    app_name = SETTINGS_APP_NAME # Use the constant
    script_path = get_script_path()

    # Determine the command to run
    if getattr(sys, 'frozen', False): # Bundled app
        run_command = f'"{script_path}"'
    else: # Running as script
        python_exe = get_python_executable()
        run_command = f'"{python_exe}" "{script_path}"'


    print(f"Attempting to set auto-startup to: {enable}")
    print(f"  App Name: {app_name}")
    print(f"  Command: {run_command}")
    print(f"  Platform: {platform.system()}")


    if platform.system() == "Windows":
        # HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run
        # This key usually doesn't require admin rights
        settings_key = r"HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run"
        # Use NativeFormat for registry access
        settings = QSettings(settings_key, QSettings.Format.NativeFormat)
        try:
            current_value = settings.value(app_name)
            if enable:
                if current_value != run_command:
                    print(f"Writing registry key: {settings_key}\\{app_name}")
                    settings.setValue(app_name, run_command)
                    settings.sync() # Ensure changes are written immediately
                    # Verification
                    if settings.value(app_name) == run_command:
                         print("Auto-startup enabled successfully (Registry).")
                    else:
                         print("Verification failed: Could not enable auto-startup (Registry write error?).")
                else:
                    print(f"Registry key already exists with correct value.")
            else: # Disable
                if settings.contains(app_name):
                    print(f"Removing registry key: {settings_key}\\{app_name}")
                    settings.remove(app_name)
                    settings.sync() # Ensure changes are written immediately
                     # Verification
                    if not settings.contains(app_name):
                        print("Auto-startup disabled successfully (Registry).")
                    else:
                         print("Verification failed: Could not disable auto-startup (Registry remove error?).")
                else:
                    print(f"Registry key not found for removal: {settings_key}\\{app_name}")

        except Exception as e:
            print(f"Error updating registry for auto-startup: {e}")
            # No need to suggest admin rights here as HKCU usually doesn't need it.
            # If it fails, it's likely a different issue (permissions policy, antivirus).

    elif platform.system() == "Linux":
        # ~/.config/autostart/AppName.desktop
        try:
            autostart_dir = os.path.join(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.ConfigLocation), "autostart")
            desktop_file_path = os.path.join(autostart_dir, f"{app_name}.desktop")

            if enable:
                os.makedirs(autostart_dir, exist_ok=True) # Ensure directory exists
                print(f"Creating/updating desktop entry: {desktop_file_path}")
                # Use generic AppName and Comment, or fetch from constants if defined
                desktop_entry = f"""[Desktop Entry]
Type=Application
Name={app_name}
Exec={run_command}
Comment=Start {app_name} on login
Terminal=false
X-GNOME-Autostart-enabled=true
"""
                # Try finding an icon (optional)
                icon_path = os.path.join(os.path.dirname(script_path), "assets", "icon.png") # Example path
                if os.path.exists(icon_path):
                    desktop_entry += f"Icon={icon_path}\n"

                with open(desktop_file_path, 'w', encoding='utf-8') as f:
                    f.write(desktop_entry)
                # Ensure correct permissions (usually not needed, but safe)
                os.chmod(desktop_file_path, 0o644) # rw-r--r--
                print("Auto-startup enabled (Linux .desktop file created/updated).")
            else: # Disable
                if os.path.exists(desktop_file_path):
                    print(f"Removing desktop entry: {desktop_file_path}")
                    os.remove(desktop_file_path)
                    print("Auto-startup disabled (Linux .desktop file removed).")
                else:
                    print(f"Autostart file not found for removal: {desktop_file_path}")
        except Exception as e:
            print(f"Error managing Linux auto-startup file: {e}")

    elif platform.system() == "Darwin": # macOS
        # ~/Library/LaunchAgents/com.YourOrgName.AppName.plist
        try:
            launch_agents_dir = os.path.expanduser("~/Library/LaunchAgents")
            # Use constants for label and filename consistency
            plist_label = f"com.{ORG_NAME}.{app_name}"
            plist_filename = f"{plist_label}.plist"
            plist_file_path = os.path.join(launch_agents_dir, plist_filename)


            if enable:
                os.makedirs(launch_agents_dir, exist_ok=True) # Ensure directory exists
                print(f"Creating/updating LaunchAgent file: {plist_file_path}")

                # Split the command into program and arguments for the plist
                if getattr(sys, 'frozen', False): # Bundled app
                    program_args = [script_path]
                else: # Running as script
                     program_args = [get_python_executable(), script_path]

                # Create plist content
                plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{plist_label}</string>
    <key>ProgramArguments</key>
    <array>
        {''.join(f'<string>{arg}</string>' for arg in program_args)}
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <!-- Optional: Define working directory -->
    <key>WorkingDirectory</key>
    <string>{os.path.dirname(script_path)}</string>
    <!-- Optional: Log stdout/stderr -->
    <!--
    <key>StandardOutPath</key>
    <string>/tmp/{app_name}.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/{app_name}.stderr.log</string>
    -->
</dict>
</plist>
"""
                with open(plist_file_path, 'w', encoding='utf-8') as f:
                    f.write(plist_content)
                # Ensure correct permissions
                os.chmod(plist_file_path, 0o644) # rw-r--r--
                print("Auto-startup enabled (macOS LaunchAgent created/updated).")
                print("Note: May require logout/login or manual `launchctl load` to take effect immediately.")
            else: # Disable
                if os.path.exists(plist_file_path):
                    print(f"Removing LaunchAgent file: {plist_file_path}")
                    os.remove(plist_file_path)
                    print("Auto-startup disabled (macOS LaunchAgent removed).")
                    print("Note: May require logout/login or manual `launchctl unload` to take effect immediately.")

                else:
                    print(f"LaunchAgent file not found for removal: {plist_file_path}")
        except Exception as e:
             print(f"Error managing macOS LaunchAgent file: {e}")

    else:
        print(f"Auto-startup not implemented for platform: {platform.system()}")