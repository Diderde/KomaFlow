"""环境选择器：选一台 Blender 来渲。

为什么单独拎出来
----------------
它原来长在主界面侧栏里。但"选哪台 Blender"其实是**设置**，不是每次渲片都要
看的东西 —— 跟"成片存哪儿"是一类。所以整块搬进设置窗口，主界面清爽了。

做成独立组件而不是写死在设置窗口里，是因为主界面**也需要知道当前选的是哪台**
（要报"缺插件，先用不了"这种警告），两边共用同一份逻辑，不会各写一套。

界面长这样::

    ✓ Blender 5.2.2 LTS · 可用
    [✓ Blender 5.2.2 LTS 可用（共 2 台可选） ▾]
    [重新找一遍] [自己选路径…]
    用 Blender 5.2.2 LTS，插件齐全，可以直接开工。

措辞原则：**说操作，不说感受**。不写"让物理先稳一稳"这种比方，
直接说"缺 mmd_tools 插件，读不了 .pmx / .vmd"。
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable

from . import theme as T
from . import tip as tip_module

#: 这台 Blender 能不能直接用，取决于它有没有 mmd_tools 插件 ——
#: 没这个插件，.pmx / .vmd 根本读不进去，对我们就等于废的。
#: 另外版本太老也算"用不了"，但只是"可能"，所以措辞留余地。
#:
#: ⚠️ 好的那档写**"可用"**两个字就够了。原来写"能直接开工"，
#: 在窄地方（下拉框的脸、主界面收起行）会把整行撑长、甚至被截断。
_BLENDER_STATUS_TEXT = {
    "ok": "可用",
    "notools": "缺 mmd_tools 插件，读不了 .pmx / .vmd",
    "old": "版本偏老，可能渲不出来",
}

#: 短说法，用在窄地方（下拉框的脸、收起行）
_BLENDER_STATUS_SHORT = {
    "ok": "可用",
    "notools": "缺 mmd_tools，用不了",
    "old": "版本偏老",
}

#: 每档前面的记号
MARK = {"ok": "✓", "notools": "⚠", "old": "⚠"}
#: 兼容旧名
_BLENDER_STATUS_MARK = MARK


def blender_status(item: dict) -> str:
    """这台属于哪一档：``"ok"`` / ``"notools"`` / ``"old"``。"""
    version = str(item.get("version") or "")
    if item.get("has_tools") is False:
        return "notools"
    if version and not version.startswith("5"):
        return "old"
    return "ok"


def status_text(status: str) -> str:
    """这一档的长说明（说清后果，不写"推荐/不推荐"这种空话）。"""
    return _BLENDER_STATUS_TEXT.get(status, "")


def status_short(status: str) -> str:
    """这一档的短说明（窄地方用）。"""
    return _BLENDER_STATUS_SHORT.get(status, "")


def summary_of(probed: list[dict], chosen_exe: str = "") -> str:
    """给窄地方用的一句话（主界面收起行）。**只说结论**，不报版本号。

    ⚠️ 主界面那一行只有 ~350 实际像素。原来拼的是"版本号 + 状态 + 台数"，
    结果被截成 `✓ Blender 5.2…. · 能直接开工（共` 这种半截话（用户反馈过）。
    所以这里只留结论；想看细节点开面板或进设置。
    """
    if not probed:
        return "没找到 Blender，去设置里装"
    item = next((i for i in probed if i.get("exe") == chosen_exe), probed[0])
    status = blender_status(item)
    if status == "ok":
        version = item.get("version") or "版本未知"
        return f"{MARK[status]} 可用（Blender {version}）"
    return f"{MARK[status]} {_BLENDER_STATUS_SHORT[status]}"


def _middle_ellipsis(text: str, limit: int = 34) -> str:
    """中间省略，保住两端。

    路径和版本号都是**两头有用**的：``<Blender 安装目录>\\blender.exe``
    从头截就看不出是哪一台了。
    """
    text = " ".join(str(text).split())
    if len(text) <= limit:
        return text
    keep = limit - 1
    head = keep // 2
    tail = keep - head
    return f"{text[:head]}…{text[-tail:]}"


def blender_label(item: dict) -> str:
    """下拉里的一行：``✓ Blender 5.2.2 LTS（可用） · D:\\Steam\\…``。

    路径放在最后并做中间省略 —— 装了两台 Blender 时，
    光看版本号可能分不清哪个是哪个，得靠路径的尾巴认。
    """
    status = blender_status(item)
    version = item.get("version") or "版本未知"
    name = f"{_BLENDER_STATUS_MARK[status]} Blender {version}（{_BLENDER_STATUS_TEXT[status]}）"
    where = _middle_ellipsis(str(item.get("exe") or ""))
    return f"{name} · {where}" if where else name


def pick_reason(probed: list[dict]) -> str:
    """说清"为什么默认选了这一台"。

    只有一台、或者第一台就能用时不用解释 —— 解释反而啰嗦。
    存在多台且都有毛病时才值得说明。
    """
    if len(probed) < 2:
        return ""
    if any(blender_status(item) == "ok" for item in probed):
        return ""
    return "这几台都缺东西，先挑了毛病最少的，你可以自己换。"


class EnvPicker:
    """环境选择器组件。

    它不是自给自足的：**列表由外面喂进来**（``set_list``），选中之后也是回调
    通知外面（``on_pick``）—— 因为"当前用哪台"这个状态归主程序管，
    组件只负责显示和收集点击。
    """

    def __init__(self, parent: tk.Misc, *, on_rediscover: Callable[[], None],
                 on_pick: Callable[[list[dict], int], None],
                 on_manual: Callable[[], None], wraplength: int = 380) -> None:
        self.on_rediscover = on_rediscover
        self.on_pick = on_pick
        self.on_manual = on_manual
        self.probed: list[dict] = []
        self.labels: list[str] = []

        self.frame = tk.Frame(parent, bg=T.CARD)
        self.wrap = wraplength

        # "现在用哪台、行不行" —— 颜色也带信息：能用是青的，有问题才是橙的。
        self.status_row = tk.Label(
            self.frame, text="正在检测…", bg=T.CARD, fg=T.TEXT_SUB,
            font=T.pick_font(9), anchor="w", justify="left",
            wraplength=T.S(wraplength))
        self.status_row.pack(fill="x", pady=(0, T.S(6)))

        # ⚠️ 下拉框绑的是**显示变量**，不是存路径的那个变量。
        # OptionMenu 会把自己的变量值当成脸显示出来；如果直接绑路径，
        # 一台 Blender 时那行就会变成一整条
        # ``<Blender 安装目录>\blender.exe``，又长又不好看。
        self.face = tk.StringVar(value="正在检测…")
        self.combo = tk.OptionMenu(self.frame, self.face, "正在检测…")
        self.combo.configure(width=30, relief="flat", bg="#FFFFFF", fg=T.TEXT,
                             activebackground=T.BEIGE_SOFT, font=T.pick_font(9),
                             highlightthickness=1, highlightbackground=T.BORDER,
                             anchor="w")
        self.combo["menu"].configure(bg="#FFFFFF", fg=T.TEXT,
                                     activebackground=T.BEIGE_SOFT,
                                     font=T.pick_font(9))
        self.combo.pack(fill="x")
        tip_module.attach(
            self.combo,
            "机器上装了不止一台 Blender 时，在这里选一台来渲。\n"
            "缺 mmd_tools 的那台读不了模型，别选它。")

        row = tk.Frame(self.frame, bg=T.CARD)
        row.pack(fill="x", pady=(T.S(8), 0))
        again = T.FlatButton(row, "重新找一遍", self.on_rediscover, width=T.S(88),
                             height=T.S(28), bg=T.CARD, fill=T.NAVY,
                             hover=T.NAVY_SOFT, font=T.pick_font(9, bold=True))
        again.pack(side="left")
        tip_module.attach(again, "新装了 Blender、或刚给它装了 mmd_tools 插件，点这里重找。")
        manual = T.FlatButton(row, "自己选路径…", self.on_manual, width=T.S(94),
                              height=T.S(28), bg=T.CARD, fill="#FFFFFF",
                              hover=T.BEIGE_SOFT, fg=T.NAVY, outline=T.BORDER,
                              font=T.pick_font(9))
        manual.pack(side="left", padx=T.S(6))
        tip_module.attach(manual,
                          "自动找出来的都不对时，手动指一个 blender.exe。\n"
                          "指错了点「重新找一遍」就能回到自动挑。")

        self.hint = tk.Label(self.frame, text="", bg=T.CARD, fg=T.TEXT_SUB,
                             font=T.pick_font(9), anchor="w", justify="left",
                             wraplength=T.S(wraplength))
        self.hint.pack(fill="x", pady=(T.S(8), 0))

    # -------------------------------------------------------------- 对外接口
    def set_list(self, probed: list[dict]) -> None:
        """喂进探测结果，重建下拉项。"""
        self.probed = list(probed)
        menu = self.combo["menu"]
        menu.delete(0, "end")
        self.labels = [blender_label(item) for item in probed]
        for index, label in enumerate(self.labels):
            menu.add_command(label=label,
                             command=lambda i=index: self.on_pick(self.probed, i))

    def show_choice(self, index: int) -> None:
        """把"当前选中的是哪台"反映到状态行、下拉框和提示上。"""
        if not self.probed:
            self.status_row.configure(text="还没找到 Blender", fg=T.MAPLE)
            self.face.set("没找到 Blender")
            return
        index = max(0, min(index, len(self.probed) - 1))
        item = self.probed[index]
        status = blender_status(item)
        version = item.get("version") or "版本未知"
        more = f"（共 {len(self.probed)} 台可选）" if len(self.probed) > 1 else ""

        self.status_row.configure(
            text=f"{MARK[status]} Blender {version} · {status_text(status)}",
            fg=T.TEAL_DEEP if status == "ok" else T.MAPLE)
        self.face.set(f"{MARK[status]} Blender {version} "
                      f"{status_short(status)}{more}")

    def set_hint(self, text: str) -> None:
        self.hint.configure(text=text)

    def summary(self) -> str:
        """给窄地方用的一句话（主界面收起行）。"""
        return summary_of(self.probed)
