"""把 v15 品牌资产包里的 LOGO / 图标导入到应用资源目录。

> 🚨 **先看这条：本脚本已不是 LOGO 的生成器。**
> 它直接把资产包里的图按尺寸重采样，**没有尺寸分档** —— 顶栏那个 40px 徽标
> 会把"圆里两行字"一起塞进去，缩下来就是一坨白（用户报的"LOGO 坏了"）。
> 现在 LOGO / 图标一律由 ``tools/build_logo_assets.py`` 生成
> （16~40 用无字简化版、48 起用完整标记，并打包多档 .ico）。
> **不要再跑这个脚本**，除非你确实想把资产包原图整份覆盖回去。
> 留着它是为了记录"这些图是从哪个包、按什么规则裁出来的"。

为什么要有这个脚本（而不是手工复制）
------------------------------------
1. 顶栏显示的是 **40 实际像素** 的图标，必须按这个尺寸原生渲染 ——
   不能拿 512 的图让 Tk 去缩（Tk 的 subsample 是最近邻，会把圆边啃出锯齿）。
2. 图标要**去边距**：v15 的 512 图里容器只占中间约 92%（规范写的"容器内缩 4%"），
   而且画布四周可能还有透明留白。顶栏要的是"贴满"的图，
   不然 40px 里图标只有 36px，旁边多出空隙。
3. 有**多个变体**（浅底 / 深底），顶栏该用哪个得看实际效果，
   所以脚本支持指定变体 + 出一张真机对比图。

⚠️ 开发期工具，不参与运行时。用法::

    python.exe tools/import_brand_assets.py
"""

from __future__ import annotations

import sys
import os
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "src" / "komaflow" / "ui" / "assets"
#: 品牌资产包目录（用环境变量指定；默认放在仓库外的 _assets_source 下）
PACKAGE = Path(os.environ.get("KOMEFLOW_ASSET_DIR", "_assets_source")) / "KomaFlow_品牌资产包_v15"

#: 顶栏图标的显示尺寸（实际像素）。跟 ``_apply_logo`` 里画的一致。
HEADER_ICON = 40
#: 窗口图标（Tk 的 ``iconphoto`` 喜欢大一点的）
WINDOW_ICON = 96
#: 水印用它缩放（预览区背景那枚极淡的 LOGO）
WATERMARK_SOURCE = 256


def trim_alpha(image: Image.Image) -> Image.Image:
    """按 alpha 裁到内容边界 —— 去掉透明留白，让图标"贴满"画布。"""
    box = image.getchannel("A").getbbox()
    return image.crop(box) if box else image


def square(image: Image.Image) -> Image.Image:
    """补成正方形（按较长边），保证图标不被拉变形。"""
    side = max(image.width, image.height)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(image, ((side - image.width) // 2, (side - image.height) // 2))
    return canvas


def load(source: Path, size: int) -> Image.Image:
    with Image.open(source) as raw:
        image = raw.convert("RGBA")
    return square(trim_alpha(image)).resize((size, size), Image.LANCZOS)


def main() -> int:
    if not PACKAGE.is_dir():
        print(f"找不到资产包：{PACKAGE}")
        return 1

    mark = PACKAGE / "01_LOGO主干"
    icons = PACKAGE / "02_图标"

    produced: list[str] = []

    # ── 顶栏图标 ──
    # 品牌规范说"深色界面用深底系列"；我们顶栏是深蓝，先按规范用深底版。
    # 另一版也产出来，方便在真机上对比挑选。
    for name, src in (("logo_40.png", mark / "02_mark_深底_512.png"),
                      ("logo_40_alt.png", mark / "01_mark_浅底_512.png")):
        load(src, HEADER_ICON).save(ASSETS / name)
        produced.append(name)

    load(mark / "02_mark_深底_512.png", WINDOW_ICON).save(ASSETS / "logo_96.png")
    produced.append("logo_96.png")

    # 大图留着给水印 / 别的地方按需缩
    load(mark / "02_mark_深底_512.png", WATERMARK_SOURCE).save(ASSETS / "logo.png")
    produced.append("logo.png")

    # ── 多尺寸小图标（Tk 有些场景要 16/24/26/32/48/64）──
    for size in (16, 24, 26, 32, 48, 64):
        load(mark / "02_mark_深底_512.png", size).save(ASSETS / f"logo_{size}.png")
        produced.append(f"logo_{size}.png")

    # ── Windows 图标：直接用官方 .ico（已经含 16–256 全套）──
    ico = icons / "KomaFlow.ico"
    if ico.is_file():
        (ASSETS / "logo.ico").write_bytes(ico.read_bytes())
        produced.append("logo.ico")

    print(f"已导入 {len(produced)} 个文件到 {ASSETS}")
    for name in produced:
        path = ASSETS / name
        size = path.stat().st_size
        print(f" {name:22s} {size / 1024:>7.1f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
