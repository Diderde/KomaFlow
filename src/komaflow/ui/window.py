"""⚠️ 这个模块**已经不用了，留在这里是当反面教材**（别再照着做一遍）。

一句话教训
----------
**不要为了"界面一体化"去掉系统窗口框。**

曾经的思路是：B站 / 抖音 / 微信 那些客户端看着"整个窗口都自己画"，
所以我们也 ``overrideredirect(True)`` 把系统窗口框去掉、自己画标题栏。
**这个推断是错的**：Electron 应用用的是**系统标准窗口**（有 Windows 的边框和
标题栏），只是把内容画到标题栏下面。系统框一直在，所以拖边改大小、双击最大化、
系统贴边吸附、多屏 DPI、任务栏按钮……**全都是系统负责的，不用写一行代码**。

我们去掉系统框之后，把上面这些能力**全部丢掉了**，然后手工补：
自己实现拖动、自己实现贴边、自己补任务栏按钮（``WS_EX_APPWINDOW``）、
自己处理"最小化后回不来"（``iconify`` 之后窗口再也回不来，得在最小化前
临时关掉无边框）。补了的能用，没补的一直缺 —— 用户第一句反馈就是
**"为什么抖音 B站 能拖边改大小，你这个不能"**。

而且代价不只是"少几个功能"：

* 窗口圆角被一起带走（要用 DWM 属性 33 补回来）
* ``WM_SETICON`` 的 HWND 得取 ``GetParent()``，否则静默失败
* 补任务栏按钮那对 ``ShowWindow(HIDE/SHOW)`` 会**同步派发消息**，
  Tk 在派发路径里把待执行的 ``after`` 顺手跑掉，反复套进去直接把调用栈压坏 ——
  进程毫无提示地崩掉，退出码 ``-1073740791``（见 ``work/repro_taskbar_recursion.py``）

现在 ``app.py`` 的 ``_build_header`` 用的是**系统标准窗口 + 自绘顶栏**，
只保留 ``_polish_title_bar``（DWM 属性 20 = 暗色模式，让系统标题栏接近品牌深蓝）。
系统框照常，一切交给 Windows。

下面这套代码留着只为对照：想重新发明窗口的话，先读一遍上面这段。

**原本的设计说明（留档，供对照）**：

* 按钮是圆角方块，跟界面里所有卡片同一套语言
* 关闭键悬停浮出枫红 ``#B33A2B``（角色主色），不是系统红
* 标题栏里放实时状态（就绪 / 渲染中 62%）
* 丢掉的四样：任务栏按钮（补 ``WS_EX_APPWINDOW``）、拖动与双击最大化与贴边
  （自己实现，**不复用 ``WM_NCHITTEST`` 子类化**）、最小化后回不来
  （最小化前临时关掉 ``overrideredirect``）、窗口圆角
  （``DWMWA_WINDOW_CORNER_PREFERENCE (33)``）
"""

from __future__ import annotations

import ctypes
import tkinter as tk

from . import assets as ui_assets
from . import theme as T

# ---- Win32 常量 ----
GWL_EXSTYLE = -20
WS_EX_APPWINDOW = 0x00040000
WS_EX_TOOLWINDOW = 0x00000080
SW_HIDE, SW_SHOW = 0, 5

#: 拖到离屏幕边缘多少像素内算"贴边"
SNAP_MARGIN = 16

#: 标题栏高度（设计像素，用时过 ``T.S()``）
BAR_HEIGHT = 40


