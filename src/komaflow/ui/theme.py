"""配色、字体与自绘基础件。

配色
----
主色 **#0C3967**（深蓝），辅色 **#EAD0B0**（暖米）。这一对是"现代工具软件"的
常见气质：深蓝压住结构，米色做底不刺眼。

关于 MIKU 元素（**合规说明，别删这段**）
----------------------------------------
初音未来（初音ミク / Hatsune Miku / VOCALOID）是**受保护的角色形象与商标**，
按需求书 / / 的规定：

* ❌ 不得出现角色形象、名字、`初音ミク` / `MIKU` / `VOCALOID` 字样
* ❌ 不得使用任何官方立绘、图标、Logo
* ❌ 不得暗示官方关联或背书

因此这里只用**抽象且通用**的元素来点那个气质：

* **青色点缀** `TEAL` —— 颜色本身不构成商标
* **音符符号** ♪ ♫ —— Unicode 通用音乐符号
* **抽象双飘带** —— 原创的 S 形曲线，不指向任何具体角色造型

这三样都画在 :func:`draw_emblem` 里，全部按坐标现画，不含任何第三方素材。
"""

from __future__ import annotations

import math
import tkinter as tk
from tkinter import font as tkfont

# --------------------------------------------------------------------------
# 配色
# --------------------------------------------------------------------------

NAVY = "#0C3967" # 主色（深蓝）
NAVY_DEEP = "#082A4E" # 更深，用于顶栏/按下态
NAVY_SOFT = "#1B4F85" # 稍亮，用于悬停
NAVY_TINT = "#E8EEF5" # 深蓝的极浅底

BEIGE = "#EAD0B0" # 辅色（暖米）
BEIGE_SOFT = "#F5E7D5" # 浅米
BEIGE_LINE = "#E7D6BE" # 米色描边（比原来淡一档）

CREAM = "#F5F1E9" # 页面底色（暖米白 —— 大块纯白太刺眼，这里刻意压暗一点）
CARD = "#FCFAF6" # 卡片底（暖白，不用 #FFFFFF）
CARD_TINT = "#F8F4ED" # 卡片浅底
PREVIEW_TOP = "#F2FAF9" # 预览区渐变起点（极浅青）
PREVIEW_BOTTOM = "#FBF5EE" # 预览区渐变终点（极浅暖）
PREVIEW_LINE = "#DCEBE8" # 预览区里水印描边

TEAL = "#3EC9C0" # 点缀（青）
TEAL_DEEP = "#2AA79F"
TEAL_SOFT = "#E2F7F5"

# ── 来自本项目吉祥物本项目的角色色（见 assets/README.md）──
# 设定文档里这几个值是写死的：主色枫红、辅色暖橘/深褐、发色亚麻、瞳琥珀、红绳。
# 用法有讲究：**暖色只用在"正在发生"的地方**（进度条、运行中的卡片），
# 静态结构仍然保持深蓝，免得整个界面变成一片红。
MAPLE = "#B33A2B" # 主色 枫红
MAPLE_DEEP = "#8E2C20"
MAPLE_SOFT = "#F9E7E2"
ORANGE = "#E88B3C" # 暖橘（与枫红搭成渐变）
LINEN = "#D9C09A" # 亚麻（发色 / 狐耳外）
AMBER = "#D89A2B" # 琥珀（瞳）
CORD = "#C0392B" # 红绳
BROWN = "#4A3728" # 深褐（描边）
TAIL_SOFT = "#EFDCC6" # 尾巴水印

TEXT = "#22303F" # 主文字
TEXT_SUB = "#6B7C90" # 次文字
TEXT_FAINT = "#A7B4C2" # 极浅文字
BORDER = "#EDE5D9" # 分隔线（刻意压得很淡：硬线一多就有"尖锐感"）
SHADOW = "#EFE6DA" # 阴影
SHADOW_SOFT = "#F3EBE1" # 更淡的一层（卡片做两层投影用）

