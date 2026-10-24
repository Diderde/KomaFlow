"""Blender 适配层接口。

对应需求：（版本差异全部收敛到适配层）· （适配层显式声明支持范围）·
（**禁止核心逻辑层硬编码版本判断**）· （为将来的 6.x 预留结构）·
设计取舍 / 32（当前只支持 5.x，4.2 LTS 预留位置）。

本文件把"版本差异"抽象成**属性**而不是分支
------------------------------------------------
核心层要问"EEVEE 引擎叫什么"，不应该写成 ``if version >= (5, 0): "BLENDER_EEVEE" else ...``，
而是问适配器 ``adapter.engine_eevee``。这样将来加 4.2 适配器时，
只需在新类里把属性填成 ``"BLENDER_EEVEE_NEXT"``，核心层一行都不用改。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

#: 版本号元组，如 ``(5, 2, 2)``。比较用元组比较即可（``(5, 2) < (6, 0)``）。
VersionTuple = tuple[int, ...]


@dataclass(frozen=True)
class BlenderInfo:
    """一次探测的结果。"""

    exe: Path
    version_string: str # 例如 "5.2.2 LTS"
    version: VersionTuple # 例如 (5, 2, 2)
    mmd_tools_installed: bool
    mmd_tools_version: str | None = None

    @property
    def display(self) -> str:
        tools = self.mmd_tools_version or ("已安装" if self.mmd_tools_installed else "未安装")
        return f"{self.exe} Blender {self.version_string} mmd_tools: {tools}"


class BlenderAdapter(ABC):
    """一个 Blender 大版本系列的支持实现。"""

    #: 内部标识，写入日志与工程档
    key: str = ""
    #: 界面上显示的名字
    label: str = ""
    #: 支持的版本范围（闭区间）， 要求显式声明
    supported_min: VersionTuple = (0,)
    supported_max: VersionTuple = (999,)
    #: 是否为"统一基准版本"。工具以它为唯一验证目标。
    is_baseline: bool = False

    # ---------------------------------------------------------------- 版本差异
    # 以下属性就是需求书「附录 F · Blender 5.2 API 适配清单」的全部内容。
    # 任何一处版本相关的写法差异，都必须变成这里的属性，不得散落到核心层。

    #: EEVEE 引擎的枚举名（5.x 是 BLENDER_EEVEE；4.2 是 BLENDER_EEVEE_NEXT）
    engine_eevee: str = ""
    #: 输出视频时是否**必须**先设 media_type 再设 file_format（顺序错会报 enum 不存在）
    needs_media_type_first: bool = False
    #: 控制材质透明方式的属性名（5.2 是 surface_render_method，写入 blend_method 无效）
    material_transparency_attr: str = ""
    #: 合成器节点树的访问路径（5.2 是 scene.compositing_node_group，scene.node_tree 已删）
    compositor_attr: str = ""

    # ------------------------------------------------------------------ 能力

    def supports(self, version: VersionTuple) -> bool:
        """该版本是否落在本适配器的支持范围内。"""
        return self.supported_min <= version <= self.supported_max

    @abstractmethod
    def probe(self, exe: str | Path) -> BlenderInfo:
        """探测这个 blender.exe：版本号、mmd_tools 是否可用。

        实现方式约定（K-10.11）：``blender --background --python <探针脚本>``，
        结果以文件或 stdout 的约定标记返回，**不解析人类可读的屏幕输出**。
        """

    @abstractmethod
    def script(self, name: str) -> Path:
        """取一个注入 Blender 执行的脚本路径（``adapters/scripts/`` 下）。"""

    # ------------------------------------------------------------------ 展示

    def describe(self) -> str:
        """一行说明，用于设置页与 CLI。"""
        low = ".".join(str(x) for x in self.supported_min)
        high = ".".join(str(x) for x in self.supported_max)
        mark = "（统一基准版本）" if self.is_baseline else ""
        return f"{self.label}{mark} 支持 {low} ~ {high}"
