"""回归：卡片的**删除按钮**、以及**合并行不能重叠**。

用户截图指出两件事：

1. 合并成一行之后显示成 ``动作 / 表情示例动作动作.vmd ＋ 示例动作表情.vmd`` ——
   **标签和文件名粘在一起**。
   实测：两个文件名拼起来 228px，扣掉标签后只剩 144px，必然重叠。
2. 「应该有删除」—— 放了文件之后必须能撤掉，否则选错一个只能重启程序。

这两条都属于"看着没问题、一画就露馅"，所以用 **Tk 真实坐标**去验，
而不是只断言源码里有没有那句话。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))


class TestCardClearButton(unittest.TestCase):
    """右上角「×」：有内容才出现，点了要回调，不能抢走选文件。"""

    def setUp(self) -> None:
        import tkinter as tk

        from komaflow.ui import theme as T
        from komaflow.ui import assets as ui_assets
        from komaflow.ui.widgets import Card

        ui_assets.reset()
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"建不了 Tk 窗口：{exc}")
        self.root.withdraw()
        self.T = T
        self.Card = Card
        self.holder = tk.Frame(self.root)

    def tearDown(self) -> None:
        try:
            self.root.destroy()
        except Exception: # noqa: BLE001
            pass

    def _card(self, slots=(), **kw):
        from komaflow.ui import theme as T

        class Fixed(self.Card):
            def winfo_width(self) -> int: # type: ignore[override]
                return T.S(190)

            def winfo_height(self) -> int: # type: ignore[override]
                return T.S(146)

        return Fixed(self.holder, index=1, slots=slots, **kw)

    @staticmethod
    def _event(x: int, y: int):
        return type("E", (), {"x": x, "y": y})()

    def test_no_clear_button_when_empty(self):
        card = self._card()
        card.show_drop("角色模型", ".pmx")
        self.assertIsNone(card.clear_rect(), "空卡不该有「×」")

    def test_clear_button_appears_when_filled(self):
        card = self._card()
        card.show_drop("角色模型", ".pmx", r"<样例>\Miku.pmx")
        self.assertIsNotNone(card.clear_rect(), "放了文件就该有「×」")

    def test_click_clear_calls_clear_command(self):
        hits: list[int] = []
        card = self._card(clear_command=lambda: hits.append(1),
                          command=lambda *_: hits.append(2))
        card.show_drop("角色模型", ".pmx", r"<样例>\Miku.pmx")
        rect = card.clear_rect()
        card._on_click(self._event((rect[0] + rect[2]) // 2,
                                   (rect[1] + rect[3]) // 2))
        self.assertEqual(hits, [1], "点「×」应该只触发删除，不触发选文件")

    def test_two_slot_card_filled_has_clear_button(self):
        card = self._card(slots=("动作", "表情"), merge_label="动作 / 表情")
        card.show_slots("动作", [r"<样例>\a.vmd", ""])
        self.assertIsNotNone(card.clear_rect())

    def test_click_outside_clear_still_browses(self):
        hits: list[int] = []
        card = self._card(clear_command=lambda: hits.append(1),
                          command=lambda *_: hits.append(2))
        card.show_drop("角色模型", ".pmx", r"<样例>\Miku.pmx")
        card._on_click(self._event(20, 130)) # 卡片下部，离「×」很远
        self.assertEqual(hits, [2], "点卡片其它位置仍应该开文件对话框")


class TestSingleBoxNoCategoryLabels(unittest.TestCase):
    """「动作」卡是**一个框**，里面只列文件名，**不显示分类标签**。

    用户要求（原话）：

    > 表情和动作可以直接导入不用现在一样分两个吧，毕竟有些作者他不写那个
    > 是动作哪个是表情
    > 无序分类

    所以界面上不该出现「动作 / 表情」这种让人分类的字样。
    """

    def setUp(self) -> None:
        import tkinter as tk

        from komaflow.ui import theme as T
        from komaflow.ui import assets as ui_assets
        from komaflow.ui.widgets import Card

        ui_assets.reset()
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"建不了 Tk 窗口：{exc}")
        self.root.withdraw()

        class Fixed(Card):
            def winfo_width(self) -> int: # type: ignore[override]
                return T.S(190)

            def winfo_height(self) -> int: # type: ignore[override]
                return T.S(150)

        self.card = Fixed(tk.Frame(self.root), index=2, slots=("动作", "表情"))
        self.card.show_slots("动作", [r"<样例>\动作.vmd",
                                     r"<样例>\素材.vmd"])
        self.card.redraw()

    def tearDown(self) -> None:
        try:
            self.root.destroy()
        except Exception: # noqa: BLE001
            pass

    def _texts(self) -> list[str]:
        return [self.card.itemcget(i, "text")
                for i in self.card.find_all() if self.card.type(i) == "text"]

    def test_no_category_labels_on_screen(self):
        """**这条就是用户要的「无序分类」。**

        ⚠️ 卡片**标题**就是「动作」（这张卡管的就是动作+表情），
        所以不能断言"界面上不出现「动作」两个字" —— 那会把标题也误判。
        要禁的是**作为分类标签**出现的那几个（标签是单独一段文字）。
        """
        texts = self._texts()
        for banned in ("动作 / 表情", "动作/表情"):
            self.assertNotIn(banned, texts,
                             f"界面上还出现了分类标签「{banned}」")
        # 「表情」只该作为**文件名的一部分**出现，不该是独立的一段文字
        self.assertNotIn("表情", texts, "「表情」被当成分类标签画出来了")

    def test_only_title_and_filenames(self):
        """框里只有文件名，没有额外的分类文字。"""
        texts = self._texts()
        # 标题 1 段 + 序号 1 段 + 文件名 2 段 = 4 段，不该再有别的
        self.assertEqual(len(texts), 4, f"多出了文字：{texts}")

    def test_filenames_are_listed(self):
        texts = self._texts()
        self.assertIn("动作.vmd", texts)
        self.assertIn("素材.vmd", texts)

    def test_filenames_do_not_overlap(self):
        """一个框里列两行，两行 bbox 不能相交。

        ⚠️ 行高写死会露馅：字体实际高度约 20px，写 13px 会让相邻两行
        bbox 差 1px 重叠（肉眼看不出来，只能量）。
        """
        boxes = [(self.card.itemcget(i, "text"), self.card.bbox(i))
                 for i in self.card.find_all()
                 if self.card.type(i) == "text"]
        vmd = [(t, b) for t, b in boxes if b and t.endswith(".vmd")]
        self.assertEqual(len(vmd), 2)
        (t0, b0), (t1, b1) = vmd[0], vmd[1]
        overlap = not (b1[0] > b0[2] or b1[2] < b0[0]
                       or b1[1] > b0[3] or b1[3] < b0[1])
        self.assertFalse(overlap, f"两个文件名重叠：{t0}{b0} vs {t1}{b1}")

    def test_whole_box_is_one_clickable_area(self):
        """整个框都是可点的 —— 不分左右/上下格（用户不该为落点操心）。"""
        rects = self.card.slot_rects()
        self.assertTrue(rects)
        top = rects[0][1] + 2
        bottom = rects[-1][3] - 2
        self.assertIsNotNone(self.card.slot_at_point(top))
        self.assertIsNotNone(self.card.slot_at_point(bottom))

    def test_empty_box_shows_placeholder(self):
        self.card.show_slots("动作", ["", ""])
        self.card.redraw()
        self.assertIn("点这里选，或拖进来", self._texts())

    def test_clear_button_present_when_filled(self):
        self.assertIsNotNone(self.card.clear_rect())


if __name__ == "__main__":
    unittest.main()
