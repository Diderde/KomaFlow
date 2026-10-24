"""② 界面层。

**规则**：本层只做展示与输入，**不得直接调用 Blender** ——
一切操作经核心逻辑层（``core.pipeline``）转发。

形态（§8）：单窗口表单式 ——
Blender 行 · 素材区 · 参数区 · 操作区 · 进度区 · 日志面板。
刻意**没有** 3D 视口、时间轴、曲线编辑器、材质节点。

技术选型：**tkinter**。它是唯一不违反 NFR-16（禁止 pip 安装的依赖）的 GUI 方案。
"""

from .app import KomaFlowApp, main

__all__ = ["KomaFlowApp", "main"]
