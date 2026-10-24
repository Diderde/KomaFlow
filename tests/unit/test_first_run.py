"""首次启动引导 / 提示窗 —— 契约测试。

覆盖这一轮新加的东西：

* ``Settings`` 多出来的两个字段（``blender_exe`` / ``first_run_done``）
  必须能**存下来、读回来**，而且旧配置（没这两个字段）不能读崩
* 三个提示窗的存在与按钮契约（``MissingBlenderNotice`` / ``BlenderPickNotice``
  / 原有的 ``DependencyNotice`` / ``ReadyNotice``）

⚠️ 这些窗都继承 ``notice_base.NoticeWindow``，所以这里的断言是**契约**：
   改基类时如果动了这些性质，测试会先响。
"""

from __future__ import annotations

import json
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

from komaflow.settings import Settings


class TestSettingsNewFields(unittest.TestCase):
    """两个新字段的读写与向前兼容。"""

    def test_defaults(self):
        """默认值：没选过、没走过引导。"""
        settings = Settings()
        self.assertEqual(settings.blender_exe, "")
        self.assertFalse(settings.first_run_done)

    def test_round_trip(self):
        """写进去能读回来。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            with mock.patch.object(Settings, "path", classmethod(lambda cls: path)):
                settings = Settings()
                settings.blender_exe = r"D:\Blender\blender.exe"
                settings.first_run_done = True
                settings.save()

                again = Settings.load()
                self.assertEqual(again.blender_exe, r"D:\Blender\blender.exe")
                self.assertTrue(again.first_run_done)

    def test_old_config_without_new_fields(self):
        """旧配置文件（没有这两个字段）不能读崩，也不能把字段丢掉。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            # 模拟"上一版写出来的"配置：只有老字段
            path.write_text(json.dumps({
                "output_dir": str(Path(tmp) / "out"),
                "snapshot_enabled": False,
                "ui_zoom": 1.25,
            }), encoding="utf-8")

            with mock.patch.object(Settings, "path", classmethod(lambda cls: path)):
                settings = Settings.load()
                self.assertEqual(settings.blender_exe, "")
                self.assertFalse(settings.first_run_done)
                # 老字段要照常读到
                self.assertFalse(settings.snapshot_enabled)
                self.assertAlmostEqual(settings.ui_zoom, 1.25)

    def test_broken_config_does_not_crash(self):
        """配置文件坏掉也要起得来（返回默认值）。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text("{ 这不是 json", encoding="utf-8")
            with mock.patch.object(Settings, "path", classmethod(lambda cls: path)):
                settings = Settings.load()
                self.assertEqual(settings.blender_exe, "")
                self.assertFalse(settings.first_run_done)


class TestNoticeContracts(unittest.TestCase):
    """四个提示窗的契约：吉祥物、标题、按钮。

    ⚠️ 只做**不需要 Tk 主循环**的检查（导入 + 类属性），
       真要开窗的验证在 ``work/selfcheck3.py`` / ``selfcheck4.py`` 里。
    """

    def test_classes_exist_with_mascots(self):
        from komaflow.ui import dependency_notice as dn

        expected = {
            "DependencyNotice": "mascot_peek.png",
            "ReadyNotice": "mascot_happy.png",
            "MissingBlenderNotice": "mascot_peek.png",
            "BlenderPickNotice": "mascot_happy.png",
        }
        for name, mascot in expected.items():
            cls = getattr(dn, name, None)
            self.assertIsNotNone(cls, f"少了 {name}")
            self.assertEqual(cls.mascot, mascot, f"{name} 的吉祥物变了")

    def test_all_assets_exist(self):
        """四个窗用到的吉祥物文件都必须在 assets 里。"""
        from komaflow.ui import assets as ui_assets

        for name in ("mascot_peek.png", "mascot_happy.png"):
            self.assertTrue((ui_assets.ASSETS / name).is_file(),
                            f"缺资产 {name}")

    def test_each_notice_has_own_mascot_intent(self):
        """别再出现"同一个姿势裁两刀"—— 不同情绪要用不同的图。

        ⚠️ 探头（缺插件/没找到）用 mascot_peek，开心（就绪/选版本）用
           mascot_happy。两者必须是**不同的文件**，否则又回到千篇一律。
        """
        from komaflow.ui import dependency_notice as dn

        worry = {dn.DependencyNotice.mascot, dn.MissingBlenderNotice.mascot}
        joy = {dn.ReadyNotice.mascot, dn.BlenderPickNotice.mascot}
        self.assertEqual(len(worry), 1, "两张'小心确认'的图应该一致")
        self.assertEqual(len(joy), 1, "两张'开心'的图应该一致")
        self.assertNotEqual(worry, joy, "两种情绪不能共用同一张图")


class TestSelfCheckNotice(unittest.TestCase):
    """自检结果窗 —— 用户要的「选完版本**然后自检**」那一屏。

    这里守两条：

    * **文案不能说反**：三项全过才配叫「都准备好了」；
      缺 mmd_tools 时标题必须老实说「有几处要注意」。
    * **结论口径要一致**：窗上写的和 ``self_check_facts()`` 给的必须是同一份。
    """

    def test_ready_counts(self):
        from komaflow.ui.dependency_notice import SelfCheckNotice

        ready = SelfCheckNotice(None, blender="5.2.2 LTS", tools="4.5.7",
                                tools_ok=True, disk="D: 盘剩 79.5 GB",
                                disk_ok=True)
        self.assertTrue(ready.ready)
        self.assertEqual(ready.title_text, "都准备好了")

    def test_missing_tools_is_not_ready(self):
        """缺插件还说「都准备好了」就是骗人。"""
        from komaflow.ui.dependency_notice import SelfCheckNotice

        bad = SelfCheckNotice(None, blender="5.0.1", tools="没找到",
                              tools_ok=False, disk="C: 盘剩 120 GB",
                              disk_ok=True)
        self.assertFalse(bad.ready)
        self.assertEqual(bad.title_text, "有几处要注意")

    def test_tight_disk_is_not_ready(self):
        from komaflow.ui.dependency_notice import SelfCheckNotice

        bad = SelfCheckNotice(None, blender="5.2.2 LTS", tools="4.5.7",
                              tools_ok=True, disk="D: 盘剩 1.2 GB",
                              disk_ok=False)
        self.assertFalse(bad.ready)

    def test_blocks_show_three_facts(self):
        from komaflow.ui.dependency_notice import SelfCheckNotice

        notice = SelfCheckNotice(None, blender="5.2.2 LTS", tools="4.5.7",
                                 tools_ok=True, disk="D: 盘剩 79.5 GB",
                                 disk_ok=True, output_dir=r"D:\out")
        heads = [head for head, _text in notice.blocks]
        for wanted in ("Blender", "mmd_tools 插件", "目标盘"):
            self.assertIn(wanted, heads)
        joined = "\n".join(text for _head, text in notice.blocks)
        self.assertIn("5.2.2 LTS", joined)
        self.assertIn("4.5.7", joined)
        self.assertIn("79.5 GB", joined)

    def test_buttons(self):
        from komaflow.ui.dependency_notice import SelfCheckNotice

        notice = SelfCheckNotice(None, on_start=lambda: None,
                                 on_settings=lambda: None)
        labels = [row[0] for row in notice.buttons]
        self.assertIn("好，开始用", labels)
        self.assertIn("去设置里看看", labels)
        # 主按钮永远排第一（跟其它提示窗一致）
        self.assertTrue(notice.buttons[0][2])

    def test_no_markdown_marks_in_visible_text(self):
        """用户可见文案里不能出现 markdown 记号（会原样显示）。"""
        from komaflow.ui.dependency_notice import SelfCheckNotice

        notice = SelfCheckNotice(None, blender="5.2.2 LTS", tools="没找到",
                                 tools_ok=False, disk="", disk_ok=True,
                                 output_dir=r"D:\out", version="V1.1.0-beta")
        visible = [notice.title_text, notice.footnote]
        visible += [head for head, _t in notice.blocks]
        visible += [text for _h, text in notice.blocks]
        visible += [row[0] for row in notice.buttons]
        for text in visible:
            self.assertNotIn("**", text, f"文案里混进了 markdown 记号：{text}")


class _TkAppCase(unittest.TestCase):
    """建真 Tk 窗口 + 真 ``KomaFlowApp`` 的用例基类。

    ⚠️ 两条必须做的事（都是踩过的）：

    ① **探测那步要换掉** —— 真跑的话测试里会起 Blender 子进程，又慢又吵。
    ② **设置写到临时目录** —— 不换的话，用例里一句 ``settings.save()``
       就把运行机器上真实的 ``%APPDATA%\\KomaFlow\\settings.json`` 覆盖掉了
       （上一轮的 ``selfcheck4.py`` 就干过这事，把 ``blender_exe`` 写成了 4.2）。
    """

    def setUp(self) -> None:
        try:
            from komaflow.ui import app as app_module
        except Exception as exc: # noqa: BLE001
            self.skipTest(f"界面模块导入失败：{exc}")
        self.app_module = app_module
        self._tmp = tempfile.TemporaryDirectory(prefix="komaflow_test_")
        self._settings_path = Path(self._tmp.name) / "settings.json"
        self._real_path = Settings.path
        Settings.path = classmethod(lambda cls: self._settings_path)
        app_module.KomaFlowApp._detect_blender_async = lambda self: None
        # ⚠️ 每个用例新建 Tk root，图像资源必须跟着清（见 test_ui_zoom 的说明）
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
        for attr in ("_dep_notice", "_ready_notice", "_self_check_notice",
                     "_blender_pick_notice", "_missing_blender_notice"):
            notice = getattr(self.app, attr, None)
            if notice is not None:
                try:
                    notice.close()
                except Exception: # noqa: BLE001
                    pass
        try:
            from komaflow.ui import model_render_window as mrw
            if mrw.ModelRenderWindow._instance is not None:
                mrw.ModelRenderWindow._instance.close()
        except Exception: # noqa: BLE001
            pass
        try:
            self.app._shutdown()
        except Exception: # noqa: BLE001
            pass
        try:
            self.root.destroy()
        except (tk.TclError, AttributeError):
            pass
        Settings.path = self._real_path
        self._tmp.cleanup()

    def _live(self, attr: str) -> bool:
        """某个提示窗此刻是不是真的开着。"""
        notice = getattr(self.app, attr, None)
        if notice is None or notice.window is None:
            return False
        try:
            return bool(notice.window.winfo_exists())
        except tk.TclError:
            return False


class TestSelfCheckFacts(_TkAppCase):
    """``KomaFlowApp.self_check_facts()`` —— 自检的**唯一一份**结论。"""

    def _facts(self, probed: list[dict], exe: str = "") -> dict:
        self.app._blender_probed = probed
        self.app.vars["blender"].set(exe or (probed[0]["exe"] if probed else ""))
        return self.app.self_check_facts()

    def test_all_good(self):
        facts = self._facts([{"exe": r"D:\Blender\blender.exe",
                              "version": "5.2.2 LTS", "tools": "4.5.7",
                              "has_tools": True}])
        self.assertEqual(facts["blender"], "5.2.2 LTS")
        self.assertEqual(facts["tools"], "4.5.7")
        self.assertTrue(facts["tools_ok"])
        # 输出目录默认一定是存在的路径，所以这一项必须查得到
        self.assertTrue(facts["disk"], "目标盘剩余没查出来")
        self.assertIn("剩 ", facts["disk"])
        self.assertTrue(facts["ready"])

    def test_missing_tools(self):
        facts = self._facts([{"exe": r"C:\Blender\5.0\blender.exe",
                              "version": "5.0.1", "has_tools": False}])
        self.assertFalse(facts["tools_ok"])
        self.assertEqual(facts["tools"], "没找到")
        self.assertFalse(facts["ready"], "缺插件不能算准备好")

    def test_tools_without_version_number_still_ok(self):
        """探不到插件版本号 ≠ 缺插件。

        ⚠️ 早期的写法要求"has_tools 与版本号同时为真"，那样会把
           明明能用的一台报成缺插件（用户照着去装，装也装不出区别）。
        """
        facts = self._facts([{"exe": r"D:\Blender\blender.exe",
                              "version": "5.2.2 LTS", "has_tools": True}])
        self.assertTrue(facts["tools_ok"])
        self.assertEqual(facts["tools"], "已装好")

    def test_selected_blender_wins(self):
        """报的必须是**当前选用的**那台，不是列表里第一台。"""
        probed = [
            {"exe": r"C:\Blender\5.0\blender.exe", "version": "5.0.1",
             "has_tools": False},
            {"exe": r"D:\Blender\blender.exe", "version": "5.2.2 LTS",
             "tools": "4.5.7", "has_tools": True},
        ]
        facts = self._facts(probed, exe=probed[1]["exe"])
        self.assertEqual(facts["blender"], "5.2.2 LTS")
        self.assertTrue(facts["tools_ok"])

    def test_empty_probe_does_not_crash(self):
        facts = self._facts([])
        self.assertEqual(facts["blender"], "版本未知")
        self.assertFalse(facts["tools_ok"])
        self.assertFalse(facts["ready"])

    def test_finish_first_run_is_idempotent(self):
        """收尾要幂等：窗关掉和正常路径都会调它。"""
        self.app.settings.first_run_done = False
        self.app._finish_first_run()
        self.assertTrue(self.app.settings.first_run_done)
        self.app._finish_first_run() # 再来一次不能炸
        self.assertTrue(self.app.settings.first_run_done)


class TestFirstRunSelfCheckFlow(_TkAppCase):
    """首次启动的**接线**：什么时候弹自检、什么时候不该弹。"""

    def test_first_run_available_shows_self_check(self):
        self.app.settings.first_run_done = False
        self.app.settings.blender_exe = ""
        self.app._apply_blender_list([{
            "exe": r"D:\Blender\blender.exe", "version": "5.2.2 LTS",
            "tools": "4.5.7", "has_tools": True}])
        self.root.update()
        self.assertTrue(self._live("_self_check_notice"), "首次启动没弹自检窗")
        # 弹出来就该算引导走完了（关掉不会再弹第二遍）
        self.assertTrue(self.app.settings.first_run_done)

    def test_first_run_missing_tools_shows_install_not_selfcheck(self):
        """缺插件时先解决插件，别拿自检结果挡着他。"""
        self.app.settings.first_run_done = False
        self.app.settings.blender_exe = ""
        self.app._apply_blender_list([{
            "exe": r"C:\Blender\5.0\blender.exe", "version": "5.0.1",
            "has_tools": False}])
        self.root.update()
        self.assertTrue(self._live("_dep_notice"), "缺插件时没弹安装说明窗")
        self.assertFalse(self._live("_self_check_notice"),
                         "插件都没装就先弹自检结果，顺序反了")
        # 这一屏还没走完 —— 不能提前记成"引导完成"，否则自检永远看不到
        self.assertFalse(self.app.settings.first_run_done,
                         "还没自检就记了 first_run_done")

    def test_not_first_run_stays_quiet(self):
        self.app.settings.first_run_done = True
        self.app.settings.blender_exe = ""
        self.app._apply_blender_list([{
            "exe": r"D:\Blender\blender.exe", "version": "5.2.2 LTS",
            "tools": "4.5.7", "has_tools": True}])
        self.root.update()
        self.assertFalse(self._live("_self_check_notice"),
                         "不是首次启动还弹自检窗，太吵了")


if __name__ == "__main__":
    unittest.main()
