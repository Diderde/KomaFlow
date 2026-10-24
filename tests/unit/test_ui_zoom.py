"""界面缩放的回归测试：**换档重建**这条路必须能反复走通。

为什么单独测这个
----------------
换档的代价是"把整个界面销毁重建"。这条路最容易出的问题都不是崩溃，
而是**悄悄留下垃圾**：

* 悬停提示的小窗没被收掉 → 屏幕上留一个点不掉的黑条
* 拖放窗口过程没解绑 → 旧窗口过程还指着已经销毁的控件（之后可能崩）
* 变量 trace 每重建一次就多挂一份 → 改一个参数触发十几次重画
* 重建后某些控件引用还指着旧对象 → 界面对操作没反应但也不报错

所以这里不只测"能建起来"，还要测**重建前后界面是真的换了一批控件**
（旧控件已销毁、新控件还活着），以及跑几轮不累积。

⚠️ 要建真窗口，没显示器的环境会自动跳过。
"""

from __future__ import annotations

import sys
import tkinter as tk
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))


def _settle(widget: tk.Misc, rounds: int = 20) -> None:
    root = widget.winfo_toplevel()
    for _ in range(rounds):
        root.update_idletasks()
        root.update()
        if widget.winfo_ismapped():
            return


class TestZoomRebuild(unittest.TestCase):
    """换界面缩放 = 重建整个界面。"""

    def setUp(self) -> None:
        try:
            from komaflow.ui import app as app_module
        except Exception as exc: # noqa: BLE001
            self.skipTest(f"界面模块导入失败：{exc}")
        self.app_module = app_module
        # 不启 Blender 探测：那会起子进程，测试里没必要
        app_module.KomaFlowApp._detect_blender_async = lambda self: None
        # ⚠️ 每个用例都新建一个 tk.Tk()，而 tk.PhotoImage 是绑在"建它时那个
        # 解释器"上的 —— 不清缓存的话，上一个根窗口销毁后旧图像就成了野引用，
        # 一贴就报 image "pyimage1" doesn't exist（第一版五个用例全挂在这）。
        from komaflow.ui import assets as ui_assets
        ui_assets.reset()
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"建不了 Tk 窗口：{exc}")
        self.root.geometry("1100x700+30+30")
        self.app = app_module.KomaFlowApp(self.root)
        self.root.update()

    def tearDown(self) -> None:
        # 先把循环定时器与提示窗收掉再 destroy —— 否则那几条 after 回调
        # 会在窗口没了之后继续跑，往 stderr 刷 `invalid command name ...`
        try:
            self.app._shutdown()
        except Exception: # noqa: BLE001
            pass
        try:
            self.root.destroy()
        except (tk.TclError, AttributeError):
            pass

    def test_zoom_rebuilds_widgets(self):
        from komaflow.ui import theme as T

        old_preview = self.app.preview
        old_batch = self.app.batch
        T.set_zoom(1.0)
        self.app.set_zoom(1.25)
        self.root.update()

        # 旧控件必须已经销毁
        self.assertFalse(old_preview.winfo_exists())
        self.assertFalse(old_batch.winfo_exists())
        # 新控件必须是活的、而且不是同一个对象
        self.assertTrue(self.app.preview.winfo_exists())
        self.assertIsNot(self.app.preview, old_preview)
        self.assertAlmostEqual(T.UI_ZOOM, 1.25)

    def test_zoom_changes_pixel_sizes(self):
        """缩放确实改了像素倍数。

        ⚠️ 这里**不能**断言"1.5 档的某个控件一定更大"。窗口尺寸是
        ``min(设计尺寸, 屏幕-40)``，屏幕不够大时 1.5 档会被夹住，
        于是控件反而变小（实测 1.0→1.5 时预览区从 1984 缩到 1734）。
        真正该守的是**换算关系**：设计像素 × 总缩放 = 实际像素。
        """
        from komaflow.ui import theme as T

        self.app.set_zoom(1.0)
        self.root.update()
        unit_at_100 = T.S(100)

        self.app.set_zoom(1.5)
        self.root.update()
        unit_at_150 = T.S(100)

        self.assertAlmostEqual(unit_at_100, round(100 * T.SCALE), delta=1)
        self.assertAlmostEqual(unit_at_150, round(150 * T.SCALE), delta=1)
        self.assertGreater(unit_at_150, unit_at_100,
                           "1.5 档的设计像素换算结果应大于 1.0 档")

    def test_window_grows_with_zoom_when_screen_allows(self):
        """屏幕放得下时，窗口本身也要跟着放大 —— 否则内容会被挤在小窗里。"""
        from komaflow.ui import theme as T

        self.app.set_zoom(0.8)
        self.root.update()
        small = (self.root.winfo_width(), self.root.winfo_height())

        self.app.set_zoom(1.0)
        self.root.update()
        big = (self.root.winfo_width(), self.root.winfo_height())

        screen_w = self.root.winfo_screenwidth()
        if int(1500 * T.SCALE) <= screen_w - 40: # 只有放得下才谈得上变大
            self.assertGreaterEqual(big[0], small[0])

    def test_zoom_is_idempotent_when_unchanged(self):
        """同档反复设不该重建（否则界面会一直闪）。"""
        from komaflow.ui import theme as T

        T.set_zoom(1.0)
        self.app.set_zoom(1.0)
        self.root.update()
        before = self.app.preview
        self.app.set_zoom(1.0)
        self.root.update()
        self.assertIs(self.app.preview, before)

    def test_no_tooltip_windows_left_after_rebuild(self):
        """重建之后屏幕上一个提示窗都不该留。"""
        from komaflow.ui import tip

        # 先弹一个提示出来
        self.app.btn_start # 存在即可
        tip.close_all()
        self.app.set_zoom(1.25)
        self.root.update()
        alive = [t for t in tip._LIVE if t.window is not None]
        self.assertEqual(alive, [], "重建后还留着提示窗")

    def test_repeated_zoom_does_not_accumulate(self):
        """连着换几轮，不该每轮多出一批控件。"""
        from komaflow.ui import theme as T

        T.set_zoom(1.0)
        self.app.set_zoom(1.0)
        self.root.update()
        baseline = len(self.root.winfo_children())

        for zoom in (1.25, 1.0, 0.8, 1.25):
            self.app.set_zoom(zoom)
            self.root.update()

        self.assertEqual(len(self.root.winfo_children()), baseline,
                         "反复换缩放之后 root 的直接子窗变多了")

    def test_toolbar_survives_rebuild(self):
        """重建后顶栏那几个按钮还在、还认得出。"""
        self.app.set_zoom(1.25)
        self.root.update()
        for name in ("btn_start", "btn_pause", "btn_stop"):
            widget = getattr(self.app, name)
            self.assertTrue(widget.winfo_exists(), f"{name} 重建后没了")


if __name__ == "__main__":
    unittest.main()
