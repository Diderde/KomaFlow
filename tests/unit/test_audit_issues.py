# -*- coding: utf-8 -*-
"""审计 Issue 的回归测试（对应 Diderde 的 #1 #4 #7 #8 #9）。

这些测试**不启动 Blender**：装配那一层用假执行器替换，
其余（PNG 导出、复用判据、路径净化）都是真实函数直调。
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from komaflow.core import pipeline as P  # noqa: E402
from komaflow.core.errors import ErrorKind, KomaFlowError  # noqa: E402
from komaflow.core.paths import safe_basename  # noqa: E402
from komaflow.core.segment import plan_segments  # noqa: E402

PNG = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])


class TestIssue4PngExport(unittest.TestCase):
    """#4：PNG 导出既不能删用户文件，也不能写出输出目录。"""

    def _scene(self, base: Path, name: str, *, with_frames: bool = True):
        work = base / name / "work"
        out = base / name / "out"
        (work / "segments").mkdir(parents=True)
        out.mkdir(parents=True)
        segment = plan_segments(6, 6)[0]
        if with_frames:
            (work / "segments" / (segment.filename("png") + "0000.png")).write_bytes(PNG)
        return work, out

    def test_existing_pngs_survive_a_failed_export(self):
        """导出失败时，用户上一次的 PNG 必须还在（原来是无条件先删）。"""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            work, out = self._scene(base, "fail", with_frames=False)
            frames = out / "hello_frames"
            frames.mkdir()
            precious = frames / "my_precious_render.png"
            precious.write_bytes(PNG + b"user data")

            with self.assertRaises(KomaFlowError):
                P._export_png_frames(segments=plan_segments(6, 6), work_dir=work,
                                     output_dir=out, basename="hello")

            self.assertTrue(precious.is_file(), "失败时不该删用户的 PNG")
            self.assertEqual(precious.read_bytes(), PNG + b"user data")

    def test_basename_cannot_escape_output_dir(self):
        """``../evil`` 这类成片名只能落在输出目录里。"""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            work, out = self._scene(base, "escape")
            target, count = P._export_png_frames(
                segments=plan_segments(6, 6), work_dir=work,
                output_dir=out, basename="../evil")
            self.assertEqual(count, 1)
            self.assertIn(out.resolve(), target.resolve().parents,
                          f"导出目录跑出输出目录了：{target}")

    def test_failed_export_leaves_no_temp_dir(self):
        """失败后不该留下 ``<名>_frames.tmp`` 这种半成品目录。"""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            work, out = self._scene(base, "tmpclean", with_frames=False)
            with self.assertRaises(KomaFlowError):
                P._export_png_frames(segments=plan_segments(6, 6), work_dir=work,
                                     output_dir=out, basename="hello")
            leftovers = [p.name for p in out.iterdir()]
            self.assertEqual(leftovers, [], f"输出目录留下了东西：{leftovers}")

    def test_success_replaces_previous_frames(self):
        """成功时旧的那批要被替换掉（不能越攒越多）。"""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            work, out = self._scene(base, "ok")
            frames = out / "hello_frames"
            frames.mkdir()
            (frames / "stale_0009.png").write_bytes(PNG)

            P._export_png_frames(segments=plan_segments(6, 6), work_dir=work,
                                 output_dir=out, basename="hello")
            names = sorted(p.name for p in frames.glob("*.png"))
            self.assertEqual(names, ["hello_0000.png"])


class TestIssue7ReuseKey(unittest.TestCase):
    """#7：同名覆盖素材必须被识别为"变了"。"""

    def test_same_path_different_content_changes_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = Path(tmp) / "model.pmx"
            model.write_bytes(b"v1" * 100)
            spec = {"route": "assets", "model": str(model), "motions": []}
            first = P._key_inputs(spec)

            model.write_bytes(b"v2 replaced with other content")
            second = P._key_inputs(spec)

            self.assertNotEqual(first["_stat"], second["_stat"],
                                "同名覆盖后指纹必须变化")
            self.assertFalse(P._same_inputs(first, spec),
                             "内容变了却仍判为可复用")

    def test_unchanged_file_still_reuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = Path(tmp) / "model.pmx"
            model.write_bytes(b"same")
            spec = {"route": "assets", "model": str(model), "motions": []}
            self.assertTrue(P._same_inputs(P._key_inputs(spec), spec))

    def test_old_saved_key_without_stats_is_not_reused(self):
        """老工程档里没有 _stat → 当作变了，重装一次最稳。"""
        with tempfile.TemporaryDirectory() as tmp:
            model = Path(tmp) / "model.pmx"
            model.write_bytes(b"same")
            spec = {"route": "assets", "model": str(model), "motions": []}
            saved = P._key_inputs(spec)
            saved.pop("_stat", None)
            self.assertFalse(P._same_inputs(saved, spec))


