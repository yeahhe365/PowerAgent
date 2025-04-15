# ========================================
# 文件名: PowerAgent/core/gui_controller.py
# (MODIFIED - Added UI tree extraction functions)
# ----------------------------------------
# core/gui_controller.py
# -*- coding: utf-8 -*-

"""
Handles Windows GUI automation using the 'uiautomation' library.
Includes functions to extract and format UI structure information.
This module should only be imported and used on Windows platforms.
"""

import platform
import time
import traceback
import json # For JSON formatting of UI tree
from typing import Dict, Any, Optional, Union, List # Added List

from PySide6.QtCore import QObject, Signal

# --- uiautomation Import ---
UIAUTOMATION_AVAILABLE = False
UIAUTOMATION_IMPORT_ERROR = ""
if platform.system() == "Windows":
    try:
        import uiautomation as auto
        try:
            # Verify basic functionality without excessive waiting
            auto.GetRootControl(wait_time=0.1)
            UIAUTOMATION_AVAILABLE = True
            print("[GuiController] 'uiautomation' library imported and verified successfully.")
        except Exception as verify_err:
            UIAUTOMATION_AVAILABLE = False
            UIAUTOMATION_IMPORT_ERROR = f"Failed to verify 'uiautomation' functionality: {verify_err}"
            print(f"ERROR: {UIAUTOMATION_IMPORT_ERROR}")
            traceback.print_exc()
    except ImportError:
        UIAUTOMATION_IMPORT_ERROR = "Failed to import 'uiautomation'. Please install it (`pip install uiautomation`). GUI control disabled."
        print(f"WARNING: {UIAUTOMATION_IMPORT_ERROR}")
    except Exception as import_err:
        UIAUTOMATION_IMPORT_ERROR = f"An unexpected error occurred importing 'uiautomation': {import_err}. GUI control disabled."
        print(f"ERROR: {UIAUTOMATION_IMPORT_ERROR}")
        traceback.print_exc()
else:
    UIAUTOMATION_IMPORT_ERROR = "GUI Automation is only supported on Windows."
    auto = None # Define auto as None for type hinting consistency outside Windows

# ============================================================= #
# <<< MODIFICATION START: Added UI Tree Extraction Functions >>>
# ============================================================= #

# --- ERROR LOCATION 1: Line 53 ---
# Pylance Error: 类型表达式中不允许使用变量 (Variable is not allowed in type expression) - referring to 'auto'
def get_simplified_ui_tree(control: auto.Control, max_depth: int = 3, current_depth: int = 0) -> Optional[Dict[str, Any]]:
    """
    递归地获取控件及其子控件的简化信息字典。
    Args:
        control: The uiautomation control object to start from.
        max_depth: Maximum recursion depth.
        current_depth: Current recursion depth (internal use).
    Returns:
        A dictionary representing the simplified UI tree, or None if error/invalid.
    """
    if not UIAUTOMATION_AVAILABLE or not control or current_depth > max_depth:
        return None

    try:
        # 检查控件是否存在且有效 (快速检查)
        # Using Exists with short timeouts helps avoid long waits for disappearing elements.
        if not control.Exists(0.1, 0.05):
             return None

        # 提取关键属性
        info: Dict[str, Any] = {
            "name": control.Name,
            "control_type": control.ControlTypeName.replace("Control", ""), # 更简洁
            "automation_id": control.AutomationId,
            # "class_name": control.ClassName, # 可选，可能太长
            "is_enabled": control.IsEnabled,
            # BoundingRectangle can sometimes throw exceptions if the element disappears
            "rect": None,
            "children": []
        }
        try:
            rect = control.BoundingRectangle
            if rect: info["rect"] = rect.tuple() # 位置信息 (left, top, right, bottom)
        except Exception: pass # Ignore rect errors gracefully

        # 过滤掉完全没有标识信息的控件 (可根据需要调整)
        if not info["name"] and not info["automation_id"] and info["control_type"] not in ["Separator", "Image"]:
             return None # 跳过完全匿名的非结构性控件

        # 递归获取子控件 (限制深度)
        if current_depth < max_depth:
            children = []
            try:
                # GetChildren can also fail if the parent disappears
                children = control.GetChildren()
            except Exception as get_child_err:
                 print(f"Warning: Failed to get children for control {info.get('name', 'N/A')}: {get_child_err}")

            if children:
                for child in children:
                    child_info = get_simplified_ui_tree(child, max_depth, current_depth + 1)
                    if child_info:
                        info["children"].append(child_info)
            # 如果没有子节点或子节点递归返回None，移除空的 children 列表
            if not info["children"]:
                del info["children"]

        return info

    except Exception as e:
        # 捕获查找或访问属性时可能发生的错误 (例如控件消失)
        control_name = "[Error getting name]"
        try: control_name = control.Name
        except Exception: pass
        print(f"Warning: Error processing control '{control_name}': {type(e).__name__} - {e}")
        return None

