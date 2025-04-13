# PowerAgent

一个将 AI 聊天助手与本地命令行控制相结合的桌面应用程序。

![image](https://github.com/user-attachments/assets/451b6bde-ef95-4b63-b0ae-5c2127cf6f73)


## 主要功能

*   **AI 聊天界面**:
    *   与可配置的 AI 模型进行交互，获取帮助或执行任务。
    *   支持多模型选择。
    *   通过 `/help` 查看内置命令。
*   **集成命令行 (CLI)**:
    *   在应用程序内直接执行标准的 Shell 命令 (如 `ls`, `cd`, `python script.py`)。
    *   使用 `↑`/`↓` 浏览命令历史。
    *   使用 `Tab` 键在聊天输入和 CLI 输入之间快速切换焦点。
*   **AI 驱动的操作**:
    *   AI 可以生成 `<cmd>命令</cmd>`，这些命令会自动在下方的 CLI 窗口回显并执行。
    *   AI 可以生成 `<function>键盘动作</function>` (如模拟按键、热键、粘贴)，这些动作会被自动执行。
*   **上下文感知**:
    *   应用程序在当前工作目录 (CWD) 中运行，支持 `cd` 命令更改目录。
    *   (可选) 可配置将近期的 CLI 输出自动作为上下文发送给 AI。
*   **多步骤 AI (实验性)**:
    *   (可选) 启用后，允许 AI 根据上一步操作的结果连续执行多个命令或键盘动作。
*   **个性化设置**:
    *   通过设置对话框 (`/settings` 或工具栏按钮) 配置 API 密钥/URL、模型列表。
    *   支持 **暗色**、**亮色** 和 **系统默认** 界面主题。
    *   配置是否开机自启动。
    *   配置是否在提示中包含时间戳。
*   **状态指示**:
    *   工具栏显示 AI 或 CLI 是否正在忙碌。

## 快速开始

1.  **运行**: 启动应用程序 (`python main.py`)。
2.  **配置**:
    *   首次运行时，点击工具栏左侧的 **设置** 按钮 (或在聊天框输入 `/settings`)。
    *   填入你的 AI 服务 API URL、API 密钥，以及想要使用的模型 ID (逗号分隔)。
    *   根据需要调整其他设置 (主题、自启动等)。
    *   点击“确定”保存。
3.  **选择模型**: 在工具栏右侧的下拉框中选择一个已配置的模型。
4.  **使用**:
    *   **聊天框 (右上)**: 向 AI 提出你的需求，例如：
        *   `列出当前目录的所有 python 文件` (可能会生成 `<cmd>ls *.py</cmd>`)
        *   `创建一个名为 temp 的目录` (可能会生成 `<cmd>mkdir temp</cmd>`)
        *   `模拟按下 CTRL+C` (可能会生成 `<function call='keyboard_hotkey' args='{"keys": ["ctrl", "c"]}'>`)
        *   AI 建议的 `<cmd>` 或 `<function>` 会在执行前在聊天和 CLI 窗口中提示。
    *   **CLI 框 (左下)**: 直接输入并执行标准的 Shell 命令。按 `Enter` 执行。

## 功能演示

### AI 执行命令

![image](https://github.com/user-attachments/assets/2a2b1098-4da5-4cf8-b67a-4d1432815e75)


### AI 模拟键盘操作

![image](https://github.com/user-attachments/assets/fdd1ef2e-e2ef-49f8-820a-a3f97c50e3ab)


### 手动执行命令与 Tab 切换

![image](https://github.com/user-attachments/assets/857c00ce-b9a8-4a65-bf8d-2dcbf7502fda)


---

