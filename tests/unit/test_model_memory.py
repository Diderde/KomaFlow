# -*- coding: utf-8 -*-
"""验「角色卡记忆」：上次确定用的模型，下次打开还在。

用户要求：

> 角色板块应该带有记忆性，上一次用户确定使用之后，下一次打开应该默认
> 还是那个，直到用户渲染下一个模型或者用户导入模型

这组测试盯四件事：

1. 确定用了之后**记得住**（写进设置文件，不是只在内存里）
2. 重开界面**自动填回来**
3. 用户换了模型 → 记忆**跟着更新**（不是一直记第一个）
4. 记忆里的文件**不见了** → 清掉记忆并提示，不能悄悄指一个不存在的路径

⚠️ 每个用例都把设置目录指到临时目录，绝不碰用户真实的设置文件。
"""

from __future__ import annotations

import sys
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from komaflow.settings import Settings # noqa: E402


class _TkCase(unittest.TestCase):
    """起一个真 Tk 根窗口（应用构造要用），并把设置落到临时目录。"""

    def setUp(self) -> None:
        import tempfile

        from komaflow.ui import assets as ui_assets

        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        # 设置文件改到临时目录 —— 不能污染用户真实的设置
        self._patchers = [
            mock.patch.object(Settings, "path",
                              classmethod(lambda cls: self.tmp / "settings.json")),
        ]
        for p in self._patchers:
            p.start()
        self.root = tk.Tk()
        self.root.withdraw()
        # ⚠️ 必须丢掉图片缓存：``tk.PhotoImage`` 绑在**建它时那个解释器**上，
        # 上一个用例销毁根窗口后，旧图在新窗口里就是野引用，
        # 一贴就报 ``image "pyimage1" doesn't exist``（这坑踩过多次）。
        ui_assets.reset()

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

        # 别真的去探测 Blender（会起子进程、拖慢测试）
        with mock.patch.object(app_module.KomaFlowApp, "_detect_blender_async",
                               lambda self: None):
            return app_module.KomaFlowApp(self.root)

    def _make_model(self, name: str) -> str:
        path = self.tmp / name
        path.write_bytes(b"pmx")
        return str(path)


class TestRememberModel(_TkCase):
    """记忆的写入与恢复。"""

    def test_remembers_model_after_assign(self):
        app = self._app()
        model = self._make_model("角色.pmx")
        app._assign("model", model)
        saved = Settings.load()
        self.assertEqual(saved.last_model, model,
                         "确定用了之后要写进设置文件（不能只在内存里）")

    def test_restores_on_next_open(self):
        model = self._make_model("角色.pmx")
        first = self._app()
        first._assign("model", model)

        # 模拟"关掉再打开"：新建一个应用实例，它应该自动填回这个模型
        second_root = tk.Toplevel(self.root)
        from komaflow.ui import app as app_module
        with mock.patch.object(app_module.KomaFlowApp, "_detect_blender_async",
                               lambda self: None):
            second = app_module.KomaFlowApp(second_root)
        self.assertEqual(second.vars["model"].get(), model,
                         "下次打开应该默认还是上次那个角色")

    def test_switching_model_updates_memory(self):
        app = self._app()
        first = self._make_model("角色A.pmx")
        second = self._make_model("角色B.pmx")
        app._assign("model", first)
        app._assign("model", second)
        self.assertEqual(Settings.load().last_model, second,
                         "换模型之后要记最新的，不能一直记第一个")

    def test_blend_route_is_remembered_separately(self):
        """`.blend`（已配好的工程）跟 `.pmx` 是两条路，字段要分开。"""
        app = self._app()
        blend = self.tmp / "工程.blend"
        blend.write_bytes(b"blend")
        app._assign("model", str(blend))
        saved = Settings.load()
        self.assertEqual(saved.last_blend, str(blend))
        self.assertEqual(saved.last_model, "",
                         "换成 .blend 之后不该还留着旧的 pmx")

    def test_stage_is_not_remembered(self):
        """舞台不是"角色板块"，不该被记住。"""
        app = self._app()
        stage = self.tmp / "舞台.blend"
        stage.write_bytes(b"blend")
        app._assign("stage", str(stage))
        saved = Settings.load()
        self.assertEqual(saved.last_blend, "",
                         "舞台属于环境，不算角色，不该写进记忆")

    def test_missing_file_clears_memory(self):
        """记忆里的文件被删了 → 清掉记忆并提示，不能悄悄指个空路径。"""
        model = self._make_model("会没的.pmx")
        first = self._app()
        first._assign("model", model)
        Path(model).unlink() # 用户把它删了/移走了

        second_root = tk.Toplevel(self.root)
        from komaflow.ui import app as app_module
        with mock.patch.object(app_module.KomaFlowApp, "_detect_blender_async",
                               lambda self: None):
            second = app_module.KomaFlowApp(second_root)
        self.assertEqual(second.vars["model"].get(), "",
                         "文件都不在了，不该填一个不存在的路径进去")
        self.assertEqual(Settings.load().last_model, "",
                         "记忆要作废，否则每次启动都提示一次")

    def test_no_memory_means_empty_card(self):
        """从没记过 → 卡片是空的（不能因为要"记忆"就随便塞个东西）。"""
        app = self._app()
        self.assertEqual(app.vars["model"].get(), "")


if __name__ == "__main__":
    unittest.main()
