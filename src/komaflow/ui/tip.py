"""悬停提示：鼠标停在控件上才浮出来的那行小字。

为什么要有它
------------
界面里原先有一堆"解释性"文字是**常驻**的：把文件拖到卡片上即可、
镜头留空会怎样、盘还够不够……全摊在面板上，把真正要看的东西挤没了。
这些东西的正确位置是**鼠标停上去才出来**——想查的能查到，平时不占地方。

怎么实现的
----------
Tk 没有自带 tooltip。这里用 ``tk.Toplevel`` 做一个无边框小窗：

* ``overrideredirect(True)`` 去掉系统边框和标题栏；``-topmost`` 让它飘在所有窗口之上
* 不是 ``transient`` —— transient 的子窗关不掉、还会跟着主窗一起最小化
* 延迟 600ms 才弹出。鼠标扫过一排按钮时不该闪出一串气泡
* ⚠️ 所有定时器都用 ``after`` 挂在主窗上，**不在** tooltip 自己身上 ——
  tooltip 会被销毁，挂在它身上的 ``after`` 会连回调一起没掉
* ⚠️ 不用 ``waitvar`` / 不阻塞：那会把主线程卡住

用法::

    from . import tip
    tip.attach(button, "重新扫描一遍本机的 Blender")

⚠️ 文字要**短**（一句话，最多两句）。它不是文档，浮出来挡住别的东西就不好了。
"""

from __future__ import annotations

import re
import tkinter as tk

from . import theme as T

#: 鼠标停住多久才弹出（毫秒）。太短会一闪一闪，太长用户以为没有。
DELAY_MS = 600

#: 同一个 tooltip 最多活多久（毫秒）。没人碰它时自己收掉，免得残留。
LINGER_MS = 12000

#: 提示小窗最宽多少**设计像素**（超了就折行）
MAX_WIDTH = 420

#: 在这些标点**之前**断行比较好看（别让标点跑到下一行开头）。
_NO_BREAK_BEFORE = "，。：；！？、）】」》"


def wrap_text(text: str, width_px: int, *, size: int = 9) -> str:
    """按**像素宽度**给中文折行，返回插好换行符的文字。

    为什么不用 Tk 的 ``wraplength``
    ------------------------------
    ``wraplength`` 是**按空格断词**的。中文整句没有空格，Tk 就把整句
    当成一个超长单词、**根本不换行** —— 标签自然宽度撑到几百像素，
    被提示条窗口裁掉右边（用户截图反馈过）。

    试过在中文之间插零宽空格（U+200B）当断点，实测**不起作用**：
    在固定宽容器里量行数，插与不插都一样是一行（``work/probe_wrap_lines.py``）。

    所以改成自己算：逐个字量宽度、超了就换行。完全确定，不依赖 Tk 的断词规则。

    :param width_px: 一行最多多少实际像素。
    """
    from . import theme as T

    lines: list[str] = []
    for paragraph in text.split("\n"):
        if not paragraph:
            lines.append("")
            continue
        line = ""
        for chunk in _chunks(paragraph):
            candidate = line + chunk
            if line and T.measure_text(None, candidate, size) > width_px:
                # ⚠️ 别把标点甩到下一行开头，那样很难看：把上一个字一起挪下去
                if chunk and chunk[0] in _NO_BREAK_BEFORE and len(line) > 1:
                    lines.append(line[:-1])
                    line = line[-1] + chunk
                else:
                    lines.append(line)
                    line = chunk
            else:
                line = candidate
        if line:
            lines.append(line)
    return "\n".join(lines)


#: 折行时**当成一个整体**的字符段：连续的英文/数字/常见符号。
#: ⚠️ 不这么做的话 ``MB`` 会被折成 ``M`` / ``B``、``.pmx`` 折成 ``.pm`` / ``x``
#: —— 逐字符折行对中文没问题，对夹杂的英文就很难看（实际截图里出现过
#: 「它只有几 M / B，但它是 GPL…」）。
_ASCII_RUN = re.compile(r"[0-9A-Za-z_.\-+/#@]+")


def _chunks(paragraph: str):
    """把一段拆成"折行单位"：英文串整体一个，中文一个字一个。"""
    position = 0
    for match in _ASCII_RUN.finditer(paragraph):
        if match.start() > position:
            yield from paragraph[position:match.start()]
        yield match.group()
        position = match.end()
    if position < len(paragraph):
        yield from paragraph[position:]

#: 所有活着的提示。重建界面时要按这份名单统一收掉（见 :func:`close_all`）。
_LIVE: list["Tip"] = []