class FramelessWindow:
    """把 ``tk.Tk`` 变成无边框，并补回丢掉的能力。"""

    def __init__(self, root: tk.Tk, *, on_close, drag_from=()) -> None:
        self.root = root
        self.on_close = on_close
        self.drag_from = list(drag_from)
        self.enabled = False
        self._pressed: tuple[int, int, int, int] | None = None
        self._restore_geometry: str | None = None
        self._maximized = False
        self._minimizing = False
        #: 防重入：_restore_taskbar_button 里调 ShowWindow 会同步回调窗口过程，
        #: 又触发 <Map>，再排一次本方法 —— 不拦就是无限递归（见该方法的说明）
        self._restoring = False

    # ------------------------------------------------------------ 安装
    def install(self) -> bool:
        """装上无边框。**任何异常都退回系统窗口框**并返回 False。"""
        try:
            self.root.overrideredirect(True)
            for widget in self.drag_from:
                widget.bind("<Button-1>", self._press, add="+")
                widget.bind("<B1-Motion>", self._drag, add="+")
                widget.bind("<ButtonRelease-1>", self._release, add="+")
                widget.bind("<Double-Button-1>", self._double_click, add="+")
            # 逃生通道之一：键盘就能关
            self.root.bind("<Alt-F4>", lambda _e: self.close(), add="+")
            self.root.bind("<Map>", self._on_map, add="+")
            self.enabled = True
            # 任务栏按钮要等窗口真正映射出来再补
            self.root.after(80, self._restore_taskbar_button)
            return True
        except tk.TclError:
            self.uninstall()
            return False

    def uninstall(self) -> None:
        """退回系统窗口框。"""
        try:
            self.root.overrideredirect(False)
        except tk.TclError:
            pass
        self.enabled = False

    # ------------------------------------------------------------ Win32
    def _hwnd(self) -> int:
        user32 = ctypes.windll.user32
        return user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()

    def _restore_taskbar_button(self) -> None:
        """``overrideredirect`` 会让窗口从任务栏消失，用 ``WS_EX_APPWINDOW`` 补回。

        ⚠️ **只改样式，绝不要在这里补 ``ShowWindow`` 一隐一显。**
        原先这里照着"让任务栏重新登记按钮"的常见做法加了
        ``ShowWindow(HIDE)`` + ``ShowWindow(SHOW)``，结果是**进程毫无提示地崩掉**
        （退出码 ``-1073740791``，栈里最后一帧是 ``CallWindowProcW`` 的
        access violation）。原因：``ShowWindow`` 会**同步**派发消息，
        而 Tk 在那条派发路径里会把待执行的 ``after`` 任务顺手跑掉 ——
        包含又一次 ``_restore_taskbar_button``。于是同一个 C 调用栈上
        反复套进去，窗口过程链被压坏。改样式本身就够系统重新登记按钮了。
        复现脚本：``work/repro_taskbar_recursion.py``。
        """
        if self._restoring:
            return
        self._restoring = True
        try:
            user32 = ctypes.windll.user32
            hwnd = self._hwnd()
            getter = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
            setter = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
            getter.restype = ctypes.c_longlong
            getter.argtypes = [ctypes.c_void_p, ctypes.c_int]
            setter.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_longlong]
            style = getter(hwnd, GWL_EXSTYLE)
            setter(hwnd, GWL_EXSTYLE,
                   (style | WS_EX_APPWINDOW) & ~WS_EX_TOOLWINDOW)
        except (AttributeError, OSError):
            pass # 补不上也不影响别的功能，只是任务栏少个按钮
        finally:
            self._restoring = False

    # ------------------------------------------------------------ 拖动
    def _press(self, event: tk.Event) -> None:
        self._pressed = (event.x_root, event.y_root,
                         self.root.winfo_x(), self.root.winfo_y())

    def _drag(self, event: tk.Event) -> None:
        if self._pressed is None or self._maximized:
            return
        start_x, start_y, win_x, win_y = self._pressed
        self.root.geometry(f"+{win_x + event.x_root - start_x}"
                           f"+{win_y + event.y_root - start_y}")

    def _release(self, event: tk.Event) -> None:
        if self._pressed is not None:
            self._snap(event)
        self._pressed = None

    def _snap(self, event: tk.Event) -> None:
        """自己实现的贴边分屏：拖到左右边缘各占半屏，拖到顶部最大化。

        宽度用 ``winfo_screenwidth()``（Tk 自己的坐标空间），
        跟 ``geometry()`` 的单位一致，DPI 缩放不会错位。
        """
        try:
            margin = T.S(SNAP_MARGIN)
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
            half = screen_w // 2
            if event.x_root <= margin:
                self._forget_maximize()
                self.root.geometry(f"{half}x{screen_h}+0+0")
            elif event.x_root >= screen_w - margin:
                self._forget_maximize()
                self.root.geometry(f"{half}x{screen_h}+{half}+0")
            elif event.y_root <= margin:
                self.toggle_maximize()
        except tk.TclError:
            pass

    def _double_click(self, _event: tk.Event) -> None:
        self.toggle_maximize()

    # ------------------------------------------------------------ 按钮
    def minimize(self) -> None:
        """最小化。

        ⚠️ ``overrideredirect`` 的窗口直接 ``iconify()`` 之后**回不来**
        （任务栏点它没反应）。所以先临时关掉无边框，映射回来时再装上。
        """
        self._minimizing = True
        try:
            self.root.overrideredirect(False)
            self.root.iconify()
        except tk.TclError:
            self._minimizing = False

    def _on_map(self, _event: tk.Event) -> None:
        """从最小化恢复：把无边框重新装上。"""
        if not self._minimizing:
            return
        self._minimizing = False
        try:
            self.root.overrideredirect(True)
            self.root.after(60, self._restore_taskbar_button)
        except tk.TclError:
            pass

    def _forget_maximize(self) -> None:
        self._maximized = False
        self._restore_geometry = None

    def toggle_maximize(self) -> None:
        try:
            if self._maximized:
                if self._restore_geometry:
                    self.root.geometry(self._restore_geometry)
                self._forget_maximize()
            else:
                self._restore_geometry = self.root.geometry()
                self.root.geometry(f"{self.root.winfo_screenwidth()}"
                                   f"x{self.root.winfo_screenheight()}+0+0")
                self._maximized = True
        except tk.TclError:
            pass

    @property
    def maximized(self) -> bool:
        return self._maximized

    def close(self) -> None:
        self.on_close()


