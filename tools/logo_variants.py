"""生成 LOGO 备选方案，并输出多尺寸对比图。

⚠️ **开发期工具，不参与运行时。**

为什么要专门做对比图：LOGO 会被缩到 **16×16** 用在任务栏和标题栏上，
在 480 尺寸下好看不等于在 16 下认得出。这脚本一次画出几个候选，
每个都按 16/24/32/48/64/128 排一行，一眼就能看出哪个糊成球。

用法::

    python tools/logo_variants.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

SS = 4
OUT = Path(__file__).resolve().parent.parent / "work"

NAVY = (12, 57, 103)
CYAN = (110, 244, 232)
MAGENTA = (250, 148, 236)
CREAM = (247, 243, 235)

#: 狐狸头轮廓（比例坐标）。两耳 + 额头凹口 + 脸颊 + 下巴。
HEAD = [
    (0.300, 0.115), (0.420, 0.375), (0.580, 0.375), (0.700, 0.115),
    (0.795, 0.495), (0.740, 0.720), (0.500, 0.885), (0.260, 0.720), (0.205, 0.495),
]

PLAY = [(0.432, 0.478), (0.432, 0.722), (0.638, 0.600)]


def _lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def _scaled(points, size, scale: float, dx: float = 0.0, dy: float = 0.0):
    return [((x - 0.5) * scale * size * SS + size * SS / 2 + dx * size * SS,
             (y - 0.5) * scale * size * SS + size * SS / 2 + dy * size * SS)
            for x, y in points]


def variant_a(size: int) -> Image.Image:
    """A 渐变狐狸头 + 挖空播放三角（当前方案，但更满、更实）。"""
    big = size * SS
    canvas = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    ImageDraw.Draw(canvas).ellipse([0, 0, big - 1, big - 1], fill=NAVY)

    head = _scaled(HEAD, size, 1.16)
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).polygon(head, fill=255)

    grad = Image.new("RGBA", (big, big))
    painter = ImageDraw.Draw(grad)
    for y in range(big):
        painter.line([(0, y), (big, y)], fill=_lerp(CYAN, MAGENTA, y / (big - 1)))

    glow = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    glow.paste(grad, (0, 0), mask)
    glow = glow.filter(ImageFilter.GaussianBlur(radius=size * 0.03 * SS))
    canvas.alpha_composite(glow)
    canvas.paste(grad, (0, 0), mask)
    ImageDraw.Draw(canvas).polygon(_scaled(PLAY, size, 1.16), fill=NAVY)
    return canvas.resize((size, size), Image.LANCZOS)


def variant_b(size: int) -> Image.Image:
    """B 纯剪影：亮色狐狸头 + 播放三角，**高对比、零渐变**。

    16px 下最考验的是"轮廓是否独立于底色"。纯色剪影没有渐变过渡，
    缩到 16 也就还是那个形状，不会糊成一团。
    """
    big = size * SS
    canvas = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    ImageDraw.Draw(canvas).ellipse([0, 0, big - 1, big - 1], fill=NAVY)
    ImageDraw.Draw(canvas).polygon(_scaled(HEAD, size, 1.10), fill=CREAM)
    ImageDraw.Draw(canvas).polygon(_scaled(PLAY, size, 1.10), fill=NAVY)
    return canvas.resize((size, size), Image.LANCZOS)


def variant_c(size: int) -> Image.Image:
    """C 反白：亮底 + 深色狐狸头。对比最强，最像"应用图标"。"""
    big = size * SS
    canvas = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.ellipse([0, 0, big - 1, big - 1], fill=CREAM)
    rim = max(2, int(size * 0.020 * SS))
    draw.ellipse([rim, rim, big - 1 - rim, big - 1 - rim],
                 outline=NAVY, width=rim)
    draw.polygon(_scaled(HEAD, size, 1.06), fill=NAVY)
    draw.polygon(_scaled(PLAY, size, 1.06), fill=CREAM)
    return canvas.resize((size, size), Image.LANCZOS)


def variant_d(size: int) -> Image.Image:
    """D 双耳 + 播放：最简，去掉整颗头，只剩两条耳朵和中间的三角。"""
    big = size * SS
    canvas = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.ellipse([0, 0, big - 1, big - 1], fill=NAVY)
    for sign in (-1, 1):
        cx = 0.5 + sign * 0.185
        draw.polygon(_scaled([(cx - 0.115, 0.700), (cx + sign * 0.035, 0.180),
                              (cx + 0.115, 0.700)], size, 1.0), fill=CYAN)
    draw.polygon(_scaled([(0.400, 0.500), (0.400, 0.760), (0.660, 0.630)],
                         size, 1.0), fill=CREAM)
    return canvas.resize((size, size), Image.LANCZOS)


def variant_e(size: int) -> Image.Image:
    """E 狐头 + **动势弧**：脑袋后面甩一道弧线 —— 弧线=在动=跳舞，
    正好补上"角色有了但没体现 MMD（跳舞/动作）"这一半。"""
    big = size * SS
    canvas = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.ellipse([0, 0, big - 1, big - 1], fill=CREAM)
    rim = max(2, int(size * 0.020 * SS))
    draw.ellipse([rim, rim, big - 1 - rim, big - 1 - rim], outline=NAVY, width=rim)

    # 动势弧：从左下甩到右上的一道月牙
    arc_w = max(2, int(size * 0.055 * SS))
    draw.arc([int(big * 0.02), int(big * 0.10), int(big * 0.98), int(big * 0.98)],
             start=205, end=330, fill=CYAN, width=arc_w)
    draw.polygon(_scaled(HEAD, size, 1.00), fill=NAVY)
    draw.polygon(_scaled(PLAY, size, 1.00), fill=CREAM)
    return canvas.resize((size, size), Image.LANCZOS)


def variant_f(size: int) -> Image.Image:
    """F 狐头 + **动势线**：两侧各画三条短促的速度线（漫画里表示"在动"的通用符号）。

    比弧线更直白，而且短粗笔画在 16px 下比细弧线更不容易糊。
    """
    big = size * SS
    canvas = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.ellipse([0, 0, big - 1, big - 1], fill=CREAM)
    rim = max(2, int(size * 0.020 * SS))
    draw.ellipse([rim, rim, big - 1 - rim, big - 1 - rim], outline=NAVY, width=rim)

    stroke = max(2, int(size * 0.036 * SS))
    for sign in (-1, 1):
        for i, (y, length) in enumerate(((0.32, 0.13), (0.50, 0.17), (0.68, 0.13))):
            x0 = 0.5 + sign * (0.44 - 0.0)
            x1 = 0.5 + sign * (0.44 - length)
            draw.line([(x0 * big, y * big), (x1 * big, y * big)],
                      fill=CYAN, width=stroke)
    draw.polygon(_scaled(HEAD, size, 0.94), fill=NAVY)
    draw.polygon(_scaled(PLAY, size, 0.94), fill=CREAM)
    return canvas.resize((size, size), Image.LANCZOS)


def variant_g(size: int) -> Image.Image:
    """G 狐头 + 动势弧 + **节拍点**：弧线上挂一个圆点。

    圆点=关键帧，暗示"动作数据/时间轴"，是最贴近 MMD 的那种暗示。
    """
    big = size * SS
    canvas = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.ellipse([0, 0, big - 1, big - 1], fill=CREAM)
    rim = max(2, int(size * 0.020 * SS))
    draw.ellipse([rim, rim, big - 1 - rim, big - 1 - rim], outline=NAVY, width=rim)

    arc_w = max(2, int(size * 0.050 * SS))
    draw.arc([int(big * 0.04), int(big * 0.12), int(big * 0.96), int(big * 0.96)],
             start=208, end=332, fill=CYAN, width=arc_w)
    dot = size * 0.052
    draw.ellipse([big * 0.795 - dot * SS, big * 0.700 - dot * SS,
                  big * 0.795 + dot * SS, big * 0.700 + dot * SS], fill=CYAN)
    draw.polygon(_scaled(HEAD, size, 1.00), fill=NAVY)
    draw.polygon(_scaled(PLAY, size, 1.00), fill=CREAM)
    return canvas.resize((size, size), Image.LANCZOS)


VARIANTS = {"C 反白(现用)": variant_c, "E 狐头+动势弧": variant_e,
            "F 狐头+动势线": variant_f, "G 狐头+弧+节拍点": variant_g}

SIZES = (128, 64, 48, 32, 24, 16)


def build() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pad, gap = 18, 16
    row_h = max(SIZES) + pad
    width = 190 + sum(s + gap for s in SIZES)
    sheet = Image.new("RGBA", (width, row_h * len(VARIANTS) + pad), (236, 232, 224, 255))
    draw = ImageDraw.Draw(sheet)

    for row, (name, maker) in enumerate(VARIANTS.items()):
        y = pad // 2 + row * row_h
        draw.text((16, y + row_h // 2), name, fill=(40, 48, 60))
        x = 190
        for size in SIZES:
            icon = maker(size)
            sheet.alpha_composite(icon, (x, y + (row_h - pad - size) // 2))
            x += size + gap
    sheet.convert("RGB").save(OUT / "logo_variants.png")
    print("对比图 ->", OUT / "logo_variants.png")
    for name, maker in VARIANTS.items():
        maker(480).save(OUT / f"logo_{name.split()[0]}.png")
    print("单张 ->", OUT / "logo_A.png 等")


if __name__ == "__main__":
    build()
