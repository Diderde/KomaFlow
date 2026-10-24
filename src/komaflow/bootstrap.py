# -*- coding: utf-8 -*-
"""打包版（PyInstaller 冻结）的**启动自举** —— 只做冻结环境下必须做的事。

为什么单独一个模块
------------------
源码直接跑时，这些东西有现成的默认值；**打包之后全部要重算**：

1. **程序目录在哪**（放便携 FFmpeg、放许可文件、放使用说明）
2. **便携 FFmpeg 要用上** —— 别人电脑上不一定装了 ffmpeg。
   随包带一份放进 ``<程序目录>/ffmpeg/``，这里把它接进
   ``KomaFlow_FFMPEG`` 环境变量（``media/ffmpeg.py`` 会读，**代码一行都不用改**）
3. **默认保存位置** —— 见 :func:`komaflow.settings.default_paths`：
   打包版放"文档\\KomaFlow"，不再跟着工作目录跑

⚠️ 本模块**必须在任何会用 FFmpeg 的东西之前被 import**。
   现在由 ``komaflow.ui.app`` 与 ``komaflow.cli`` 在顶部 import 一次。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

#: 便携 FFmpeg 放这个子目录（跟 exe 并排）
FFMPEG_DIRNAME = "ffmpeg"

#: 交给 ``media/ffmpeg.py`` 读的环境变量名（**不要改**，那边写的就是它）
ENV_FFMPEG = "KomaFlow_FFMPEG"


def is_frozen() -> bool:
    """是不是 PyInstaller 打出来的包。"""
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """程序目录 —— 用户能看见、能放东西的那个目录。

    ⚠️ 不能用 ``sys._MEIPASS``：那是 PyInstaller 的解包/内部目录
       （onedir 下是 ``_internal``，onefile 下是临时目录、退出就删）。
       我们要的是"exe 旁边那个目录" —— ``sys.executable`` 的父目录。
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    # 源码直接跑：仓库根（本文件在 src/komaflow/ 下）
    return Path(__file__).resolve().parents[2]


def prepare() -> dict:
    """冻结环境下的一次性准备。**返回做过什么**（方便自检与日志）。

    幂等：重复调用没有副作用。
    """
    actions: dict = {"frozen": is_frozen(), "app_dir": str(app_dir())}

    # ── 便携 FFmpeg ──
    # ⚠️ 只在用户**没有**自己指定时才接 —— 别覆盖用户的选择。
    if not os.environ.get(ENV_FFMPEG):
        for candidate in (app_dir() / FFMPEG_DIRNAME,
                          app_dir() / "bin",
                          app_dir()):
            exe = candidate / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
            if exe.is_file():
                os.environ[ENV_FFMPEG] = str(candidate)
                actions["ffmpeg"] = str(candidate)
                break
        else:
            actions["ffmpeg"] = ""
    else:
        actions["ffmpeg"] = os.environ[ENV_FFMPEG]

    # ── 便携 Blender ──
    # 用户的路线是"不随包带 Blender"（GPL 义务），但**留个口子**：
    # 要是有人自己把便携 Blender 放进 ``<程序目录>/blender/``，
    # 就自动用上，省得再去设置里指路径。
    if not os.environ.get("BLENDER"):
        for candidate in (app_dir() / "blender", app_dir() / "blender-portable"):
            exe = candidate / ("blender.exe" if os.name == "nt" else "blender")
            if exe.is_file():
                os.environ["BLENDER"] = str(exe)
                actions["blender"] = str(exe)
                break

    return actions


#: import 本模块即完成准备（放在顶部 import 就够，不用再记得调）
_ACTIONS = prepare()
