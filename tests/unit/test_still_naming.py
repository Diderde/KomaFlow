# -*- coding: utf-8 -*-
"""单帧预览的**命名**：默认跟着动作名走，用户改了名就听用户的。

用户原话：

> 瞬间导出，但是视频是一个，并不是用户导入的，并且这里的右面应该出现
> 一个命名窗口，没动就是显示默认名称（动作名称不带后缀）

两个要点：

1. 默认名 = **动作文件名去掉后缀**（不是固定的 ``still_000370.png``）
2. 产物落在**输出目录**（用户找得到），不是藏在中间产物目录里
"""

from __future__ import annotations

import sys
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from komaflow.core.pipeline import _safe_filename, default_still_name # noqa: E402
from komaflow.core.project import Inputs, Output, Project # noqa: E402
from komaflow.settings import Settings # noqa: E402


def _project(model: str = "", motions: list[str] | None = None) -> Project:
    return Project(
        name="Still",
        inputs=Inputs(route="assets", model=model, motions=list(motions or [])),
        output=Output(dir=".", basename="成片"),
    )


class TestDefaultStillName(unittest.TestCase):
    """默认名的取值顺序：动作名 > 模型名 > 兜底。"""

    def test_uses_motion_name_without_suffix(self):
        project = _project(model="示例模型.pmx", motions=["<示例>/示例动作.vmd"])
        self.assertEqual(default_still_name(project, 370), "示例动作",
                         "默认名要跟着动作走，并且去掉 .vmd 后缀")

    def test_falls_back_to_model_name(self):
        project = _project(model="<示例>/示例模型.pmx")
        self.assertEqual(default_still_name(project, 0), "示例模型")

    def test_falls_back_when_nothing_set(self):
        self.assertEqual(default_still_name(_project(), 0), "单帧预览")

    def test_first_motion_wins(self):
        """多个动作时取第一个（那是用户心里的"主动作"）。"""
        project = _project(motions=["D:/a/第一个.vmd", "D:/a/第二个.vmd"])
        self.assertEqual(default_still_name(project, 0), "第一个")

    def test_illegal_characters_are_cleaned(self):
        """名字里不能有 Windows 非法字符，否则存盘直接失败。"""
        self.assertEqual(_safe_filename('a<b>c:d"e/f\\g|h?i*j'), "a_b_c_d_e_f_g_h_i_j")

    def test_blank_name_falls_back(self):
        self.assertEqual(_safe_filename(" "), "单帧预览")
        self.assertEqual(_safe_filename("..."), "单帧预览")


class TestStillNameInUi(unittest.TestCase):
    """界面里那个「命名」框：没动就显示默认名，动了就别再覆盖。"""

    def setUp(self) -> None:
        import tempfile

        from komaflow.ui import assets as ui_assets

        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._patchers = [mock.patch.object(
            Settings, "path", classmethod(lambda cls: self.tmp / "settings.json"))]
        for p in self._patchers:
            p.start()
        ui_assets.reset()
        try:
            self.root = tk.Tk()
        except tk.TclError as exc: # pragma: no cover
            self.skipTest(f"建不了 Tk：{exc}")
        self.root.withdraw()

    def tearDown(self) -> None:
        try:
            self.root.destroy()
        except Exception: # noqa: BLE001
            pass
        for p in self._patchers:
            p.stop()
        self._tmp.cleanup()

    def _app(self):
        from komaflow.ui import app as app_module

        with mock.patch.object(app_module.KomaFlowApp, "_detect_blender_async",
                               lambda self: None):
            return app_module.KomaFlowApp(self.root)

    def test_box_shows_motion_name_by_default(self):
        app = self._app()
        motion = self.tmp / "示例动作.vmd"
        motion.write_bytes(b"Vocaloid Motion Data 0002")
        app._assign("motion", str(motion))
        self.assertEqual(app.vars["still_name"].get(), "示例动作",
                         "没动过命名框时，框里要**看得见**默认名")

    def test_box_tracks_new_motion_until_user_edits(self):
        """换掉动作（先删掉旧的）之后，默认名跟着换成新的。

        ⚠️ 注意动作是**列表**：再放一个文件是"追加"，第一个仍是主动作，
           所以默认名不会变 —— 只有把旧的那个删掉才算"换"。
        """
        app = self._app()
        first = self.tmp / "动作A.vmd"
        second = self.tmp / "动作B.vmd"
        for path in (first, second):
            path.write_bytes(b"Vocaloid Motion Data 0002")
        app._assign("motion", str(first))
        self.assertEqual(app.vars["still_name"].get(), "动作A")
        app._remove_motion_file(0) # 把 A 拿掉
        app._assign("motion", str(second))
        self.assertEqual(app.vars["still_name"].get(), "动作B")

    def test_adding_a_second_motion_keeps_the_first_as_default(self):
        """追加动作不改默认名 —— 第一个是主动作。"""
        app = self._app()
        first = self.tmp / "动作A.vmd"
        second = self.tmp / "补充动作.vmd"
        for path in (first, second):
            path.write_bytes(b"Vocaloid Motion Data 0002")
        app._assign("motion", str(first))
        app._assign("motion", str(second))
        self.assertEqual(app.vars["still_name"].get(), "动作A")

    def test_user_edit_is_never_overwritten(self):
        """用户改过名之后，换动作也不能把他填的冲掉。"""
        app = self._app()
        motion = self.tmp / "动作A.vmd"
        motion.write_bytes(b"Vocaloid Motion Data 0002")
        app._assign("motion", str(motion))
        app.vars["still_name"].set("我自己起的名字")
        app._refresh_panels()
        self.assertEqual(app.vars["still_name"].get(), "我自己起的名字")

    def test_empty_box_means_default(self):
        """框清空 = 回到"跟着动作走"。"""
        app = self._app()
        self.assertEqual(app._default_still_name_hint(), "单帧预览")


if __name__ == "__main__":
    unittest.main()
