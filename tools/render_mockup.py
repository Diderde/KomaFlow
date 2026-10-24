"""出一张**完整窗口的成品图**（按 1.5 倍渲染，即 DPI 修好之后的样子）。

⚠️ **开发期工具，不参与运行时。** 需要 Pillow。

它是什么
--------
不是截图，是**按最终设计一比一画出来的效果图**：真实配色、真实预渲染素材
（LOGO / 装饰 / 表情 / 窗口按钮）、真实布局尺寸，整体按 1.5 倍渲染 ——
也就是做完 DPI 感知之后应该呈现的样子（文字和图形按物理像素直接画，不发虚）。

用途有两个：给人**先看成品**，以及当实现的**验收基准**。

用法::

    python tools/render_mockup.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

#: 缩放。1.5 = 150% 屏（也就是做完 DPI 之后的实际像素）
S = 1.5

ASSETS = Path(__file__).resolve().parent.parent / "src" / "komaflow" / "ui" / "assets"
WORK = Path(__file__).resolve().parent.parent / "work"

# ── 配色（与 theme.py 保持一致）──
NAVY = (12, 57, 103)
NAVY_DEEP = (8, 42, 78)
NAVY_SOFT = (27, 79, 133)
NAVY_TINT = (232, 238, 245)
CREAM = (245, 241, 233)
CARD = (252, 250, 246)
BEIGE = (234, 208, 176)
BEIGE_SOFT = (245, 231, 213)
BORDER = (237, 229, 217)
TEXT = (34, 48, 63)
TEXT_SUB = (107, 124, 144)
TEXT_FAINT = (167, 180, 194)
TEAL = (62, 201, 192)
TEAL_DEEP = (42, 167, 159)
MAPLE = (179, 58, 43)
MAPLE_SOFT = (249, 231, 226)
ORANGE = (232, 139, 60)
OK = (46, 158, 107)
OK_SOFT = (227, 245, 236)
PREVIEW_TOP = (242, 250, 249)
PREVIEW_BOTTOM = (251, 245, 238)

W, H = 1600, 1000 # 逻辑尺寸
WIN = (int(W * S), int(H * S))

BAR = 40 # 自绘标题栏
HEADER = 52 # 顶栏
SIDEBAR = 300


def px(v: float) -> float:
    return v * S


def _font(size: float, bold: bool = False):
    for path in ((r"C:\Windows\Fonts\msyhbd.ttc" if bold else
                  r"C:\Windows\Fonts\msyh.ttc"),
                 r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\segoeui.ttf"):
        try:
            return ImageFont.truetype(path, int(size * S))
        except OSError:
            continue
    return ImageFont.load_default()


def rrect(draw, box, radius, fill=None, outline=None, width=1.0):
    draw.rounded_rectangle([px(box[0]), px(box[1]), px(box[2]), px(box[3])],
                           radius=px(radius), fill=fill, outline=outline,
                           width=max(1, int(px(width))))


def text(draw, x, y, s, size=10, color=TEXT, bold=False, anchor="la"):
    draw.text((px(x), px(y)), s, font=_font(size, bold), fill=color, anchor=anchor)


def paste(img, name, x, y, height=None, width=None):
    path = ASSETS / name
    if not path.is_file():
        return None
    with Image.open(path) as raw:
        art = raw.convert("RGBA")
    if height:
        art = art.resize((max(1, round(art.width * height / art.height)),
                          int(px(height))), Image.LANCZOS)
    elif width:
        art = art.resize((int(px(width)),
                          max(1, round(art.height * width / art.width))),
                         Image.LANCZOS)
    img.alpha_composite(art, (int(px(x)), int(px(y))))
    return art


def chip(draw, x, y, label, size=9, pad=6, fill=BEIGE_SOFT, fg=TEXT):
    width = draw.textlength(label, font=_font(size)) / S + pad * 2
    rrect(draw, (x, y, x + width, y + 18), 5, fill=fill)
    text(draw, x + pad, y + 9, label, size, fg, anchor="lm")
    return width


def main() -> None:
    img = Image.new("RGBA", WIN, CREAM + (255,))
    d = ImageDraw.Draw(img)

    # ══ 自绘标题栏 ══
    d.rectangle([0, 0, WIN[0], px(BAR)], fill=NAVY)
    paste(img, "logo_26.png", 12, 7, height=26)
    text(d, 44, BAR / 2, "KomaFlow", 11, (255, 255, 255), bold=True, anchor="lm")
    d.line([px(140), px(11), px(140), px(BAR - 11)], fill=(255, 255, 255, 70),
           width=max(1, int(S)))
    text(d, 152, BAR / 2, "就绪", 9, (159, 192, 222), anchor="lm")
    for i, name in enumerate(("min", "max", "close")):
        paste(img, f"win_{name}.png", W - 8 - (3 - i) * 34 - 26, (BAR - 30) / 2)

    # ══ 顶栏 ══
    top = BAR
    d.rectangle([0, px(top), WIN[0], px(top + HEADER)], fill=NAVY)
    text(d, 18, top + HEADER / 2, "整理素材 → 预热 → 分批渲染 → 合并 → 出片",
         10, (159, 192, 222), anchor="lm")
    widths = (100, 72, 72, 42)
    group = (("开始渲染", TEAL, (8, 48, 58)),
             ("暂停", (42, 94, 149), (255, 255, 255)),
             ("终止", (107, 65, 65), (255, 255, 255)),
             ("⋯", NAVY_SOFT, (255, 255, 255)))
    bx = W - 14 - (sum(widths) + 8 * (len(widths) - 1))
    text(d, bx - 18, top + HEADER / 2, "21:44", 15, (255, 255, 255), bold=True,
         anchor="rm")
    paste(img, "deco_notes_header.png", bx - 116, top + 10, height=32)
    for bw, (label, fill, fg) in zip(widths, group):
        rrect(d, (bx, top + 10, bx + bw, top + 42), 8, fill=fill)
        text(d, bx + bw / 2, top + 26, label, 10, fg, bold=(label == "开始渲染"),
             anchor="mm")
        bx += bw + 8

    # ══ 侧栏 ══
    body = top + HEADER + 12
    # 助手卡
    rrect(d, (14, body, 14 + SIDEBAR, body + 110), 8, fill=CARD, outline=BORDER)
    paste(img, "avatar.png", 22, body + 7, height=96)
    rrect(d, (134, body + 12, 14 + SIDEBAR - 12, body + 98), 8, fill=MAPLE_SOFT)
    text(d, 146, body + 55, "把素材拖到右边的卡片上，", 9, NAVY_DEEP, anchor="lm")
    text(d, 146, body + 71, "就能开始。", 9, NAVY_DEEP, anchor="lm")

    # 环境（收起）
    y = body + 122
    rrect(d, (14, y, 14 + SIDEBAR, y + 40), 8, fill=CARD, outline=BORDER)
    d.rectangle([px(18), px(y + 10), px(21), px(y + 30)], fill=TEAL)
    text(d, 30, y + 20, "环境", 10, TEXT, bold=True, anchor="lm")
    text(d, 74, y + 20, "Blender 5.2.2 LTS · mmd_tools 4.5.7（共 2 台）", 9,
         TEXT_SUB, anchor="lm")
    text(d, 14 + SIDEBAR - 22, y + 20, "▸", 10, TEXT_FAINT, anchor="mm")

    # 参数
    y += 52
    # ⚠️ 参数面板要**撑满**到输出预估卡上方 —— 真机上它是 expand=True。
    # 写死高度会让侧栏底下留出一整块**裸背景**，那才是真的"空一大块"。
    card_h = 96
    card_y = H - 14 - card_h
    panel_h = card_y - 12 - y
    rrect(d, (14, y, 14 + SIDEBAR, y + panel_h), 8, fill=CARD, outline=BORDER)
    d.rectangle([px(18), px(y + 10), px(21), px(y + 30)], fill=TEAL)
    text(d, 30, y + 20, "参数", 10, TEXT, bold=True, anchor="lm")

    rows = [("画面方向", "select", "横屏 16:9"),
            ("清晰度", "size", "2560 × 1440　每秒张数 30"),
            ("画质档", "select", "标准成品档")]
    ry = y + 38
    for label, kind, value in rows:
        text(d, 30, ry + 14, label, 10, TEXT_SUB, anchor="lm")
        if kind == "select":
            rrect(d, (108, ry, 268, ry + 28), 6, fill=(255, 255, 255), outline=BORDER)
            text(d, 118, ry + 14, value, 10, TEXT, anchor="lm")
            text(d, 254, ry + 13, "⌄", 10, NAVY, anchor="mm")
        else:
            rrect(d, (108, ry, 150, ry + 28), 6, fill=(255, 255, 255), outline=BORDER)
            text(d, 129, ry + 14, "2560", 10, TEXT, anchor="mm")
            text(d, 156, ry + 14, "×", 9, TEXT_SUB, anchor="mm")
            rrect(d, (164, ry, 206, ry + 28), 6, fill=(255, 255, 255), outline=BORDER)
            text(d, 185, ry + 14, "1440", 10, TEXT, anchor="mm")
            text(d, 214, ry + 14, "每秒张数", 9, TEXT_SUB, anchor="lm")
            rrect(d, (268, ry, 300, ry + 28), 6, fill=(255, 255, 255), outline=BORDER)
            text(d, 284, ry + 14, "30", 10, TEXT, anchor="mm")
        ry += 36

    # 透明格式（新增）
    text(d, 30, ry + 14, "透明格式", 10, TEXT_SUB, anchor="lm")
    rrect(d, (108, ry, 292, ry + 28), 6, fill=(255, 255, 255), outline=BORDER)
    text(d, 118, ry + 14, "ProRes MOV（体积小）", 10, TEXT, anchor="lm")
    text(d, 278, ry + 13, "⌄", 10, NAVY, anchor="mm")
    ry += 40

    # ── 输出预估：贴在侧栏最底部 ──
    rrect(d, (14, card_y, 14 + SIDEBAR, card_y + card_h), 8, fill=CARD,
          outline=BORDER)
    d.rectangle([px(18), px(card_y + 10), px(21), px(card_y + 30)], fill=MAPLE)
    text(d, 30, card_y + 20, "输出预估", 10, TEXT, bold=True, anchor="lm")
    text(d, 30, card_y + 46, "透明 MOV（ProRes）　5.6 ~ 14.1GB", 9, TEXT_SUB)
    text(d, 30, card_y + 62, "普通 MP4　　　　　228 ~ 759MB", 9, TEXT_SUB)
    text(d, 30, card_y + 80, "所在盘剩余 80.4GB · 够用", 9, OK)

    # ══ 主区 ══
    mx = 14 + SIDEBAR + 12
    mw = W - mx - 14
    # 四张卡
    zones = [("角色模型 / 工程", ".pmx / .pmd / .blend", "示例角色.pmx",
              "filled"),
             ("动作", ".vmd", "依赖摇完整-整合表情.vmd", "filled"),
             ("镜头", ".vmd（可留空）", "", "empty"),
             ("舞台", ".pmx / .pmd / .blend", "", "empty")]
    cw = (mw - 3 * 10) / 4
    for i, (title, sub, value, state) in enumerate(zones):
        cx = mx + i * (cw + 10)
        box = (cx, body, cx + cw, body + 146)
        if state == "filled":
            rrect(d, box, 7, fill=BEIGE_SOFT, outline=NAVY)
        else:
            rrect(d, box, 7, fill=(255, 255, 255), outline=BORDER)
            rrect(d, (cx + 11, body + 11, cx + cw - 11, body + 135), 5,
                  outline=BORDER)
        rrect(d, (cx + 14, body + 3, cx + cw - 16, body + 6), 1.5,
              fill=NAVY if state == "filled" else BEIGE)
        paste(img, f"badge_{'navy' if state == 'filled' else 'beige'}.png",
              cx + 14, body + 14)
        text(d, cx + 26, body + 26, str(i + 1), 9, (255, 255, 255), bold=True,
             anchor="mm")
        text(d, cx + cw / 2, body + 62, title, 12, NAVY if state == "filled"
             else TEXT, bold=True, anchor="mm")
        mid = value if value else "拖文件到这里"
        text(d, cx + cw / 2, body + 92, mid[:16], 9,
             TEXT if value else TEXT_SUB, anchor="mm")
        text(d, cx + cw / 2, body + 124, sub, 9, TEXT_FAINT, anchor="mm")
        if state == "empty":
            paste(img, "deco_note_card.png", cx + 13, body + 104)

    # 工具行
    ty = body + 158
    rrect(d, (mx, ty, mx + 96, ty + 32), 8, fill=(255, 255, 255), outline=BORDER)
    text(d, mx + 48, ty + 16, "单帧预览", 10, NAVY, anchor="mm")
    text(d, mx + 112, ty + 16, "预览帧号", 10, TEXT_SUB, anchor="lm")
    rrect(d, (mx + 166, ty, mx + 206, ty + 32), 6, fill=(255, 255, 255),
          outline=BORDER)
    text(d, mx + 186, ty + 16, "30", 10, TEXT, anchor="mm")
    text(d, mx + 220, ty + 16, "把文件拖到卡片上即可", 9, TEXT_FAINT, anchor="lm")
    rrect(d, (mx + mw - 78, ty, mx + mw, ty + 32), 16, fill=NAVY_TINT)
    text(d, mx + mw - 39, ty + 16, "就绪", 9, NAVY, anchor="mm")

    # 预览区**不再一味拉高** —— 拉高只会得到一大片空渐变。
    # 固定成一条，下面让给真正有用的东西（分批进度 / 素材清单）。
    py0, py1 = ty + 44, ty + 44 + 336
    rrect(d, (mx, py0, mx + mw, py1), 7, fill=CARD, outline=BORDER)
    for i in range(int(px(py1 - py0 - 8))):
        t = i / max(1, px(py1 - py0 - 8))
        color = tuple(round(a + (b - a) * t)
                      for a, b in zip(PREVIEW_TOP, PREVIEW_BOTTOM))
        d.line([px(mx + 4), px(py0 + 4) + i, px(mx + mw - 4), px(py0 + 4) + i],
               fill=color, width=1)
    paste(img, "deco_tail_l.png", mx + mw * 0.06, py0 + 30, height=250)
    paste(img, "deco_tail_r.png", mx + mw * 0.86, py0 + 30, height=250)
    paste(img, "deco_notes_soft.png", mx + mw * 0.28, py0 + 40, height=90)
    paste(img, "deco_notes_soft.png", mx + mw * 0.58, py0 + 180, height=70)

    # 正中一枚**极淡的 LOGO 水印**：把大片留白压实，又不抢将来的渲染图
    logo_path = ASSETS / "logo.png"
    if logo_path.is_file():
        with Image.open(logo_path) as raw:
            size = int(px(240))
            wm = raw.convert("RGBA").resize((size, size), Image.LANCZOS)
        wm.putalpha(wm.getchannel("A").point(lambda v: int(v * 0.09)))
        img.alpha_composite(wm, (int(px(mx + mw / 2)) - size // 2,
                                 int(px(py0 + (py1 - py0) / 2)) - size // 2))

    # ── 空态：正中一张"快速开始"卡 ──
    # 大片留白最忌讳只放一句话 —— 那读起来就是"没做完"。
    # 放一张有结构的卡（标题 + 三步 + 次要动作），空白才读成"设计留白"。
    cw2, ch2 = 540, 252
    cx2 = mx + mw / 2 - cw2 / 2
    cy2 = py0 + (py1 - py0) / 2 - ch2 / 2 - 24
    rrect(d, (cx2, cy2, cx2 + cw2, cy2 + ch2), 10, fill=(255, 255, 255),
          outline=BORDER)
    text(d, cx2 + 30, cy2 + 32, "开始做一条片子", 13, TEXT, bold=True, anchor="lm")
    text(d, cx2 + 30, cy2 + 54, "三步就行，素材拖到卡片上", 9, TEXT_SUB, anchor="lm")
    sy2 = cy2 + 82
    for num, title, sub in (("1", "拖入角色模型", ".pmx / .pmd / .blend"),
                            ("2", "拖入动作", ".vmd（镜头可以留空）"),
                            ("3", "点「开始渲染」", "先单帧预览确认构图")):
        rrect(d, (cx2 + 30, sy2, cx2 + 54, sy2 + 24), 12, fill=NAVY)
        text(d, cx2 + 42, sy2 + 12, num, 10, (255, 255, 255), bold=True,
             anchor="mm")
        text(d, cx2 + 66, sy2 + 12, title, 10, TEXT, anchor="lm")
        text(d, cx2 + 210, sy2 + 12, sub, 9, TEXT_FAINT, anchor="lm")
        sy2 += 36
    rrect(d, (cx2 + 30, cy2 + ch2 - 46, cx2 + 156, cy2 + ch2 - 16), 8,
          fill=(255, 255, 255), outline=BORDER)
    text(d, cx2 + 93, cy2 + ch2 - 31, "打开已有工程…", 9, NAVY, anchor="mm")

    # ── 预览区底部的配置摘要条：把下半部分的空也压实 ──
    band = py1 - 46
    rrect(d, (mx + 10, band, mx + mw - 10, band + 34), 8, fill=(255, 255, 255),
          outline=BORDER)
    text(d, mx + 26, band + 17, "素材 2 / 4", 9, MAPLE, bold=True, anchor="lm")
    text(d, mx + 100, band + 17, "2560 × 1440 · 30 帧/秒 · 标准成品档", 9,
         TEXT_SUB, anchor="lm")
    text(d, mx + 360, band + 17, "输出：透明 MOV + MP4", 9, TEXT_SUB, anchor="lm")
    text(d, mx + mw - 26, band + 17, "预计 5.8 ~ 14.8 GB", 9, TEXT_SUB,
         anchor="rm")

    # 右下角伴侣：**正常比例**的动作立绘（透明底，跳跃姿势）
    # 左上角那个头像是 Q 版，两者分工：小的当助手，大的当角色展示。
    #
    # ⚠️ 尺寸和位置都要算过：
    # * 预览高 336，人物取 **252**（75%）—— 顶天立地(95%)会跟卡片/面板不成比例
    # * 底边必须落在**摘要条之上**（摘要条占 py1-46 ~ py1-12），
    # 否则腿脚会压在"预计 5.8~14.8 GB"那行字上
    paste(img, "mascot_normal.png", mx + mw - 200, py1 - 306, height=252)

    # ══ 预览下面：分批进度 + 素材清单 ══
    # 这两块本来就该在界面上 —— 这是分批渲染的工具，进度和素材状态是核心信息。
    # 它们一摆出来，"下面一大块空"就自然没了。
    gap = 12
    info_y = py1 + gap
    info_bottom = H - 14 - 56 - gap
    half = (mw - gap) / 2

    rrect(d, (mx, info_y, mx + half, info_bottom), 7, fill=CARD, outline=BORDER)
    d.rectangle([px(mx + 14), px(info_y + 12), px(mx + 17), px(info_y + 32)],
                fill=TEAL)
    text(d, mx + 26, info_y + 22, "分批进度", 10, TEXT, bold=True, anchor="lm")
    segs = (("第 1 批", "已完成 1860 张", OK, "✓"),
            ("第 2 批", "渲染中 1240 / 2000 张", MAPLE, "●"),
            ("第 3 批", "待执行", TEXT_FAINT, "·"))
    seg_y = info_y + 46
    for name, note, color, mark in segs:
        rrect(d, (mx + 14, seg_y, mx + half - 14, seg_y + 44), 7,
              fill=(255, 255, 255), outline=BORDER)
        text(d, mx + 28, seg_y + 15, name, 10, TEXT, anchor="lm")
        text(d, mx + 28, seg_y + 32, note, 9, color, anchor="lm")
        text(d, mx + half - 30, seg_y + 22, mark, 12, color, anchor="mm")
        seg_y += 52

    rrect(d, (mx + half + gap, info_y, mx + mw, info_bottom), 7, fill=CARD,
          outline=BORDER)
    d.rectangle([px(mx + half + gap + 14), px(info_y + 12),
                 px(mx + half + gap + 17), px(info_y + 32)], fill=MAPLE)
    text(d, mx + half + gap + 26, info_y + 22, "素材清单", 10, TEXT, bold=True,
         anchor="lm")
    rows2 = (("角色", "示例角色（形态二）.pmx", True),
             ("动作", "示例动作（含表情）.vmd", True),
             ("镜头", "留空 → 自动生成正面机位", False),
             ("舞台", "留空 → 不渲染背景（输出带透明）", False))
    row_y = info_y + 50
    for label, value, done in rows2:
        text(d, mx + half + gap + 26, row_y, label, 9, TEXT_FAINT, anchor="lm")
        text(d, mx + half + gap + 68, row_y, value, 9,
             TEXT if done else TEXT_SUB, anchor="lm")
        text(d, mx + mw - 28, row_y, "✓" if done else "—", 10,
             OK if done else TEXT_FAINT, anchor="mm")
        d.line([px(mx + half + gap + 26), px(row_y + 18), px(mx + mw - 26),
                px(row_y + 18)], fill=BORDER, width=1)
        row_y += 30

    sy = H - 14 - 56

    # 底部状态条
    rrect(d, (mx, sy, mx + mw, sy + 56), 7, fill=CARD, outline=BORDER)
    rrect(d, (mx + 10, sy + 12, mx + 220, sy + 22), 5, fill=(233, 226, 214))
    for i in range(int(px(0.62 * 210))):
        t = i / max(1, px(210))
        color = tuple(round(a + (b - a) * t) for a, b in zip(MAPLE, ORANGE))
        d.line([px(mx + 10) + i, px(sy + 12), px(mx + 10) + i, px(sy + 22)],
               fill=color, width=1)
    text(d, mx + 234, sy + 17, "62.00%", 10, TEXT, bold=True, anchor="lm")
    text(d, mx + 300, sy + 17, "已渲 1860/3000 张 · 3.81 秒/张 · 预计还要 1小时12分",
         9, TEXT_SUB, anchor="lm")
    text(d, mx + 10, sy + 42, "有 154 根动作骨骼在这个模型上找不到（多是裙骨和饰品骨），"
         "对应部位不会动，其余正常。", 9, (200, 135, 31))

    WORK.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(WORK / "mockup_full.png")
    print("成品图 ->", WORK / "mockup_full.png", img.size)


if __name__ == "__main__":
    main()
