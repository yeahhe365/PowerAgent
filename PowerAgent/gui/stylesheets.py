# ========================================
# 文件名: PowerAgent/gui/stylesheets.py
# ---------------------------------------
# gui/stylesheets.py
# -*- coding: utf-8 -*-

"""
Contains the QSS stylesheet templates used by the MainWindow.
"""

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
    QToolBar QLabel#ModelIdLabel {{
        padding: 0px 5px;
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
    #ClearChatButton:hover {{ }}
    /* <<< ADDED: Placeholder selectors for the new button >>> */
    #ClearCliButton {{ }}
    #ClearCliButton:hover {{ }}
    #ClearCliButton:pressed {{ }}
    #ClearCliButton:disabled {{ }}
    /* <<< END ADDED >>> */
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
    QToolBar QLabel#ModelIdLabel {{
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