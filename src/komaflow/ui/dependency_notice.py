"""两个提示窗 —— 都走 :class:`notice_base.NoticeWindow` 那套柔和卡片风。

用户要求（原话）
----------------
> 不随（包）,但是告诉用户：该插件不...，因为...，所以需要联网。这种句式，
> 而且窗口参考主程序识图的风格，柔和些，可以渲染个相关情绪的吉祥物拔在窗口，
> 可以半遮掩那种探头式
>
> 面部表情你也可以改，符合当前情绪就行，装好后还有提示准备就绪窗口，
> 那是另一个开心的样子，这几个界面 Q版、人物版，你自己选，
> 缺失让补充的情绪是**探头出来小心翼翼的在确认**那种

情绪映射（我定的）
------------------
=================== ========================== ======================
场景 情绪 吉祥物
=================== ========================== ======================
缺 mmd_tools 插件 探头、小心翼翼在确认 ``mascot_peek.png``
装好了 / 准备就绪 开心 ``mascot_happy.png``
=================== ========================== ======================

两张都是从**人物版透明立绘**裁的（跳跃 / 舞姿），不是 Q 版 ——
原因见 ``work/make_mood_assets.py`` 的模块说明：Q 版全身那两张带背景，
而人设集自带的抠图脚本依赖 rembg + scipy，不值得为一张图引入重依赖。
"""

from __future__ import annotations

import tkinter as tk

from .notice_base import NoticeWindow

#: mmd_tools 是干什么的（两个窗都要用，写一份）
WHAT_IT_DOES = ("mmd_tools 负责把 MMD 的模型与动作读进 Blender —— "
                ".pmx、.vmd（动作 / 表情 / 镜头）都靠它。"
                "没有它，这些文件读不进来。")

#: 为什么不随包（用户要的"因为…"）
WHY_NOT_BUNDLED = ("本工具不自带 mmd_tools：它只有几 MB，"
                   "但它是 GPL 许可的插件，随包分发会带来额外的分发义务；"
                   "而且它跟 Blender 版本绑定，装最新版反而更稳。")


class DependencyNotice(NoticeWindow):
    """缺插件时的说明窗：探头、小心翼翼在确认。"""

    mascot = "mascot_peek.png"

    def __init__(self, parent: tk.Misc, *, on_install=None, on_recheck=None,
                 missing: str = "mmd_tools", on_close=None) -> None:
        super().__init__(parent, on_close=on_close)
        self.on_install = on_install
        self.on_recheck = on_recheck
        self.missing = missing

    @property
    def title_text(self) -> str:
        return f"缺一个插件：{self.missing}"

    @property
    def blocks(self) -> list[tuple[str, str]]:
        return [
            ("它是干什么的", WHAT_IT_DOES),
            ("为什么没随包", WHY_NOT_BUNDLED),
            ("怎么装", "从 Blender 官方插件库下载安装 —— 它由 Blender 官方托管、"
                       "随版本更新，比我们塞一份旧的进去更稳。"
                       "所以这一步需要联网，装完之后就不再需要网了。"),
        ]

    @property
    def buttons(self) -> list[tuple[str, object, bool]]:
        rows: list[tuple[str, object, bool]] = []
        if self.on_install is not None:
            rows.append(("下载并安装（需要联网）", self._install, True))
        if self.on_recheck is not None:
            rows.append(("我已自己装好，重新检测", self._recheck, False))
        return rows

    @property
    def footnote(self) -> str:
        return ("也可以自己在 Blender 里装：编辑 → 偏好设置 → 获取扩展，"
                "搜索 MMD Tools。装完回来点「重新检测」。")

    def _install(self) -> None:
        if self.on_install is not None:
            self.on_install()
        self.close()

    def _recheck(self) -> None:
        if self.on_recheck is not None:
            self.on_recheck()
        self.close()


