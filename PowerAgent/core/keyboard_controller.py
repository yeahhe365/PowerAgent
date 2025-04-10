# ========================================
# 文件名: PowerAgent/core/keyboard_controller.py
# (NEW FILE - Contains keyboard control logic)
# ----------------------------------------
# core/keyboard_controller.py
# -*- coding: utf-8 -*-

"""
Handles keyboard control actions using pynput.
"""

import time
import traceback
from PySide6.QtCore import QObject, Signal

try:
    from pynput import keyboard
    PYNPUT_AVAILABLE = True
    print("pynput library imported successfully for keyboard control.")
except ImportError:
    PYNPUT_AVAILABLE = False
    print("*"*60)
    print("WARNING: Failed to import 'pynput'. Keyboard control functionality will be disabled.")
    print("Please install it using: pip install pynput")
    print("On macOS, you might need to grant accessibility permissions.")
    print("On Linux, X server access is typically required.")
    print("*"*60)

class KeyboardController(QObject):
    """Encapsulates pynput keyboard control logic."""
    error_signal = Signal(str) # Emits error messages

    def __init__(self, parent=None):
        super().__init__(parent)
        self._controller = None
        if PYNPUT_AVAILABLE:
            try:
                # 尝试初始化 pynput 控制器
                self._controller = keyboard.Controller()
                print("[KeyboardCtrl] pynput.keyboard.Controller initialized successfully.")
            except Exception as e:
                # 捕获初始化时可能发生的任何错误 (例如权限、环境问题)
                err_msg = f"Failed to initialize pynput Controller: {e}. Keyboard control disabled."
                print(err_msg)
                traceback.print_exc()
                self.error_signal.emit(err_msg) # 发出错误信号
                self._controller = None # 确保控制器为 None
        else:
             self._controller = None # 如果 pynput 不可用，控制器也为 None

    def is_available(self) -> bool:
        """Check if the keyboard controller is initialized and ready."""
        return self._controller is not None

    def _emit_error(self, message: str):
        """Safely emit an error message."""
        print(f"[KeyboardCtrl] Error: {message}")
        try:
            self.error_signal.emit(message)
        except RuntimeError as e:
            print(f"[KeyboardCtrl] Warning: Could not emit error signal: {e}")
        except Exception as e:
            print(f"[KeyboardCtrl] Unexpected error emitting signal: {e}")

    def _get_pynput_key(self, key_name: str):
        """Maps string names to pynput Key objects or characters. Raises ValueError if invalid."""
        if not isinstance(key_name, str) or not key_name:
            raise ValueError("Key name must be a non-empty string.")

        key_name_lower = key_name.lower()
        # Map common special keys
        # Using getattr for robustness against different pynput versions/platforms
        key_map = {
            'enter': getattr(keyboard.Key, 'enter', None), 'return': getattr(keyboard.Key, 'enter', None),
            'tab': getattr(keyboard.Key, 'tab', None),
            'space': getattr(keyboard.Key, 'space', None), 'spacebar': getattr(keyboard.Key, 'space', None),
            'esc': getattr(keyboard.Key, 'esc', None), 'escape': getattr(keyboard.Key, 'esc', None),
            'ctrl': getattr(keyboard.Key, 'ctrl', None), 'ctrl_l': getattr(keyboard.Key, 'ctrl_l', None), 'ctrl_r': getattr(keyboard.Key, 'ctrl_r', None),
            'shift': getattr(keyboard.Key, 'shift', None), 'shift_l': getattr(keyboard.Key, 'shift_l', None), 'shift_r': getattr(keyboard.Key, 'shift_r', None),
            'alt': getattr(keyboard.Key, 'alt', None), 'alt_l': getattr(keyboard.Key, 'alt_l', None),
            'alt_gr': getattr(keyboard.Key, 'alt_gr', None), 'alt_r': getattr(keyboard.Key, 'alt_r', None),
            'cmd': getattr(keyboard.Key, 'cmd', None), 'cmd_l': getattr(keyboard.Key, 'cmd_l', None), 'cmd_r': getattr(keyboard.Key, 'cmd_r', None),
            'win': getattr(keyboard.Key, 'cmd', None), 'super': getattr(keyboard.Key, 'cmd', None), # Map win/super to cmd
            'backspace': getattr(keyboard.Key, 'backspace', None),
            'delete': getattr(keyboard.Key, 'delete', None), 'del': getattr(keyboard.Key, 'delete', None),
            'caps_lock': getattr(keyboard.Key, 'caps_lock', None),
            'home': getattr(keyboard.Key, 'home', None),
            'end': getattr(keyboard.Key, 'end', None),
            'page_up': getattr(keyboard.Key, 'page_up', None), 'pgup': getattr(keyboard.Key, 'page_up', None),
            'page_down': getattr(keyboard.Key, 'page_down', None), 'pgdn': getattr(keyboard.Key, 'page_down', None),
            'up': getattr(keyboard.Key, 'up', None),
            'down': getattr(keyboard.Key, 'down', None),
            'left': getattr(keyboard.Key, 'left', None),
            'right': getattr(keyboard.Key, 'right', None),
            'insert': getattr(keyboard.Key, 'insert', None), 'ins': getattr(keyboard.Key, 'insert', None),
            'print_screen': getattr(keyboard.Key, 'print_screen', None), 'prtscn': getattr(keyboard.Key, 'print_screen', None),
            'scroll_lock': getattr(keyboard.Key, 'scroll_lock', None),
            'pause': getattr(keyboard.Key, 'pause', None),
            'num_lock': getattr(keyboard.Key, 'num_lock', None),
            'menu': getattr(keyboard.Key, 'menu', None),
            # Function keys F1-F20
            **{f'f{i}': getattr(keyboard.Key, f'f{i}', None) for i in range(1, 21)}
        }
        # Filter out None values where key might not exist on a platform/version
        key_map = {k: v for k, v in key_map.items() if v is not None}

        special_key = key_map.get(key_name_lower)
        if special_key:
            # print(f"    Mapping '{key_name}' to Special Key: {special_key}") # Debug print
            return special_key
        elif len(key_name) == 1:
            # Assume single characters are literal keys
             # print(f"    Mapping '{key_name}' to Literal Character Key") # Debug print
             return key_name # pynput controller methods handle single chars
        else:
            # Raise an error if the key name is not recognized
            raise ValueError(f"Unrecognized key name for keyboard action: '{key_name}'")

    def type_text(self, text: str):
        """Types the given text using the keyboard controller."""
        if not self.is_available():
            self._emit_error("Keyboard controller not available.")
            return
        if not isinstance(text, str):
             self._emit_error(f"Invalid argument for type_text: 'text' must be a string, got {type(text).__name__}.")
             return

        print(f"[KeyboardCtrl] Attempting to type: '{text[:50]}{'...' if len(text)>50 else ''}'")
        try:
            # Add small delay before typing for robustness
            time.sleep(0.2)
            self._controller.type(text)
            print(f"[KeyboardCtrl] Typed successfully.")
            # Add small delay after typing
            time.sleep(0.2)
        except Exception as e:
             err_msg = f"Error during type_text: {e}"
             self._emit_error(err_msg)
             traceback.print_exc()

    def press_key(self, key_name: str):
        """Presses and releases a single key (special or character)."""
        if not self.is_available():
            self._emit_error("Keyboard controller not available.")
            return
        print(f"[KeyboardCtrl] Attempting to press key: '{key_name}'")
        try:
            target_key = self._get_pynput_key(key_name) # Can raise ValueError
             # Add small delay before pressing
            time.sleep(0.2)
            self._controller.press(target_key)
            time.sleep(0.05) # Small delay between press and release
            self._controller.release(target_key)
            print(f"[KeyboardCtrl] Pressed and released key: {key_name}")
             # Add small delay after action
            time.sleep(0.2)
        except ValueError as e: # Catch mapping errors from _get_pynput_key
            self._emit_error(str(e))
        except Exception as e:
             err_msg = f"Error during press_key '{key_name}': {e}"
             self._emit_error(err_msg)
             traceback.print_exc()


    def press_hotkey(self, key_names: list[str]):
        """Presses and releases a combination of keys (modifiers + main key)."""
        if not self.is_available():
            self._emit_error("Keyboard controller not available.")
            return
        if not isinstance(key_names, list) or len(key_names) < 2:
             self._emit_error(f"Invalid argument for press_hotkey: 'keys' must be a list of at least two strings, got {key_names}.")
             return

        print(f"[KeyboardCtrl] Attempting hotkey: {'+'.join(key_names)}")
        mapped_keys = []
        pressed_keys_for_cleanup = []
        try:
            # Map all keys first - this can raise ValueError
            for name in key_names:
                mapped_keys.append(self._get_pynput_key(name))

             # Add small delay before starting hotkey
            time.sleep(0.2)

            # Press modifiers (all keys except the last one)
            modifiers = mapped_keys[:-1]
            main_key = mapped_keys[-1]

            for mod in modifiers:
                self._controller.press(mod)
                pressed_keys_for_cleanup.append(mod) # Track pressed keys
                time.sleep(0.05)

            # Press and release the main key
            self._controller.press(main_key)
            pressed_keys_for_cleanup.append(main_key)
            time.sleep(0.05)
            self._controller.release(main_key)
            pressed_keys_for_cleanup.remove(main_key) # Main key released
            time.sleep(0.05)

            # Release modifiers in reverse order
            for mod in reversed(modifiers):
                self._controller.release(mod)
                if mod in pressed_keys_for_cleanup:
                    pressed_keys_for_cleanup.remove(mod)
                time.sleep(0.05)

            print(f"[KeyboardCtrl] Executed hotkey: {'+'.join(key_names)}")
             # Add small delay after action
            time.sleep(0.2)

        except ValueError as e: # Catch mapping errors
            self._emit_error(str(e))
            # Release any keys that might have been pressed before the error
            self._release_keys_safely(pressed_keys_for_cleanup)
        except Exception as e:
             err_msg = f"Error during press_hotkey '{'+'.join(key_names)}': {e}"
             self._emit_error(err_msg)
             traceback.print_exc()
             # Release any potentially stuck keys
             self._release_keys_safely(pressed_keys_for_cleanup)

    def _release_keys_safely(self, keys_to_release):
        """Attempt to release a list of potentially pressed keys, ignoring errors."""
        if not self.is_available() or not keys_to_release:
            return
        print(f"[KeyboardCtrl] Attempting cleanup release for keys: {keys_to_release}")
        # Release in reverse order of typical pressing
        for key in reversed(keys_to_release):
            try:
                self._controller.release(key)
                time.sleep(0.02) # Small delay between cleanup releases
            except Exception as release_err:
                 # Ignore errors during cleanup release, just log them
                 print(f"[KeyboardCtrl] Ignoring error during cleanup release of key {key}: {release_err}")