# --------------------------------------------------------------------------
# DPI —— "锯齿严重"的真凶就在这
# --------------------------------------------------------------------------
# Tk 只按 96 DPI 画界面。屏幕若是 150% 缩放，Windows 会把整张位图**拉伸 1.5 倍**，
# 文字发虚、圆角带锯，怎么调素材都没用（预锐化只是创可贴）。
#
# 正解：**声明 DPI 感知**让系统别再拉伸。但那样界面会缩到 2/3 ——
# 所以每个尺寸都要 ×SCALE，这就是 S() 存在的全部理由。
#
# ⚠️ 声明必须在**建任何窗口之前**，所以它放在模块导入时（见 claim_dpi_awareness）。

#: Tk 的基准假设 DPI
BASE_DPI = 96

#: DPI 缩放比（真实DPI/96）。claim_dpi_awareness() 填。
SCALE = 1.0

#: 用户手动选的**界面缩放**（1.0 = 100%）。跟 DPI 是两回事：
#: DPI 是"这台屏幕要求多大"，界面缩放是"我想要多大"。
#: 两者相乘才是最终的像素倍数 —— 这样在 150% 屏上选 100%，得到的是"物理尺寸正常"，
#: 而不是"被系统放大过的 150%"。
UI_ZOOM = 1.0

#: 界面缩放的档位。给几个整数档而不是滑块：档位少、好复现，
#: 而且界面每换一档都要整个重建，连续拖动会卡。
ZOOM_LEVELS: tuple[float, ...] = (0.8, 1.0, 1.25, 1.5)


def total_scale() -> float:
    """最终像素倍数 = DPI 缩放 × 用户选的界面缩放。"""
    return SCALE * UI_ZOOM


def set_zoom(zoom: float) -> None:
    """设定界面缩放（只管记下来，重建界面由调用方负责）。"""
    global UI_ZOOM
    UI_ZOOM = max(0.5, min(3.0, float(zoom)))


def S(px: float) -> int:
    """设计像素 → 实际像素。所有尺寸都要过这一道。

    ``0`` 原样返回 0 —— 布局里 ``padx=(0, 12)`` 这种"左 0 右 12"很常见，
    把 0 变成 1 会让整排控件歪掉。
    """
    if px == 0:
        return 0
    return max(1, round(px * total_scale()))


def _system_dpi() -> int:
    """问系统要真实 DPI。不依赖 Tk（Tk 建窗之前就要知道）。"""
    try:
        import ctypes
        return int(ctypes.windll.user32.GetDpiForSystem())
    except (ImportError, AttributeError, OSError):
        pass
    try:
        import ctypes
        hdc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88) # LOGPIXELSX
        ctypes.windll.user32.ReleaseDC(0, hdc)
        return int(dpi)
    except (ImportError, AttributeError, OSError):
        return BASE_DPI


def claim_dpi_awareness() -> float:
    """声明 DPI 感知并定下 SCALE。**模块导入时调用，早于 tk.Tk()**。"""
    global SCALE
    try:
        import ctypes
        # 2 = PROCESS_PER_MONITOR_DPI_AWARE（Win8.1+）
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (ImportError, AttributeError, OSError):
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware() # 老系统的退路
        except (ImportError, AttributeError, OSError):
            pass
    SCALE = max(1.0, round(_system_dpi() / BASE_DPI, 2))
    return SCALE


#: 字号相对设计像素的倍数。
#: 设计稿里"10 号字"是**设计像素**（mockup 就是按这个画的），而 Tk 的 ``scaling``
#: 意思不同 —— 它的 1.0 相当于"10 号字画成 10×96/72≈13.3 设备像素"。
#: 所以两者要换算：``tk scaling = DESIGN_FONT_SCALE × SCALE``。
#:
#: ⚠️ 1.5 是**实机拟合值**，不是拍脑袋：设计稿按 1.5 倍渲染，
#: "10 号字"在 150% 屏上是 22.5 物理像素；而 ``tk scaling = 1.5×1.5 = 2.25`` 时
#: Tk 把 10 号字画成 17 设备像素，在 150% 屏上正好折合 25 物理像素 —— 对得上。
DESIGN_FONT_SCALE: float = 1.5


