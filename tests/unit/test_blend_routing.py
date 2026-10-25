"""回归：**点卡片选文件**和**拖放文件**必须走同一套归类。

甲方踩到的坑
------------
第 1 张卡（角色模型 / 工程）支持 ``.blend``，但 ``.blend`` 有**两种含义**：

* 放到**舞台卡** → 「环境」：只把里面的场景物件挂进来
* 放到**其它卡** → 「已配好的整份工程」：不组装，直接拿它渲

拖放那条路（``_assign``）有这个分岔；而**点卡片选文件**那条路
（``_browse_into``）原来是无脑 ``vars[key].set(path)`` ——
于是用户点第 1 张卡选了一个 ``.blend``，它进了 ``vars["model"]``、
``vars["blend"]`` 还是空的、``route`` 仍是 ``assets``，
build.py 就拿 PMX 导入器去读那个 .blend，报
「File signature is invalid.」→ **用户看到的结论是"不能渲染"**。

这个测试盯的就是：两条路的结果必须一致。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))


class TestBlendRouting(unittest.TestCase):
    """``.blend`` 该进哪个字段 —— 点选与拖放必须一致。"""

    def setUp(self) -> None:
        import tkinter as tk

        from komaflow.ui import app as app_module
        from komaflow.ui import assets as ui_assets

        ui_assets.reset()
        app_module.KomaFlowApp._detect_blender_async = lambda self: None
        try:
            self.root = tk.Tk()
        except tk.TclError as exc: # 没有显示环境就跳过
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

    def _clear(self) -> None:
        # ⚠️ 动作不在 ``vars`` 里了（它是 ``self.motion_list``，可以有任意多个）。
        for key in ("model", "blend", "stage", "camera"):
            self.app.vars[key].set("")
        self.app._set_motion_paths([])

    def test_drop_blend_on_model_card_goes_to_blend(self):
        self._clear()
        self.app._assign("model", r"<样例>\scene.blend")
        self.assertEqual(self.app.vars["blend"].get(), r"<样例>\scene.blend")
        self.assertEqual(self.app.vars["model"].get(), "")

    def test_drop_blend_on_stage_card_goes_to_stage(self):
        self._clear()
        self.app._assign("stage", r"<样例>\dark.blend")
        self.assertEqual(self.app.vars["stage"].get(), r"<样例>\dark.blend")
        self.assertEqual(self.app.vars["blend"].get(), "")

    def test_browse_blend_on_model_card_goes_to_blend(self):
        """**这条就是甲方踩到的那个 bug。**"""
        self._clear()
        with mock.patch("komaflow.ui.app.filedialog.askopenfilename",
                        return_value=r"<示例>\示例模型.blend"):
            self.app._browse_into("model", "model")
        self.assertEqual(self.app.vars["blend"].get(), r"<示例>\示例模型.blend")
        self.assertEqual(self.app.vars["model"].get(), "",
                         "点选 .blend 不该塞进 model —— route 会算错")

    def test_browse_route_becomes_blend(self):
        """接口层：``route`` 必须跟着变成 ``blend``，build.py 才不会用 PMX 导入器。"""
        self._clear()
        with mock.patch("komaflow.ui.app.filedialog.askopenfilename",
                        return_value=r"<样例>\scene.blend"):
            self.app._browse_into("model", "model")
        project = self.app._collect_project()
        self.assertEqual(project.inputs.route, "blend")
        self.assertEqual(project.inputs.blend, r"<样例>\scene.blend")
        self.assertIsNone(project.inputs.model)

    def test_browse_pmx_stays_in_model(self):
        """正常 .pmx 还是进 model —— 别把分岔写成"一律进 blend"。"""
        self._clear()
        with mock.patch("komaflow.ui.app.filedialog.askopenfilename",
                        return_value=r"<样例>\Miku.pmx"):
            self.app._browse_into("model", "model")
        self.assertEqual(self.app.vars["model"].get(), r"<样例>\Miku.pmx")
        self.assertEqual(self.app.vars["blend"].get(), "")

    def test_browse_expression_slot_goes_to_expression(self):
        """动作卡里的文件统一进 ``motions`` 列表（不再分动作/表情字段）。"""
        self._clear()
        with mock.patch("komaflow.ui.app.filedialog.askopenfilenames",
                        return_value=[r"<示例>\示例表情.vmd"]):
            self.app._browse_zone("motion")
        self.assertEqual(self.app._motion_paths(), [r"<示例>\示例表情.vmd"])

    def test_browse_motion_slot_stays_motion(self):
        self._clear()
        with mock.patch("komaflow.ui.app.filedialog.askopenfilenames",
                        return_value=[r"<示例>\示例动作.vmd"]):
            self.app._browse_zone("motion")
        self.assertEqual(self.app._motion_paths(), [r"<示例>\示例动作.vmd"])

    def test_browse_motion_can_add_several(self):
        """一次选多个 → 全部进列表，顺序保持。"""
        self._clear()
        with mock.patch("komaflow.ui.app.filedialog.askopenfilenames",
                        return_value=[r"<样例>\a.vmd", r"<样例>\b.vmd",
                                      r"<样例>\c.vmd"]):
            self.app._browse_zone("motion")
        self.assertEqual(self.app._motion_paths(),
                         [r"<样例>\a.vmd", r"<样例>\b.vmd", r"<样例>\c.vmd"])

    def test_motion_remove_and_reorder_are_independent(self):
        """删掉中间那个，其余顺序不变。"""
        self._clear()
        self.app._set_motion_paths([r"<样例>\a.vmd", r"<样例>\b.vmd", r"<样例>\c.vmd"])
        self.app._remove_motion_file(1)
        self.assertEqual(self.app._motion_paths(), [r"<样例>\a.vmd", r"<样例>\c.vmd"])


    def test_blend_on_model_card_asks_when_context_exists(self):
        """已经放了场景/动作时，拖 .blend 到角色卡要先问，别默默顶掉。

        用户报的原话：「场景导进去出来场景消失了」—— 就是被默默顶掉的。
        """
        self._clear()
        self.app.vars["stage"].set(r"<样例>\场景.blend")
        with mock.patch("komaflow.ui.app.messagebox.askyesno",
                        return_value=False) as ask:
            self.app._assign("model", r"<样例>\角色.blend")
        self.assertTrue(ask.called, "有场景在时要问一句")
        self.assertEqual(self.app.vars["stage"].get(), r"<样例>\角色.blend",
                         "选「否」→ 放进舞台当场景")
        self.assertEqual(self.app.vars["blend"].get(), "")

    def test_blend_on_model_card_keeps_whole_project_when_confirmed(self):
        self._clear()
        self.app.vars["stage"].set(r"<样例>\场景.blend")
        with mock.patch("komaflow.ui.app.messagebox.askyesno",
                        return_value=True):
            self.app._assign("model", r"<样例>\角色.blend")
        self.assertEqual(self.app.vars["blend"].get(), r"<样例>\角色.blend")
        self.assertEqual(self.app.vars["stage"].get(), r"<样例>\场景.blend")


if __name__ == "__main__":
    unittest.main()
