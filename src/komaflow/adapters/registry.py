"""适配器注册与选择。

对应需求：（统一基准版本）· / （新增版本只加适配器）·
设计取舍（多版本时由**用户自己选**，工具绝不代选）。

将来支持 Blender 4.2 LTS 时，唯一要改的地方是 :data:`ADAPTERS`：

.. code-block:: python

    from .blender42 import Blender42Adapter
    ADAPTERS = (Blender5Adapter(), Blender42Adapter())

核心逻辑层无需改动。
"""

from __future__ import annotations

from ..core.errors import ErrorKind, KomaFlowError
from .base import BlenderAdapter, VersionTuple
from .blender5 import Blender5Adapter

#: 已登记的适配器。**基准版本排在最前**。
ADAPTERS: tuple[BlenderAdapter, ...] = (Blender5Adapter(),)

#: 统一基准版本：工具以它为唯一验证目标。
BASELINE: BlenderAdapter = next(a for a in ADAPTERS if a.is_baseline)


def adapter_by_key(key: str) -> BlenderAdapter:
    """按标识取适配器。"""
    for adapter in ADAPTERS:
        if adapter.key == key:
            return adapter
    known = ", ".join(a.key for a in ADAPTERS)
    raise KeyError(f"没有名为 {key!r} 的适配器；已知：{known}")


def select_adapter(version: VersionTuple) -> BlenderAdapter:
    """按版本号选适配器。

    :raises KomaFlowError: 版本不在任何已登记适配器的支持范围内（K-8.9：
        组合不在矩阵内必须**明确报错**，不允许静默失败或崩溃）。
    """
    for adapter in ADAPTERS:
        if adapter.supports(version):
            return adapter

    shown = ".".join(str(x) for x in version)
    supported = "、".join(
        "{}.{}.x ~ {}.{}.x".format(*a.supported_min[:2], *a.supported_max[:2])
        for a in ADAPTERS
    )
    raise KomaFlowError(
        ErrorKind.BLENDER_VERSION_UNSUPPORTED,
        detail=f"检测到 Blender {shown}，当前支持：{supported}",
    )
