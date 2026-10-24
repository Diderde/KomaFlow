"""KomaFlow —— MMD 本地渲染流水线。

严格三层（见 docs/architecture.md）：

    core ① 核心逻辑层：不依赖 GUI、不依赖 Blender，可在命令行单独跑
    adapters ③ Blender 适配层：所有版本相关调用集中于此
    ui ② 界面层：只做展示与输入，不得直接调用 Blender

依赖约束：**仅标准库**（NFR-16 禁止需要 pip 安装的运行时依赖）。
"""

from .branding import APP_NAME, APP_VERSION

__all__ = ["APP_NAME", "APP_VERSION"]
