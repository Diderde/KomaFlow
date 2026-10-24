"""自绘标题栏的**原创设计**素材 + 效果预览。

⚠️ **开发期工具，不参与运行时。** 需要 Pillow。

为什么要先画
------------
自绘窗口（无边框）一旦改坏，后果是"窗口拖不动""关不掉"这类致命缺陷，
不能盲改。所以先把**设计**画出来给人看，确认了再动窗口代码。

设计原则：**不抄任何人**
------------------------
* **不抄 Windows**：它的最小化/最大化/关闭是贴边的直角矩形、悬停变系统灰。
  我们的是**圆角方块**按钮（跟界面里所有卡片/按钮同一套语言），
  悬停时最小化/最大化浮出半透明白，关闭浮出**枫红**（角色的主色）。
* **不抄 Electron 应用**（B站/抖音/VS Code 那类）：它们的标题栏就是一个
  普通 `<div>`，没有信息。我们在标题栏里放**实时状态**（就绪 / 渲染中 62%），
  这是它们不会做的事。
* 图形全部用本项目自己的几何语言画：圆角、2px 描边、枫红/青点缀。

用法::

    python tools/render_titlebar.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

SS = 4
OUT = Path(__file__).resolve().parent.parent / "src" / "komaflow" / "ui" / "assets"
WORK = Path(__file__).resolve().parent.parent / "work"

NAVY = (12, 57, 103)
WHITE = (255, 255, 255)
MAPLE = (179, 58, 43)
TEAL = (62, 201, 192)

#: 标题栏高度（逻辑像素）。比系统的 32 略高，松一点。
BAR_HEIGHT = 40
#: 窗口按钮尺寸（逻辑像素）
BUTTON = 30


def _canvas(width: int, height: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGBA", (width * SS, height * SS), (0, 0, 0, 0))
    return image, ImageDraw.Draw(image)


def _save(image: Image.Image, name: str, folder: Path = OUT) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    final = image.resize((image.width // SS, image.height // SS), Image.LANCZOS)
    final.save(folder / name, optimize=True)
    print(f" {name} {final.width}×{final.height}")


def _rounded(draw: ImageDraw.ImageDraw, box, radius: float, fill=None,
             outline=None, width: float = 1) -> None:
    draw.rounded_rectangle([v * SS for v in box], radius=radius * SS,
                           fill=fill, outline=outline,
                           width=max(1, int(width * SS)))


def _button(kind: str, hover: tuple | None) -> Image.Image:
    """一个窗口按钮：圆角方块底 + 我们的几何图形。

    ``kind`` 取 ``min`` / ``max`` / ``restore`` / ``close``。
    ``hover`` 是悬停时的底色（None 表示常态）。
    """
    image, draw = _canvas(BUTTON, BUTTON)
    if hover is not None:
        _rounded(draw, (0, 0, BUTTON - 1, BUTTON - 1), 8, fill=hover)

    ink = WHITE
    mid = BUTTON / 2

    def s(value: float) -> float:
        return value * SS

    if kind == "min":
        draw.line([s(9), s(mid), s(BUTTON - 9), s(mid)], fill=ink,
                  width=int(1.8 * SS))
    elif kind == "max":
        _rounded(draw, (9.5, 9.5, BUTTON - 9.5, BUTTON - 9.5), 3,
                 outline=ink, width=1.6)
    elif kind == "restore":
        # 两个错开的方框：本项目自己的画法，不用系统那种斜杠
        _rounded(draw, (8, 11, BUTTON - 12, BUTTON - 8), 3, outline=ink, width=1.5)
        _rounded(draw, (12, 8, BUTTON - 8, BUTTON - 12), 3, outline=ink, width=1.5)
    elif kind == "close":
        draw.line([s(10), s(10), s(BUTTON - 10), s(BUTTON - 10)], fill=ink,
                  width=int(1.8 * SS))
        draw.line([s(BUTTON - 10), s(10), s(10), s(BUTTON - 10)], fill=ink,
                  width=int(1.8 * SS))
    return image


def build_buttons() -> None:
    """窗口按钮：常态 + 悬停态各出一套。

    悬停底色是我们自己的：最小化/最大化浮出**半透明白**，
    关闭浮出**枫红**（角色主色）—— 这是跟系统和其他软件最不一样的地方。
    """
    print("窗口按钮（原创设计：圆角方块）…")
    for kind in ("min", "max", "restore", "close"):
        _save(_button(kind, None), f"win_{kind}.png")
        tint = MAPLE + (235,) if kind == "close" else (255, 255, 255, 46)
        _save(_button(kind, tint), f"win_{kind}_hover.png")


def _font(size: int, bold: bool = False):
    """找一个能显示中文的字体。"""
    from PIL import ImageFont
    candidates = (
        r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\segoeui.ttf",
    )
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def build_mockup(hover_close: bool = False) -> Image.Image:
    """把标题栏按真实尺寸拼一张效果图。``hover_close`` 时关闭键浮出枫红。"""
    width, height = 1280, BAR_HEIGHT
    image = Image.new("RGBA", (width * SS, height * SS), NAVY + (255,))
    draw = ImageDraw.Draw(image)

    # 左：LOGO（复用已经做好的 40px 版本）
    logo_path = OUT / "logo_40.png"
    if logo_path.is_file():
        with Image.open(logo_path) as raw:
            logo = raw.convert("RGBA").resize((26 * SS, 26 * SS), Image.LANCZOS)
        image.alpha_composite(logo, (13 * SS, 7 * SS))

    # 右：三个窗口按钮
    cursor = width - 3 * (BUTTON + 4) - 10
    for kind in ("min", "max", "close"):
        tint = MAPLE + (235,) if (kind == "close" and hover_close) else None
        image.alpha_composite(_button(kind, tint),
                              (cursor * SS, (height - BUTTON) // 2 * SS))
        cursor += BUTTON + 4

    # 底沿一条 1px 半透明分隔线（标题栏里要克制，不做渐变）
    draw.line([(0, (height - 1) * SS), (width * SS, (height - 1) * SS)],
              fill=(255, 255, 255, 42), width=int(1 * SS))

    bar = image.resize((width, height), Image.LANCZOS)

    # ⚠️ **文字必须画在降采样之后**：Pillow 的 draw.text 用的是字体自身像素，
    # 在 4 倍超采样坐标系上写字，出来只有芝麻大（第一版就是这么翻车的）。
    painter = ImageDraw.Draw(bar)
    painter.text((48, 10), "KomaFlow", font=_font(15, bold=True), fill=WHITE)
    painter.line([(140, 12), (140, 28)], fill=(255, 255, 255, 60))
    painter.text((152, 13), "就绪", font=_font(11), fill=(255, 255, 255, 150))
    return bar


def main() -> None:
    build_buttons()
    WORK.mkdir(parents=True, exist_ok=True)
    normal = build_mockup()
    hover = build_mockup(hover_close=True)
    # 上下叠一起：上=常态，下=关闭键悬停
    gap = 22
    sheet = Image.new("RGBA", (normal.width, BAR_HEIGHT * 2 + gap),
                      (34, 42, 58, 255))
    sheet.alpha_composite(normal, (0, 0))
    sheet.alpha_composite(hover, (0, BAR_HEIGHT + gap))
    sheet.convert("RGB").save(WORK / "titlebar_mockup.png")
    print("效果图 ->", WORK / "titlebar_mockup.png")


if __name__ == "__main__":
    main()