def apply_scaling(root: tk.Misc) -> None:
    """把字号也跟上。**建好 root 之后调用。**

    ⚠️ 这里**不能**直接用系统 DPI 算（``_system_dpi()/72``）。
    Tk 的 ``scaling`` 是相对它自己那套 96DPI/72pt 基准的，所以"物理 DPI / 72"
    会让字号比设计稿**大一档** —— 100% 缩放下尤其明显：界面按 1.0 缩小了、
    字却还按 1.333 画，于是"图画得下、字溢出来"（下拉框文字叠在一起、
    卡片标题糊成一团，三档验收里实测踩到）。

    正确做法：字号跟**同一套缩放比**走 —— ``scaling = 1.5 × 总缩放``。
    """
    try:
        root.tk.call("tk", "scaling", DESIGN_FONT_SCALE * total_scale())
    except (tk.TclError, AttributeError):
        pass

OK = "#2E9E6B" # 已完成
OK_SOFT = "#E3F5EC"
WARN = "#C8871F"
DANGER = "#C4453F"
DANGER_SOFT = "#FBE9E8"
DISABLED = "#C9D2DC"

#: 字体候选
FONT_CANDIDATES = ("Microsoft YaHei UI", "Microsoft YaHei", "微软雅黑", "SimHei", "PingFang SC")


def pick_font(size: int = 10, bold: bool = False) -> tuple:
    try:
        available = set(tkfont.families())
    except tk.TclError:
        available = set()
    family = next((name for name in FONT_CANDIDATES if name in available), FONT_CANDIDATES[0])
    return (family, size, "bold") if bold else (family, size)


# --------------------------------------------------------------------------
# 基础绘制
# --------------------------------------------------------------------------


#: 每个圆角用多少段折线逼近。9 段 = 每段 10°，肉眼已看不出棱角。
CORNER_SEGMENTS = 9