class Tip:
    """一条悬停提示。一个实例管一个控件。

    不要在 :class:`Tip` 里直接写 ``self.root.after(...)`` 然后就忘了它 ——
    控件被销毁时必须把定时器取消掉，否则回调会去碰已经没了的窗口。
    """

    def __init__(self, widget: tk.Misc, text: str) -> None:
        self.widget = widget
        self.text = text
        self.window: tk.Toplevel | None = None
        self._show_job: str | None = None
        self._hide_job: str | None = None
        self._linger_job: str | None = None
        self._alive = True
        _LIVE.append(self)

        # ⚠️ ``add="+"``：控件上可能已经绑了别的处理（按钮的悬停变色就是），
        # 直接 bind 会把原来那个覆盖掉，按钮就"没反应"了。
        widget.bind("<Enter>", self._on_enter, add="+")
        widget.bind("<Leave>", self._on_leave, add="+")
        widget.bind("<ButtonPress>", self._on_leave, add="+")
        widget.bind("<Destroy>", self._on_destroy, add="+")
        widget.bind("<Unmap>", self._on_leave, add="+")

    # ------------------------------------------------------------ 事件
    def _on_enter(self, _event=None) -> None:
        self._cancel(self._hide_job)
        self._hide_job = None
        if self.window is not None:
            return
        self._show_job = self.widget.after(DELAY_MS, self._show)

    def _on_leave(self, _event=None) -> None:
        self._cancel(self._show_job)
        self._show_job = None
        self._hide()

    def _on_destroy(self, event) -> None:
        # <Destroy> 会冒泡：只有事件源就是本控件时才收工
        if event.widget is not self.widget:
            return
        self._alive = False
        for job in (self._show_job, self._hide_job, self._linger_job):
            self._cancel(job)
        self._hide()

    def _cancel(self, job: str | None) -> None:
        if job is None:
            return
        try:
            self.widget.after_cancel(job)
        except (tk.TclError, ValueError):
            pass

    # ------------------------------------------------------------ 显示
    def _show(self) -> None:
        self._show_job = None
        if not self._alive or self.window is not None or not self.text:
            return
        try:
            if not self.widget.winfo_ismapped():
                return
            x = self.widget.winfo_rootx() + T.S(12)
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + T.S(4)
        except tk.TclError:
            return

        window = tk.Toplevel(self.widget)
        window.overrideredirect(True)
        window.configure(bg=T.NAVY_DEEP)
        try:
            window.attributes("-topmost", True)
        except tk.TclError:
            pass # 个别系统不支持，就少一层置顶，不影响功能

        # ⚠️ **不要依赖 wraplength**：它按空格断词，中文整句没空格就不换行，
        # 标签会撑到几百像素、右边被窗口裁掉。自己按像素折好再交给 Label。
        wrapped = wrap_text(self.text, T.S(MAX_WIDTH))
        tk.Label(window, text=wrapped, bg=T.NAVY_DEEP, fg="#FFFFFF",
                 font=T.pick_font(9), justify="left", padx=T.S(8),
                 pady=T.S(5)).pack()
        # 算好尺寸再定位，否则会先在屏幕左上角闪一下
        window.update_idletasks()
        screen_w = window.winfo_screenwidth()
        if x + window.winfo_width() > screen_w - T.S(8):
            x = max(T.S(8), screen_w - window.winfo_width() - T.S(8))
        window.geometry(f"+{x}+{y}")

        self.window = window
        self._linger_job = self.widget.after(LINGER_MS, self._hide)

    def _hide(self) -> None:
        self._cancel(self._linger_job)
        self._linger_job = None
        if self.window is None:
            return
        try:
            self.window.destroy()
        except tk.TclError:
            pass
        self.window = None


def attach(widget: tk.Misc, text: str) -> Tip:
    """给控件挂一条悬停提示，返回 :class:`Tip`（一般不用管返回值）。"""
    return Tip(widget, text)


def find(widget: tk.Misc) -> Tip | None:
    """找某个控件身上挂着的提示。

    用来**改已挂好的提示文字**（比如"透明格式"换了编码器，
    介绍也得跟着换）。不用每处调用都存返回值，省一堆变量。
    """
    for owner in list(_LIVE):
        if getattr(owner, "widget", None) is widget:
            return owner
    return None


def close_all(root: tk.Misc | None = None) -> int:
    """把所有还挂着的提示窗收掉，返回收掉几个。

    ⚠️ **重建界面之前必须调一次**。提示窗是挂在*旧*控件上的，
    把那些控件 ``destroy()`` 掉之后，提示对象的 ``<Destroy>`` 回调会跑，
    但已经弹出来的那个 ``Toplevel`` 不一定来得及销毁 ——
    屏幕上就会留一个"孤零零的小黑条"，而且再也点不掉（踩过）。
    """
    closed = 0
    for owner in list(_LIVE):
        try:
            if owner.window is not None:
                closed += 1
            owner._hide()
            owner._alive = False
        except Exception: # noqa: BLE001 - 收尾阶段不该因为一个提示窗失败就崩
            pass
    _LIVE.clear()
    return closed
