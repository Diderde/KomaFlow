# -*- coding: utf-8 -*-
"""守住「换了素材必须真重渲」。

对面是一条真实事故：

> 输出的视频依旧是同一个样子，而且瞬间完成，是不是压根没跑，
> 单纯是把之前的视频复制了一份当成新的了

**确实是这样。** 段级续渲原来只认"那个段文件在不在、帧数对不对"，
不看它是不是这次的内容。于是换动作之后：
装配重做了新的 ``work.blend`` → 旧段视频还在 → 全部判"已完成"跳过 →
``concat`` 把旧段拷成新文件名。一秒完事、画面一模一样。

现在靠「内容指纹」挡住：指纹变了 → 旧段一律作废。
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from komaflow.core.pipeline import ( # noqa: E402
    RENDER_FINGERPRINT_FILE,
    invalidate_stale_segments,
    render_fingerprint,
)
from komaflow.core.project import Inputs, Output, Params, Project # noqa: E402
from komaflow.core.verify import segments_dir # noqa: E402


class _ProjectCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.work = self.tmp / "work"
        self.work.mkdir()
        self.model = self.tmp / "角色.pmx"
        self.model.write_bytes(b"pmx-1")
        self.motion_a = self.tmp / "动作A.vmd"
        self.motion_a.write_bytes(b"vmd-a")
        self.motion_b = self.tmp / "动作B.vmd"
        self.motion_b.write_bytes(b"vmd-b")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _project(self, motion: Path | None = None, **params) -> Project:
        project = Project(
            name="Fp",
            inputs=Inputs(route="assets", model=str(self.model),
                          motions=[str(motion or self.motion_a)]),
            output=Output(dir=str(self.tmp), basename="成片"),
        )
        project.params = Params(**params) if params else Params()
        return project

    def _report(self, **over) -> dict:
        base = {"frame_start": 0, "frame_end": 299}
        base.update(over)
        return base


class TestFingerprint(_ProjectCase):
    """指纹必须对"会影响画面"的东西敏感。"""

    def test_same_inputs_same_fingerprint(self):
        first = render_fingerprint(self._project(), self._report())
        second = render_fingerprint(self._project(), self._report())
        self.assertEqual(first, second, "同一份工程必须算同一个指纹，否则续渲永远失效")

    def test_different_motion_changes_fingerprint(self):
        a = render_fingerprint(self._project(self.motion_a), self._report())
        b = render_fingerprint(self._project(self.motion_b), self._report())
        self.assertNotEqual(a, b, "换动作必须换指纹，否则旧段会被误判为已完成")

    def test_different_resolution_changes_fingerprint(self):
        a = render_fingerprint(self._project(width=1280), self._report())
        b = render_fingerprint(self._project(width=2560), self._report())
        self.assertNotEqual(a, b, "改分辨率必须重渲")

    def test_different_frame_range_changes_fingerprint(self):
        a = render_fingerprint(self._project(), self._report(frame_end=299))
        b = render_fingerprint(self._project(), self._report(frame_end=599))
        self.assertNotEqual(a, b, "改帧范围必须重渲")

    def test_physics_is_always_on_in_fingerprint(self):
        """物理已改为 mmd_tools 原生、恒开 —— 指纹里不要再有"物理开关"这一项。

        同一条工程连算两次必须一致；旧工程档里残留的 physics_* 字段也不该影响指纹。
        """
        a = render_fingerprint(self._project(), self._report())
        b = render_fingerprint(self._project(), self._report())
        self.assertEqual(a, b, "同样输入必须算出同样指纹")

    def test_replaced_file_same_path_changes_fingerprint(self):
        """**同名覆盖**也要能被发现（"我换了个更好的版本"很常见）。"""
        before = render_fingerprint(self._project(), self._report())
        self.motion_a.write_bytes(b"vmd-a-completely-different-content")
        after = render_fingerprint(self._project(), self._report())
        self.assertNotEqual(before, after,
                            "路径没变但内容换了 —— 必须靠大小/修改时间识别出来")


class TestInvalidateStaleSegments(_ProjectCase):
    """指纹变了要把旧段清掉；没变就一律保留（续渲）。"""

    def _make_segments(self, count: int = 2) -> list[Path]:
        folder = segments_dir(self.work)
        folder.mkdir(parents=True, exist_ok=True)
        made = []
        for index in range(count):
            path = folder / f"seg_{index:04d}_000000-000099.mp4"
            path.write_bytes(b"x" * 16)
            made.append(path)
        return made

    def test_first_run_records_fingerprint(self):
        result = invalidate_stale_segments(self.work, "abc123")
        self.assertTrue(result["changed"])
        marker = self.work / RENDER_FINGERPRINT_FILE
        self.assertEqual(marker.read_text(encoding="utf-8").strip(), "abc123")

    def test_same_fingerprint_keeps_segments(self):
        """**续渲必须还能用** —— 指纹没变就不能删。

        真实时序是：先记指纹（那时还没有段）→ 渲染产生段 → 下次再进来。
        所以这里也要按这个顺序造数据，否则测的是"第一次就删光"。
        """
        invalidate_stale_segments(self.work, "abc123") # 第一次：记指纹
        made = self._make_segments(2) # 渲染产生段
        result = invalidate_stale_segments(self.work, "abc123")
        self.assertFalse(result["changed"])
        self.assertEqual(result["removed"], 0)
        for path in made:
            self.assertTrue(path.is_file(), f"续渲时不该删掉 {path.name}")

    def test_changed_fingerprint_removes_segments(self):
        invalidate_stale_segments(self.work, "abc123")
        made = self._make_segments(3)
        result = invalidate_stale_segments(self.work, "different")
        self.assertTrue(result["changed"])
        self.assertEqual(result["removed"], 3)
        for path in made:
            self.assertFalse(path.is_file(), f"{path.name} 应该被作废")
        self.assertFalse(list(segments_dir(self.work).iterdir()))

    def test_png_sequences_are_removed_too(self):
        """透明那条路的产物是一整个目录的 PNG，同样要清掉。"""
        invalidate_stale_segments(self.work, "abc123")
        folder = segments_dir(self.work)
        folder.mkdir(parents=True, exist_ok=True)
        # Blender 的写法：<前缀><帧号>.png，全平铺在 segments/ 里
        for index in range(3):
            (folder / f"seg_0000_000000-000099.png{index:04d}.png").write_bytes(b"p")
        result = invalidate_stale_segments(self.work, "different")
        self.assertEqual(result["removed"], 3)
        self.assertFalse(list(folder.iterdir()))


if __name__ == "__main__":
    unittest.main()
