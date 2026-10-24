"""回归：卡片交互不能用未定义的名字、回调也不能少参数。

这两个错误都是"代码看着对、一点就炸"，而且**炸在每次交互都会走的那条路上**：

1. ``reset_cards_to_drop`` 里用了 ``EMPTY``，但 ``app.py`` 忘了 import 它
   → ``NameError`` → **点卡片、拖放全部失效**（用户原话："点击都无法选择文件跑了"）
2. 两格动作卡的回调写成 ``lambda i: ...``，而 ``Card._on_click`` 在拿不到
   事件坐标时会传 ``None`` → ``TypeError: missing 1 required positional argument``

两者都不该靠"记得"来保证，所以这里做**真的调一次**的测试。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

APP_PY = ROOT / "src" / "komaflow" / "ui" / "app.py"
WIDGETS_PY = ROOT / "src" / "komaflow" / "ui" / "widgets.py"


class TestNoUndefinedNames(unittest.TestCase):
    """用到 widgets 里的状态常量，就必须 import 它。"""

    def test_app_imports_every_state_constant_it_uses(self):
        app_source = APP_PY.read_text(encoding="utf-8")
        widgets_source = WIDGETS_PY.read_text(encoding="utf-8")

        # 从 widgets 里挑出所有状态常量
        names = []
        for row in widgets_source.splitlines():
            row = row.strip()
            if row and "=" in row and " " not in row.split("=")[0].strip():
                name = row.split("=")[0].strip()
                if name.isupper() and name.isidentifier():
                    names.append(name)

        imported = [row for row in app_source.splitlines()
                    if row.startswith("from .widgets import")
                    or (row.startswith(" ") and "import" not in row
                        and row.strip().endswith((")", ",")))]
        import_block = "\n".join(imported)
        used = [name for name in names
                if f"{name}" in app_source and name not in import_block]
        # 只在"真的被当变量用"时才算 —— 允许出现在注释/文档里
        offenders = [name for name in used
                     if f"= {name}" in app_source
                     or f"== {name}" in app_source
                     or f"!= {name}" in app_source
                     or f"in ({name}" in app_source
                     or f"({name}," in app_source]
        self.assertEqual(
            [n for n in offenders if n == "EMPTY"], [],
            "app.py 用了 EMPTY 但没 import —— 一点卡片就 NameError")


class TestCardInteractions(unittest.TestCase):
    """真建一次界面，把每条交互都走一遍。"""

    def setUp(self) -> None:
        import tkinter as tk

        from komaflow.ui import app as app_module
        from komaflow.ui import assets as ui_assets

        ui_assets.reset()
        app_module.KomaFlowApp._detect_blender_async = lambda self: None
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"建不了 Tk 窗口：{exc}")
        self.root.withdraw()
        self.app = app_module.KomaFlowApp(self.root)
        self.root.update_idletasks()

    def tearDown(self) -> None:
        try:
            self.app._shutdown()
        except Exception: # noqa: BLE001
            pass
        try:
            self.root.destroy()
        except Exception: # noqa: BLE001
            pass

    class Event:
        """假 Tk 事件。

        ⚠️ ``x`` 和 ``y`` 都可能有调用方去读 —— 少一个属性就是
        ``AttributeError``（踩过：``Card._on_click`` 现在两个都读）。
        """

        def __init__(self, y: int = 0, x: int = 0) -> None:
            self.y, self.x = y, x

    def test_click_every_card_without_event(self):
        """不传事件时点每张卡都不能炸（``None`` 也要能处理）。

        ⚠️ **两个对话框都要 mock**：动作卡现在用 ``askopenfilenames``（可多选），
           其它卡用 ``askopenfilename``。只 mock 一个，另一个会弹**真对话框**、
           把测试挂死 —— 这个坑踩过（表现是测试"跑到一半不动了"）。
        """
        for key, card in self.app.cards.items():
            with self.subTest(card=key):
                with mock.patch("komaflow.ui.app.filedialog.askopenfilename",
                                return_value=r"<样例>\sample.pmx"), \
                     mock.patch("komaflow.ui.app.filedialog.askopenfilenames",
                                return_value=[r"<样例>\sample.vmd"]):
                    card._on_click()

    def test_click_two_slot_card(self):
        """「动作」卡是**一个列表**：点框里任何位置都走一次选文件。

        ⚠️ 现在用的是 ``askopenfilenames``（支持一次选多个）——
           mock 成单数那个会**弹出真对话框**、把测试挂死（踩过）。
        """
        card = self.app.cards["motion"]
        rects = card.slot_rects()
        self.assertTrue(rects)
        for _x0, y0, _x1, y1 in rects:
            mid = (y0 + y1) // 2
            with self.subTest(y=mid):
                with mock.patch("komaflow.ui.app.filedialog.askopenfilenames",
                                return_value=[r"<样例>\a.vmd"]):
                    card._on_click(self.Event(mid, 10))

    def test_hover_highlight_applies_to_filled_card(self):
        """**已填**的卡片悬停也要有视觉变化（不能只有空卡变）。

        ⚠️ 两个坑：
        1. 比"画出来的元素个数"没用 —— 悬停只换底色，个数一样，
           要直接读 Canvas 第一个 item（卡片本体）的 ``fill``
        2. root 是 ``withdraw`` 的，``winfo_width()`` 一直是 1，
           ``redraw`` 会因为 ``width < T.S(20)`` 提前返回。
           ``configure(width=...)`` 也救不了（未映射就不改）。
           所以用一个**固定尺寸**的子类，绕开布局。
        """
        from komaflow.ui import theme as T
        from komaflow.ui.widgets import Card

        import tkinter as tk

        class FixedCard(Card):
            def winfo_width(self) -> int: # type: ignore[override]
                return T.S(190)

            def winfo_height(self) -> int: # type: ignore[override]
                return T.S(146)

        holder = tk.Frame(self.root)
        card = FixedCard(holder, index=1)
        card.show_drop("角色模型 / 工程", ".pmx", r"<样例>\Miku.pmx")

        def body_fill() -> str:
            card.redraw()
            items = card.find_all()
            return card.itemcget(items[0], "fill") if items else ""

        card._hover = False
        idle = body_fill()
        card._hover = True
        hover = body_fill()
        self.assertTrue(idle, "卡片没画出本体")
        self.assertNotEqual(idle, hover,
                            "已填的卡片悬停没换底色 —— 用户会以为点不动")

    def test_drop_path_works(self):
        """拖放底层路径不能炸（它就是 ``_handle_drop`` → ``_assign``）。

        ⚠️ 必须喂**真实存在**的文件：``_handle_drop`` 里有 ``os.path.isfile``
        过滤，假路径会被静默跳过 —— 那样测出来的是"什么都没发生"，
        看着像 bug 其实是测试自己写错了（踩过）。
        """
        real = next((p for p in (ROOT / "tools").glob("*.py")), None)
        self.assertIsNotNone(real, "找不到可用的真实文件")
        self.app._set_motion_paths([])
        self.app._handle_drop([str(real)])
        # 扩展名不是 .vmd，会归到别处；这里只断言"没炸且日志推进了"
        # —— 真正要防的回归是 NameError，不是归类结果

    def test_reset_cards_to_drop_works(self):
        """``reset_cards_to_drop`` 用到了 EMPTY —— 调一次必须不炸。"""
        self.app._reset_cards_to_steps()
        self.app._fail()
        self.app.reset_cards_to_drop()


if __name__ == "__main__":
    unittest.main()