def format_tree_as_text(node: Optional[Dict[str, Any]], indent: str = "") -> str:
    """
    (示例) 将简化的 UI 树字典格式化为人类可读的文本。
    Args:
        node: The dictionary node from get_simplified_ui_tree.
        indent: The current indentation string.
    Returns:
        A formatted string representation of the UI tree node and its children.
    """
    if not node: return ""

    # 提取基本信息，处理 None 值
    name = f"'{node.get('name', '')}'" if node.get('name') else "[无名称]"
    ctype = node.get('control_type', '未知类型')
    aid = f" (ID: '{node.get('automation_id')}')" if node.get('automation_id') else ""
    enabled = '可用' if node.get('is_enabled', True) else '禁用'
    # rect_info = f" @{node.get('rect')}" if node.get('rect') else "" # 坐标信息通常太冗长

    # 改进格式，更紧凑
    line = f"{indent}- {ctype}{aid}: {name} [{enabled}]\n"
    text = line

    children_info: List[Dict[str, Any]] = node.get("children", [])
    if children_info:
        # text += f"{indent}  Children:\n" # 可选的层级提示
        for i, child in enumerate(children_info):
            # Pass indent + "  " for deeper levels
            text += format_tree_as_text(child, indent + "  ")
    return text

def get_active_window_ui_text(format_type: str = "text", max_depth: int = 3) -> Optional[str]:
    """
    获取当前活动窗口的 UI 结构信息，并格式化为文本。
    Args:
        format_type: "json" or "text".
        max_depth: Maximum depth to traverse the UI tree.
    Returns:
        A string containing the formatted UI information, or an error message string, or None if uiautomation unavailable.
    """
    if not UIAUTOMATION_AVAILABLE:
        print("[get_active_window_ui_text] Error: uiautomation is not available.")
        return "错误: GUI 分析功能不可用 (uiautomation 未加载)。" # Return error message

    active_window: Optional[auto.Control] = None
    try:
        # 尝试获取前台窗口，超时设短一点避免卡死
        active_window = auto.GetForegroundWindow(wait_time=0.5)

        if not active_window:
            # 如果前台窗口获取失败，尝试获取焦点控件并向上找到窗口
            focused_control = auto.GetFocusedControl(wait_time=0.2)
            if focused_control:
                parent = focused_control
                for _ in range(10): # Limit search depth
                    if parent is None: break
                    if isinstance(parent, auto.WindowControl):
                        active_window = parent
                        break
                    try: parent = parent.GetParentControl()
                    except Exception: break # Stop if GetParentControl fails

        if not active_window:
            print("[get_active_window_ui_text] Error: Could not get the active window.")
            return "错误: 无法确定当前活动窗口。" # Return error message

        window_name = "[Error getting name]"
        window_class = "[Error getting class]"
        try: window_name = active_window.Name
        except Exception: pass
        try: window_class = active_window.ClassName
        except Exception: pass

        print(f"[get_active_window_ui_text] Analyzing active window: '{window_name}' ({window_class})")

        # 2. 获取简化的 UI 树信息
        start_time = time.time()
        simplified_tree = get_simplified_ui_tree(active_window, max_depth)
        analysis_time = time.time() - start_time
        print(f"[get_active_window_ui_text] UI tree analysis took: {analysis_time:.3f}s")

        if not simplified_tree:
            print("[get_active_window_ui_text] No analyzable UI elements found in the active window.")
            return f"信息: 活动窗口 '{window_name}' 中未找到可分析的 UI 元素 (或分析出错)。" # Return info message

        # 3. 格式化为文本 (限制元素数量可以在这里实现，或在递归函数中)
        output_str: Optional[str] = None
        if format_type.lower() == "json":
            try:
                # 使用 indent=None 生成更紧凑的 JSON，节省 token
                output_str = json.dumps(simplified_tree, ensure_ascii=False, indent=None, separators=(',', ':'))
            except Exception as json_err:
                print(f"[get_active_window_ui_text] Error serializing UI tree to JSON: {json_err}")
                return f"错误: 无法将 UI 树序列化为 JSON: {json_err}" # Return error message
        elif format_type.lower() == "text":
            try:
                header = f"活动窗口: '{window_name}' ({window_class})\nUI 结构 (深度 {max_depth}):\n"
                tree_text = format_tree_as_text(simplified_tree, indent="  ")
                output_str = header + tree_text if tree_text else header + "  (无子元素或分析错误)"
            except Exception as text_format_err:
                 print(f"[get_active_window_ui_text] Error formatting UI tree as text: {text_format_err}")
                 return f"错误: 格式化 UI 树为文本时出错: {text_format_err}" # Return error message
        else:
            print(f"[get_active_window_ui_text] Error: Unsupported format type '{format_type}'.")
            return f"错误: 不支持的格式类型 '{format_type}'。" # Return error message

        return output_str

    except Exception as e:
        print(f"[get_active_window_ui_text] Unexpected error: {type(e).__name__} - {e}")
        traceback.print_exc()
        return f"错误: 获取 UI 信息时发生意外错误: {e}" # Return error message

