# ========================================
# 文件名: PowerAgent/core/keyboard_controller.py
# (MODIFIED - Replaced type_text with paste_text using pyperclip and hotkeys)
# ----------------------------------------
# core/keyboard_controller.py
# -*- coding: utf-8 -*-

"""
Handles keyboard control actions using pynput for hotkeys and pyperclip for clipboard.
"""

import time
import platform
import traceback
from PySide6.QtCore import QObject, Signal

# --- pynput Import ---
try:
    from pynput import keyboard
    PYNPUT_AVAILABLE = True
    print("[KeyboardCtrl] pynput library imported successfully.")
except ImportError:
    PYNPUT_AVAILABLE = False
    print("*"*60)
    print("WARNING: Failed to import 'pynput'. Keyboard hotkey functionality WILL BE DISABLED.")
    print("Please install it using: pip install pynput")
    print("On macOS, ensure PowerAgent has Accessibility permissions.")
    print("On Linux, ensure input event manipulation is allowed.")
    print("*"*60)
except Exception as import_err:
    PYNPUT_AVAILABLE = False
    print("*"*60)
    print(f"ERROR: An unexpected error occurred while importing pynput: {import_err}")
    print("Keyboard hotkey functionality WILL BE DISABLED.")
    print("*"*60)
    traceback.print_exc()

# --- pyperclip Import ---
try:
    import pyperclip
    PYPERCLIP_AVAILABLE = True
    print("[KeyboardCtrl] pyperclip library imported successfully.")
except ImportError:
    PYPERCLIP_AVAILABLE = False
    print("*"*60)
    print("WARNING: Failed to import 'pyperclip'. Clipboard paste functionality WILL BE DISABLED.")
    print("Please install it using: pip install pyperclip")
    print("*"*60)
except Exception as import_err:
    PYPERCLIP_AVAILABLE = False
    print("*"*60)
    print(f"ERROR: An unexpected error occurred while importing pyperclip: {import_err}")
    print("Clipboard paste functionality WILL BE DISABLED.")
    print("*"*60)
    traceback.print_exc()


