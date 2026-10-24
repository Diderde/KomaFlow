# -*- coding: utf-8 -*-
"""打包用的**入口脚本**（PyInstaller 从这里开始分析依赖）。

为什么不直接用 ``-m komaflow.ui.app``：``komaflow/ui/app.py`` 底部有
``if __name__ == "__main__": sys.exit(main())``，但 PyInstaller 需要一个
**明确的、能被静态分析找到的入口文件**。这个文件就是那根入口。

⚠️ 它里面**只做一件事**：把界面跑起来。初始化逻辑全在 ``komaflow.ui.app``。
"""

from __future__ import annotations

import sys

from komaflow.ui.app import main

if __name__ == "__main__":
    sys.exit(main())