class ReadyNotice(NoticeWindow):
    """装好了 / 准备就绪：另一个开心的样子。

    什么时候弹
    ----------
    * 插件刚装成功，重新探测确认**已经可用**之后
    * 手动点「重新检测」，结果从"缺插件"变成"可用"时

    ⚠️ **不要在缺插件时也弹这个** —— 那是 :class:`DependencyNotice` 的活。
    这里必须是"确实能用了"才弹，否则就是骗人。
    """

    mascot = "mascot_happy.png"

    def __init__(self, parent: tk.Misc, *, version: str = "",
                 on_start=None, on_settings=None) -> None:
        super().__init__(parent)
        self.version = version
        self.on_start = on_start
        self.on_settings = on_settings

    @property
    def title_text(self) -> str:
        return "准备就绪"

    @property
    def blocks(self) -> list[tuple[str, str]]:
        where = f"Blender {self.version} " if self.version else "Blender "
        return [
            ("现在可以做什么", f"{where}已经把 MMD 插件装好并启用了。"
                               "把模型、动作、镜头拖进主窗口，就能开始渲。"),
            ("拖进去就行", "素材拖到窗口任意位置都能放；放错了点卡片右上角的×"
                           "就能清掉。动作和表情不用你分类 —— "
                           "工具会自己看文件内容判断。"),
        ]

    @property
    def buttons(self) -> list[tuple[str, object, bool]]:
        rows: list[tuple[str, object, bool]] = []
        if self.on_start is not None:
            rows.append(("好，开始用", self.on_start, True))
        if self.on_settings is not None:
            rows.append(("先去设置里看看", self.on_settings, False))
        return rows

    @property
    def footnote(self) -> str:
        return "以后缺什么插件也会这样提醒你，不会让你渲到一半才发现。"

    def _start(self) -> None:
        if self.on_start is not None:
            self.on_start()
        self.close()

    def _settings(self) -> None:
        if self.on_settings is not None:
            self.on_settings()
        self.close()


class MissingBlenderNotice(NoticeWindow):
    """一个 Blender 都没找到。

    为什么要有这个窗
    ----------------
    原来"没找到 Blender"只在面板里写一行小字，而"缺 mmd_tools"却会弹窗 ——
    **后者更轻（装个插件就行），前者更重（完全没法用），结果重的反而更安静。**
    这个窗就是把这个不一致补上。

    吉祥物用探头那张：歪着头、小心地确认 —— 跟"我们没找到"的语气一致，
    不用"出错"那种吓人的样子。
    """

    mascot = "mascot_peek.png"

    def __init__(self, parent: tk.Misc, *, on_redetect=None,
                 on_download=None) -> None:
        super().__init__(parent)
        self.on_redetect = on_redetect
        self.on_download = on_download

    @property
    def title_text(self) -> str:
        return "没找到 Blender"

    @property
    def blocks(self) -> list[tuple[str, str]]:
        return [
            ("为什么需要它", "本工具自己不渲染 —— 它把活儿交给 Blender 去干。"
                            "所以机器上得先有一个 Blender，工具才动得起来。"),
            ("本工具不自带 Blender", "Blender 有一千多 MB，而且它是 GPL 许可的；"
                                    "把它塞进来会让安装包变得很大，"
                                    "分发时还要多担一层义务。"
                                    "用你自己装的那个，升级也方便。"),
            ("装哪个版本", "装 5.x 的任意一版就行（官方下载页那个「LTS」版本最稳）。"
                          "装的时候不用改任何选项，默认下一步即可。"),
        ]

    @property
    def buttons(self) -> list[tuple[str, object, bool]]:
        rows: list[tuple[str, object, bool]] = []
        if self.on_download is not None:
            rows.append(("打开官网下载页", self._download, True))
        if self.on_redetect is not None:
            rows.append(("我已装好，重新找一遍", self._redetect, False))
        return rows

    @property
    def footnote(self) -> str:
        return ("装完不用重启本工具，点「重新找一遍」就会重新扫描。")

    def _download(self) -> None:
        if self.on_download is not None:
            self.on_download()
        self.close()

    def _redetect(self) -> None:
        if self.on_redetect is not None:
            self.on_redetect()
        self.close()


class BlenderPickNotice(NoticeWindow):
    """找到多台 Blender，让用户选一台。

    需求书设计取舍：**多个 Blender 时由用户自己选，工具绝不代选。**
    但原来只是"不代选"—— 程序还是自己按优先级挑了一台，
    用户想去改得自己进设置里翻。

    这里补上：首次启动发现多台时，**直接把选择摆到面前**，
    选完记进设置，下次不再问。
    """

    mascot = "mascot_happy.png"

    def __init__(self, parent: tk.Misc, *, candidates: list[dict],
                 on_pick=None) -> None:
        super().__init__(parent)
        self.candidates = candidates
        self.on_pick = on_pick

    @property
    def title_text(self) -> str:
        return f"找到 {len(self.candidates)} 个 Blender"

    @property
    def blocks(self) -> list[tuple[str, str]]:
        lines = []
        for index, item in enumerate(self.candidates, start=1):
            exe = str(item.get("exe") or "")
            version = str(item.get("version") or "版本未知")
            tools = "插件齐全" if item.get("has_tools") else "缺 mmd_tools 插件"
            lines.append(f"{index}. Blender {version} —— {tools}\n{exe}")
        return [
            ("用哪一台", "本工具不替你挑 —— 用哪个版本由你定，"
                        "选完会记住，以后不再问。"),
            ("这一台的情况", "\n".join(lines)),
        ]

    @property
    def buttons(self) -> list[tuple[str, object, bool]]:
        rows: list[tuple[str, object, bool]] = []
        for index, item in enumerate(self.candidates):
            version = str(item.get("version") or "?")
            rows.append((f"用第 {index + 1} 台（Blender {version}）",
                         (lambda i=index: self._pick(i)),
                         index == 0))
        return rows

    @property
    def footnote(self) -> str:
        return "选错了也不要紧：设置窗口里随时能换。"

    def _pick(self, index: int) -> None:
        if self.on_pick is not None:
            self.on_pick(index)
        self.close()