class KeyboardController(QObject):
    """Encapsulates pynput keyboard control logic and pyperclip paste."""
    error_signal = Signal(str) # Emits error messages

    def __init__(self, parent=None):
        super().__init__(parent)
        self._controller = None
        self._pynput_initialized_ok = False
        self._init_error_emitted = False # Track if init error was already emitted

        if PYNPUT_AVAILABLE:
            try:
                print("[KeyboardCtrl] Initializing pynput.keyboard.Controller...")
                self._controller = keyboard.Controller()
                self._controller.release(keyboard.Key.shift) # Try releasing shift (harmless check)
                self._pynput_initialized_ok = True
                print("[KeyboardCtrl] pynput.keyboard.Controller initialized successfully.")
            except Exception as e:
                err_msg = f"FATAL: Failed to initialize or verify pynput Controller: {e}. Keyboard hotkey control DISABLED."
                print(err_msg)
                traceback.print_exc()
                self._controller = None
                self._pynput_initialized_ok = False
        else:
             self._controller = None
             self._pynput_initialized_ok = False

        # Check pyperclip availability (no complex init needed)
        if not PYPERCLIP_AVAILABLE and not self._init_error_emitted:
            # Emit error only once if pyperclip failed import
            self._emit_error("pyperclip library not available. Clipboard paste functionality disabled.")
            self._init_error_emitted = True # Prevent spamming

    def is_pynput_available(self) -> bool:
        """Check if the pynput keyboard controller is initialized and ready for hotkeys."""
        if not PYNPUT_AVAILABLE:
            return False
        if not self._pynput_initialized_ok:
            if not self._init_error_emitted:
                 self._emit_error("pynput controller failed to initialize (check logs/permissions). Keyboard hotkey control disabled.")
                 self._init_error_emitted = True
            return False
        return self._controller is not None

    def is_paste_available(self) -> bool:
        """Check if both pynput (for hotkey) and pyperclip (for clipboard) are ready."""
        pynput_ready = self.is_pynput_available()
        pyperclip_ready = PYPERCLIP_AVAILABLE
        if not pyperclip_ready and not self._init_error_emitted:
             self._emit_error("pyperclip library not available. Clipboard paste functionality disabled.")
             self._init_error_emitted = True # May have already been set, but safe to set again

        return pynput_ready and pyperclip_ready

    def _emit_error(self, message: str):
        """Safely emit an error message."""
        print(f"[KeyboardCtrl] Error: {message}")
        try:
            if self.receivers(self.error_signal) > 0:
                 self.error_signal.emit(message)
            else:
                 print("[KeyboardCtrl] Warning: No receivers connected to error_signal.")
        except RuntimeError as e:
            print(f"[KeyboardCtrl] Warning: Could not emit error signal: {e}")
        except Exception as e:
            print(f"[KeyboardCtrl] Unexpected error emitting signal: {e}")

    def _get_pynput_key(self, key_name: str):
        """Maps string names to pynput Key objects or characters. Raises ValueError if invalid."""
        # (This function remains the same as before)
        if not isinstance(key_name, str) or not key_name:
            raise ValueError("Key name must be a non-empty string.")

        key_name_lower = key_name.lower()
        key_map = {
            'enter': keyboard.Key.enter, 'return': keyboard.Key.enter,
            'tab': keyboard.Key.tab,
            'space': keyboard.Key.space, 'spacebar': keyboard.Key.space,
            'esc': keyboard.Key.esc, 'escape': keyboard.Key.esc,
            'ctrl': keyboard.Key.ctrl, 'ctrl_l': keyboard.Key.ctrl_l, 'ctrl_r': keyboard.Key.ctrl_r,
            'shift': keyboard.Key.shift, 'shift_l': keyboard.Key.shift_l, 'shift_r': keyboard.Key.shift_r,
            'alt': keyboard.Key.alt, 'alt_l': keyboard.Key.alt_l,
            'alt_gr': keyboard.Key.alt_gr, 'alt_r': keyboard.Key.alt_r,
            'cmd': keyboard.Key.cmd, 'cmd_l': keyboard.Key.cmd_l, 'cmd_r': keyboard.Key.cmd_r, # macOS command key
            'win': keyboard.Key.cmd, 'super': keyboard.Key.cmd, 'windows': keyboard.Key.cmd, # Windows/Linux Super key mapped to cmd
            'backspace': keyboard.Key.backspace,
            'delete': keyboard.Key.delete, 'del': keyboard.Key.delete,
            'caps_lock': keyboard.Key.caps_lock,
            'home': keyboard.Key.home,
            'end': keyboard.Key.end,
            'page_up': keyboard.Key.page_up, 'pgup': keyboard.Key.page_up,
            'page_down': keyboard.Key.page_down, 'pgdn': keyboard.Key.page_down,
            'up': keyboard.Key.up,
            'down': keyboard.Key.down,
            'left': keyboard.Key.left,
            'right': keyboard.Key.right,
            'insert': keyboard.Key.insert, 'ins': keyboard.Key.insert,
            'print_screen': keyboard.Key.print_screen, 'prtscn': keyboard.Key.print_screen,
            'scroll_lock': keyboard.Key.scroll_lock,
            'pause': keyboard.Key.pause,
            'num_lock': keyboard.Key.num_lock,
            'menu': keyboard.Key.menu,
            **{f'f{i}': getattr(keyboard.Key, f'f{i}', None) for i in range(1, 21)}
        }
        key_map = {k: v for k, v in key_map.items() if v is not None}

        special_key = key_map.get(key_name_lower)
        if special_key:
            return special_key
        elif len(key_name) == 1:
             # For literal characters, pynput expects the character itself for hotkeys
             return key_name
        else:
            raise ValueError(f"Unrecognized or unsupported key name: '{key_name}'")

    # --- REMOVED type_text method ---
    # def type_text(self, text: str): ...

    # --- NEW paste_text method ---
    def paste_text(self, text: str):
        """Copies text to clipboard and simulates Paste hotkey (Ctrl+V or Cmd+V)."""
        if not self.is_paste_available(): # Checks both pynput and pyperclip
            print("[KeyboardCtrl] paste_text skipped: Controller or pyperclip not available.")
            # Error already emitted by is_paste_available if needed
            return
        if not isinstance(text, str):
             self._emit_error(f"Invalid argument for paste_text: 'text' must be a string, got {type(text).__name__}.")
             return

        print(f"[KeyboardCtrl] Attempting to paste text (len={len(text)}): '{text[:50]}{'...' if len(text)>50 else ''}'")
        original_clipboard_content = None
        paste_keys = []
        try:
            # 1. Get Paste Hotkey based on OS
            os_name = platform.system()
            if os_name == "Darwin": # macOS
                paste_keys = ['cmd', 'v']
            else: # Windows, Linux
                paste_keys = ['ctrl', 'v']
            print(f"[KeyboardCtrl]   Using paste hotkey: {'+'.join(paste_keys)}")

            # 2. (Optional but recommended) Store original clipboard content
            try:
                original_clipboard_content = pyperclip.paste()
                print("[KeyboardCtrl]   Stored original clipboard content.")
            except Exception as paste_err:
                # Non-fatal error, proceed without restoring later
                print(f"[KeyboardCtrl]   Warning: Could not get original clipboard content: {paste_err}")
                original_clipboard_content = None # Ensure it's None

            # Add small delay before clipboard interaction
            time.sleep(0.2)

            # 3. Copy desired text to clipboard
            print(f"[KeyboardCtrl]   Copying target text to clipboard...")
            pyperclip.copy(text)
            time.sleep(0.1) # Give clipboard time to update

            # 4. Simulate Paste Hotkey
            print(f"[KeyboardCtrl]   Simulating paste hotkey press...")
            self.press_hotkey(paste_keys) # Use existing hotkey method

            # 5. (Optional) Restore original clipboard content
            if original_clipboard_content is not None:
                print("[KeyboardCtrl]   Restoring original clipboard content...")
                time.sleep(0.2) # Wait a bit before restoring
                try:
                    pyperclip.copy(original_clipboard_content)
                except Exception as copy_err:
                    print(f"[KeyboardCtrl]   Warning: Could not restore original clipboard content: {copy_err}")
            else:
                 # Clear clipboard if we couldn't store original? Risky. Let's leave it.
                 # pyperclip.copy("")
                 pass

            print(f"[KeyboardCtrl] Pasted text successfully.")
            # Add small delay after action
            time.sleep(0.2)

        except Exception as e:
             err_msg = f"Error during paste_text execution: {type(e).__name__} - {e}"
             self._emit_error(err_msg)
             traceback.print_exc()
             # If error occurred after copying but before restoring, try restoring anyway
             if original_clipboard_content is not None:
                 print("[KeyboardCtrl] Attempting clipboard restore after error.")
                 try:
                     time.sleep(0.1)
                     pyperclip.copy(original_clipboard_content)
                 except Exception as restore_err:
                     print(f"[KeyboardCtrl]   Ignoring error during clipboard restore after failure: {restore_err}")

    def press_key(self, key_name: str):
        """Presses and releases a single key (special or character)."""
        if not self.is_pynput_available(): # Check pynput availability
            print(f"[KeyboardCtrl] press_key '{key_name}' skipped: pynput Controller not available.")
            return
        print(f"[KeyboardCtrl] Attempting to press key: '{key_name}'")
        target_key = None
        try:
            target_key = self._get_pynput_key(key_name) # Can raise ValueError
            time.sleep(0.2)
            if not self._controller: raise RuntimeError("Controller became invalid unexpectedly.")

            print(f"[KeyboardCtrl]   Pressing: {target_key}")
            self._controller.press(target_key)
            time.sleep(0.05)

            print(f"[KeyboardCtrl]   Releasing: {target_key}")
            self._controller.release(target_key)
            print(f"[KeyboardCtrl] Pressed and released key '{key_name}' successfully.")
            time.sleep(0.2)
        except ValueError as e:
            self._emit_error(str(e))
        except Exception as e:
             err_msg = f"Error during press_key execution for '{key_name}': {type(e).__name__} - {e}"
             self._emit_error(err_msg)
             traceback.print_exc()
             if target_key:
                 print(f"[KeyboardCtrl] Attempting cleanup release for {target_key} after error.")
                 self._release_keys_safely([target_key])

    def press_hotkey(self, key_names: list[str]):
        """Presses and releases a combination of keys (modifiers + main key)."""
        if not self.is_pynput_available(): # Check pynput availability
            print(f"[KeyboardCtrl] press_hotkey '{'+'.join(key_names)}' skipped: pynput Controller not available.")
            return
        if not isinstance(key_names, list) or len(key_names) < 1:
             self._emit_error(f"Invalid argument for press_hotkey: 'keys' must be a non-empty list of strings, got {key_names}.")
             return

        print(f"[KeyboardCtrl] Attempting hotkey: {'+'.join(key_names)}")
        mapped_keys = []
        pressed_keys_for_cleanup = []
        try:
            if not self._controller: raise RuntimeError("Controller became invalid unexpectedly.")
            print("[KeyboardCtrl]   Mapping keys...")
            for name in key_names:
                mapped_keys.append(self._get_pynput_key(name))
            print(f"[KeyboardCtrl]   Mapped keys: {mapped_keys}")
            time.sleep(0.2)

            print("[KeyboardCtrl]   Pressing keys...")
            for key in mapped_keys:
                print(f"[KeyboardCtrl]     Pressing: {key}")
                self._controller.press(key)
                pressed_keys_for_cleanup.append(key)
                time.sleep(0.05)

            print("[KeyboardCtrl]   Releasing keys (reverse order)...")
            for key in reversed(pressed_keys_for_cleanup):
                print(f"[KeyboardCtrl]     Releasing: {key}")
                self._controller.release(key)
                time.sleep(0.05)
            pressed_keys_for_cleanup = []

            print(f"[KeyboardCtrl] Executed hotkey '{'+'.join(key_names)}' successfully.")
            time.sleep(0.2)

        except ValueError as e:
            err_msg = f"Error mapping keys for hotkey '{'+'.join(key_names)}': {e}"
            self._emit_error(err_msg)
            self._release_keys_safely(pressed_keys_for_cleanup)
        except Exception as e:
             err_msg = f"Error during press_hotkey execution for '{'+'.join(key_names)}': {type(e).__name__} - {e}"
             self._emit_error(err_msg)
             traceback.print_exc()
             self._release_keys_safely(pressed_keys_for_cleanup)

    def _release_keys_safely(self, keys_to_release):
        """Attempt to release a list of potentially pressed keys, ignoring errors."""
        # (This function remains the same as before)
        if not self._controller or not keys_to_release:
            return
        print(f"[KeyboardCtrl] Attempting cleanup release for keys: {keys_to_release}")
        for key in reversed(keys_to_release):
            try:
                print(f"[KeyboardCtrl]   Cleanup releasing: {key}")
                self._controller.release(key)
                time.sleep(0.02)
            except Exception as release_err:
                 print(f"[KeyboardCtrl]   Ignoring error during cleanup release of key {key}: {release_err}")
        print("[KeyboardCtrl] Cleanup release finished.")