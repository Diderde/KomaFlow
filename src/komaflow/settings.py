"""用户设置：存哪儿、渲染快照放哪儿。

和「工程文件」的区别
--------------------
* **工程文件（``.kfproj``）**：某个具体片子的素材与参数，跟着片子走。
* **设置**：这台机器上"我习惯把东西放哪儿"，跨片子复用，改一次一直有效。

所以设置单独放一份 JSON，位置在 ``%APPDATA%\\KomaFlow\\settings.json``
（Windows 惯例；非 Windows 退回用户主目录下的 ``.komaflow``）。
不进仓库、不跟工程混在一起 —— 免得"打开别人的工程"把别人的路径习惯也带过来。

三类保存位置**分开设**（用户明确要的）：

``output_dir`` 成片（MOV / MP4）放哪儿
``project_dir`` 工程文件（``.kfproj``）默认存哪儿
``snapshot_dir`` 点「开始渲染」时那一份**装配好的快照**放哪儿

还有两个：

``work_dir`` 中间产物（分段、PNG 序列、work.blend）。**很占地方**
                    （透明那条路 2K 三分钟几十 GB），所以也可以单独指到快一点的盘。
``snapshot_enabled`` 关掉就不存快照（有人就是不想让盘里多出文件）
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

#: 设置的存放目录名
APP_DIRNAME = "KomaFlow"

#: 设置文件名
SETTINGS_FILENAME = "settings.json"


def config_dir() -> Path:
    """设置放哪个目录。

    Windows 用 ``%APPDATA%``（惯例，也是用户预期能找到的地方）；
    其他系统退回用户主目录下的隐藏目录。**只读环境也不该崩** ——
    取不到就退回当前工作目录，无非是设置跟着程序走。
    """
    base = os.environ.get("APPDATA") or os.environ.get("XDG_CONFIG_HOME")
    if base:
        return Path(base) / APP_DIRNAME
    home = Path.home()
    if os.name == "nt":
        return home / "AppData" / "Roaming" / APP_DIRNAME
    return home / ".komaflow"


def default_paths() -> dict[str, str]:
    """第一次运行时给一套默认位置。

    ⚠️ **打包之后不能再按"当前工作目录"算**（原来就是 ``Path.cwd()``）。
       安装版是被快捷方式启动的，工作目录可能是
       ``C:\\Windows\\System32`` 之类 —— 成片会被扔到那种地方，
       用户永远找不到（而且没权限时直接失败）。
       所以打包版默认放到**用户文档目录**下的 ``KomaFlow``。

    开发期（源码直接跑）仍按工作目录，跟我们的习惯一致。
    """
    if getattr(sys, "frozen", False):
        base = Path.home() / "Documents" / APP_DIRNAME
        return {
            "output_dir": str(base / "成片"),
            "project_dir": str(base / "工程"),
            "snapshot_dir": str(base / "快照"),
            "work_dir": str(base / "中间产物"),
        }
    here = Path.cwd()
    return {
        "output_dir": str(here / "output"),
        "project_dir": str(here / "output" / "projects"),
        "snapshot_dir": str(here / "output" / "snapshots"),
        "work_dir": str(here / "work"),
    }


@dataclass
class Settings:
    """用户设置。字段都有默认值，缺字段能向前兼容。"""

    #: 成片输出目录
    output_dir: str = ""
    #: 工程文件（.kfproj）默认目录
    project_dir: str = ""
    #: 渲染快照目录
    snapshot_dir: str = ""
    #: 中间产物目录（分段 / PNG 序列 / work.blend）
    work_dir: str = ""
    #: 点「开始渲染」时是否存一份快照
    snapshot_enabled: bool = True
    #: 界面缩放（0.8 / 1.0 / 1.25 / 1.5）。跟 DPI 是两回事，见 ui/theme.py。
    ui_zoom: float = 1.0
    #: 用户选定用哪台 Blender（空 = 还没选过，程序按优先级自动挑）。
    #: ⚠️ 存下来是有必要的：需求书设计取舍 说"多个 Blender 时由用户自己选、
    #: 工具绝不代选" —— 既然让用户选过一次，就不该下次启动又给他换掉。
    blender_exe: str = ""
    #: 第一次启动的引导是否已经走过。
    #: 只在**首次**给"找 Blender / 选版本 / 自检"这套引导，
    #: 之后启动就安静地按已存的选择走，别再弹一遍烦人。
    first_run_done: bool = False

    #: 上次**确定使用**的角色模型（`.pmx` / `.pmd`，或模型渲染出的 `.blend`）。
    #:
    #: 用户要求：
    # > 角色板块应该带有记忆性，上一次用户确定使用之后，下一次打开应该默认
    # > 还是那个，直到用户渲染下一个模型或者用户导入模型
    #:
    #: 所以它不是"最近打开过的文件"，而是**上次真正确定用过的那个**。
    #: 什么时候才会被改写：用户拖/选了一个模型、或模型渲染点了「继续」。
    #: 只在界面里点开看、渲染一半取消，都不会动它。
    last_model: str = ""
    #: 上次用的「已配好的工程」（`.blend`）。跟 ``last_model`` 分开存：
    #: 两者是**两条不同的路线**（PMX 组装 / 用户自带工程），不能混成一个字段。
    last_blend: str = ""

    #: 「渲染模型」那个独立窗口里上次用的模型文件。
    #:
    #: 用户要求：这个位置也要记住。
    #: ⚠️ 跟 ``last_model`` 分开：那个是**主流程角色卡**（要按它渲整片），
    #: 这个是**静帧三视图**的输入。混用会让"我只是想渲个三视图"
    #: 把主流程的角色悄悄换掉。
    last_render_model: str = ""
    #: 那个窗口里上次的出图目录（空 = 用默认的「输出目录/模型预览」）。
    last_render_outdir: str = ""

    #: 最近一次「渲染模型」存出的 .blend —— 作为**观感来源**。
    #:
    #: 整片渲染时可以把它调好的材质与色彩管理迁移到我们装配的工程上，
    #: 这样"物理走我方链路、观感用能力包的卡渲"两样都能拿到。
    last_look_blend: str = ""

    # ------------------------------------------------------------ 读写

    @classmethod
    def path(cls) -> Path:
        return config_dir() / SETTINGS_FILENAME

    @classmethod
    def load(cls) -> "Settings":
        """读设置。**读不到/读坏了都给默认值，绝不抛异常** ——
        一个坏掉的配置文件不该让程序起不来。"""
        defaults = default_paths()
        data: dict[str, Any] = {}
        try:
            raw = cls.path().read_text(encoding="utf-8")
            loaded = json.loads(raw)
            if isinstance(loaded, dict):
                data = loaded
        except (OSError, ValueError):
            data = {}

        known = {f.name for f in fields(cls)}
        clean = {k: v for k, v in data.items() if k in known}
        settings = cls(**clean)

        # 空路径一律补成默认值：手改配置文件留下空串是很常见的事
        for key, value in defaults.items():
            if not str(getattr(settings, key) or "").strip():
                setattr(settings, key, value)
        if not 0.5 <= float(settings.ui_zoom or 1.0) <= 3.0:
            settings.ui_zoom = 1.0
        return settings

    def save(self) -> Path:
        """写设置。目录不存在会建。**写失败也不抛**（只读环境照常用）。"""
        target = self.path()
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(asdict(self), ensure_ascii=False, indent=2)
            target.write_text(payload + "\n", encoding="utf-8")
        except OSError:
            pass
        return target

    # ------------------------------------------------------------ 便捷

    def dir_for(self, kind: str) -> str:
        """按用途取目录：``output`` / ``project`` / ``snapshot`` / ``work``。"""
        return str(getattr(self, f"{kind}_dir", "") or "")

    def describe(self) -> str:
        """一句话概览，给设置窗口底部显示。"""
        return (f"成片 → {self.output_dir}\n"
                f"工程 → {self.project_dir}\n"
                f"快照 → {self.snapshot_dir}{'' if self.snapshot_enabled else '（已关闭）'}")