class SelfCheckNotice(NoticeWindow):
    """引导走完最后一屏：**把自检结果摆出来**再进主界面。

    用户原话
    --------
    > 第一次启动会引导到选择版本，然后自检

    「选版本」那一屏是 :class:`BlenderPickNotice`；这里补的是它后面的
    **自检结果**。以前选完直接进主界面 —— 一句"到底行不行"都没有，
    用户得自己去看侧栏那几行小字。

    这里是**最后一道关卡**：查完 Blender、插件、目标盘，再放他进主界面。
    所以文案要能一句话读完：三个结论 + 一句"结果放哪儿了"。

    ⚠️ **"都准备好了"只在三项全过时才说**（见 :attr:`ready`）。
       一个"缺 mmd_tools 插件"的环境是最需要看这一屏的，
       这时候标题就得老实说"有几处要注意" —— 光图好看就是骗人。
    """

    mascot = "mascot_happy.png"

    def __init__(self, parent: tk.Misc, *, blender: str = "",
                 tools: str = "", tools_ok: bool = True,
                 disk: str = "", disk_ok: bool = True, output_dir: str = "",
                 version: str = "", on_start=None, on_settings=None) -> None:
        super().__init__(parent)
        self.blender = str(blender or "版本未知")
        self.tools = str(tools or ("已装好" if tools_ok else "没找到"))
        self.tools_ok = bool(tools_ok)
        self.disk = str(disk)
        self.disk_ok = bool(disk_ok)
        self.output_dir = str(output_dir)
        self.version = str(version)
        self.on_start = on_start
        self.on_settings = on_settings

    # ------------------------------------------------------------ 结果判定
    @property
    def ready(self) -> bool:
        """三项全过才算"都准备好了"。"""
        return bool(self.tools_ok and self.disk_ok and self.disk)

    @property
    def title_text(self) -> str:
        return "都准备好了" if self.ready else "有几处要注意"

    @property
    def blocks(self) -> list[tuple[str, str]]:
        rows = [
            ("Blender", f"{self.blender} —— "
                        + ("能读 MMD 素材，可以直接用。"
                           if self.tools_ok else "这台没装插件，读不了素材。")),
            ("mmd_tools 插件", self.tools
             + ("（已启用）" if self.tools_ok else "（缺这个插件就读不了 .pmx / .vmd）")),
            ("目标盘", self.disk or "暂时查不到 —— 不放素材也看不出来，先开始也行。"),
        ]
        if self.output_dir:
            rows.append(("成片放这儿", self.output_dir))
        return rows

    @property
    def buttons(self) -> list[tuple[str, object, bool]]:
        rows: list[tuple[str, object, bool]] = []
        if self.on_start is not None:
            rows.append(("好，开始用", self._start, True))
        if self.on_settings is not None:
            # 有毛病时把"去改"放前面？不行 —— 按钮顺序是用户的预期位置，
            # 主按钮永远在第一个；有问题时靠标题和正文说清楚。
            rows.append(("去设置里看看", self._settings, False))
        return rows

    @property
    def footnote(self) -> str:
        tail = f"当前版本 {self.version}。" if self.version else ""
        if self.ready:
            return ("这就是第一次启动的引导，走完就不再打扰你。"
                    "以后缺插件、换 Blender 仍会提醒。" + tail)
        return ("带 ⚠ 的那几项照着正文处理一下即可；"
                "处理完这个提示就不再出现。" + tail)

    def _start(self) -> None:
        if self.on_start is not None:
            self.on_start()
        self.close()

    def _settings(self) -> None:
        if self.on_settings is not None:
            self.on_settings()
        self.close()
