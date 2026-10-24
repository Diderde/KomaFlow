# -*- coding: utf-8 -*-
"""把 MMD 静帧渲染器的多张出图拼成**一张三视图**（跑在 Blender 里）。

为什么要它
----------
渲染器一跑就是三张独立 PNG（正面 / 侧面 / 背面）。用户要看"这个角色长什么样"，
三张图得来回切；而且**模型卡只接一个文件** —— 所以拼成一张最省事。

为什么不用 Pillow
-----------------
上游那份 ``拼三视图.py`` 用的是系统 Python 的 PIL。本工具的规定是
"不引入需要 pip 安装的依赖"（需求 NFR-16），装不了 PIL 就整条路走不通。

实测过：**Blender 5.2 里也没有 PIL**（``ModuleNotFoundError: No module named 'PIL'``）。
但 Blender **自带 numpy 和 bpy** —— 所以这里不用 PIL，改走
``bpy.data.images`` 读像素 + numpy 拼数组，零新增依赖。

为什么图上的字是自己画的
------------------------
没有字体库可用（PIL 没有、Blender 在 ``--background`` 下也不加载 UI 字体），
而"这格是哪一面"必须看得出来。所以内置一套 3×5 的点阵数字
（``MONO_3X5``）：编号 1/2/3 排在每格左上角，顺序就是 ``--`` 后面给的顺序。
与其画一堆不像字的东西，不如只画数字 —— 清楚，而且骗不了自己。

用法::

    blender --background --python stitch_views.py -- <名字> <输出路径> <图1> [图2 ...]

⚠️ **不要加 ``--noaudio``**：Blender 5.2 不认这个参数（会当成要打开的文件名），
   一加就整条命令失败。上游渲染器那条命令同理。
"""
from __future__ import annotations

import os
import sys

#: 画几号格用的点阵数字（3 宽 × 5 高）。只画 1~9 够用 —— 一张图最多四个视角。
MONO_3X5 = {
    "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"),
    "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"),
    "7": ("111", "001", "010", "010", "010"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "111"),
}


def _argv() -> list[str]:
    argv = sys.argv
    return argv[argv.index("--") + 1:] if "--" in argv else []


def _load_rgba(path: str):
    """读一张 PNG 成 ``(高, 宽, 4)`` 的 float 数组（自上而下）。

    ``bpy.data.images.load`` 拿到的 ``pixels`` 是**自下而上**的一维 RGBA 数组，
    跟普通图片的行序相反 —— 不翻一次的话拼出来和图是倒的。
    """
    import bpy
    import numpy as np

    image = bpy.data.images.load(path, check_existing=False)
    try:
        width, height = int(image.size[0]), int(image.size[1])
        if width <= 0 or height <= 0:
            return None
        buf = np.empty(width * height * 4, dtype=np.float32)
        image.pixels.foreach_get(buf)
        return buf.reshape(height, width, 4)[::-1]
    finally:
        bpy.data.images.remove(image)


def _draw_number(plane, row0: int, col0: int, digit: str, *, scale: int = 5,
                 rgb=(0.16, 0.22, 0.31)) -> None:
    """往画布上盖一个点阵数字（放大 ``scale`` 倍）。"""
    glyph = MONO_3X5.get(digit)
    if glyph is None:
        return
    height, width = plane.shape[0], plane.shape[1]
    for gy, line in enumerate(glyph):
        for gx, cell in enumerate(line):
            if cell != "1":
                continue
            y0 = row0 + gy * scale
            x0 = col0 + gx * scale
            y1 = min(height, y0 + scale)
            x1 = min(width, x0 + scale)
            if y0 < 0 or x0 < 0 or y1 <= y0 or x1 <= x0:
                continue
            plane[y0:y1, x0:x1, 0] = rgb[0]
            plane[y0:y1, x0:x1, 1] = rgb[1]
            plane[y0:y1, x0:x1, 2] = rgb[2]
            plane[y0:y1, x0:x1, 3] = 1.0


def main() -> int:
    rest = _argv()
    if len(rest) < 3:
        print("用法: -- <名字> <输出路径> <图1> [图2 ...]", flush=True)
        return 2
    _name, out, sources = rest[0], rest[1], rest[2:]

    import numpy as np

    loaded = []
    for path in sources:
        if not os.path.isfile(path):
            print("[拼图] 缺一张：%s" % path, flush=True)
            continue
        plane = _load_rgba(path)
        if plane is None:
            print("[拼图] 读不出尺寸：%s" % path, flush=True)
            continue
        loaded.append(plane)
    if not loaded:
        print("[拼图] 一张图都没读进来，跳过", flush=True)
        return 1

    # ⚠️ 尺寸可能不一致（不同视角想给不同的取景），所以按**最大**的那张算格子，
    # 每张自己在格子里居中 —— 直接按第一张算会裁掉比它大的。
    gap = 12
    cell_h = max(p.shape[0] for p in loaded)
    cell_w = max(p.shape[1] for p in loaded)
    cols = 2 if len(loaded) > 2 else len(loaded)
    rows = (len(loaded) + cols - 1) // cols
    width = gap + (cell_w + gap) * cols
    height = gap + (cell_h + gap) * rows

    # 暖米底（跟界面同色系，不像"截图拼的"那么生硬）
    sheet = np.zeros((height, width, 4), dtype=np.float32)
    sheet[:, :, 0] = 0.972
    sheet[:, :, 1] = 0.957
    sheet[:, :, 2] = 0.929
    sheet[:, :, 3] = 1.0

    for index, plane in enumerate(loaded):
        col, row = index % cols, index // cols
        # 最后一行只有一张时居中，别孤零零挂在左边
        in_row = min(cols, len(loaded) - row * cols)
        offset = (cols - in_row) * (cell_w + gap) // 2
        x = gap + offset + col * (cell_w + gap) + (cell_w - plane.shape[1]) // 2
        y = gap + row * (cell_h + gap) + (cell_h - plane.shape[0]) // 2
        target = sheet[y:y + plane.shape[0], x:x + plane.shape[1]]
        _paste(target, plane)
        _draw_number(sheet, y + 10, x + 10, str(index + 1),
                     scale=max(3, min(8, cell_h // 90 or 3)))

    # 出路：Blender 的 image.save 认 float 缓冲，转成自下而上再写
    import bpy

    flipped = sheet[::-1]
    image = bpy.data.images.new("三视图", width=width, height=height, alpha=True)
    image.pixels.foreach_set(np.ascontiguousarray(flipped).reshape(-1))
    image.filepath_raw = out
    image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)
    print("[拼图] -> %s %dx%d（%d 张）" % (out, width, height, len(loaded)),
          flush=True)
    return 0


def _paste(target, plane) -> None:
    """把一张图贴进目标区域，**按 alpha 合成**（图是透明底也不会变黑块）。"""
    import numpy as np

    src_a = plane[:, :, 3:4]
    dst = target
    dst[:, :, :3] = plane[:, :, :3] * src_a + dst[:, :, :3] * (1.0 - src_a)
    dst[:, :, 3] = np.maximum(dst[:, :, 3], src_a[:, :, 0])


if __name__ == "__main__":
    sys.exit(main())
