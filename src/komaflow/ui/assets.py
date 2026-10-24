"""界面静态资源的缓存加载器。

Tk 的 Canvas **不做抗锯齿**，所以像音符、飘带这类曲线装饰一律用
**预渲染好的 PNG**（见 ``tools/render_ui_assets.py``，Pillow 4 倍超采样后降采样），
在这里 1:1 贴上去 —— 像素里已经带着抗锯齿，边缘自然干净。

⚠️ 缓存必须是**模块级**的：``tk.PhotoImage`` 一旦没有引用会被 GC 掉，
界面上就变成一片空白（这个坑踩过）。
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path

#: 静态资源目录
ASSETS = Path(__file__).parent / "assets"

#: 模块级缓存，兼作"保活"用途
_CACHE: dict[str, tk.PhotoImage | None] = {}


def image(name: str) -> tk.PhotoImage | None:
    """取一张装饰图；取不到返回 ``None``（调用方自己退回自绘）。"""
    if name not in _CACHE:
        try:
            _CACHE[name] = tk.PhotoImage(file=str(ASSETS / name))
        except (tk.TclError, OSError):
            _CACHE[name] = None
    return _CACHE[name]


def blit(canvas: tk.Canvas, name: str, x: float, y: float, *, anchor: str = "center",
         tags=()) -> int | None:
    """把装饰图贴到画布上。图不存在就返回 ``None``。"""
    picture = image(name)
    if picture is None:
        return None
    return canvas.create_image(round(x), round(y), image=picture, anchor=anchor,
                               tags=tags)


def mascot() -> tk.PhotoImage | None:
    """取界面吉祥物（**Q 版**）。

    用在侧栏助手卡那种小尺寸处 —— Q 版五官大，缩到 30~96px 才看得清。
    """
    return image("mascot.png")


def mascot_normal() -> tk.PhotoImage | None:
    """取**正常比例**的动作立绘。

    用在预览区右下角那种大尺寸处：这里要的是"角色"，不是"图标"。
    素材是用户自备的**透明底**成品（``透明立绘/透明_活泼跳跃.png``），
    生成时**不能抠底** —— 抠底会先转 RGB 把 alpha 抹平。
    """
    return image("mascot_normal.png")


def preload(*names: str) -> None:
    """预先加载，避免第一次显示时闪一下。"""
    for name in names:
        image(name)


def reset() -> None:
    """丢掉图片缓存。

    ⚠️ **必须**在"换了一个 Tk 根窗口"之后调用。``tk.PhotoImage`` 绑在建它时
    那个解释器上：第一个 ``tk.Tk()`` 销毁之后，旧图像在下一个根窗口里就成了
    野引用，一贴就报 ``image "pyimage1" doesn't exist``
    （写界面缩放测试时踩到的，五个用例全挂在这上面）。

    换界面缩放不用调这个 —— 那时根窗口没换，图像还能用。
    """
    _CACHE.clear()
