"""自绘控件：素材投放卡、步骤卡、细进度条。

一张卡片**两种用途**（这也是"更方便"的关键）：
* 配置时 = **素材投放区**（显示"拖文件到这里"、已选文件名）
* 执行时 = **步骤状态卡**（待执行 / 运行中 / 已完成 / 失败）

两者形状一致，切换时视觉连续，窗口不用跳来跳去。

本文件里画东西的那些方法有个共同点：**坐标一律要过 ``T.S()``**。
``tk.Canvas`` 不参与布局缩放，控件被拉大了，里面画的图形不会跟着变大。
只在 ``width=`` 上包 ``T.S()``、却漏掉 ``create_text`` 的坐标，出来就是
"框大了，字还挤在左上角"——比不缩放还难看。
"""

from __future__ import annotations

import os
import tkinter as tk

from . import assets as ui_assets
from . import theme as T

#: 步骤/投放卡状态
EMPTY = "empty"
FILLED = "filled"
PENDING = "pending"
RUNNING = "running"
DONE = "done"
FAILED = "failed"


def shorten_filename(path: str, limit: int = 26) -> str:
    """文件名太长就中间省略，但**保留扩展名** —— 扩名是判断素材类型的依据。"""
    name = os.path.basename(path) if path else ""
    if len(name) <= limit:
        return name
    stem, ext = os.path.splitext(name)
    keep = max(4, limit - len(ext) - 1)
    return f"{stem[:keep]}…{ext}"


#: 助手卡气泡里最多放几个汉字。
#: 实测：9 号字下 16 个汉字约 288~306 设备像素，气泡能放下约 330（150% 缩放）。
#: 第 17 个字就折行，气泡一折行会把整张助手卡顶高，跟下面的面板错位。
BUBBLE_CHARS = 16


def _one_line(text: str, limit: int = BUBBLE_CHARS) -> str:
    """把一句话裁到能放进助手卡气泡的长度，见 :data:`BUBBLE_CHARS`。"""
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _fit_text(widget: tk.Misc, text: str, max_px: int, size: int = 9) -> str:
    """把一行字裁到 ``max_px`` 像素以内（超出就加「…」）。

    Tk 的 Canvas 文字**不会自动换行**，也不会报错 —— 太长就直接画到卡片外面，
    看着像界面坏了。分批进度那行现在带"秒/帧 + 还剩多久"，比原来长得多，
    所以按**实际测量宽度**裁，而不是按字符数猜（中英混排宽度差很多）。
    """
    if not text or max_px <= 0:
        return text
    if T.measure_text(widget, text, size) <= max_px:
        return text
    # 二分找最长能放下的前缀
    low, high = 0, len(text)
    while low < high:
        mid = (low + high + 1) // 2
        if T.measure_text(widget, text[:mid] + "…", size) <= max_px:
            low = mid
        else:
            high = mid - 1
    return text[:low] + "…" if low else "…"


