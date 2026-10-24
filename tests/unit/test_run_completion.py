"""回归：**收尾必须解锁界面**、**进度必须按时间刷**。

这两个都是用户实际踩到的：

1. "失败时无法更改文件" —— ``self.mode = "run"`` 在开始渲染时设上，
   但全文件**没有一处**把它改回 ``"config"``；而渲染失败走的 ``_fail()``
   连 ``_set_busy(False)`` 都不调。于是点过一次「开始渲染」之后，
   拖放、点卡片选文件全被 ``if self.mode == "run": return`` 挡掉，
   **只能重启程序**。

2. "不知道渲染进度" —— 进度是按**帧数**节流的（每 25 帧写一次进度文件），
   慢工程一帧好几秒 → 好几分钟才更新一次，界面上看着像卡死。

这两个都属于"功能都在、但有一条路径忘了收尾"的类型，所以用**接口级**的
断言钉住（而不是去测 UI 像素）。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

RENDER_PY = (ROOT / "src" / "komaflow" / "adapters" / "scripts" / "render.py")
APP_PY = ROOT / "src" / "komaflow" / "ui" / "app.py"


class TestProgressIsTimeBased(unittest.TestCase):
    """进度必须按时间刷，不能按帧数。"""

    def setUp(self) -> None:
        self.source = RENDER_PY.read_text(encoding="utf-8")

    def test_has_render_pre_hook(self):
        """必须有 render_pre —— 一帧渲很久时，至少能看到"正在渲第几帧"。"""
        self.assertIn("handlers.render_pre.append(on_render_pre)", self.source)
        self.assertIn("def on_render_pre(", self.source)

    def test_no_frame_count_throttling(self):
        """不能再出现按帧数节流的**代码**。

        ⚠️ 只搜 ``done % progress_every`` 是不行的 ——
        注释里为了说明"原来错在哪"也写了这句，一搜就撞上（踩过）。
        所以改成搜**节流的写法**：不能再有 ``if done % ... == 0`` 那种判断。
        """
        import re

        code_lines = [row for row in self.source.splitlines()
                      if not row.lstrip().startswith("#")]
        code = "\n".join(code_lines)
        self.assertIsNone(
            re.search(r"if\s+done\s*%\s*\w+\s*==", code),
            "还有按帧数节流的判断 —— 慢工程会好几分钟不更新进度")

    def test_time_based_threshold_exists(self):
        self.assertIn("PROGRESS_SECONDS", self.source)
        self.assertIn("def _flush(", self.source)

    def test_both_hooks_removed_after_render(self):
        """钩子用完要摘掉，不然下次渲染会重复挂。"""
        self.assertIn("handlers.render_pre.remove(on_render_pre)", self.source)
        self.assertIn("handlers.render_post.remove(on_render_post)", self.source)


class TestRunEndUnlocksUi(unittest.TestCase):
    """跑完（成功或失败）必须把界面解锁。"""

    #: 从方法定义切到下一个方法定义为止 —— 比写死偏移可靠
    @staticmethod
    def _body(source: str, name: str) -> str:
        # ⚠️ 方法签名可能是 ``(self)`` 也可能是 ``(self, paths)``，
        # 写死 ``def name(self)`` 会漏掉带参数的方法（踩过）
        marker = f"def {name}("
        start = source.index(marker)
        rest = source[start + len(marker):]
        nxt = rest.find("\n def ")
        return rest[: nxt if nxt > 0 else len(rest)]

    def setUp(self) -> None:
        self.source = APP_PY.read_text(encoding="utf-8")

    def test_fail_calls_set_busy_false(self):
        """``_fail()`` 必须调 ``_set_busy(False)`` —— 它是复位 mode 的地方。"""
        body = self._body(self.source, "_fail")
        self.assertIn("_set_busy(False)", body,
                      "_fail() 没解锁界面 —— 渲染一失败就改不了素材了")

    def test_set_busy_resets_mode(self):
        """``_set_busy(False)`` 里必须有把 mode 改回 config 的那句。"""
        body = self._body(self.source, "_set_busy")
        self.assertIn('self.mode = "config"', body)

    def test_run_mode_is_set_somewhere(self):
        self.assertIn('self.mode = "run"', self.source)

    def test_fail_marks_after_unlock(self):
        """先解锁、再标失败 —— 反了的话"失败"标记会被重画擦掉。"""
        body = self._body(self.source, "_fail")
        unlock = body.index("_set_busy(False)")
        mark = body.index("FAILED")
        self.assertLess(unlock, mark, "应当先解锁再标失败")


class TestEditingAfterRun(unittest.TestCase):
    """跑完之后还能改素材 —— 真建一次界面来验。"""

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

    def test_mode_returns_to_config_after_fail(self):
        from komaflow.ui import app as app_module

        self.app._reset_cards_to_steps()
        self.assertEqual(self.app.mode, "run")
        self.app._fail()
        self.assertEqual(self.app.mode, "config",
                         "失败之后 mode 没复位 —— 素材会改不了")

    def test_mode_returns_to_config_after_finish(self):
        self.app._reset_cards_to_steps()
        self.assertEqual(self.app.mode, "run")
        self.app._set_busy(False)
        self.assertEqual(self.app.mode, "config")

    def test_can_assign_after_fail(self):
        """失败之后 ``_assign`` 必须还能写进变量（这是"改文件"的底层动作）。

        ⚠️ 动作现在进的是 ``self.motion_list``（可以有任意多个），
           不再是 ``vars["motion"]``。
        """
        self.app._reset_cards_to_steps()
        self.app._fail()
        self.app._set_motion_paths([])
        self.app._assign("motion", r"<样例>\另一个动作.vmd")
        self.assertEqual(self.app._motion_paths(), [r"<样例>\另一个动作.vmd"])

    def test_drop_guard_only_blocks_while_running(self):
        """``_handle_drop`` 的守卫只在真跑着的时候拦，跑完就不该拦。"""
        body = TestRunEndUnlocksUi._body(APP_PY.read_text(encoding="utf-8"),
                                         "_handle_drop")
        self.assertIn('if self.mode == "run"', body)
        # 守卫之后要能继续走 —— 而且会先把卡片恢复成投放态
        self.assertIn("reset_cards_to_drop", body)


if __name__ == "__main__":
    unittest.main()
