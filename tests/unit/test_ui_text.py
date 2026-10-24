"""界面里那两件"文字"的护栏测试。

守两件事：

1. **悬停提示真的会弹出来**，而且鼠标一走就收掉。
   ``ui/tip.py`` 是靠 ``after`` 定时器做延迟的，很容易写成"定时器挂在会被
   销毁的窗口上"或者"走开不取消"—— 那两种都不会报错，只会悄悄漏一个窗口在屏幕上。
   这里用 ``after`` 的毫秒数直接触发，不睡真实时间。
2. **助手卡那几句话不会被气泡截断**。
   气泡只有一行高，超一个字就折行、把卡片顶变形（见 ``widgets.BUBBLE_CHARS``）。

⚠️ 这两个测试要建 Tk 窗口，所以**没有显示器的环境会自动跳过**，
不会让 CI 挂掉。
"""

from __future__ import annotations

import tkinter as tk
import unittest

from komaflow.ui import tip, widgets


def _settle(widget: tk.Misc, rounds: int = 20) -> None:
    """把事件泵到控件**真正映射出来**为止。

    只调一次 ``update()`` 不够：Tk 要在收到 ``<Map>`` 之后才算 mapped，
    而 ``tip`` 靠这个判断控件在不在屏幕上（控件还没显示就不该有提示）。
    一次 update 偶尔赶不上，所以这里多泵几轮。
    """
    root = widget.winfo_toplevel()
    for _ in range(rounds):
        root.update_idletasks()
        root.update()
        if widget.winfo_ismapped():
            return


def _make_root() -> tk.Tk:
    """建一个真正映射出来的根窗口（原因见 :func:`_settle`）。"""
    root = tk.Tk()
    root.geometry("240x120+40+40")
    root.update()
    return root


class TestTip(unittest.TestCase):
    """悬停提示的显示与收回。"""

    def setUp(self) -> None:
        try:
            self.root = _make_root()
        except tk.TclError as exc: # 没有图形环境
            self.skipTest(f"建不了 Tk 窗口：{exc}")

    def tearDown(self) -> None:
        try:
            self.root.destroy()
        except (tk.TclError, AttributeError):
            pass

    def test_enter_then_delay_shows_tooltip(self):
        label = tk.Label(self.root, text="目标")
        label.pack()
        _settle(label)
        bubble = tip.attach(label, "这是一条提示")

        self.assertIsNone(bubble.window)
        label.event_generate("<Enter>")
        self.root.update()
        # 延迟没到，还不该弹
        self.assertIsNone(bubble.window)

        bubble._show() # 直接跳过等待
        self.root.update()
        self.assertIsNotNone(bubble.window)
        self.assertTrue(bubble.window.winfo_exists())

    def test_leave_hides_tooltip(self):
        label = tk.Label(self.root, text="目标")
        label.pack()
        _settle(label)
        bubble = tip.attach(label, "这是一条提示")
        bubble._show()
        self.root.update()
        self.assertIsNotNone(bubble.window)

        label.event_generate("<Leave>")
        self.root.update()
        self.assertIsNone(bubble.window)

    def test_destroying_widget_does_not_leave_window(self):
        """控件没了，提示窗也必须跟着没 —— 否则屏幕上会留一块孤儿小窗。"""
        frame = tk.Frame(self.root)
        frame.pack()
        label = tk.Label(frame, text="目标")
        label.pack()
        _settle(label)
        bubble = tip.attach(label, "这是一条提示")
        bubble._show()
        self.root.update()
        self.assertIsNotNone(bubble.window)

        label.destroy()
        self.root.update()
        self.assertIsNone(bubble.window)
        self.assertFalse(bubble._alive)

    def test_empty_text_never_shows(self):
        label = tk.Label(self.root, text="目标")
        label.pack()
        _settle(label)
        bubble = tip.attach(label, "")
        bubble._show()
        self.root.update()
        self.assertIsNone(bubble.window)


class TestBubbleLines(unittest.TestCase):
    """助手卡那几句话必须放得下一行。"""

    #: 界面上会出现的那几句（改文案时同步这里）
    LINES = (
        "拖素材到卡片上，开工啦。",
        "素材放好啦，等你点头。",
        "我盯着进度，摇铃报数。",
        "出片啦，收工！",
        "这轮没通，底下有提示。",
    )

    def test_lines_fit_one_line(self):
        for line in self.LINES:
            with self.subTest(line=line):
                self.assertEqual(widgets._one_line(line), line,
                                 f"{len(line)} 字超过气泡上限 "
                                 f"{widgets.BUBBLE_CHARS}，会被截断")

    def test_too_long_text_is_truncated_with_ellipsis(self):
        long_line = "把素材拖到右边的卡片上，就能开始。"
        result = widgets._one_line(long_line)
        self.assertLessEqual(len(result), widgets.BUBBLE_CHARS)
        self.assertTrue(result.endswith("…"))


if __name__ == "__main__":
    unittest.main()