def round_rect(canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float,
               radius: float = 8, **kwargs) -> int:
    """圆角矩形。

    走**真正的圆弧采样**，而不是 `create_polygon(smooth=True)` 那种样条近似 ——
    后者在角上会"发毛"、半径小时甚至鼓成怪形状，正是"看着劣质"的来源。
    坐标也统一取整，避免半像素导致的边缘发虚。
    """
    x1, y1, x2, y2 = round(x1), round(y1), round(x2), round(y2)
    radius = max(0.0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    if radius < 1:
        return canvas.create_rectangle(x1, y1, x2, y2, **kwargs)

    points: list[float] = []
    corners = (
        (x2 - radius, y1 + radius, -90.0), # 右上
        (x2 - radius, y2 - radius, 0.0), # 右下
        (x1 + radius, y2 - radius, 90.0), # 左下
        (x1 + radius, y1 + radius, 180.0), # 左上
    )
    for cx, cy, start in corners:
        for index in range(CORNER_SEGMENTS + 1):
            angle = math.radians(start + 90.0 * index / CORNER_SEGMENTS)
            points.append(cx + radius * math.cos(angle))
            points.append(cy + radius * math.sin(angle))
    return canvas.create_polygon(points, **kwargs)


def round_rect_radius(height: float) -> float:
    """胶囊形（进度条那种）的圆角半径。"""
    return max(1.0, height / 2)


def draw_h_gradient(canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float,
                    color_a: str, color_b: str, steps: int = 48) -> None:
    steps = max(2, steps)
    ra, ga, ba = _hex_to_rgb(color_a)
    rb, gb, bb = _hex_to_rgb(color_b)
    width = (x2 - x1) / steps
    for index in range(steps):
        ratio = index / (steps - 1)
        color = "#%02x%02x%02x" % (
            round(ra + (rb - ra) * ratio),
            round(ga + (gb - ga) * ratio),
            round(ba + (bb - ba) * ratio),
        )
        start = x1 + index * width
        canvas.create_rectangle(start, y1, start + width + 1, y2, fill=color, outline=color)


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def mix(color_a: str, color_b: str, ratio: float) -> str:
    """两色按比例混出中间色（做渐变条用）。"""
    ra, ga, ba = _hex_to_rgb(color_a)
    rb, gb, bb = _hex_to_rgb(color_b)
    ratio = max(0.0, min(1.0, ratio))
    return "#%02x%02x%02x" % (
        round(ra + (rb - ra) * ratio),
        round(ga + (gb - ga) * ratio),
        round(ba + (bb - ba) * ratio),
    )


def draw_v_gradient(canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float,
                    color_a: str, color_b: str, steps: int | None = None, tags=()) -> None:
    """纵向渐变。

    ``steps=None`` 时**一条一像素** —— 之前 40 条铺 400px 就是 10px 一道，
    肉眼能看到明显横条纹（"劣质感"的主要来源之一）。
    """
    x1, x2 = round(x1), round(x2)
    top, bottom = round(y1), round(y2)
    height = max(1, bottom - top)
    if steps is None:
        steps = height
    steps = max(2, steps)
    ra, ga, ba = _hex_to_rgb(color_a)
    rb, gb, bb = _hex_to_rgb(color_b)
    for index in range(steps):
        ratio = index / (steps - 1)
        color = "#%02x%02x%02x" % (
            round(ra + (rb - ra) * ratio),
            round(ga + (gb - ga) * ratio),
            round(ba + (bb - ba) * ratio),
        )
        start = top + round(height * index / steps)
        end = top + round(height * (index + 1) / steps)
        if end <= start:
            continue
        canvas.create_rectangle(x1, start, x2, end, fill=color, outline=color, tags=tags)


def draw_ribbon(canvas: tk.Canvas, cx: float, cy: float, height: float,
                color: str, *, sign: int = 1, width: int = 3,
                spread: float = 0.30, sway: float = 1.7, tags=()) -> None:
    """一条抽象的 S 形飘带。

    ⚠️ 这只是"双马尾"的**意象**，一条纯几何曲线 —— 不指向任何具体角色造型，
    也没有任何第三方素材。
    """
    points: list[float] = []
    for step in range(17):
        t = step / 16
        x = cx + sign * height * (spread * 0.5 + spread * t) \
            + sign * height * 0.07 * math.sin(t * math.pi * sway)
        y = cy - height * 0.5 + height * t
        points.extend((x, y))
    canvas.create_line(*points, fill=color, width=width, smooth=True,
                       capstyle="round", splinesteps=14, tags=tags)


def draw_note_cluster(canvas: tk.Canvas, cx: float, cy: float, size: float,
                      color: str = TEAL, gap: float = 1.5, tags=()) -> None:
    """两三个音符凑一组，做角落点缀。"""
    draw_music_note(canvas, cx, cy, size, color, tags=tags)
    draw_music_note(canvas, cx + size * gap, cy - size * 0.34, size * 0.78, color,
                    tags=tags)


def draw_music_note(canvas: tk.Canvas, cx: float, cy: float, size: float,
                    color: str = TEAL, tags=()) -> None:
    """画一个音符（符头 + 符干 + 符尾）。纯几何图形，不涉及任何商标素材。"""
    head_r = size * 0.26
    canvas.create_oval(cx - head_r, cy + size * 0.30 - head_r,
                       cx + head_r, cy + size * 0.30 + head_r,
                       fill=color, outline="", tags=tags)
    canvas.create_line(cx + head_r * 0.85, cy + size * 0.30,
                       cx + head_r * 0.85, cy - size * 0.42,
                       fill=color, width=max(1, int(size * 0.10)),
                       capstyle="round", tags=tags)
    canvas.create_line(cx + head_r * 0.85, cy - size * 0.42,
                       cx + head_r * 0.85 + size * 0.34, cy - size * 0.26,
                       fill=color, width=max(1, int(size * 0.10)),
                       capstyle="round", tags=tags)


def draw_emblem(canvas: tk.Canvas, cx: float, cy: float, size: float) -> None:
    """KomaFlow 徽标：抽象双飘带 + 音符。

    ⚠️ 完全原创的几何图形。**不要**换成任何角色形象、也不要加
    `MIKU` / `初音` / `VOCALOID` 字样。
    """
    # 底座圆环
    canvas.create_oval(cx - size, cy - size, cx + size, cy + size,
                       fill=NAVY, outline=TEAL, width=2)
    # 两条抽象飘带（S 形），点在青与米色上
    for sign, color in ((-1, TEAL), (1, BEIGE)):
        points = []
        for step in range(13):
            t = step / 12
            x = cx + sign * size * (0.16 + 0.42 * t) + sign * size * 0.16 * math.sin(t * 3.4)
            y = cy - size * 0.74 + size * 1.48 * t
            points.extend((x, y))
        canvas.create_line(*points, fill=color, width=max(2, int(size * 0.13)),
                           smooth=True, capstyle="round", splinesteps=12)
    draw_music_note(canvas, cx, cy - size * 0.02, size * 0.62, color="#FFFFFF")


# --------------------------------------------------------------------------
# 控件
# --------------------------------------------------------------------------


#: 量文字用的字体对象缓存，键是 `(字号, 粗体)`。
#:
#: ⚠️ **必须缓存。** `tkfont.Font(...)` 每建一次都要跟 Tk 通信、开销不小，
#: 而 `tip.wrap_text` 是**逐字符**调 :func:measure_text 的 ——
#: "每个字新建一个 Font" 会直接把界面卡死。
#: 实测：提示窗文案一变长（"选哪台 Blender"里带两条完整 Windows 路径），
#: 程序就 `Responding=False`、CPU 连烧几十秒、窗口频繁闪动。
#: 缓存按 **Tk 解释器** 分开存：`{解释器标识: {(字号, 粗体): Font}}`。
#:
#: ⚠️ 不能只按 (字号, 粗体) 存 —— `tkfont.Font` 是**绑在某个 Tk root 上**的。
#: 测试里每个用例建一个 root、用完销毁；下一个用例的 root 换了之后，
#: 复用旧 Font 就会炸 `can't invoke "font" command:
#: application has been destroyed`（实测一次跑挂 33 个用例）。
#: 这也解释了为什么单元测试比自检脚本更早发现它。
_FONT_CACHE: dict[object, dict[tuple[int, bool], "tkfont.Font"]] = {}


def _interp_key(canvas: tk.Misc | None) -> object:
    """取"当前是哪个 Tk 解释器"当缓存键。拿不到就退回默认 root 的 id。"""
    root = None
    if canvas is not None:
        try:
            root = canvas.winfo_toplevel()
        except Exception: # noqa: BLE001 - 控件已销毁
            root = None
    if root is None:
        root = getattr(tk, "_default_root", None)
    if root is None:
        return "<no-root>"
    try:
        return root.tk.interpaddr()
    except Exception: # noqa: BLE001
        return id(root)


def measure_text(canvas: tk.Misc, text: str, size: int = 9,
                 bold: bool = False) -> int:
    """量一段文字有多少像素宽。

    为什么需要：Canvas 里没有"左对齐排一串文字"的布局器。
    摘要条那种"几段字横着排"的地方，只能自己一段段算宽度、一段段往前挪。

    ⚠️ 字体对象**按 (字号, 粗体) 缓存**，不要每次新建（见 `_FONT_CACHE`）。
       调用方传 `canvas=None` 也照常工作：第一次用默认根窗口建好，
       之后一直复用缓存里那个。
    """
    key = (int(size), bool(bold))
    per_root = _FONT_CACHE.setdefault(_interp_key(canvas), {})
    font = per_root.get(key)
    if font is None:
        font = tkfont.Font(root=canvas, font=pick_font(size, bold))
        per_root[key] = font
    return font.measure(text)


class FlatButton(tk.Canvas):
    """扁平按钮。深蓝实心 / 米色描边两种风格，悬停有反馈。"""

    def __init__(self, master, text: str, command=None, *, width: int | None = None,
                 height: int | None = None, bg: str = CREAM, fill: str = NAVY,
                 hover: str = NAVY_SOFT, fg: str = "#FFFFFF",
                 outline: str = "", font: tuple | None = None,
                 radius: int | None = None) -> None:
        # ⚠️ 默认尺寸过 ``S()``：这些默认值在类定义时就固定了，
        # 而 ``SCALE`` 要等建窗之后才定 —— 写死就永远是 1x。
        width = S(112) if width is None else width
        height = S(34) if height is None else height
        radius = S(6) if radius is None else radius
        super().__init__(master, width=width, height=height, bg=bg,
                         highlightthickness=0, bd=0, takefocus=1)
        self._text, self._command = text, command
        # ⚠️ 绝不能用 self._w / self._h：那是 tkinter 内部存控件路径名的属性，
        # 覆盖掉之后所有 Tk 调用都会报 invalid command name（踩过）。
        self._box_w, self._box_h, self._radius_px = width, height, radius
        self._fill, self._hover, self._fg, self._outline = fill, hover, fg, outline
        self._font = font or pick_font(10, bold=True)
        self._enabled, self._hovered = True, False
        self._draw()
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)

    def _draw(self) -> None:
        self.delete("all")
        if not self._enabled:
            fill, fg, outline = "#EFE9E1", DISABLED, "#E4DCD2"
        elif self._hovered:
            fill, fg, outline = self._hover, self._fg, self._outline or self._hover
        else:
            fill, fg, outline = self._fill, self._fg, self._outline or self._fill
        round_rect(self, 1, 1, self._box_w - 1, self._box_h - 1, self._radius_px,
                   fill=fill, outline=outline, width=1)
        self.create_text(self._box_w / 2, self._box_h / 2 + 1, text=self._text,
                         fill=fg, font=self._font)

    def _on_enter(self, _e=None) -> None:
        if self._enabled:
            self._hovered = True
            self.configure(cursor="hand2")
            self._draw()

    def _on_leave(self, _e=None) -> None:
        self._hovered = False
        self.configure(cursor="")
        self._draw()

    def _on_click(self, _e=None) -> None:
        if self._enabled and self._command:
            self._command()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self._hovered = False
        self._draw()

    def set_text(self, text: str) -> None:
        self._text = text
        self._draw()


class Pill(tk.Canvas):
    """状态小标签。"""

    def __init__(self, master, text: str = "", *, bg: str = CARD,
                 fill: str = NAVY_TINT, fg: str = NAVY, width: int | None = None,
                 height: int | None = None, font: tuple | None = None) -> None:
        width = S(74) if width is None else width
        height = S(22) if height is None else height
        super().__init__(master, width=width, height=height, bg=bg,
                         highlightthickness=0, bd=0)
        # 同样避开 self._w / self._h（tkinter 内部属性）
        self._box_w, self._box_h = width, height
        self._font = font or pick_font(9)
        self._text, self._fill, self._fg = text, fill, fg
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        round_rect(self, 0, 0, self._box_w, self._box_h, self._box_h / 2,
                   fill=self._fill, outline="")
        self.create_text(self._box_w / 2, self._box_h / 2 + 1, text=self._text,
                         fill=self._fg, font=self._font)

    def set(self, text: str, fill: str, fg: str) -> None:
        self._text, self._fill, self._fg = text, fill, fg
        self._draw()
