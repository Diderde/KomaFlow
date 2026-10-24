# -*- coding: utf-8 -*-
"""重建 LOGO / 图标资产：**全部尺寸统一用无字狐首标**。

为什么统一无字
--------------
旧版大尺寸用的是外部品牌资产包里的"定稿标记"，圆内有旧产品名的两行字母。
产品改名 **KomaFlow** 之后：

* 那两行字母属于**旧名**，必须彻底消失（否则打出来的图标还带着旧名字）
* 圆里塞文字在 16~48px 必然糊成一团 —— 这是尺寸问题，不是画得不好
* 依赖外部图片会让构建**不可复现**（换个机器就没法重新生成）

所以改成：**一套几何形状，按尺寸缩放**。
形状本身是自洽的（深蓝圆角容器 + 白狐首圆 + 湖青描边耳 + 播放三角），
16px 看得懂，256px 也不空。

产出（覆盖同名文件，代码不用改）：
``logo.png`` / ``logo.ico`` / ``logo_{16,24,26,32,40,48,64,96,256}.png`` / ``logo_watermark.png``

用法::

    <python> tools/build_logo_assets.py # 生成
    <python> tools/build_logo_assets.py --check # 只看现状，不写文件
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "src" / "komaflow" / "ui" / "assets"
#: 兼容旧常量：现在**所有尺寸都用同一套无字形状**，这个值不再参与判定。
#: 保留它是因为 `make()` 与检查脚本里还引用着；改成 0 表示"任何尺寸都不上带字版"。
FULL_MARK_MIN = 0

#: 要产出的尺寸（顶栏 40 / 窗口 96 / 水印 256 / 其余小图标）
SIZES = (16, 24, 26, 32, 40, 48, 64, 96, 256)
#: .ico 里要打包的尺寸（Windows 全套）
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)

#: 与定稿一致的配色（从品牌资产包的 logo_final.py 抄的常量）
INK = (22, 32, 46) # #16202E 容器
TEAL = (34, 167, 159) # #22A79F 耳
DEEP = (14, 122, 116) # #0E7A74
CERAMIC = (245, 246, 248) # 近白（比纯白柔和一档）

SS = 8 # 超采样倍数：Tk 不做抗锯齿，靠预渲染带进去


def _rounded_square(size: int, radius_ratio: float = 0.235) -> Image.Image:
    """深蓝圆角正方容器（大画布，SS 倍）。"""
    big = size * SS
    canvas = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle([0, 0, big - 1, big - 1],
                           radius=big * radius_ratio, fill=INK + (255,))
    return canvas


#: 写进 LOGO 的名字。产品改名后只改这一处 + branding.APP_NAME。
WORDMARK = "KomaFlow"

#: 小于这个尺寸就不写字 —— 笔画会细于 1 像素，只会糊成一条白线。
#: 32 是实测下限（32px 时字高约 6px，仍能认出 KomaFlow 的轮廓）。
TEXT_MIN = 32

#: 字体候选（系统自带，**不随包分发字体文件**，避免字体授权问题）
FONT_CANDIDATES = (
    r"C:\Windows\Fonts\segoeuib.ttf", # Segoe UI Bold
    r"C:\Windows\Fonts\arialbd.ttf", # Arial Bold
    r"C:\Windows\Fonts\msyhbd.ttc", # 微软雅黑 Bold
)


def _load_font(px: int) -> ImageFont.FreeTypeFont | None:
    """按目标像素高加载一个粗体字；都找不到就返回 None（不写字）。"""
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, px)
        except OSError:
            continue
    return None


def build_small_mark(size: int) -> Image.Image:
    """画标记：深蓝圆角容器 + 白色狐首 + 湖青描边耳 + 播放三角 + **产品名**。

    ⚠️ 两个老坑记下来免得重犯：
    * **别按"白色"键控抠图 / 别把字塞进狐首圆里**：圆的直径撑不住两行字，
      16~48px 一律糊成一个白点
    * 字放在容器**下半部**，狐首相应缩小并上移，这样 32px 也还认得出写的是什么
    """
    big = size * SS
    canvas = _rounded_square(size)
    draw = ImageDraw.Draw(canvas)

    show_text = size >= TEXT_MIN
    # 有字时狐首整体上移、缩小，把下半部让出来
    radius = 0.300 if show_text else 0.365
    cy = 0.470 if show_text else 0.640

    # ── 耳：粗三角，耳内挖空形成描边 ──
    stroke = max(2, int(big * 0.085))
    ear_sign_scale = 0.88 if show_text else 1.0
    for sign in (-1, 1):
        cx = 0.5 + sign * 0.185 * ear_sign_scale
        tip = ((cx + sign * 0.055 * ear_sign_scale) * big, 0.075 * big)
        left = ((cx - 0.150 * ear_sign_scale) * big, (cy - 0.05) * big)
        right = ((cx + 0.150 * ear_sign_scale) * big, (cy - 0.05) * big)
        draw.polygon([tip, left, right], fill=TEAL + (255,))
        draw.polygon([(tip[0] - sign * stroke * 0.15, tip[1] + stroke * 3.4),
                      (left[0] + stroke * 1.15, left[1] - stroke * 1.6),
                      (right[0] - stroke * 1.15, right[1] - stroke * 1.6)],
                     fill=(0, 0, 0, 0))

    # ── 狐首：白圆 ──
    draw.ellipse([(0.5 - radius) * big, (cy - radius) * big,
                  (0.5 + radius) * big, (cy + radius) * big],
                 fill=CERAMIC + (255,))

    # ── 播放三角：挖空（显露容器深蓝）──
    tri = radius * 0.62
    draw.polygon([((0.5 - tri * 0.55) * big, (cy - tri) * big),
                  ((0.5 - tri * 0.55) * big, (cy + tri) * big),
                  ((0.5 + tri * 1.05) * big, cy * big)],
                 fill=INK + (255,))

    # ── 产品名：容器下半部，白色 ──
    #
    # ⚠️ 必须**按可用宽度自动缩字**：定死字号时 256px 下 "KomaFlow" 会顶到
    # 圆角上（实测 w 被切成半个），而小尺寸又会细到看不清。
    # 所以先按比例取一个字号，再按实际文本宽度压到 78% 容器宽以内。
    if show_text:
        usable = big * 0.78
        font_px = int(big * 0.150)
        font = _load_font(font_px)
        while font is not None and font_px > 6:
            box = draw.textbbox((0, 0), WORDMARK, font=font)
            if (box[2] - box[0]) <= usable:
                break
            font_px -= max(1, font_px // 12)
            font = _load_font(font_px)
        if font is not None:
            box = draw.textbbox((0, 0), WORDMARK, font=font)
            tw, th = box[2] - box[0], box[3] - box[1]
            tx = (big - tw) / 2 - box[0]
            # 下沿留 8% 边距，字心落在 0.78 高度附近
            ty = big * 0.86 - th - box[1]
            draw.text((tx, ty), WORDMARK, font=font, fill=CERAMIC + (255,))
    return canvas.resize((size, size), Image.LANCZOS)


#: 水印的整图不透明度（0~1）。Tk **做不了真半透明**（没有 alpha 合成），
#: 所以"极淡"只能靠**预渲染一张已经调好透明的图** —— 这个值就是那个透明度。
#: 8% 是量出来的：再高就会在预览区里"看得见"，比留白更丑。
WATERMARK_ALPHA = 0.08


def build_watermark(size: int = 256) -> Image.Image:
    """预览区那枚**极淡**的 LOGO 水印。

    ⚠️ 这张图**必须自带极低 alpha**。踩过的坑：生成器里它一度被写成
    "跟 logo.png 同一张不透明图"，于是预览区正中冒出一个扎眼的大白圆
    （而且跟引导卡叠在一起，卡片左边露出一块白）。
    客户端 Tk 改不了透明度，所以只能在这里预渲染。
    """
    mark = build_full_mark(size).convert("RGBA")
    alpha = mark.getchannel("A").point(lambda v: int(v * WATERMARK_ALPHA))
    mark.putalpha(alpha)
    return mark


def build_full_mark(size: int) -> Image.Image:
    """完整标记 —— **现在与无字版是同一套形状**（旧版读外部定稿图，已废弃）。

    保留函数名只是为了不让历史调用点报错；实际渲染交给 :func:`build_small_mark`。
    """
    return build_small_mark(size)


def make(size: int) -> Image.Image:
    """按尺寸自动分档。"""
    return build_small_mark(size)


def _strip(sizes=(48, 40, 32, 24, 16), bg=(236, 232, 224)) -> Image.Image:
    """验收图：每个尺寸一行，白底 + 深底各来一遍，方便一眼看哪个糊。"""
    pad, gap = 16, 14
    cell = 190
    width = pad * 2 + sum(cell + gap for _ in sizes)
    sheet = Image.new("RGB", (width, pad * 2 + (cell + gap) * 2), bg)

    for row, backdrop in enumerate(((255, 255, 255, 255), INK + (255,))):
        x = pad
        for size in sizes:
            tile = Image.new("RGBA", (cell, cell), backdrop)
            icon = make(size)
            tile.alpha_composite(icon, ((cell - size) // 2, (cell - size) // 2))
            # 再单独放大一份贴右下角，看像素级细节
            zoom = size * 3
            if zoom <= cell // 2:
                big = icon.resize((zoom, zoom), Image.NEAREST)
                tile.alpha_composite(big, (cell - zoom - 6, cell - zoom - 6))
            sheet.paste(tile.convert("RGB"), (x, pad + row * (cell + gap)))
            x += cell + gap
    return sheet


def main() -> int:
    check_only = "--check" in sys.argv
    rows = []
    for size in SIZES:
        icon = make(size)
        which = "无字狐首标"
        rows.append((size, which, icon))
        print(f" {size:>4}px {which}")
        if check_only:
            continue
        icon.save(ASSETS / f"logo_{size}.png", optimize=True)
        if size == 256:
            icon.save(ASSETS / "logo.png", optimize=True)
            # ⚠️ 水印**不是**把 logo 复制一份 —— 它必须自带极低 alpha，
            # 否则预览区正中会冒出一个扎眼的大白圆（见 build_watermark 的说明）。
            build_watermark(256).save(ASSETS / "logo_watermark.png", optimize=True)

    if not check_only:
        # 多尺寸 .ico（任务栏 / 标题栏用）。**每档都按同一套分档规则**生成：
        # 16~40 无字、48 起带字 —— Windows 会挑最合适的那一档显示。
        #
        # ⚠️ PIL 存 ICO 的坑：``frames[0].save(..., sizes=[...])`` 只会留下**一档**
        # （实测写出 0.8 KB 的 16×16 单档 ico，原来是 40 KB 的七档）。
        # 正确写法：拿**最大**那张当底，其余档走 ``append_images``。
        frames = {size: make(size).convert("RGBA") for size in ICO_SIZES}
        largest = max(ICO_SIZES)
        frames[largest].save(
            ASSETS / "logo.ico", format="ICO",
            sizes=[(s, s) for s in ICO_SIZES],
            append_images=[frames[s] for s in sorted(ICO_SIZES) if s != largest])
        packed = Image.open(ASSETS / "logo.ico")
        got = sorted(packed.ico.sizes())
        print(f" logo.ico {len(got)} 档：{', '.join(str(s[0]) for s in got)}"
              f"　{(ASSETS / 'logo.ico').stat().st_size / 1024:.1f} KB")
        if len(got) != len(ICO_SIZES):
            raise SystemExit(f"✗ .ico 只写进 {len(got)} 档，应为 {len(ICO_SIZES)} 档")

        strip = _strip()
        strip.save(ROOT / "work" / "logo_sizes_check.png")
        print(f" 验收图 -> {ROOT / 'work' / 'logo_sizes_check.png'}")

    print()
    print(f"分档线：>= {FULL_MARK_MIN}px 用完整标记，小于它用无字简化版")
    return 0


if __name__ == "__main__":
    sys.exit(main())
