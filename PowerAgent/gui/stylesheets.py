# ========================================
# 文件名: PowerAgent/gui/stylesheets.py
# (MODIFIED - Removed QPushButton:hover styling)
# ---------------------------------------
# gui/stylesheets.py
# -*- coding: utf-8 -*-

"""
Contains the QSS stylesheet templates used by the MainWindow.
"""

# Stylesheet template (Removed QPushButton:hover styling)
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
    /* <<< REMOVED Toolbar CWD Label Styling >>> */

    /* <<< ADDED: Styling for Toolbar ComboBox >>> */
    QToolBar QComboBox#ModelSelectorCombo {{
        /* font-size: 9pt; */ /* Uncomment to match label font size */
        color: {status_label_color}; /* Match other status text color */
        /* Add padding if needed */
        /* padding: 1px 5px 1px 5px; */
        min-width: 100px; /* Give it some minimum space */
        /* background-color: {button_bg}; */ /* Optional: Match button background */
        /* border: 1px solid {border}; */ /* Optional: Add border */
        /* border-radius: 3px; */ /* Optional: Round corners */
    }}
    QToolBar QComboBox#ModelSelectorCombo:disabled {{
        color: {text_disabled};
    }}
    /* <<< END ADDED >>> */

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
        color: {cli_output}; /* Default text color for CLI output */
        border: 1px solid {border};
        padding: 3px;
        font-family: {mono_font_family};
        font-size: {mono_font_size}pt;
    }}
    #CliInput {{
        background-color: {cli_bg};
        color: {cli_output}; /* Match output color */
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
    /* <<< REMOVED QPushButton:hover block >>> */
    /* QPushButton:hover {{ ... }} */

    QPushButton:pressed {{
        background-color: {button_pressed_bg};
    }}
    QPushButton:disabled {{
        background-color: {button_disabled_bg};
        color: {text_disabled};
        border: 1px solid {border_disabled};
        padding: 5px 10px; /* Keep padding consistent */
        min-height: 26px; /* Keep min-height consistent */
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
    /* Specific Button Styling (Placeholders) */
    #ClearChatButton {{ }}
    /* <<< REMOVED #ClearChatButton:hover placeholder >>> */
    /* <<< ADDED: Placeholder selectors for the new button >>> */
    #ClearCliButton {{ }}
    /* <<< REMOVED #ClearCliButton:hover placeholder >>> */
    #ClearCliButton:pressed {{ }}
    #ClearCliButton:disabled {{ }}
    /* <<< END ADDED >>> */
"""

# Minimal stylesheet (Removed ToolbarCwdLabel font styling)
# This template already doesn't have a QPushButton:hover rule,
# so hover effects rely on the base Qt style (Fusion).
# Removing hover completely from Fusion might require more complex styling or subclassing,
# but removing it from the custom QSS is achieved by simply not defining it.
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
    /* <<< REMOVED Toolbar CWD Label Styling >>> */

    /* <<< ADDED: Basic Styling for Toolbar ComboBox in System Theme >>> */
    QToolBar QComboBox#ModelSelectorCombo {{
        /* font-size: 9pt; */ /* Uncomment to match label font size */
        min-width: 100px; /* Give it some minimum space */
        /* padding: 1px 5px 1px 5px; */ /* Optional padding */
    }}
    /* <<< END ADDED >>> */

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
        /* No explicit hover rule here - uses style default */
    }}
    QPushButton:disabled {{
        padding: 5px 10px;
        min-height: 26px;
    }}
"""