class TestIssue1PhysicsFailure(unittest.TestCase):
    """#1：烘焙失败必须让整次装配失败，不能存一份坏工程继续。"""

    def test_bake_error_aborts_assembly(self):
        from komaflow.core import project as project_mod

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "out"
            output_dir.mkdir()
            work = root / "work"
            work.mkdir()

            project = project_mod.Project()
            project.inputs.route = "assets"
            project.inputs.model = str(root / "model.pmx")
            (root / "model.pmx").write_bytes(b"pmx")
            project.inputs.motions = [str(root / "m.vmd")]
            (root / "m.vmd").write_bytes(b"vmd")
            project.output.dir = str(output_dir)
            project.output.basename = "hello"

            # 假执行器：装配"成功"，但物理烘焙报了 error
            class _Outcome:
                ok = True
                report = {
                    "ok": True,
                    "total_frames": 10,
                    "camera": {"name": "KomaFlow_Cam"},
                    "motion_span": {"max": 10},
                    "physics_bake": {"error": "RuntimeError: boom"},
                }

            original_run = P.run_blender_script
            original_sel = P.select_adapter
            original_probe = getattr(P, "BASELINE", None)
            try:
                P.run_blender_script = lambda *a, **kw: _Outcome()
                P.select_adapter = lambda version: type(
                    "A", (), {"script": staticmethod(lambda name: root / name)})()

                class _Base:
                    @staticmethod
                    def probe(exe):
                        return type("I", (), {"version": (5, 2, 0),
                                              "version_string": "Blender 5.2.0",
                                              "mmd_tools_version": "4.5.13",
                                              "mmd_tools_installed": True})()

                P.BASELINE = _Base

                with self.assertRaises(KomaFlowError) as ctx:
                    P._prepare_and_assemble(
                        project, work, blender_exe=str(root / "blender.exe"),
                        on_event=lambda ev: None)
                self.assertEqual(ctx.exception.kind, ErrorKind.PHYSICS_FAILED)
            finally:
                P.run_blender_script = original_run
                P.select_adapter = original_sel
                if original_probe is not None:
                    P.BASELINE = original_probe


class TestIssue8StreamingCopy(unittest.TestCase):
    """#8：单段成片不许整文件读进内存。"""

    def test_source_does_not_read_whole_video(self):
        text = (ROOT / "src/komaflow/core/pipeline.py").read_text(encoding="utf-8")
        self.assertNotIn("final.write_bytes(source.read_bytes())", text,
                         "整文件读进内存的写法又回来了")
        self.assertIn("shutil.copy2(source, final)", text)


class TestIssue9SmallOnes(unittest.TestCase):
    """#9：裸解析缓存、重复调用栈、重复字典键。"""

    def test_build_report_parse_is_guarded(self):
        text = (ROOT / "src/komaflow/core/pipeline.py").read_text(encoding="utf-8")
        self.assertIn("except (OSError, ValueError):", text)
        self.assertNotIn(
            'cached = json.loads(build_report_path.read_text(encoding="utf-8"))\n'
            '        if previous', text)

    def test_traceback_emitted_once(self):
        """同一个异常只该写一份调用栈（原来连写两遍）。

        ⚠️ 全文有两处 emit（预览 / 整片各一处，分属不同函数，都该保留），
           所以这里查的是"连续两遍"这个错误形态，而不是总数。
        """
        text = (ROOT / "src/komaflow/core/pipeline.py").read_text(encoding="utf-8")
        doubled = ('_tb.format_exc())\n'
                   '        import traceback as _tb\n')
        self.assertNotIn(doubled, text, "调用栈又被写成两遍了")

    def test_frame_end_key_not_duplicated(self):
        text = (ROOT / "src/komaflow/core/pipeline.py").read_text(encoding="utf-8")
        self.assertEqual(text.count('"frame_end": params.frame_end'), 1)


class TestSafeBasename(unittest.TestCase):
    """成片名净化（#4 的另一半）。"""

    def test_cases(self):
        cases = {
            "../../逃逸": "逃逸",
            r"..\..\x": "x",
            r"C:\Windows\evil": "evil",
            "a/b/c": "c",
            "名字.": "名字",
            "CON": "_CON",
            "": "KomaFlow",
            "...": "KomaFlow",
            "a:b*c?": "a_b_c_",
        }
        for raw, want in cases.items():
            self.assertEqual(safe_basename(raw), want, raw)

    def test_long_name_is_truncated(self):
        self.assertLessEqual(len(safe_basename("x" * 300)), 120)


if __name__ == "__main__":
    unittest.main()
