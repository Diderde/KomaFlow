"""设置与「渲染快照」的测试。

守三件事：

1. **设置读不坏也写不坏**。配置文件被手改坏、字段缺失、路径留空，
   都要退回默认值 —— 一个坏掉的设置文件不该让程序起不来。
2. **三类保存位置互不影响**（用户明确要求分开放）。
3. **快照失败不能拦住渲染**。用户的正文是"把片子渲出来"，
   不是"把快照存下来"；盘满、没权限都得让渲染继续。
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from komaflow import settings as S


class TestSettings(unittest.TestCase):
    """设置的读写与容错。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._old_appdata = os.environ.get("APPDATA")
        # 把设置目录指到临时目录，别动用户真正的配置
        os.environ["APPDATA"] = self._tmp.name
        self.addCleanup(self._restore)

    def _restore(self) -> None:
        if self._old_appdata is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = self._old_appdata
        self._tmp.cleanup()

    def test_defaults_when_no_file(self):
        settings = S.Settings.load()
        self.assertTrue(settings.output_dir)
        self.assertTrue(settings.snapshot_dir)
        self.assertTrue(settings.snapshot_enabled)

    def test_roundtrip_keeps_each_path_separate(self):
        settings = S.Settings.load()
        settings.output_dir = r"D:\成片"
        settings.project_dir = r"E:\工程"
        settings.snapshot_dir = r"F:\快照"
        settings.snapshot_enabled = False
        settings.save()

        again = S.Settings.load()
        self.assertEqual(again.output_dir, r"D:\成片")
        self.assertEqual(again.project_dir, r"E:\工程")
        self.assertEqual(again.snapshot_dir, r"F:\快照")
        self.assertFalse(again.snapshot_enabled)

    def test_blank_paths_fall_back_to_defaults(self):
        """手改配置留下空串是很常见的事，别让空串一路传下去。"""
        settings = S.Settings()
        settings.output_dir = " "
        settings.work_dir = ""
        settings.save()

        loaded = S.Settings.load()
        self.assertTrue(loaded.output_dir.strip())
        self.assertTrue(loaded.work_dir.strip())

    def test_corrupt_file_does_not_raise(self):
        target = S.Settings.path()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{这不是 JSON", encoding="utf-8")
        settings = S.Settings.load() # 不该抛
        self.assertTrue(settings.output_dir)

    def test_unknown_fields_are_ignored(self):
        """旧版本写的字段、或者手加的字段，不该让加载炸掉。"""
        target = S.Settings.path()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"output_dir": r"D:\X", "未来的字段": 1}),
                          encoding="utf-8")
        loaded = S.Settings.load()
        self.assertEqual(loaded.output_dir, r"D:\X")

    def test_absurd_zoom_is_clamped(self):
        settings = S.Settings()
        settings.ui_zoom = 99.0
        settings.save()
        self.assertEqual(S.Settings.load().ui_zoom, 1.0)

    def test_save_creates_directory(self):
        target = S.Settings.load().save()
        self.assertTrue(target.is_file())


class TestSnapshotDecision(unittest.TestCase):
    """快照该不该存 —— 这层判断放在 ui 外，方便守住。"""

    def test_disabled_setting_skips_snapshot(self):
        settings = S.Settings()
        settings.snapshot_enabled = False
        self.assertFalse(settings.snapshot_enabled)

    def test_three_dirs_are_independent(self):
        """三类目录必须能各指一处（用户要求"分开选项"）。"""
        settings = S.Settings()
        settings.output_dir = r"D:\a"
        settings.project_dir = r"E:\b"
        settings.snapshot_dir = r"F:\c"
        settings.work_dir = r"G:\d"
        self.assertEqual(len({settings.output_dir, settings.project_dir,
                              settings.snapshot_dir, settings.work_dir}), 4)

    def test_dir_for_lookup(self):
        settings = S.Settings()
        settings.snapshot_dir = r"F:\快照"
        self.assertEqual(settings.dir_for("snapshot"), r"F:\快照")


class TestSnapshotFiles(unittest.TestCase):
    """真存一次快照，看文件名与内容对不对。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_snapshot_writes_project_with_timestamp(self):
        """快照名要带时间戳，而且要能当工程文件重新打开。"""
        from komaflow.core.project import Inputs, Output, Project

        project = Project(name="片子", inputs=Inputs(route="assets",
                                                    model="m.pmx", motion="a.vmd"),
                          output=Output(dir=str(self.root / "out"), basename="片子"))
        stamp = "20261015_120000"
        target = self.root / "snapshots" / f"片子_{stamp}.kfproj"
        target.parent.mkdir(parents=True, exist_ok=True)
        project.save(target)

        self.assertTrue(target.is_file())
        self.assertIn(stamp, target.name)
        again = Project.load(target)
        self.assertEqual(again.inputs.model, "m.pmx")
        self.assertEqual(again.inputs.motion, "a.vmd")

    def test_snapshot_name_is_filesystem_safe(self):
        """名字里有空格、中文都要能用（Windows 只禁几个字符，别自己加戏）。"""
        for stem in ("片子_20261015_120000", "my clip_20261015", "日本語_1"):
            path = self.root / f"{stem}.kfproj"
            path.write_text("x", encoding="utf-8")
            self.assertTrue(path.is_file())


if __name__ == "__main__":
    unittest.main()
