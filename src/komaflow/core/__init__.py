"""① 核心逻辑层。

铁律：

* 本层**不得**导入 ``bpy`` 或任何 GUI 库
* 本层**不得**出现 Blender 版本判断（如 ``if version == "4.2"``）
  —— 一律经 ``komaflow.adapters`` 的接口拿能力
* 本层必须能在**无界面环境**下单独跑，便于集成测试
"""

from . import errors, project, segment, verify

__all__ = ["errors", "project", "segment", "verify"]
