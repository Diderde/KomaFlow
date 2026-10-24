"""回归：动作 / 表情**按文件内容**分，不靠文件名。

用户原话
--------
> 表情和动作可以直接导入不用现在一样分两个吧，毕竟有些作者他不写那个
> 是动作哪个是表情

技术依据
--------
``mmd_tools.import_vmd`` **一次调用就把骨骼 / 表情 / 相机全读进去**，
没有"只读某一段"的开关。所以：

* 一个文件里同时有骨骼和表情 → 放进任意一格都会被**完整**导入
* 同一个文件导两遍也**不会互相覆盖**（骨骼动画与表情变形是两套独立数据）

结论：这两格只是**收纳**"作者发两个文件"的情况，
用户**不需要**知道哪个是哪个 —— 我们数帧数就能准确判定。
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

#: 用户真实素材（不在就跳过相关断言）
YSB = Path(tempfile.gettempdir()) / "vmd_samples"
CAM = Path(r"<样例>\素材.vmd"
           r"\糟糕的视角【镜头动作】")


def build_vmd(bones: int = 0, morphs: int = 0, cameras: int = 0) -> bytes:
    """造一个最小 VMD：只写各段的帧数，帧数据用零填充（够解析就行）。

    ⚠️ 头部要**正好 50 字节**：签名占 **30** 字节（``Vocaloid Motion Data 0002``
    只有 25 字符，后面补 5 个 ``\\x00``），再加 20 字节模型名。
    我第一版把签名写成 25 字节，于是后面所有段都错位 5 字节、数出来全是 0
    —— **是测试的锅，不是被测代码的锅**（踩过）。
    """
    signature = b"Vocaloid Motion Data 0002".ljust(30, b"\x00")
    head = signature + b"\x00" * 20
    assert len(head) == 50, len(head)
    return (head
            + bones.to_bytes(4, "little") + b"\x00" * (bones * 111)
            + morphs.to_bytes(4, "little") + b"\x00" * (morphs * 23)
            + cameras.to_bytes(4, "little") + b"\x00" * (cameras * 61))


class TestVmdParts(unittest.TestCase):
    """``vmd_parts`` 要能准确数出各段帧数。"""

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
        self.tmp = Path(tempfile.mkdtemp(prefix="vmdtest_"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)
        try:
            self.app._shutdown()
            self.root.destroy()
        except Exception: # noqa: BLE001
            pass

    def _write(self, name: str, **kw) -> Path:
        path = self.tmp / name
        path.write_bytes(build_vmd(**kw))
        return path

    def test_counts_each_section(self):
        path = self._write("x.vmd", bones=3, morphs=5, cameras=7)
        self.assertEqual(self.app.vmd_parts(str(path)),
                         {"bones": 3, "morphs": 5, "cameras": 7})

    def test_bad_signature_returns_none(self):
        path = self.tmp / "bad.vmd"
        path.write_bytes(b"not a vmd at all")
        self.assertIsNone(self.app.vmd_parts(str(path)))

    def test_missing_file_returns_none(self):
        self.assertIsNone(self.app.vmd_parts(str(self.tmp / "nope.vmd")))


class TestClassifyByContent(unittest.TestCase):
    """分类必须靠内容，文件名只能兜底。"""

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
        self.tmp = Path(tempfile.mkdtemp(prefix="vmdcls_"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)
        try:
            self.app._shutdown()
            self.root.destroy()
        except Exception: # noqa: BLE001
            pass

    def _write(self, name: str, **kw) -> Path:
        path = self.tmp / name
        path.write_bytes(build_vmd(**kw))
        return path

    def test_pure_bones_is_motion(self):
        self.assertEqual(
            self.app._classify_vmd(str(self._write("001.vmd", bones=10))),
            "motion")

    def test_pure_morphs_is_expression(self):
        self.assertEqual(
            self.app._classify_vmd(str(self._write("002.vmd", morphs=10))),
            "expression")

    def test_pure_camera_is_camera(self):
        self.assertEqual(
            self.app._classify_vmd(str(self._write("003.vmd", cameras=10))),
            "camera")

    def test_bones_plus_morphs_is_motion(self):
        """合一文件归动作 —— 一次导入两样都进去了，归哪格都不影响结果。

        用户原话：

        > 如果用户只导入一个文件，代表那是多合一，懂我意思吧（除了摄像机）

        也就是说：**动作卡里只有一个 vmd 时，它就是"多合一"** ——
        骨骼和表情都在里面，导入一次两样都要生效。
        """
        self.assertEqual(
            self.app._classify_vmd(str(self._write("both.vmd", bones=10, morphs=5))),
            "motion")

    def test_all_in_one_with_camera_is_still_motion(self):
        """多合一文件里**即使带摄像机帧**，也归动作，不归镜头。

        用户括号里那句"（除了摄像机）"就是这条：摄像机是**独立一栏**，
        多合一文件里的相机段不该把整个文件拽到「镜头」里 ——
        那样动作就丢了。
        """
        path = self._write("all_in_one.vmd", bones=10, morphs=5, cameras=8)
        self.assertEqual(self.app._classify_vmd(str(path)), "motion")

    def test_camera_only_file_is_camera(self):
        """纯相机帧（这不算"多合一"）才归镜头。"""
        self.assertEqual(
            self.app._classify_vmd(str(self._write("cam.vmd", cameras=8))),
            "camera")

    def test_misleading_name_still_classified_by_content(self):
        """**用户最关心的那条**：名字写着 morph/face，内容是纯骨骼 → 必须是动作。

        光看文件名会分错，这就是"有些作者不写标注"的后果。
        """
        path = self._write("morph_face_facial.vmd", bones=20)
        self.assertEqual(self.app._classify_vmd(str(path)), "motion")

    def test_expression_name_but_content_is_expression(self):
        path = self._write("表情.vmd", morphs=8)
        self.assertEqual(self.app._classify_vmd(str(path)), "expression")


class TestRealAssetsIfPresent(unittest.TestCase):
    """用户真实素材在的话，顺手核对一遍（不在就跳过）。"""

    def test_real_motion_and_expression(self):
        try:
            import tkinter as tk

            from komaflow.ui import app as app_module
            from komaflow.ui import assets as ui_assets
        except Exception: # noqa: BLE001
            self.skipTest("环境不支持")
        if not (YSB / "示例动作动作.vmd").is_file():
            self.skipTest("素材不在本机")

        ui_assets.reset()
        app_module.KomaFlowApp._detect_blender_async = lambda self: None
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"建不了 Tk 窗口：{exc}")
        root.withdraw()
        app = app_module.KomaFlowApp(root)
        try:
            parts = app.vmd_parts(str(YSB / "示例动作动作.vmd"))
            self.assertIsNotNone(parts)
            # 用户这个动作文件**一个表情帧都没有** ——
            # 证明"分开"是作者发的两个文件，不是我们拆细了
            self.assertEqual(parts["morphs"], 0)
            self.assertGreater(parts["bones"], 0)
            self.assertEqual(app._classify_vmd(str(YSB / "示例动作动作.vmd")), "motion")
            if (YSB / "示例动作表情.vmd").is_file():
                self.assertEqual(
                    app._classify_vmd(str(YSB / "示例动作表情.vmd")), "expression")
        finally:
            try:
                app._shutdown()
                root.destroy()
            except Exception: # noqa: BLE001
                pass


if __name__ == "__main__":
    unittest.main()