class TitleBar(tk.Canvas):
    """自绘标题栏：LOGO + 产品名 + 实时状态 + 三个窗口按钮。

    整条画在一个 Canvas 上（而不是拼一堆小控件）：少一层嵌套，图形也更干净。
    """

    def __init__(self, master: tk.Misc, *, app_name: str, on_minimize,
                 on_maximize, on_close) -> None:
        # ⚠️ 整条标题栏是**一个 Canvas 上现画的**，Canvas 不参与布局缩放：
        # 控件高度包了 ``T.S()``、里面的坐标不包，就会"条变高了、字还缩在左上"。
        # 所以下面每一处坐标都过 ``T.S()``。
        super().__init__(master, height=T.S(BAR_HEIGHT), bg=T.NAVY,
                         highlightthickness=0, bd=0)
        self._status = "就绪"
        self._hover: str | None = None
        self._tags: dict[str, str] = {}
        self._build(app_name, on_minimize, on_maximize, on_close)

    # ---- 绘制 ----
    def _build(self, app_name: str, on_minimize, on_maximize, on_close) -> None:
        bar = T.S(BAR_HEIGHT)
        logo = ui_assets.image("logo_26.png")
        if logo is not None:
            self.create_image(T.S(24), bar // 2, image=logo)
        self.create_text(T.S(44), bar // 2, text=app_name, anchor="w",
                         fill="#FFFFFF", font=T.pick_font(11, bold=True))
        self.create_line(T.S(140), T.S(11), T.S(140), bar - T.S(11),
                         fill="#4E7BAA")
        self._status_item = self.create_text(T.S(152), bar // 2, text=self._status,
                                             anchor="w", fill="#9FC0DE",
                                             font=T.pick_font(9))

        # 三个窗口按钮：贴图 + 自己处理悬停
        self.update_idletasks()
        for name, command in (("min", on_minimize), ("max", on_maximize),
                              ("close", on_close)):
            self._add_button(name, command)

        # 底沿一条 1px 半透明分隔线（标题栏里要克制，不做渐变）
        self.create_line(0, bar - 1, T.S(4000), bar - 1, fill="#1B4F85")

    def _add_button(self, name: str, command) -> None:
        tag = f"winbtn_{name}"
        self._tags[name] = tag
        normal = ui_assets.image(f"win_{name}.png")
        if normal is None:
            return
        self.create_image(0, 0, image=normal, anchor="nw", tags=(tag, "winbtn"))
        self.tag_bind(tag, "<Button-1>", lambda _e, fn=command: fn())
        self.tag_bind(tag, "<Enter>", lambda _e, n=name: self._set_hover(n))
        self.tag_bind(tag, "<Leave>", lambda _e: self._set_hover(None))
        self.bind("<Configure>", lambda _e: self._layout())

    def _set_hover(self, name: str | None) -> None:
        self._hover = name
        for key, tag in self._tags.items():
            suffix = "_hover" if key == name else ""
            picture = ui_assets.image(f"win_{key}{suffix}.png")
            if picture is not None:
                try:
                    self.itemconfigure(tag, image=picture)
                except tk.TclError:
                    pass
        self.configure(cursor="hand2" if name else "arrow")

    def _layout(self) -> None:
        """按钮靠右排：窗口宽度变了要跟着走。

        ⚠️ 按钮尺寸用 ``T.S()`` 算，但**贴图的原生尺寸没变**（30px）——
        自绘按钮的 PNG 没法在 Tk 里缩放（``subsample`` 是最近邻，30→20 会把
        图标啃出锯齿，这坑踩过）。所以这里只按比例拉开**间距**，
        图本身保持原生大小，观感是"排得松一点"，不会糊。
        """
        width = self.winfo_width() or T.S(1200)
        size = T.S(30)
        gap = T.S(4)
        cursor = width - (size + gap) * 3 - T.S(8)
        for name in ("min", "max", "close"):
            tag = self._tags.get(name)
            if tag is None:
                continue
            self.coords(tag, cursor, (T.S(BAR_HEIGHT) - size) // 2)
            cursor += size + gap

    def set_status(self, text: str) -> None:
        """把当前状态写到标题栏里 —— 窗口被挡着时也能瞥一眼。"""
        self._status = text
        try:
            self.itemconfigure(self._status_item, text=text)
        except tk.TclError:
            pass