class Card(tk.Canvas):
    """素材投放卡 / 步骤卡。

    可选 ``slots``：给这张卡分成**两个独立槽位**（每格一个文件名）。
    「动作」那张卡用它 —— MMD 的**动作**（骨骼动画）和**表情**（morph 动画）通常是
    两个分开的 .vmd 文件，一个槽位放不下。
    """

    def __init__(self, master, index: int = 1, *, bg: str = T.CREAM,
                 command=None, height: int | None = None,
                 slots: tuple[str, ...] = (),
                 slot_browse=None, merge_label: str = "",
                 clear_command=None, remove_command=None) -> None:
        # 默认尺寸也要过 T.S()。这个类在侧栏和主区都是不带尺寸直接建的，
        # 漏掉的话它在 150% 屏上只有旁边那些控件三分之二大。
        super().__init__(master, bg=bg, highlightthickness=0, bd=0,
                         width=T.S(190), height=height or T.S(146))
        self.index = index
        self.command = command
        #: 点右上角「×」时调 —— 清空这张卡的素材（用户要求：「应该有删除」）
        self.clear_command = clear_command
        #: 点列表里**某一行的 ×** 时调，参数是那一行的索引。
        #:
        #: 为什么需要单独一个：动作卡现在能挂**任意多个** vmd，
        #: "整卡清空"不够用 —— 用户可能只想删掉第三个文件。
        self.remove_command = remove_command
        self._state = EMPTY
        self._title = ""
        self._subtitle = ""
        self._filename = ""
        self._badge = ""
        self._hover = False

        #: 每个槽位对应一个文件。**槽位数是可变的**（见 ``show_slots``），
        #: 界面上合并成一个框、用户看不到"格"这个概念。
        self._slots = tuple(slots)
        self._slot_browse = slot_browse
        self._slot_files: list[str] = [""] * len(self._slots)
        self._hover_slot: int | None = None
        #: 当前悬停在第几行的「×」上（多文件列表用）
        self._hover_row: int | None = None
        #: 每行「×」的命中矩形（重画时算、点击时用）
        self._row_rects: list[tuple[float, float, float, float]] = []
        #: 两个槽位**都填了**时合并成一行显示，左边用这个标签。
        #: 空串＝不合并（永远保持两行）。
        self._merge_label = merge_label
        self._merged = False

        self.bind("<Configure>", lambda _e: self.redraw())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        if self._slots:
            self.bind("<Motion>", self._on_motion)

    # ------------------------------------------------------- 槽位（两格模式）
    def slot_rects(self, width: int | None = None,
                   height: int | None = None) -> list[tuple[int, int, int, int]]:
        """槽位矩形，跟 :meth:`_draw_slots` 用的是同一套算法。

        抽出来是为了**鼠标点在哪、拖到哪**都能用同一份几何 ——
        分别算两遍迟早对不上。

        ⚠️ 界面上**只有一个框**（不显示分类标签），但内部仍然是两个槽位
        （动作 / 表情在工程文件里是两个字段，存的时候要分开）。
        所以这里把两格算成**紧挨着**的两条 —— 画的时候用第一条的
        ``x0/y0`` 和最后一条的 ``x1/y1`` 拼成一个大框，正好盖住两条。
        """
        if not self._slots:
            return []
        w = width if width is not None else (self.winfo_width() or T.S(190))
        h = height if height is not None else (self.winfo_height() or T.S(146))
        pad_x = T.S(12)
        top = T.S(46) # 让开标题
        bottom = h - T.S(16) # 让开底部说明
        gap = T.S(4)
        count = max(1, len(self._slots))
        row_h = max(T.S(16), (bottom - top - gap * (count - 1)) // count)
        rects = []
        for index in range(count):
            y0 = top + index * (row_h + gap)
            rects.append((pad_x, y0, w - pad_x, y0 + row_h))
        return rects

    def slot_at(self, y: int) -> int | None:
        """这个 y 坐标落在第几个槽位里（拖放 / 点击用）。

        ``x`` 参数不需要 —— 合并成一行时仍然是"上下两半"对应两个槽位，
        因为合并行的矩形是两格矩形并起来的，``y`` 落在上半就是第 0 格。
        """
        for index, (_x0, y0, _x1, y1) in enumerate(self.slot_rects()):
            if y0 <= y <= y1:
                return index
        return None

    def slot_at_point(self, y: int) -> int | None:
        """这个 ``y`` 落在哪一条里。

        ⚠️ 界面上只有一个框，所以按 ``y`` 分条只对"点在框内哪一行"有意义；
        真正的归类交给内容判断（``_classify_vmd``），不靠落点。
        保留这个方法名是为了跟调用方一致。
        """
        return self.slot_at(y)

    # ----------------------------------------------------------- 删除按钮
    def clear_rect(self, width: int | None = None,
                   height: int | None = None) -> tuple[int, int, int, int] | None:
        """右上角「×」的矩形。没放东西时返回 ``None``（那时没什么可删）。

        用户要求：「应该有删除」—— 放了文件之后必须能撤掉，
        否则选错一个就只能重启程序。
        """
        if not self._has_content():
            return None
        w = width if width is not None else (self.winfo_width() or T.S(190))
        size = T.S(20)
        margin = T.S(6)
        return (w - margin - size, margin, w - margin, margin + size)

    def clear_at(self, x: int, y: int) -> bool:
        """这个点是不是落在「×」上。"""
        rect = self.clear_rect()
        if rect is None:
            return False
        x0, y0, x1, y1 = rect
        return x0 <= x <= x1 and y0 <= y <= y1

    def _has_content(self) -> bool:
        """这张卡上有没有已选的素材。"""
        if self._slots:
            return any(f.strip() for f in self._slot_files)
        return bool(self._filename.strip())

    def _hit(self, x: int, y: int) -> str:
        """这个点落在卡片的哪个部位：``clear`` / ``slot:<n>`` / ``body``。

        抽出来是为了**点击**和**悬停高亮**用同一套判断 ——
        分别写两遍迟早对不上（跟 ``slot_rects`` 同一个理由）。
        """
        if self.clear_at(x, y):
            return "clear"
        if self._slots:
            index = self.slot_at_point(y)
            if index is not None:
                return f"slot:{index}"
        return "body"

    def show_slots(self, title: str, files: list[str],
                   labels: tuple[str, ...] | None = None) -> None:
        """槽位刷新：``files`` 是**这一卡里所有文件**（任意多个，按顺序）。

        ⚠️ **界面上不区分"动作 / 表情"**（``labels`` 参数保留只是为了兼容调用方）。
        用户要求"无序分类"：

        > 表情和动作可以直接导入不用现在一样分两个吧，毕竟有些作者他不写那个
        > 是动作哪个是表情

        所以框里**只列文件名**，谁承担哪个角色由 ``import_vmd`` 自己处理。
        后来用户又要求数量不设限：

        > 这个动作和表情，可以添加多个而不是局限于2个

        ⚠️ 这里槽位数**跟着文件数走**（不再固定 2 个）。内部字段仍分
           ``motions`` / ``expressions`` 两个列表（工程文件要分开存），
           但界面上就是一个有序清单。
        """
        self._title = title
        if labels:
            self._slots = tuple(labels)
        # 文件数可能超过/少于原有槽位数 —— 两边都对齐，谁短就补空
        self._slot_files = list(files)
        need = max(len(self._slot_files), len(self._slots))
        while len(self._slot_files) < need:
            self._slot_files.append("")
        self._slots = tuple([""] * need) if need > len(self._slots) \
            else self._slots
        self._state = FILLED if any(f.strip() for f in self._slot_files) else EMPTY
        self._hover_row = None
        self.redraw()

    # ------------------------------------------------------------- 对外接口
    def show_drop(self, title: str, subtitle: str, filename: str = "") -> None:
        self._title, self._subtitle = title, subtitle
        self._filename = filename
        self._state = FILLED if filename else EMPTY
        self.redraw()

    def show_step(self, title: str, state: str, badge: str = "") -> None:
        self._title, self._state, self._badge = title, state, badge
        self._subtitle, self._filename = "", ""
        self.redraw()

    @property
    def state(self) -> str:
        return self._state

    # --------------------------------------------------------------- 交互
    def _on_enter(self, _e=None) -> None:
        self._hover = True
        self.configure(cursor="hand2")
        self.redraw()

    def _on_leave(self, _e=None) -> None:
        self._hover = False
        self._hover_slot = None
        self.configure(cursor="")
        self.redraw()

    def _on_motion(self, event) -> None:
        """鼠标移动：更新「哪一格 / 哪一行的 ×」高亮，让"能点"看得出来。

        「×」区域单独给一次高亮反馈（不然用户不知道那里能点）。
        多文件列表时还要分辨"悬停在哪一行的 × 上"。
        """
        x = int(getattr(event, "x", 0))
        y = int(event.y)
        if self.clear_at(x, y):
            if self._hover_slot != -1:
                self._hover_slot = -1 # -1 表示"悬停在删除按钮上"
                self.configure(cursor="hand2")
                self.redraw()
            return
        if not self._slots:
            return
        row = self.row_at(x, y)
        if row != self._hover_row:
            self._hover_row = row
            self.configure(cursor="hand2" if row is not None else "hand2")
            self.redraw()
        if row is not None:
            return # 悬停在某一行的 × 上时，不再管"整格"高亮
        index = self.slot_at_point(y)
        if index != self._hover_slot:
            self._hover_slot = index
            self.redraw()

    def row_at(self, x: int, y: int) -> int | None:
        """这个点落在第几个文件的「×」上？没有就 ``None``。

        ⚠️ 只在**多文件列表**里有意义；单格卡没有行。
        """
        for index, (x0, y0, x1, y1) in enumerate(
                getattr(self, "_row_rects", [])):
            if x0 <= x <= x1 and y0 <= y <= y1:
                return index
        return None

    def _on_click(self, event=None) -> None:
        """点击：先看是不是「×」，再看落在哪一格。

        顺序不能反 —— 「×」画在最上层，点到它就该**删除**而不是选文件。
        """
        x = int(getattr(event, "x", 0)) if event is not None else 0
        y = int(getattr(event, "y", 0)) if event is not None else 0

        if event is not None and self.clear_at(x, y):
            if self.clear_command:
                self.clear_command()
            return

        # 多文件列表：点到某一行的「×」就删掉**那一个**，不是整卡清空
        if event is not None and self._slots:
            row = self.row_at(x, y)
            if row is not None:
                if self.remove_command:
                    self.remove_command(row)
                return

        if not self.command:
            return
        if self._slots and event is not None:
            # ⚠️ **不传槽位索引**：界面上只有一个框，用户点哪儿都是"往这张卡里放"，
            # 具体归到哪个字段由工具自己挑空位（``_next_motion_slot``）。
            # 传索引会让回调签名变复杂，而且用户根本不关心是第几格。
            self.command()
            return
        self.command()

    # --------------------------------------------------------------- 绘制
    def redraw(self) -> None:
        """重画整张卡（坐标都要过 T.S()，见模块说明）。"""
        self.delete("all")
        width = self.winfo_width() or T.S(190)
        height = self.winfo_height() or T.S(168)
        if width < T.S(20) or height < T.S(20):
            return

        palette = {
            EMPTY: ("#FFFFFF" if not self._hover else T.BEIGE_SOFT,
                    T.BEIGE_LINE, T.TEXT),
            FILLED: (T.BEIGE_SOFT if not self._hover else "#F2E7D6",
                     T.NAVY, T.NAVY),
            PENDING: (T.CARD, T.BORDER, T.TEXT_FAINT),
            # 「正在跑」用角色的枫红 —— 暖色只出现在"正在发生"的地方
            RUNNING: (T.MAPLE_SOFT, T.MAPLE, T.MAPLE_DEEP),
            DONE: (T.OK_SOFT, T.OK, T.OK),
            FAILED: (T.DANGER_SOFT, T.DANGER, T.DANGER),
        }
        fill, border, accent = palette.get(self._state, palette[PENDING])
        # ⚠️ **已填的卡片也要有悬停反馈**。原来只有 EMPTY 那档变底色，
        # 放了文件之后鼠标划上去毫无反应 —— 用户会以为"坏了 / 点不动"
        # （用户报过"没有高光"）。这里统一再加深一点点。
        if self._hover and self._state not in (EMPTY, RUNNING, DONE, FAILED):
            fill = "#F2E7D6"

        # 卡片本体。⚠️ 不做"内缩 + 外投影"那种做法：tk 的 Canvas 会裁掉画布外的
        # 内容，投影只能画在卡片里面，而卡片里所有内容都是按 height 贴底排的，
        # 一内缩全体错位。宁可要一条干净的顶部色条，也不要错位的假阴影。
        # 半径从 10 收到 7：Tk 不做抗锯齿，圆角越大台阶越长越显眼。
        # （真正的解法是九宫格预渲染，但每套"填充色+描边色"都要单独出图，先不做。）
        T.round_rect(self, 1, 1, width - 1, height - 1, T.S(7),
                     fill=fill, outline=border,
                     width=1) # 描边统一 1px：2px 深色描边是"尖锐感"的主要来源，
                                   # 状态靠**底色**区分就够了，不用靠加粗边框喊

        # 顶部一条细色条：卡片自己的"层次"，比纯色块耐看
        strip = accent if self._state != EMPTY else T.BEIGE_LINE
        T.round_rect(self, T.S(14), T.S(3), width - T.S(16), T.S(6), T.S(1.5),
                     fill=strip, outline="")

        # 空卡：内层虚线框，明确"这里是能扔东西的"
        if self._state == EMPTY:
            self.create_rectangle(T.S(11), T.S(11), width - T.S(11),
                                  height - T.S(11),
                                  outline=T.BORDER, dash=(T.S(4), T.S(4)))

        # 序号徽标：用**预渲染的抗锯齿小圆**。
        # Tk 的 create_oval 是硬边，放大一圈台阶，很显廉价；PNG 里已经带着抗锯齿。
        badge_r = T.S(12)
        badge_x, badge_y = T.S(14), T.S(14)
        if self._state == EMPTY:
            badge_key = "beige"
        elif self._state == RUNNING:
            badge_key = "maple"
        elif self._state == DONE:
            badge_key = "ok"
        elif self._state == FAILED:
            badge_key = "danger"
        elif self._state == PENDING:
            badge_key = "grey"
        else:
            badge_key = "navy"
        if ui_assets.blit(self, f"badge_{badge_key}.png",
                          badge_x + badge_r, badge_y + badge_r) is None:
            self.create_oval(badge_x, badge_y, badge_x + badge_r * 2,
                             badge_y + badge_r * 2,
                             fill=T.BEIGE_LINE if self._state == EMPTY else T.NAVY,
                             outline="")
        self.create_text(badge_x + badge_r, badge_y + badge_r + T.S(1),
                         text=str(self.index),
                         fill="#FFFFFF" if badge_key != "grey" else T.TEXT_SUB,
                         font=T.pick_font(9, bold=True))

        # 内容整体垂直居中（卡片会被拉高成"仪表盘瓷砖"，居中比贴顶好看）
        center_y = height / 2
        title_font = T.pick_font(12 if width >= T.S(150) else 11, bold=True)

        # ── 两格模式（动作 / 表情）──
        # 标题贴顶、两格居中、底部留一行，布局跟单格明显不同，所以单独走。
        if self._slots:
            self.create_text(width / 2, T.S(29), text=self._title,
                             fill=accent, font=title_font,
                             width=int(max(T.S(40), width - T.S(24))))
            self._draw_slots(width, height)
            return

        # 单格卡：有文件名时也在右上角给个「×」——删掉重选才不会卡住
        self._draw_clear_button(width, height)

        self.create_text(width / 2, center_y - T.S(18), text=self._title,
                         fill=accent, font=title_font,
                         width=int(max(T.S(40), width - T.S(24))))

        # 副标题 / 文件名
        if self._state == FILLED and self._filename:
            text = shorten_filename(self._filename, 24)
            color = T.TEXT
        elif self._state == EMPTY:
            # 空态文案。原来写"拖文件到这里"—— 卡片副标题已经写了支持哪些后缀，
            # 这句只是再说一遍"这里是空位"。改成说**能干什么**。
            text, color = "拖文件进来，或点这里选", T.TEXT_SUB
        elif self._state in (RUNNING, DONE, FAILED) and self._badge:
            text, color = self._badge, accent
        else:
            text, color = self._subtitle or "", T.TEXT_FAINT
        if text:
            self.create_text(width / 2, center_y + T.S(20), text=text, fill=color,
                             font=T.pick_font(9),
                             width=int(max(T.S(40), width - T.S(22))))

        # 底部：类型说明 或 状态
        footer = {
            EMPTY: self._subtitle,
            FILLED: self._subtitle,
            PENDING: "待执行",
            RUNNING: self._badge or "运行中",
            DONE: self._badge or "已完成",
            FAILED: self._badge or "失败",
        }.get(self._state, "")
        if footer and footer != text:
            self.create_text(width / 2, height - T.S(22), text=footer,
                             fill=T.TEXT_FAINT if self._state in (EMPTY, FILLED)
                             else accent,
                             font=T.pick_font(9))

        # 已完成打勾：同样用预渲染的抗锯齿图，不用 create_oval + create_line
        if self._state == DONE:
            if ui_assets.blit(self, "badge_check.png", width - T.S(21),
                              height - T.S(21)) is None:
                cx, cy, r = width - T.S(21), height - T.S(21), T.S(10)
                self.create_oval(cx - r, cy - r, cx + r, cy + r, fill=T.OK, outline="")
                self.create_line(cx - T.S(4.5), cy, cx - T.S(1.5), cy + T.S(3.5),
                                 cx + T.S(5), cy - T.S(4),
                                 fill="#FFFFFF", width=max(1, T.S(2)),
                                 capstyle="round", joinstyle="round")

    # ------------------------------------------------------------ 两格绘制
    def _draw_slots(self, width: int, height: int) -> None:
        """画「动作」那张卡的槽位 —— 现在是**任意多个文件的列表**。

        用户先后提过两条：

        > 表情和动作可以直接导入不用现在一样分两个吧，毕竟有些作者他不写那个
        > 是动作哪个是表情

        > 这个动作和表情，可以添加多个而不是局限于2个

        所以界面上：

        * **不分"动作 / 表情"**，拖进来什么、列出什么（归到哪个字段不影响导入）
        * **不限数量**：文件全列出来，超过 4 个就写"还有 N 个"
        * **每行右边一个小 ×**：可以单独删掉某一个，不用整卡清空
        """
        rects = self.slot_rects(width, height)
        if not rects:
            return
        # 一个框盖住所有槽位
        x0 = rects[0][0]
        y0 = rects[0][1]
        x1 = rects[0][2]
        y1 = rects[-1][3]

        names = [f.strip() for f in self._slot_files if f.strip()]
        hot = self._hover_slot is not None and self._hover_slot >= 0
        T.round_rect(self, x0, y0, x1, y1, T.S(6),
                     fill=(T.BEIGE_SOFT if hot else
                           ("#FFFFFF" if names else T.CARD)),
                     outline=(T.NAVY if hot else
                              (T.BEIGE_LINE if names else T.BORDER)),
                     width=1)

        avail = int((x1 - x0) - T.S(24))
        if not names:
            self.create_text((x0 + x1) / 2, (y0 + y1) / 2,
                             text="点这里选，或拖进来",
                             fill=T.TEXT_FAINT, font=T.pick_font(8))
            self._row_rects = []
        else:
            # 文件按行列出。⚠️ 行高按**实际字高**算（字体约 20px），
            # 写死 13px 会让相邻两行 bbox 差 1px 重叠（测试量出来的，肉眼看不见）。
            #
            # ⚠️ **能列几行要按卡片的实际高度算**。写死 4 行的话，放 5 个文件
            # 就直接溢出卡片、压到标题上（实测截图就是糊成一片）。
            # 这里从框的高度反推，放不下就少列一行、用"还有 N 个"补齐。
            line_h = T.S(22)
            room = int((y1 - y0) - T.S(8))
            fit = max(1, room // line_h)
            if len(names) > fit:
                fit = max(1, fit - 1) # 留一行给"还有 N 个"
            shown = names[:fit]
            top = (y0 + y1) / 2 - line_h * (len(shown) - 1) / 2
            if len(names) > fit:
                top -= line_h / 2

            self._row_rects = []
            for row, name in enumerate(shown):
                row_y = top + line_h * row
                short = shorten_filename(name, 20)
                # 给右边的 × 留出 T.S(20)，否则长文件名会跑到 × 底下
                while short and T.measure_text(self, short, 8) > avail - T.S(20):
                    shorter = shorten_filename(name, max(4, len(short) - 1))
                    if shorter == short:
                        break
                    short = shorter
                self.create_text(x0 + T.S(11), row_y,
                                 text=short, anchor="w",
                                 fill=T.TEXT, font=T.pick_font(8))
                # 每行一个小 ×（单独删掉这一个）
                cross_x = x1 - T.S(12)
                arm = T.S(3)
                cross_hot = self._hover_row == row
                self.create_line(cross_x - arm, row_y - arm,
                                 cross_x + arm, row_y + arm,
                                 fill=(T.DANGER if cross_hot else T.TEXT_FAINT),
                                 width=max(1, T.S(2)), capstyle="round")
                self.create_line(cross_x + arm, row_y - arm,
                                 cross_x - arm, row_y + arm,
                                 fill=(T.DANGER if cross_hot else T.TEXT_FAINT),
                                 width=max(1, T.S(2)), capstyle="round")
                self._row_rects.append((cross_x - T.S(8), row_y - line_h / 2,
                                        cross_x + T.S(8), row_y + line_h / 2))

            if len(names) > fit:
                self.create_text(x0 + T.S(11), top + line_h * len(shown),
                                 text=f"还有 {len(names) - fit} 个",
                                 anchor="w", fill=T.TEXT_FAINT,
                                 font=T.pick_font(8))

        self._draw_clear_button(width, height)
        self._draw_slot_corner(width, height)

    def _draw_clear_button(self, width: int, height: int) -> None:
        """右上角画「×」。悬停时加深 —— 让「这里能点」看得出来。"""
        rect = self.clear_rect(width, height)
        if rect is None:
            return
        x0, y0, x1, y1 = rect
        hot = self._hover_slot == -1
        T.round_rect(self, x0, y0, x1, y1, T.S(5),
                     fill=(T.DANGER_SOFT if hot else T.BEIGE_SOFT),
                     outline=(T.DANGER if hot else T.BEIGE_LINE), width=1)
        mid_x, mid_y = (x0 + x1) / 2, (y0 + y1) / 2
        arm = T.S(4)
        line_color = T.DANGER if hot else T.TEXT_SUB
        self.create_line(mid_x - arm, mid_y - arm, mid_x + arm, mid_y + arm,
                         fill=line_color, width=max(1, T.S(2)), capstyle="round")
        self.create_line(mid_x + arm, mid_y - arm, mid_x - arm, mid_y + arm,
                         fill=line_color, width=max(1, T.S(2)), capstyle="round")

    def _draw_slot_corner(self, width: int, height: int) -> None:
        """角落点缀：全部用预渲染的抗锯齿 PNG（Tk 画曲线没有抗锯齿）。

        图标取自角色设定：跑起来是她的**认真表情**，完成是**银铃**（设定里的节拍器）。
        ⚠️ 这里原本放的是"琥珀竖瞳" —— 设定上确实是她的标志，但放大成图标像在瞪人，
           用户反馈"太吓人"，所以换成 Q 版表情。
        """
        corner = {
            RUNNING: "face_small_work.png", # 小号！大号 76px 会撑出卡片
            DONE: "deco_bell.png",
            EMPTY: "deco_note_card.png",
        }.get(self._state)
        if corner:
            ui_assets.blit(self, corner, T.S(28), height - T.S(30))
        elif self._state == EMPTY:
            T.draw_music_note(self, T.S(20), height - T.S(24), T.S(13),
                              color=T.BEIGE_LINE)


class ThinProgress(tk.Canvas):
    """细进度条。

    填充是**枫红 → 暖橘的横向渐变** —— 取自角色的主色与辅色。
    进度条是界面上最"动"的元素，用她的颜色最贴切；
    静态结构仍然保持深蓝，免得整个界面变成一片红。
    """

    def __init__(self, master, *, bg: str = T.CREAM, width: int | None = None,
                 height: int | None = None, track: str = "#E9E2D6",
                 fill_a: str = T.MAPLE, fill_b: str = T.ORANGE) -> None:
        # ⚠️ 一定要给 width：tk.Canvas 默认 378，会把所在栏撑爆
        super().__init__(master, bg=bg, highlightthickness=0, bd=0,
                         width=width or T.S(200), height=height or T.S(10))
        self._track = track
        self._fill_a, self._fill_b = fill_a, fill_b
        self._value = 0.0
        self.bind("<Configure>", lambda _e: self.redraw())

    def set(self, value: float) -> None:
        self._value = max(0.0, min(1.0, float(value)))
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        width = self.winfo_width() or T.S(200)
        height = self.winfo_height() or T.S(10)
        radius = height / 2
        T.round_rect(self, 0, 0, width, height, radius, fill=self._track, outline="")
        if self._value <= 0:
            return

        end = max(height, width * self._value)
        end_int = int(end)
        # 横向渐变：2px 一条竖线，逐条插值。条数不多，开销可以忽略。
        step = max(1, T.S(2))
        for x in range(0, end_int, step):
            ratio = x / max(1.0, end - 1)
            color = T.mix(self._fill_a, self._fill_b, ratio)
            self.create_rectangle(x, 0, min(end_int, x + step), height,
                                  fill=color, outline=color)
        # 两端补半圆，不然方头会戳出圆角轨道
        self.create_oval(0, 0, height, height, fill=self._fill_a, outline="")
        tail = T.mix(self._fill_a, self._fill_b, min(1.0, end / max(1.0, width)))
        self.create_oval(end_int - height, 0, end_int, height, fill=tail, outline="")


class HelperCard(tk.Canvas):
    """侧栏助手卡：她的 Q 版头像 + 一句话气泡。

    头像**跟着状态换**（待机 / 渲染中 / 完成 / 出错），四个表情都来自
    本项目吉祥物本项目的表情集。

    为什么要这张卡：侧栏原来只是"两个可折叠面板 + 一大片空白"，
    空白本身就很像半成品。放张会变脸的助手在这里，既不空，也有"人味"。
    """

    #: 状态 → 头像文件（**半身**，有躯干；表情集那种纯头部素材只适合做小角标）
    FACES = {
        "idle": "avatar.png",
        "work": "avatar_work.png",
        "done": "avatar.png",
        "fail": "avatar.png",
    }

    def __init__(self, master, *, bg: str = T.CREAM, width: int | None = None,
                 height: int | None = None) -> None:
        super().__init__(master, bg=bg, highlightthickness=0, bd=0,
                         width=width or T.S(272), height=height or T.S(110))
        self._face = ui_assets.image(self.FACES["idle"])
        # 默认这句话压在一行内 —— 第一眼不该看到省略号。
        # 助手是本项目的本项目吉祥物，语气照她的设定来：跳着舞、摇着银铃干活。
        # ⚠️ 但**别写"开工啦"那种带货腔**。原来的"拖素材到卡片上，开工啦。"
        # 被用户点过："是人类说的话吗"。改成把事说清、留一点精神气就行。
        self._text = "素材拖进来就能开工"
        self._tone = T.MAPLE_SOFT
        self.bind("<Configure>", lambda _e: self.redraw())

    def set_state(self, state: str, text: str = "") -> None:
        face = ui_assets.image(self.FACES.get(state, self.FACES["idle"]))
        if face is not None:
            self._face = face
        self._tone = {"work": T.MAPLE_SOFT, "done": T.OK_SOFT,
                      "fail": T.DANGER_SOFT}.get(state, T.NAVY_TINT)
        if text:
            self._text = text
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        width = self.winfo_width() or T.S(272)
        height = self.winfo_height() or T.S(96)
        if width < T.S(40) or height < T.S(40):
            return
        T.round_rect(self, 1, 1, width - 1, height - 1, T.S(8),
                     fill=T.CARD, outline=T.BORDER)

        face_w = T.S(46)
        if self._face is not None:
            face_w = self._face.width()
            self.create_image(T.S(12), height / 2, image=self._face, anchor="w")

        # 气泡（左边留个小尖角指向头像）
        left = T.S(12) + face_w + T.S(8)
        T.round_rect(self, left, T.S(12), width - T.S(12), height - T.S(12), T.S(8),
                     fill=self._tone, outline="")
        self.create_polygon(left, height / 2 - T.S(6), left, height / 2 + T.S(6),
                            left - T.S(8), height / 2, fill=self._tone, outline="")
        # 气泡里的文字太长会折行，这里过一道 _one_line 裁掉
        self.create_text(left + T.S(12), height / 2, text=_one_line(self._text),
                         anchor="w", fill=T.NAVY_DEEP, font=T.pick_font(9),
                         width=int(width - left - T.S(26)))


class Select(tk.Canvas):
    """扁平下拉框。

    **为什么要自己画**：``tk.OptionMenu`` 是原生控件 —— 灰底、方角、系统字体、
    按下时闪一下系统高亮。放在一屏自绘的卡片和按钮中间，就是最刺眼的那处
    "廉价感"。这里用 Canvas 自绘一个圆的、跟配色一致的版本，
    下拉列表用一个配好色的 ``tk.Menu`` 弹出（列表本身没法自绘，但可以配平）。

    用法与 OptionMenu 接近，但宽度单位是**像素**。
    """

    def __init__(self, master, variable, values, *, width: int | None = None,
                 height: int | None = None, bg: str = T.CARD, command=None,
                 font_size: int = 10, labels: dict | None = None) -> None:
        super().__init__(master, bg=bg, highlightthickness=0, bd=0,
                         width=width or T.S(128), height=height or T.S(32),
                         cursor="hand2")
        self._var = variable
        self._values = list(values)
        self._command = command
        self._font_size = font_size
        #: 「值 → 显示名」的映射。**值可以跟显示名不一样**：
        #: 比如透明格式内部存 ``prores``，但界面上要写
        #: ``MOV（推荐，体积小）`` —— 用户认的是后者的意思，
        #: 而存盘要用前者（换显示文案时不至于让旧工程读不出来）。
        self._labels = dict(labels or {})
        self._hover = False
        self._enabled = True
        self.bind("<Configure>", lambda _e: redraw_select(self))
        self.bind("<Button-1>", lambda _e: self._popup())
        self.bind("<Enter>", lambda _e: self._set_hover(True))
        self.bind("<Leave>", lambda _e: self._set_hover(False))
        try: # 变量一变就重画（Tk 8.6+）
            self._var.trace_add("write", lambda *_: redraw_select(self))
        except AttributeError:
            pass

    def face(self) -> str:
        """当前该显示的名字（有映射就用映射，没有就原样显示值）。"""
        value = self._var.get()
        return self._labels.get(value, value)

    # ---- 数据 ----
    def set_enabled(self, enabled: bool) -> None:
        """禁用态：变灰、不再响应点击。

        ``tk.OptionMenu`` 有 ``configure(state=..., fg=...)``，自绘控件得自己实现；
        界面里"有镜头文件时禁用取景范围"就靠它。
        """
        self._enabled = bool(enabled)
        self.configure(cursor="hand2" if self._enabled else "arrow")
        redraw_select(self)

    def set_values(self, values) -> None:
        self._values = list(values)
        if self._values and self._var.get() not in self._values:
            self._var.set(self._values[0])
        redraw_select(self)

    def current(self) -> str:
        return self._var.get()

    # ---- 交互 ----
    def _set_hover(self, value: bool) -> None:
        self._hover = value
        redraw_select(self)

    def _popup(self) -> None:
        if not self._values or not self._enabled:
            return
        menu = tk.Menu(self, tearoff=0, bg="#FFFFFF", fg=T.TEXT,
                       activebackground=T.NAVY_TINT, activeforeground=T.NAVY,
                       relief="flat", bd=0, font=T.pick_font(self._font_size))
        for value in self._values:
            menu.add_command(label=self._labels.get(value, value),
                             command=lambda v=value: self._choose(v))
        try:
            menu.tk_popup(self.winfo_rootx(),
                          self.winfo_rooty() + self.winfo_height() + 2)
        finally:
            menu.grab_release()

    def _choose(self, value: str) -> None:
        self._var.set(value)
        redraw_select(self)
        if self._command is not None:
            self._command(value)


def redraw_select(widget: Select) -> None:
    """画一个扁平下拉框（独立成函数，方便被 trace 回调直接调用）。

    ⚠️ 开头那道 ``winfo_exists`` 不是多余的：控件被销毁之后，
    它挂在 ``StringVar`` 上的 trace 回调**还会再跑一次**
    （重建界面时就是这样），那时候 ``delete("all")`` 会抛
    ``invalid command name ".!frame...!select"``。回调里没法用 try 包住
    调用方，所以挡在这里。
    """
    try:
        if not widget.winfo_exists():
            return
    except tk.TclError:
        return
    widget.delete("all")
    width = widget.winfo_width() or T.S(128)
    height = widget.winfo_height() or T.S(32)
    if width < T.S(20) or height < T.S(12):
        return
    hovered = widget._hover and widget._enabled
    enabled = widget._enabled
    T.round_rect(widget, 1, 1, width - 1, height - 1, T.S(8),
                 fill=(T.NAVY_TINT if hovered else
                       ("#FFFFFF" if enabled else "#F2EEE8")),
                 outline=(T.NAVY if hovered else
                          (T.BORDER if enabled else "#E7E0D5")),
                 width=1)
    widget.create_text(T.S(12), height / 2, text=widget.face(), anchor="w",
                       fill=T.TEXT if enabled else T.TEXT_FAINT,
                       font=T.pick_font(widget._font_size),
                       width=int(width - T.S(34)))
    cx, cy = width - T.S(15), height / 2 - T.S(1)
    widget.create_line(cx - T.S(4.5), cy - T.S(1.5), cx, cy + T.S(3),
                       cx + T.S(4.5), cy - T.S(1.5),
                       fill=T.NAVY if enabled else T.DISABLED,
                       width=max(1, T.S(2)), capstyle="round", joinstyle="round")


# --------------------------------------------------------------------------
# 带标题条的信息卡（不能折叠，用来摆"分批进度 / 素材清单"这类内容）
# --------------------------------------------------------------------------


class CardPanel(tk.Canvas):
    """带标题条的信息卡：圆角、1px 描边、左上角竖色条 + 标题。

    这里是主区那两块大信息卡，用的是自绘而不是 ``tk.Frame``，
    跟整屏其他控件的圆角和竖条保持一致（``tk.Frame`` 只能给方角）。
    子类只管往 :meth:`_content` 里画，标题条由本类统一画。
    """

    # 标题条高度是方法而不是类属性：T.SCALE 要等 claim_dpi_awareness()
    # 跑完才定，写成类属性会在模块导入时就被算死成 1.0 倍。
    @staticmethod
    def head_h() -> int:
        return T.S(40)

    def __init__(self, master, title: str, *, accent: str = T.TEAL,
                 bg: str = T.CREAM, card: str = T.CARD) -> None:
        super().__init__(master, bg=bg, highlightthickness=0, bd=0)
        self._title = title
        self._accent = accent
        self._card = card
        self.bind("<Configure>", lambda _e: self.redraw())

    def redraw(self) -> None:
        self.delete("all")
        width = self.winfo_width() or T.S(400)
        height = self.winfo_height() or T.S(200)
        if width < T.S(40) or height < T.S(40):
            return

        T.round_rect(self, 1, 1, width - 1, height - 1, T.S(7),
                     fill=self._card, outline=T.BORDER, width=1)
        # 左上角竖色条，跟侧栏面板同一套语汇
        self.create_rectangle(T.S(14), T.S(12), T.S(17), T.S(32),
                              fill=self._accent, outline="")
        self.create_text(T.S(26), T.S(22), text=self._title, anchor="w", fill=T.TEXT,
                         font=T.pick_font(10, bold=True))
        self._content(width, height)

    def _content(self, width: int, height: int) -> None: # pragma: no cover
        """子类覆写：往标题条下面画自己的东西。"""


class BatchProgress(CardPanel):
    """分批进度卡：一段一行，写着这批一共多少张、已经渲了多少张。

    行高那几个数都是方法而不是类属性，原因同 :meth:`CardPanel.head_h`。
    """

    @staticmethod
    def row_step() -> int:
        """行距（含行与行之间的空隙）。"""
        return T.S(52)

    @staticmethod
    def row_h() -> int:
        """单行盒子自身的高度。"""
        return T.S(44)

    def __init__(self, master, *, bg: str = T.CREAM) -> None:
        super().__init__(master, "分批进度", accent=T.TEAL, bg=bg)
        self._rows: list[tuple[str, int]] = [] # (名字, 本批张数)
        self._states: list[str] = [] # PENDING / RUNNING / DONE / FAILED
        self._notes: list[str] = [] # 运行中那行的人话进度

    # ------------------------------------------------------------- 对外接口
    def set_plan(self, rows: list[tuple[str, int]]) -> None:
        """定下分几批、每批多少张。帧数还不知道（还没放动作）时传空表。"""
        self._rows = list(rows)
        self._states = [PENDING] * len(self._rows)
        if len(self._notes) != len(self._rows):
            self._notes = [""] * len(self._rows)
        self.redraw()

    def set_state(self, index: int, state: str, note: str = "") -> None:
        if not (0 <= index < len(self._rows)):
            return
        self._states[index] = state
        if note:
            self._notes[index] = note
        self.redraw()

    def reset(self) -> None:
        self._states = [PENDING] * len(self._rows)
        self._notes = [""] * len(self._rows)
        self.redraw()

    # --------------------------------------------------------------- 绘制
    @staticmethod
    def _mark(state: str) -> tuple[str, str]:
        """状态 → (右侧记号, 颜色)。记号与设计图一致：✓ / ● / ·"""
        return {
            DONE: ("✓", T.OK),
            RUNNING: ("●", T.MAPLE),
            FAILED: ("✕", T.DANGER),
        }.get(state, ("·", T.TEXT_FAINT))

    def _content(self, width: int, height: int) -> None:
        if not self._rows:
            self.create_text(T.S(26), self.head_h() + T.S(18), anchor="w",
                             text="放上角色和动作之后，这里会列出要分几批。",
                             fill=T.TEXT_FAINT, font=T.pick_font(9))
            return

        # 幅面放不下时就只画看得见的这几行，反正第 1 批永远在最上面
        room = max(1, (height - self.head_h() - T.S(6)) // self.row_step())
        for index, (name, frames) in enumerate(self._rows[:room]):
            state = self._states[index] if index < len(self._states) else PENDING
            note = self._notes[index] if index < len(self._notes) else ""
            mark, color = self._mark(state)
            top = self.head_h() + index * self.row_step()

            T.round_rect(self, T.S(14), top, width - T.S(14), top + self.row_h(), 7,
                         fill="#FFFFFF", outline=T.BORDER, width=1)
            self.create_text(T.S(28), top + T.S(15), text=name, anchor="w",
                             fill=T.TEXT, font=T.pick_font(10))
            if state == DONE:
                note = note or f"已完成 {frames} 张"
            elif state == PENDING:
                note = "待执行"
                color = T.TEXT_FAINT
            elif not note:
                note = "渲染中…"
            # ⚠️ 这一行现在会带"多少秒一帧 / 还剩多久"，比原来长得多。
            # 卡片宽度有限，不截断就直接画出卡片外（Tk 不会自动换行）。
            note = _fit_text(self, note, width - T.S(28) - T.S(48))
            self.create_text(T.S(28), top + T.S(32), text=note, anchor="w",
                             fill=color, font=T.pick_font(9))
            self.create_text(width - T.S(30), top + self.row_h() / 2, text=mark,
                             fill=color, font=T.pick_font(12, bold=True))


class MaterialList(CardPanel):
    """素材清单卡：角色 / 动作 / 镜头 / 舞台 四行，带 ✓ 或 — 和一句说明。

    四张投放卡管"放进去"，这张管"现在齐了没有"：哪些还缺、
    留空的项会走哪条路（自动机位、不渲染背景），一眼就能看完。
    """

    def __init__(self, master, *, bg: str = T.CREAM) -> None:
        super().__init__(master, "素材清单", accent=T.MAPLE, bg=bg)
        self._rows: list[tuple[str, str, bool]] = []

    def set_rows(self, rows: list[tuple[str, str, bool]]) -> None:
        """传入四行 ``(名称, 说明文案, 是否已就位)``。"""
        self._rows = list(rows)
        self.redraw()

    @staticmethod
    def row_step() -> int:
        """行距。是方法不是类属性，原因见 :meth:`CardPanel.head_h`。"""
        return T.S(30)

    def _content(self, width: int, height: int) -> None:
        if not self._rows:
            return
        top = self.head_h() + T.S(10)
        for index, (label, value, done) in enumerate(self._rows):
            y = top + index * self.row_step()
            if y > height - T.S(6):
                break
            self.create_text(T.S(26), y, text=label, anchor="w", fill=T.TEXT_FAINT,
                             font=T.pick_font(9))
            self.create_text(T.S(68), y, text=value, anchor="w",
                             fill=T.TEXT if done else T.TEXT_SUB,
                             font=T.pick_font(9),
                             width=max(T.S(40), width - T.S(68) - T.S(46)))
            self.create_text(width - T.S(28), y, text="✓" if done else "—",
                             fill=T.OK if done else T.TEXT_FAINT,
                             font=T.pick_font(10, bold=True))
            # 行底一条极淡的分隔线（比通栏硬线淡得多）
            self.create_line(T.S(26), y + T.S(15), width - T.S(26), y + T.S(15),
                             fill=T.BORDER)