# ============================================================= #
# <<< MODIFICATION END >>>
# ============================================================= #


class GuiController(QObject):
    """
    Encapsulates Windows UI Automation logic using the 'uiautomation' library.
    Provides methods to find and interact with UI elements.
    """
    error_signal = Signal(str) # Emits error messages

    def __init__(self, parent=None):
        super().__init__(parent)
        self._initialized_ok = UIAUTOMATION_AVAILABLE
        self._init_error_emitted = False

        if not self._initialized_ok and not self._init_error_emitted:
            self._emit_error(UIAUTOMATION_IMPORT_ERROR or "GUI Controller could not be initialized.")
            self._init_error_emitted = True

    def is_available(self) -> bool:
        """Check if the GUI controller is initialized and ready."""
        # Re-check availability in case uiautomation was loaded but failed verification initially
        if not self._initialized_ok and UIAUTOMATION_AVAILABLE:
             self._initialized_ok = True # If it's available now, mark as initialized
        elif not self._initialized_ok:
            if not self._init_error_emitted:
                self._emit_error(UIAUTOMATION_IMPORT_ERROR or "GUI Controller not initialized.")
                self._init_error_emitted = True
            return False
        return True # If initialized_ok is true

    def _emit_error(self, message: str):
        """Safely emit an error message."""
        print(f"[GuiController] Error: {message}")
        try:
            # Check if there are any connected receivers before emitting
            if self.receivers(self.error_signal) > 0:
                self.error_signal.emit(message)
            else:
                print("[GuiController] Warning: No receivers connected to error_signal.")
        except RuntimeError as e:
            # This can happen if the receiver (e.g., MainWindow) is being deleted
            print(f"[GuiController] Warning: Could not emit error signal (RuntimeError): {e}")
        except Exception as e:
             print(f"[GuiController] Unexpected error emitting signal: {e}")

    # --- ERROR LOCATION 2: Line 163 ---
    # Pylance Error: 类型表达式中不允许使用变量 (Variable is not allowed in type expression) - likely referring to 'Any'
    def _find_control_internal(
        self,
        locators: Dict[str, Any],
        parent_control: Optional[Any] = None,
        timeout_seconds: int = 5
    ) -> Optional[Any]:
        """
        Internal helper to find a control using provided locators, optionally within a parent.
        Includes a check for control stability using Exists() after finding.
        """
        if not self.is_available(): # Use the method to check availability
            return None
        if not auto: # Ensure auto is not None
            self._emit_error("uiautomation module reference is None.")
            return None

        search_args = {k: v for k, v in locators.items() if v is not None and v != ""} # Filter out None or empty string locators
        if not search_args:
            self._emit_error("Cannot search for control: No valid target locators provided.")
            return None

        search_context = parent_control if parent_control else auto.GetRootControl()
        context_name = "[Unknown Context]"
        try: context_name = parent_control.Name if parent_control else "Desktop Root"
        except Exception: pass

        print(f"[GuiController] Searching within '{context_name}' for control with locators: {search_args}, Timeout: {timeout_seconds}s")
        try:
            start_time = time.time()
            control = None
            search_depth = auto.MAX_SEARCH_DEPTH # Consider making this configurable if needed

            while time.time() - start_time < timeout_seconds:
                control = None # Reset control for each find attempt
                try:
                    # Attempt to find the control using uiautomation methods
                    # Prioritize specific methods if ControlType is given
                    control_type_name = search_args.get("ControlType")
                    search_method_name = f"{control_type_name}Control" if control_type_name else "Control"

                    if hasattr(search_context, search_method_name):
                        search_method = getattr(search_context, search_method_name)
                        # Pass only relevant args to the specific method
                        specific_args = {k: v for k, v in search_args.items() if k != 'ControlType'}
                        # Add searchDepth, waitTime=0 prevents the method from blocking internally
                        control = search_method(searchDepth=search_depth, waitTime=0, **specific_args)
                    else:
                        # Fallback to generic Control method if specific one doesn't exist
                         control = search_context.Control(searchDepth=search_depth, waitTime=0, **search_args)

                    if control:
                        # Found a potential match, check if it actually exists/is stable
                        # Use very short Exists timeouts as we are in a loop already
                        if control.Exists(0.1, 0.05):
                            control_name_found = "[Error getting name]"
                            control_type_found= "[Error getting type]"
                            try: control_name_found = control.Name
                            except Exception: pass
                            try: control_type_found = control.ControlTypeName
                            except Exception: pass
                            print(f"[GuiController] Control found and verified stable: '{control_name_found}' ({control_type_found}) within '{context_name}'")
                            return control
                        else:
                             # Found but not stable yet, log and continue loop
                             print(f"[GuiController] Control found but failed stability check. Continuing search...")
                             control = None # Reset control so loop continues correctly

                except LookupError:
                    pass # Control not found yet, continue loop
                except AttributeError as ae:
                     # This might happen if a specific control type method (e.g., EditControl) isn't found on the context
                     print(f"[GuiController] Attribute error during search (check ControlType?): {ae}")
                     pass # Continue loop, maybe the generic Control() will work
                except Exception as find_err:
                    # Catch other potential errors during find, log them, but keep trying
                    print(f"[GuiController] Error during specific find attempt: {type(find_err).__name__} - {find_err}. Continuing search...")
                    pass # Continue loop

                # If control wasn't found or wasn't stable, wait before next check
                # Use QThread.msleep if running in a QThread context, otherwise time.sleep
                try:
                    from PySide6.QtCore import QThread
                    QThread.msleep(200) # 200ms
                except ImportError:
                    time.sleep(0.2)

            # Loop finished without finding a stable control
            self._emit_error(f"Control not found or not stable within {timeout_seconds}s in '{context_name}' using locators: {search_args}")
            return None

        except Exception as e:
            # Catch unexpected errors in the overall search logic
            err_msg = f"Unexpected error finding control {search_args} in '{context_name}': {type(e).__name__} - {e}"
            self._emit_error(err_msg)
            traceback.print_exc()
            return None

    # --- _resolve_parent, click_control, set_text, get_text, select_item, toggle_checkbox, get_control_state ---
    # --- These methods remain unchanged from the previous version ---
    # --- (Copy and paste the existing implementations of these methods here) ---

    # --- ERROR LOCATION 3: Line 592 ---
    # Pylance Error: 类型表达式中不允许使用变量 (Variable is not allowed in type expression) - likely referring to 'Any'
    def _resolve_parent(self, args: Dict[str, Any], timeout: int) -> Optional[Any]:
        """Helper to find the parent control if specified in args."""
        parent_control = None
        parent_locators = {
            k.replace('parent_', ''): v
            for k, v in args.items()
            if k.startswith('parent_') and k != 'parent_control' and v is not None and v != ""
        }
        direct_parent = args.get('parent_control')

        if direct_parent:
             print("[GuiController] Using directly provided parent control.")
             # Basic check if it's a uiautomation control type
             if hasattr(direct_parent, 'Exists'):
                 parent_control = direct_parent
             else:
                 self._emit_error("Provided 'parent_control' is not a valid uiautomation control.")
                 return None
        elif parent_locators:
            print(f"[GuiController] Resolving parent control using locators: {parent_locators}")
            parent_control = self._find_control_internal(parent_locators, timeout_seconds=timeout) # Search from root for parent
            if not parent_control:
                # Emit error only if parent was specified via locators but not found.
                # If parent_control was None, it's handled differently.
                self._emit_error(f"Specified parent control (via locators) not found: {parent_locators}")
                return None
        # If no parent info provided, parent_control remains None (search starts from root)
        return parent_control

    def click_control(self, args: Dict[str, Any], timeout: int = 5) -> bool:
        """Finds and clicks a control, potentially within a specified parent."""
        if not self.is_available(): return False
        parent_control = self._resolve_parent(args, timeout)
        # Check if parent was specified via locators but not found
        has_parent_locators = any(k.startswith('parent_') and k != 'parent_control' for k in args)
        if has_parent_locators and parent_control is None:
            # Error already emitted by _resolve_parent if locators were used
            return False

        target_locators = {k: v for k, v in args.items() if not k.startswith('parent_')}

        control = self._find_control_internal(target_locators, parent_control, timeout)
        if control:
            try:
                control_name = "[Error getting name]"
                try: control_name = control.Name
                except Exception: pass
                print(f"[GuiController] Clicking control: '{control_name}'")
                # Check IsEnabled state before clicking
                is_enabled = False
                try: is_enabled = control.IsEnabled
                except Exception: print(f"Warning: Could not get IsEnabled state for control '{control_name}'")
                if not is_enabled:
                     self._emit_error(f"Cannot click control '{control_name}': Control is disabled.")
                     return False

                # Perform the click
                control.Click(waitTime=0.1) # waitTime adds a small delay *after* the action
                print(f"[GuiController] Click successful.")
                # time.sleep(0.1) # Optional additional pause
                return True
            except Exception as e:
                control_name_err = "[Error getting name]"
                try: control_name_err = control.Name
                except Exception: pass
                err_msg = f"Failed to click control '{control_name_err}': {type(e).__name__} - {e}"
                self._emit_error(err_msg)
                traceback.print_exc()
                return False
        # Error for not finding control already emitted by _find_control_internal
        return False

    def set_text(self, args: Dict[str, Any], timeout: int = 5) -> bool:
        """Finds a control (potentially within parent) and sets its text value."""
        if not self.is_available(): return False
        value = args.get('value')
        # Allow empty string, but not other non-string types (unless None, which is invalid)
        if not isinstance(value, str) and value is not None:
            self._emit_error(f"Invalid 'value' for set_text: must be a string, got {type(value).__name__}")
            return False
        # Handle None case explicitly if needed, or assume empty string if None is passed
        if value is None: value = "" # Treat None as empty string for SetValue

        parent_control = self._resolve_parent(args, timeout)
        has_parent_locators = any(k.startswith('parent_') and k != 'parent_control' for k in args)
        if has_parent_locators and parent_control is None:
            return False

        target_locators = {k: v for k, v in args.items() if not k.startswith('parent_') and k != 'value'}

        control = self._find_control_internal(target_locators, parent_control, timeout)
        if control:
            try:
                control_name = "[Error getting name]"
                try: control_name = control.Name
                except Exception: pass
                print(f"[GuiController] Setting text for control: '{control_name}' to '{value[:50]}{'...' if len(value)>50 else ''}'")

                # Check IsEnabled state before setting text
                is_enabled = False
                try: is_enabled = control.IsEnabled
                except Exception: print(f"Warning: Could not get IsEnabled state for control '{control_name}'")
                if not is_enabled:
                     self._emit_error(f"Cannot set text for control '{control_name}': Control is disabled.")
                     return False

                # Check if ValuePattern is available
                has_value_pattern = False
                try: has_value_pattern = control.IsValuePatternAvailable()
                except Exception: print(f"Warning: Could not check ValuePattern for control '{control_name}'")

                if has_value_pattern:
                    control.SetValue(value, waitTime=0.1)
                else:
                     # Fallback: Try SendKeys if ValuePattern is not supported (less reliable)
                     print(f"[GuiController] Warning: Control '{control_name}' does not support ValuePattern. Attempting SendKeys fallback.")
                     # Need to focus the control first for SendKeys
                     try:
                         control.SetFocus()
                         time.sleep(0.1) # Small delay after focus
                         # Simulate clearing existing text (Ctrl+A, Delete) - might not work everywhere
                         control.SendKeys('{Ctrl}(a)', waitTime=0.05)
                         control.SendKeys('{Delete}', waitTime=0.05)
                         time.sleep(0.05)
                         # Send the new text
                         control.SendKeys(value, interval=0.01, waitTime=0.1)
                     except Exception as sk_err:
                         self._emit_error(f"Control '{control_name}' does not support ValuePattern and SendKeys fallback failed: {sk_err}")
                         return False

                print(f"[GuiController] Set text successful (or SendKeys attempted).")
                # time.sleep(0.1) # Optional pause
                return True
            except Exception as e:
                control_name_err = "[Error getting name]"
                try: control_name_err = control.Name
                except Exception: pass
                err_msg = f"Failed to set text for control '{control_name_err}': {type(e).__name__} - {e}"
                self._emit_error(err_msg)
                traceback.print_exc()
                return False
        return False

    def get_text(self, args: Dict[str, Any], timeout: int = 5) -> Optional[str]:
        """Finds a control (potentially within parent) and returns its text/value or name."""
        if not self.is_available(): return None
        parent_control = self._resolve_parent(args, timeout)
        has_parent_locators = any(k.startswith('parent_') and k != 'parent_control' for k in args)
        if has_parent_locators and parent_control is None:
            return None

        target_locators = {k: v for k, v in args.items() if not k.startswith('parent_')}

        control = self._find_control_internal(target_locators, parent_control, timeout)
        if control:
            control_name = "[Error getting name]"
            try: control_name = control.Name
            except Exception: pass
            try:
                text_value: Optional[str] = None
                has_value_pattern = False
                try: has_value_pattern = control.IsValuePatternAvailable()
                except Exception: pass

                if has_value_pattern:
                    text_value = control.CurrentValue()
                    print(f"[GuiController] Getting text via ValuePattern for control: '{control_name}'")
                # TextPattern rarely provides full editable text, Name is often better fallback
                # elif control.IsTextPatternAvailable():
                #     print(f"[GuiController] Getting text via TextPattern (using Name fallback) for control: {control_name}")
                #     text_value = control.Name # Fallback for TextPattern only controls
                else:
                    # Default fallback to Name property
                    print(f"[GuiController] Getting text via Name property for control: '{control_name}'")
                    text_value = control.Name

                # Ensure return value is a string
                result = str(text_value) if text_value is not None else ""
                print(f"[GuiController] Get text successful. Value: '{result[:100]}{'...' if len(result)>100 else ''}'")
                return result
            except Exception as e:
                err_msg = f"Failed to get text for control '{control_name}': {type(e).__name__} - {e}"
                self._emit_error(err_msg)
                traceback.print_exc()
                return None # Return None on error
        return None # Return None if control not found

    def select_item(self, args: Dict[str, Any], timeout: int = 5) -> bool:
        """Finds a List/ComboBox (potentially within parent) and selects an item by name."""
        if not self.is_available(): return False
        value_to_select = args.get('value') # Name of the item to select
        if not isinstance(value_to_select, str) or not value_to_select:
            self._emit_error(f"Invalid/Missing 'value' for select_item: must be a non-empty string, got '{value_to_select}'")
            return False

        parent_control = self._resolve_parent(args, timeout)
        has_parent_locators = any(k.startswith('parent_') and k != 'parent_control' for k in args)
        if has_parent_locators and parent_control is None:
            return False

        # Locators for the container (List, ComboBox, etc.)
        target_locators = {k: v for k, v in args.items() if not k.startswith('parent_') and k != 'value'}

        container_control = self._find_control_internal(target_locators, parent_control, timeout)
        if container_control:
            container_name = "[Error getting name]"
            try: container_name = container_control.Name
            except Exception: pass
            try:
                print(f"[GuiController] Attempting to select item '{value_to_select}' in container: '{container_name}'")

                item_to_select: Optional[auto.Control] = None

                # --- Expand ComboBox if necessary ---
                is_expanded = True # Assume expanded unless proven otherwise
                try:
                    if container_control.IsExpandCollapsePatternAvailable():
                        current_state = container_control.CurrentExpandCollapseState
                        is_expanded = (current_state == auto.ExpandCollapseState.Expanded)
                        if not is_expanded:
                            print(f"[GuiController] Container '{container_name}' is collapsed, attempting to expand...")
                            container_control.Expand(waitTime=0.5) # Expand and wait briefly
                            # Re-check state after expanding
                            current_state = container_control.CurrentExpandCollapseState
                            is_expanded = (current_state == auto.ExpandCollapseState.Expanded)
                            if not is_expanded:
                                print(f"[GuiController] Failed to expand container '{container_name}'.")
                                # Don't necessarily fail yet, sometimes items are accessible anyway
                except Exception as exp_err:
                     print(f"Warning: Error checking/expanding container '{container_name}': {exp_err}")

                # --- Find the item ---
                # Search within the container, potentially needing longer timeout if list is large
                item_find_timeout = max(1, timeout // 2) # Allow some time for item search
                item_search_start = time.time()
                while time.time() - item_search_start < item_find_timeout:
                    try:
                        # Prioritize ListItemControl by Name
                        item_to_select = container_control.ListItemControl(Name=value_to_select, searchDepth=auto.MAX_SEARCH_DEPTH, waitTime=0)
                        if item_to_select and item_to_select.Exists(0.1, 0.05): break
                        # Fallback: Try finding any control by Name within the container
                        item_to_select = container_control.Control(Name=value_to_select, searchDepth=auto.MAX_SEARCH_DEPTH, waitTime=0)
                        if item_to_select and item_to_select.Exists(0.1, 0.05): break
                    except LookupError:
                         item_to_select = None # Reset if lookup fails
                    except Exception as item_find_err:
                         print(f"Warning: Error during item search for '{value_to_select}': {item_find_err}")
                         item_to_select = None
                    # If not found, wait briefly
                    time.sleep(0.1)

                if not item_to_select:
                    self._emit_error(f"Could not find item '{value_to_select}' within container '{container_name}' within timeout.")
                    # Optionally collapse ComboBox if expanded?
                    return False

                item_name_found = "[Error getting name]"
                try: item_name_found = item_to_select.Name
                except Exception: pass
                print(f"[GuiController] Found item to select: '{item_name_found}'")

                # --- Select the item ---
                select_success = False
                try:
                    # Method 1: SelectionItemPattern (Preferred)
                    if item_to_select.IsSelectionItemPatternAvailable():
                        item_to_select.Select()
                        select_success = True
                        print(f"[GuiController] Selected item using SelectionItemPattern.")
                    # Method 2: InvokePattern (Common for menu items)
                    elif item_to_select.IsInvokePatternAvailable():
                         item_to_select.Invoke()
                         select_success = True
                         print(f"[GuiController] Selected item using InvokePattern.")
                    # Method 3: Click (Fallback)
                    else:
                         print(f"[GuiController] Warning: Item '{item_name_found}' supports neither SelectionItem nor Invoke Pattern. Attempting Click().")
                         item_to_select.Click(waitTime=0.1)
                         select_success = True # Assume click worked if no exception
                         print(f"[GuiController] Selected item using Click fallback.")
                except Exception as select_err:
                     self._emit_error(f"Error occurred while trying to select item '{item_name_found}': {select_err}")
                     return False

                # Optional: Collapse ComboBox after selection
                # if container_control.IsExpandCollapsePatternAvailable() and is_expanded:
                #     try: container_control.Collapse(waitTime=0.1)
                #     except Exception: pass

                time.sleep(0.1) # Pause after action
                return select_success

            except Exception as e:
                err_msg = f"Failed to select item '{value_to_select}' in container '{container_name}': {type(e).__name__} - {e}"
                self._emit_error(err_msg)
                traceback.print_exc()
                return False
        return False

    def toggle_checkbox(self, args: Dict[str, Any], timeout: int = 5) -> bool:
        """Finds a CheckBox (potentially within parent) and toggles it towards the desired state."""
        if not self.is_available(): return False
        target_state: Optional[bool] = args.get('state') # Target state (True=checked, False=unchecked, None=just toggle)
        if target_state is not None and not isinstance(target_state, bool):
            self._emit_error(f"Invalid 'state' for toggle_checkbox: must be boolean or None, got {type(target_state).__name__}")
            return False

        parent_control = self._resolve_parent(args, timeout)
        has_parent_locators = any(k.startswith('parent_') and k != 'parent_control' for k in args)
        if has_parent_locators and parent_control is None:
            return False

        target_locators = {k: v for k, v in args.items() if not k.startswith('parent_') and k != 'state'}
        # Ensure ControlType is CheckBox if not specified
        if 'ControlType' not in target_locators:
            target_locators['ControlType'] = 'CheckBox'

        control = self._find_control_internal(target_locators, parent_control, timeout)
        if control:
            control_name = "[Error getting name]"
            try: control_name = control.Name
            except Exception: pass
            try:
                print(f"[GuiController] Attempting to toggle checkbox: '{control_name}' (Target state: {target_state})")

                # Check IsEnabled state first
                is_enabled = False
                try: is_enabled = control.IsEnabled
                except Exception: print(f"Warning: Could not get IsEnabled state for control '{control_name}'")
                if not is_enabled:
                     self._emit_error(f"Cannot toggle checkbox '{control_name}': Control is disabled.")
                     return False

                # Check TogglePattern availability
                has_toggle_pattern = False
                try: has_toggle_pattern = control.IsTogglePatternAvailable()
                except Exception: print(f"Warning: Could not check TogglePattern for control '{control_name}'")
                if not has_toggle_pattern:
                    # Fallback: Try clicking the checkbox if TogglePattern is unavailable
                    print(f"Warning: Checkbox '{control_name}' does not support TogglePattern. Attempting Click() fallback.")
                    try:
                        control.Click(waitTime=0.1)
                        print(f"[GuiController] Toggle attempted via Click fallback.")
                        # Cannot verify state reliably after click fallback
                        return True
                    except Exception as click_err:
                         self._emit_error(f"Control '{control_name}' does not support TogglePattern and Click fallback failed: {click_err}")
                         return False

                # Use TogglePattern
                current_state_enum = auto.ToggleState.Indeterminate # Default
                try: current_state_enum = control.GetTogglePattern().CurrentToggleState
                except Exception as get_state_err: print(f"Warning: Could not get toggle state for '{control_name}': {get_state_err}")

                # Convert enum to boolean (On -> True, Off/Indeterminate -> False for simple comparison)
                current_state_bool = bool(current_state_enum == auto.ToggleState.On)
                print(f"[GuiController] Current checkbox state: {current_state_enum} (Interpreted as Bool: {current_state_bool})")

                needs_toggle = True
                if target_state is not None: # If a specific target state is requested
                    needs_toggle = (target_state != current_state_bool)
                    print(f"[GuiController] Target state specified ({target_state}). Needs toggle: {needs_toggle}")

                if needs_toggle:
                    print(f"[GuiController] Toggling checkbox '{control_name}'...")
                    control.Toggle()
                    print(f"[GuiController] Toggle executed.")
                    time.sleep(0.1) # Pause after action
                    # Verify state if target was specified
                    if target_state is not None:
                        final_state_enum = auto.ToggleState.Indeterminate
                        try: final_state_enum = control.GetTogglePattern().CurrentToggleState
                        except Exception: pass # Ignore verification error
                        final_state_bool = bool(final_state_enum == auto.ToggleState.On)
                        if final_state_bool != target_state:
                             # Report mismatch but consider the toggle action itself successful if no exception occurred
                             print(f"Warning: Checkbox '{control_name}' state ({final_state_bool}) did not match target state ({target_state}) after toggle.")
                        else:
                             print(f"[GuiController] Verified state matches target ({target_state}).")
                else:
                    print(f"[GuiController] Checkbox '{control_name}' is already in the desired state ({current_state_bool}, matches target {target_state}). No toggle needed.")

                return True # Return True if toggle was executed or not needed

            except Exception as e:
                err_msg = f"Failed to toggle checkbox '{control_name}': {type(e).__name__} - {e}"
                self._emit_error(err_msg)
                traceback.print_exc()
                return False
        return False

    def get_control_state(self, args: Dict[str, Any], timeout: int = 5) -> Optional[Dict[str, Any]]:
        """Finds a control (potentially within parent) and returns its common states."""
        if not self.is_available(): return None
        parent_control = self._resolve_parent(args, timeout)
        has_parent_locators = any(k.startswith('parent_') and k != 'parent_control' for k in args)
        if has_parent_locators and parent_control is None:
            return None

        target_locators = {k: v for k, v in args.items() if not k.startswith('parent_')}

        control = self._find_control_internal(target_locators, parent_control, timeout)
        if control:
            control_name = "[Error getting name]"
            try: control_name = control.Name
            except Exception: pass
            try:
                print(f"[GuiController] Getting state for control: '{control_name}'")
                state_info: Dict[str, Any] = {}

                # --- Safely get common properties ---
                def safe_get(prop_name, default=None):
                    try: return getattr(control, prop_name)
                    except Exception: return default

                state_info['Name'] = control_name # Use already retrieved name
                state_info['ControlTypeName'] = safe_get('ControlTypeName', 'Unknown')
                state_info['AutomationId'] = safe_get('AutomationId', '')
                state_info['ClassName'] = safe_get('ClassName', '')
                state_info['IsEnabled'] = safe_get('IsEnabled', False)
                state_info['IsVisible'] = not safe_get('IsOffscreen', True) # IsOffscreen is False if visible

                # --- Safely check and get pattern-based properties ---
                try:
                    if safe_get('IsTogglePatternAvailable', False):
                        toggle_state = safe_get('CurrentToggleState', auto.ToggleState.Indeterminate)
                        if hasattr(toggle_state, 'name'): # Check if it's an enum member
                             state_info['ToggleState'] = toggle_state.name # Store enum name string
                        else: state_info['ToggleState'] = str(toggle_state)
                        state_info['IsChecked'] = bool(toggle_state == auto.ToggleState.On)
                except Exception as e: print(f"Warning getting TogglePattern state: {e}")

                try:
                    if safe_get('IsSelectionItemPatternAvailable', False):
                        state_info['IsSelected'] = safe_get('IsSelected', False) # Direct property from pattern interface
                except Exception as e: print(f"Warning getting SelectionItemPattern state: {e}")

                try:
                    if safe_get('IsExpandCollapsePatternAvailable', False):
                         exp_state = safe_get('CurrentExpandCollapseState', auto.ExpandCollapseState.Collapsed)
                         if hasattr(exp_state, 'name'): state_info['ExpandCollapseState'] = exp_state.name
                         else: state_info['ExpandCollapseState'] = str(exp_state)
                         state_info['IsExpanded'] = bool(exp_state == auto.ExpandCollapseState.Expanded)
                except Exception as e: print(f"Warning getting ExpandCollapsePattern state: {e}")

                try:
                    if safe_get('IsValuePatternAvailable', False):
                         state_info['Value'] = safe_get('CurrentValue', '') # Get value if available
                         state_info['IsReadOnly'] = safe_get('IsReadOnly', True) # Assume read-only if pattern exists but property fails
                except Exception as e: print(f"Warning getting ValuePattern state: {e}")

                try:
                    rect = safe_get('BoundingRectangle')
                    state_info['BoundingRect'] = rect.tuple() if rect else None
                except Exception as e: print(f"Warning getting BoundingRectangle state: {e}")


                print(f"[GuiController] Get state successful: {state_info}")
                return state_info

            except Exception as e:
                err_msg = f"Failed to get state for control '{control_name}': {type(e).__name__} - {e}"
                self._emit_error(err_msg)
                traceback.print_exc()
                return None # Return None on error
        return None # Return None if control not found