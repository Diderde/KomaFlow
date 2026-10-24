"""契约与边界测试：工程档 · 错误分类 · 适配器选择 · 产物校验 · 渲染计划 · 分层守卫。

对应需求：（纯逻辑覆盖）· （关键路径可重复的自动化用例）·
 / （分层约束**用测试守住**，而不是靠自觉）。
"""

from __future__ import annotations

import os
import re
import tempfile
import unittest
from pathlib import Path

import komaflow.core
from komaflow.adapters import ADAPTERS, BASELINE, adapter_by_key, select_adapter
from komaflow.adapters.blender5 import Blender5Adapter
from komaflow.core.errors import CATALOG, ErrorKind, KomaFlowError
from komaflow.core.pipeline import plan_run
from komaflow.core.project import (DEFAULT_ALPHA_CODEC, Inputs, Output, Params,
                                 Project)
from komaflow.core.verify import (
    ArtifactState,
    atomic_commit,
    inspect_artifact,
    make_prober_from_table,
    png_frames_of,
    png_sequence_dir,
    segment_path,
    stage_frames_zero_based,
    temp_path_for,
    verify_artifact,
    verify_png_sequence,
    VideoInfo,
)


def sane_project() -> Project:
    """一个能通过体检的最小工程。"""
    return Project(
        name="demo",
        inputs=Inputs(route="assets", model="人物.pmx", motion="动作.vmd"),
    )


class TestProject(unittest.TestCase):
    def test_roundtrip(self):
        project = sane_project()
        project.params.preroll_frames = 60
        project.output = Output(dir="D:/out", basename="片子")
        with tempfile.TemporaryDirectory() as tmp:
            path = project.save(Path(tmp) / "demo.kfproj")
            loaded = Project.load(path)
        self.assertEqual(loaded.name, "demo")
        self.assertEqual(loaded.params.preroll_frames, 60)
        self.assertEqual(loaded.output.basename, "片子")
        self.assertEqual(loaded.inputs.model, "人物.pmx")

    def test_defaults_match_frozen_scope(self):
        """冻结范围：2K 2560×1440 @30、预热 30、单段上限 1000、不裁预热。"""
        params = Params()
        self.assertEqual((params.width, params.height), (2560, 1440))
        self.assertEqual(params.fps, 30)
        self.assertEqual(params.preroll_frames, 30)
        self.assertEqual(params.segment_limit, 1000)
        self.assertFalse(params.strip_preroll)

    def test_from_dict_ignores_unknown_and_fills_missing(self):
        project = Project.from_dict(
            {"name": "x", "inputs": {"model": "a.pmx", "motion": "b.vmd", "未来的字段": 1}}
        )
        self.assertEqual(project.inputs.model, "a.pmx")
        self.assertEqual(project.params.fps, 30) # 缺字段用默认值
        self.assertEqual(project.schema, 1)

    def test_validate_accepts_sane_project(self):
        self.assertEqual(sane_project().validate(), [])

    def test_validate_catches_missing_material(self):
        """措辞刻意白话（"还没放…"），别用"未指定"这种书面行话。"""
        project = sane_project()
        project.inputs.model = None
        project.inputs.motion = None
        problems = " ".join(project.validate())
        self.assertIn("角色模型", problems)
        self.assertIn("还没放动作", problems)

    def test_validate_catches_blend_route_without_blend(self):
        project = sane_project()
        project.inputs.route = "blend"
        project.inputs.blend = None
        self.assertTrue(any(".blend" in p for p in project.validate()))

    def test_validate_rejects_directx_x_stage(self):
        """FR-1.8：明确不支持 DirectX .x 舞台。"""
        project = sane_project()
        project.inputs.stage = "D:/素材/舞台.x"
        self.assertTrue(any(".x" in p for p in project.validate()))

    def test_validate_catches_bad_params(self):
        project = sane_project()
        project.params.preroll_frames = 999
        project.params.segment_limit = 0
        project.params.crf = 99
        project.params.orientation = "diagonal"
        project.params.quality = "ultra"
        project.params.frame_start = 100
        project.params.frame_end = 50
        self.assertGreaterEqual(len(project.validate()), 6)

    def test_validate_catches_missing_absolute_file(self):
        project = sane_project()
        project.inputs.model = r"D:\绝对不存在的目录\人物.pmx"
        self.assertTrue(any("不存在" in p for p in project.validate()))

    def test_scope_warnings_flag_out_of_frozen_scope(self):
        project = sane_project()
        project.params.fps = 60
        project.params.width, project.params.height = 1920, 1080
        project.inputs.audio = "音乐.wav"
        notes = " ".join(project.scope_warnings())
        self.assertIn("30fps", notes)
        self.assertIn("2K", notes)
        self.assertIn("音频", notes)

    def test_scope_warnings_mention_auto_camera(self):
        notes = " ".join(sane_project().scope_warnings())
        self.assertIn("自动正面机位", notes)


class TestErrors(unittest.TestCase):
    def test_every_kind_has_catalog_entry(self):
        missing = [kind.value for kind in ErrorKind if kind not in CATALOG]
        self.assertEqual(missing, [], "错误类必须全部登记人话文案（FR-8.5）")

    def test_human_message_has_title_and_suggestion(self):
        error = KomaFlowError(ErrorKind.OUT_OF_VRAM, detail="当前设置 2K")
        text = error.human()
        self.assertIn("显存不足", text)
        self.assertIn("建议", text)
        self.assertIn("当前设置 2K", text)

    def test_log_line_is_greppable(self):
        error = KomaFlowError(ErrorKind.BLENDER_MISSING)
        self.assertIn("blender_missing", error.log_line())

    def test_blocking_flag(self):
        self.assertTrue(KomaFlowError(ErrorKind.BLENDER_MISSING).blocking)
        self.assertFalse(KomaFlowError(ErrorKind.FRAME_FAILED).blocking)


class TestAdapters(unittest.TestCase):
    def test_selects_blender5(self):
        for version in ((5, 0), (5, 2, 2), (5, 99)):
            with self.subTest(version=version):
                self.assertIsInstance(select_adapter(version), Blender5Adapter)

    def test_rejects_42_and_60(self):
        """设计取舍/32：只支持 5.x；R11：6.0 也要明确报错。"""
        for version in ((4, 2, 5), (4, 0), (3, 6), (6, 0, 0)):
            with self.subTest(version=version):
                with self.assertRaises(KomaFlowError) as ctx:
                    select_adapter(version)
                self.assertEqual(ctx.exception.kind, ErrorKind.BLENDER_VERSION_UNSUPPORTED)

    def test_baseline_is_before_others_and_is_blender5(self):
        self.assertIs(BASELINE, ADAPTERS[0])
        self.assertTrue(BASELINE.is_baseline)
        self.assertEqual(BASELINE.key, "blender5")

    def test_adapter_by_key(self):
        self.assertIs(adapter_by_key("blender5"), ADAPTERS[0])
        with self.assertRaises(KeyError):
            adapter_by_key("blender42")

    def test_appendix_f_constants_live_in_adapter(self):
        """附录 F 的 5.2 写法差异必须挂在适配器上。"""
        adapter = BASELINE
        self.assertEqual(adapter.engine_eevee, "BLENDER_EEVEE")
        self.assertTrue(adapter.needs_media_type_first)
        self.assertEqual(adapter.material_transparency_attr, "surface_render_method")
        self.assertEqual(adapter.compositor_attr, "compositing_node_group")


class TestVerify(unittest.TestCase):
    def test_inspect_states(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "seg_0000_000000-000999.mp4"
            self.assertIs(inspect_artifact(path), ArtifactState.MISSING)

            path.write_bytes(b"")
            self.assertIs(inspect_artifact(path), ArtifactState.PARTIAL)

            path.write_bytes(b"x" * 4096)
            self.assertIs(inspect_artifact(path), ArtifactState.UNVERIFIED)

            # 只剩 .part ⇒ 上次崩在写入途中，视为未完成
            path.unlink()
            temp_path_for(path).write_bytes(b"x" * 4096)
            self.assertIs(inspect_artifact(path), ArtifactState.PARTIAL)

    def test_verify_artifact_happy_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "seg_0000_000000-000999.mp4"
            path.write_bytes(b"x" * 4096)
            prober = make_prober_from_table(
                {path.name: VideoInfo(frame_count=1000, duration_seconds=33.33, fps=30.0)}
            )
            state, info = verify_artifact(path, 1000, prober)
            self.assertIs(state, ArtifactState.VERIFIED)
            self.assertIsNotNone(info)

    def test_verify_artifact_frame_mismatch_is_partial(self):
        """帧数对不上 = 残片，必须重跑（K-2.8）。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "seg_0000_000000-000999.mp4"
            path.write_bytes(b"x" * 4096)
            prober = make_prober_from_table(
                {path.name: VideoInfo(frame_count=987, duration_seconds=32.9, fps=30.0)}
            )
            state, _info = verify_artifact(path, 1000, prober)
            self.assertIs(state, ArtifactState.PARTIAL)

    def test_verify_artifact_unreadable_is_partial(self):
        """文件在但探测失败 ⇒ 按残片处理，不赌运气。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "seg_0000_000000-000999.mp4"
            path.write_bytes(b"x" * 4096)

            def broken(_path: Path) -> VideoInfo:
                raise RuntimeError("读不出帧数")

            state, info = verify_artifact(path, 1000, broken)
            self.assertIs(state, ArtifactState.PARTIAL)
            self.assertIsNone(info)

    def test_atomic_commit(self):
        """：先写 .part 再改名，杜绝半成品被当成完成。"""
        with tempfile.TemporaryDirectory() as tmp:
            final = Path(tmp) / "seg_0000_000000-000999.mp4"
            temp = temp_path_for(final)
            temp.write_bytes(b"x" * 4096)
            atomic_commit(temp, final)
            self.assertTrue(final.is_file())
            self.assertFalse(temp.exists())


class TestPngSequence(unittest.TestCase):
    """透明背景那条路：段产物是 PNG 序列，判据从"验视频帧数"换成"数张数"。

    这条判据决定"哪几段要重渲"，数错一次就白渲几十分钟，所以单独守住。
    判"写完没写完"看的是 **PNG 结构**（签名 + 结尾 IEND），不是体积阈值 ——
    体积在小分辨率下会误判（实测 160×120 的合法帧只有 400 字节）。
    """

    def _png_bytes(self, size: int = 24) -> bytes:
        """一张合法的 RGBA PNG。不依赖 Pillow。

        故意画成**渐变**而不是纯色：纯色压得太狠，24×24 只有 68 字节，
        会撞上 ``MIN_PNG_BYTES`` 那道"空文件"闸门 —— 那是闸门在正常工作，
        但这个测试想验的不是闸门，所以造一张有真实内容的图。
        """
        import struct
        import zlib

        def chunk(kind: bytes, payload: bytes) -> bytes:
            body = kind + payload
            return (struct.pack(">I", len(payload)) + body
                    + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF))

        # 每条扫描线前面那个 0 是 PNG 的过滤器字节
        rows = bytearray()
        for y in range(size):
            rows.append(0)
            for x in range(size):
                rows += bytes(((x * 10) % 256, (y * 10) % 256, 128, 255))

        header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
                + chunk(b"IDAT", zlib.compress(bytes(rows), 0))
                + chunk(b"IEND", b""))

    def _make_sequence(self, root: Path, count: int, *, prefix: str | None = None,
                       truncate: set[int] | None = None) -> Path:
        """造一段 PNG 序列，**用真实落盘时的命名约定**。

        ⚠️ Blender 的序列命名是 ``<filepath><帧号><扩展名>``，而 filepath
        本身就带 ``.png``（段名形如 ``seg_0000_000000-000005.png``），
        所以真实文件名是::

            seg_0000_000000-000005.png0000.png

        这里就照这个来：``{prefix}{index:04d}.png``，且 ``prefix`` 以 ``.png`` 结尾。
        早先测试造的是另一套（``seg_0000_0001.png`` + 子目录），
        把实现和测试的命名对不齐 —— 于是实现里 glob 怎么写都"能过"，
        真实渲染出来的帧却一个都认不出（透明的 PNG 序列那条路就是这么坏的）。

        ⚠️ ``prefix`` 默认每次**随机唯一**：几个测试共用一个临时目录时，
        固定前缀会让 A 测试的文件被 B 测试数进去（实测：张数怎么都对不上）。
        """
        if prefix is None:
            import uuid

            prefix = f"seg_{uuid.uuid4().hex[:8]}_000000-000005.png"
        self._last_prefix = prefix
        directory = root / "segments"
        directory.mkdir(parents=True, exist_ok=True)
        for index in range(1, count + 1):
            payload = self._png_bytes()
            if truncate and index in truncate:
                payload = payload[: len(payload) // 2] # 写到一半崩了
            (directory / f"{prefix}{index:04d}.png").write_bytes(payload)
        return directory

    def test_complete_sequence_is_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = self._make_sequence(Path(tmp), 6)
            prefix = self._last_prefix
            state, found = verify_png_sequence(directory, 6, prefix=prefix)
            self.assertIs(state, ArtifactState.VERIFIED)
            self.assertEqual(found, 6)

    def test_missing_sequence(self):
        with tempfile.TemporaryDirectory() as tmp:
            state, found = verify_png_sequence(Path(tmp) / "没有这个目录", 6)
            self.assertIs(state, ArtifactState.MISSING)
            self.assertEqual(found, 0)

    def test_half_rendered_sequence_is_partial(self):
        """渲一半崩掉留下的正是这种情况 —— 必须判残片、让它重跑。"""
        with tempfile.TemporaryDirectory() as tmp:
            directory = self._make_sequence(Path(tmp), 4)
            prefix = self._last_prefix
            state, found = verify_png_sequence(directory, 6, prefix=prefix)
            self.assertIs(state, ArtifactState.PARTIAL)
            self.assertEqual(found, 4)

    def test_truncated_frame_is_partial(self):
        """张数够了也不算什么：某一张可能是崩溃时的半截文件（缺 IEND）。"""
        with tempfile.TemporaryDirectory() as tmp:
            directory = self._make_sequence(Path(tmp), 6, truncate={6})
            prefix = self._last_prefix
            state, found = verify_png_sequence(directory, 6, prefix=prefix)
            self.assertIs(state, ArtifactState.PARTIAL)
            self.assertEqual(found, 6)

    def test_non_png_content_is_partial(self):
        """文件名叫 .png 但内容不是 PNG —— 不认。"""
        with tempfile.TemporaryDirectory() as tmp:
            directory = self._make_sequence(Path(tmp), 3)
            prefix = self._last_prefix
            # 名字用**这一段自己的前缀**，内容不是 PNG → 应被判为残片
            (directory / f"{prefix}0004.png").write_bytes(b"x" * 4096)
            state, found = verify_png_sequence(directory, 4, prefix=prefix)
            self.assertIs(state, ArtifactState.PARTIAL)
            self.assertEqual(found, 4)

    def test_prefix_keeps_other_segments_out(self):
        """同一个目录里混进别的段时，不能把它们算进这一段的张数。"""
        with tempfile.TemporaryDirectory() as tmp:
            directory = self._make_sequence(Path(tmp), 3)
            prefix = self._last_prefix
            import uuid
            other = f"seg_{uuid.uuid4().hex[:8]}_000000-000005.png"
            for index in range(1, 4): # 另一段混进来
                (directory / f"{other}{index:04d}.png").write_bytes(self._png_bytes())

            state, found = verify_png_sequence(directory, 3, prefix=prefix)
            self.assertIs(state, ArtifactState.VERIFIED)
            self.assertEqual(found, 3)

    def test_sequence_dir_is_under_segments(self):
        """帧要落在 ``segments/`` 下 —— 工作目录清理策略按这个来（K-7.14）。

        ⚠️ 这里必须区分两个语义（早先混用过，把透明那条路整个搞坏了）：

        * ``png_sequence_dir`` = 帧**所在目录** → ``<work>/segments``
        * ``segment_path(...,'png')`` = 交给 Blender 的**文件名前缀**
          → ``<work>/segments/<段名>.png``（Blender 在其后接帧号 + .png）

        所以两者**不该相等** —— 相等就说明又混了。
        """
        from komaflow.core.segment import plan_segments

        segment = plan_segments(3000, 1000)[0]
        directory = png_sequence_dir("F:/work", segment)
        prefix = segment_path("F:/work", segment, "png")

        self.assertEqual(directory.name, "segments")
        self.assertEqual(prefix.parent, directory)
        self.assertEqual(prefix.name, segment.filename("png"))

    def test_one_authority_for_frames_dir_and_prefix(self):
        """``png_frames_of`` 是「去哪找 + 认哪个前缀」的**唯一出处**。

        这是啃掉「透明成片一个都没有」那个 bug 之后立的规矩：
        渲染、校验、编码三处原来各推导各的，编码那处把**文件名前缀**当目录用，
        还按更老的 ``<段名>.png_frames/`` 约定切掉 ``_frames`` ——
        于是 ffmpeg 的输入模板指向一个不存在的目录，**零帧成功退出、两轨都不产出**，
        ``xxx_parts/`` 空着，日志里也看不出错。

        这里把三件事钉死：目录在前缀的父目录里、前缀就是段名、
        以及**模板指的就是真落盘的那个名字**。
        """
        from komaflow.core.segment import plan_segments
        from komaflow.core.verify import png_frames_of, png_frame_name

        segment = plan_segments(3000, 1000)[0]
        frames = png_frames_of("F:/work", segment)

        self.assertEqual(frames.directory, png_sequence_dir("F:/work", segment))
        self.assertEqual(frames.prefix, segment.filename("png"))
        # 模板 = 目录 + 前缀 + %04d.png，跟 Blender 落盘的名字必须一致
        self.assertEqual(
            Path(frames.inputs()).name, f"{segment.filename('png')}%04d.png")
        # 前缀**不能**被"去掉 _frames"那种老约定切过
        self.assertFalse(frames.prefix.endswith("_frames"))
        self.assertEqual(Path(frames.inputs()).parent, frames.directory)
        # 真实落盘名（Blender 补 4 位帧号 + .png）
        written = png_frame_name(frames.prefix, 0)
        self.assertTrue(written.startswith(frames.prefix))
        self.assertTrue(written.endswith(".png"))
        # glob 模式能在那个文件名上命中
        self.assertTrue(Path(written).match(frames.pattern()))

    def test_stage_frames_renumbers_from_zero(self):
        """编码前必须把帧**按 0 起重编**放进暂存目录。

        第二个致命 bug：Blender 落盘用的是**工程时间轴**的帧号（第 2 段是
        ``…0006.png``…``0011``），而 ffmpeg 的 ``%04d`` 模板**永远从 0 数起**。
        于是第 1 段（帧号从 0 起）侥幸能编，**第 2 段起一个文件都找不到** ——
        分段透明成片只出得了第一段。

        这里连"原帧不许被动过"一起守住：原帧是续渲判据的依据。
        """
        from komaflow.core.segment import plan_segments

        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "work"
            segment = plan_segments(12, 6)[1] # 第 2 段：帧 6 ~ 11
            frames = png_frames_of(work, segment)
            frames.directory.mkdir(parents=True, exist_ok=True)
            # 按真机落盘名造：帧号从 6 起
            originals = []
            for frame in range(segment.start, segment.end + 1):
                path = frames.directory / f"{frames.prefix}{frame:04d}.png"
                path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 200)
                originals.append(path)

            stage_dir, stage_prefix = stage_frames_zero_based(
                frames, Path(tmp) / "stage")

            staged = sorted(stage_dir.glob(f"{stage_prefix}*"))
            self.assertEqual(len(staged), segment.count)
            # 编号必须是 0 起、连续的
            self.assertEqual([p.name for p in staged],
                             [f"{stage_prefix}{i:04d}.png"
                              for i in range(segment.count)])
            # 原帧一个都不能少、不能改名
            self.assertEqual(
                sorted(p.name for p in frames.directory.glob(f"{frames.prefix}*")),
                sorted(p.name for p in originals))
            # 内容要真的复制过来（不是空壳）
            self.assertEqual(staged[0].stat().st_size,
                             originals[0].stat().st_size)

    def test_stage_frames_refuses_when_empty(self):
        """没有帧就别硬编 —— 报清楚是哪一段，别让 ffmpeg 去猜。"""
        from komaflow.core.segment import plan_segments
        from komaflow.core.errors import KomaFlowError

        with tempfile.TemporaryDirectory() as tmp:
            segment = plan_segments(12, 6)[0]
            frames = png_frames_of(Path(tmp) / "work", segment)
            frames.directory.mkdir(parents=True, exist_ok=True)
            with self.assertRaises(KomaFlowError):
                stage_frames_zero_based(frames, Path(tmp) / "stage")


class TestTransparentRules(unittest.TestCase):
    """「渲染背景」的四态规则（用户 2026-10-17 定，取代旧的设计取舍/4）。

    ============ ============ ====================================
    角色 舞台 这一项
    ============ ============ ====================================
    有 无 默认关（= 出透明），可选
    无 有 默认开（照舞台渲），**可选**（旧版会灰掉）
    无 无 默认开，**变灰**
    有 有 默认开，可选
    ============ ============ ====================================
    """

    def _project(self, **inputs) -> Project:
        base = {"route": "assets", "model": "m.pmx", "motion": "a.vmd"}
        base.update(inputs)
        return Project(name="t", inputs=Inputs(**base))

    # ---------------------------------------------------------- 四种组合
    def test_character_only_is_transparent_by_default(self):
        """有角色、没舞台 → 默认出透明（最常用的用法）。"""
        project = self._project()
        self.assertTrue(project.transparent_allowed())
        self.assertTrue(project.default_transparent())
        self.assertTrue(project.effective_transparent())

    def test_stage_only_is_allowed_but_renders_background(self):
        """没角色、有舞台 → **可选**（旧版灰掉），默认照舞台渲。"""
        project = self._project(model=None, stage="s.pmx")
        self.assertTrue(project.transparent_allowed())
        self.assertFalse(project.default_transparent())
        self.assertFalse(project.effective_transparent())

    def test_nothing_is_disallowed(self):
        """两样都没有 → 只有这种情况变灰。"""
        project = self._project(model=None)
        self.assertFalse(project.transparent_allowed())
        self.assertFalse(project.effective_transparent())

    def test_character_and_stage_are_both_selectable(self):
        """有角色、也有舞台 → 可选，**默认照背景渲**。

        ⚠️ 这条是旧规则的直接反转：旧版"放了舞台就互斥"，等于逼着用户
           "想看透明就只能清空舞台"。现在两样都能要。
        """
        project = self._project(stage="s.pmx")
        self.assertTrue(project.transparent_allowed())
        self.assertFalse(project.default_transparent())
        self.assertFalse(project.effective_transparent())

    # ---------------------------------------------------------- 用户手选
    def test_user_can_force_transparent_even_with_stage(self):
        """手动关掉「渲染背景」→ 就算放了舞台也出透明。"""
        project = self._project(stage="s.pmx")
        project.params.transparent_background = False # 「渲染背景」= 关
        project.params.transparent_touched = True
        self.assertTrue(project.effective_transparent())

    def test_user_can_force_background_without_stage(self):
        """手动打开「渲染背景」→ 就算没放舞台也不出透明。"""
        project = self._project()
        project.params.transparent_background = True
        project.params.transparent_touched = True
        self.assertFalse(project.effective_transparent())

    def test_untouched_falls_back_to_default(self):
        """没拨过 → 按默认规则走（哪怕字段值是 False）。"""
        project = self._project()
        project.params.transparent_background = False
        project.params.transparent_touched = False
        self.assertTrue(project.effective_transparent())

    def test_own_blend_keeps_user_background(self):
        """自带 .blend 不替用户改背景（设计取舍）—— 哪怕他手动开了开关。"""
        project = Project(name="t", inputs=Inputs(route="blend", blend="u.blend"))
        project.params.transparent_background = False
        project.params.transparent_touched = True
        self.assertFalse(project.effective_transparent())
        self.assertFalse(project.transparent_allowed())

    # ---------------------------------------------------------- 编码器校验
    def test_bad_alpha_codec_is_reported(self):
        project = self._project()
        project.params.alpha_codec = "随便写的"
        self.assertTrue(any("透明成片的格式" in p for p in project.validate()))
        # 取编码器名时也不能崩，退回默认值
        self.assertEqual(project.alpha_codec_name(), DEFAULT_ALPHA_CODEC)

    def test_mp4_is_not_blocked_when_background_is_rendered(self):
        """不出透明时，格式选 MP4（h264）**不该被拦**。

        ⚠️ 这条是用户截图里那个 bug 的回归测试：
           MP4 是格式下拉的第一个选项、也是默认值，旧版却无条件按
           "透明成片的格式只能是 prores/qtrle/png" 把它挡下来，
           报错内容还跟界面显示的选择对不上。
        丢进"透明成片"这个筐里的校验，只对透明成片成立。
        """
        project = self._project(model="m.pmx", stage="s.pmx") # 照背景渲
        project.params.alpha_codec = "h264"
        self.assertFalse(project.effective_transparent())
        self.assertFalse([p for p in project.validate() if "透明成片" in p])

    def test_mp4_is_blocked_when_actually_transparent(self):
        """真的会出透明时，选 MP4 仍然要拦 —— 它带不了 alpha。"""
        project = self._project() # 有角色没舞台 → 出透明
        project.params.alpha_codec = "h264"
        self.assertTrue(project.effective_transparent())
        problems = [p for p in project.validate() if "透明成片" in p]
        self.assertTrue(problems)
        # 提示里要给出路，而不是只说"不行"
        self.assertIn("MP4", problems[0])


class TestRunPlan(unittest.TestCase):
    """段级续渲（K-2.7 / K-2.8）—— 本产品的核心价值之一。"""

    def test_fresh_run_all_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = plan_run(3000, tmp, limit=1000)
            self.assertEqual(len(plan.segments), 3)
            self.assertEqual(len(plan.pending), 3)
            self.assertEqual(plan.completed, [])
            self.assertFalse(plan.is_resume)

    def test_completed_segment_is_skipped(self):
        """已完成的段不重跑 —— 前一段的产物在，就跳过它。"""
        with tempfile.TemporaryDirectory() as tmp:
            first = segment_path(tmp, plan_run(3000, tmp).segments[0].segment, "mp4")
            first.parent.mkdir(parents=True, exist_ok=True)
            first.write_bytes(b"x" * 4096)
            prober = make_prober_from_table(
                {first.name: VideoInfo(frame_count=1000, duration_seconds=33.33, fps=30.0)}
            )

            plan = plan_run(3000, tmp, limit=1000, prober=prober)
            self.assertEqual(len(plan.completed), 1)
            self.assertEqual([s.index for s in plan.pending], [1, 2])
            self.assertTrue(plan.is_resume)
            self.assertIn("跳过", plan.summary())

    def test_without_prober_never_claims_completed(self):
        """没有探测器时不升级为"已完成" —— 宁可重跑一段，也不交付残片。"""
        with tempfile.TemporaryDirectory() as tmp:
            first = segment_path(tmp, plan_run(3000, tmp).segments[0].segment, "mp4")
            first.parent.mkdir(parents=True, exist_ok=True)
            first.write_bytes(b"x" * 4096)

            plan = plan_run(3000, tmp, limit=1000)
            self.assertEqual(plan.completed, [])
            self.assertEqual(len(plan.pending), 3)

    def test_single_segment_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = plan_run(800, tmp, limit=1000)
            self.assertEqual(len(plan.segments), 1)
            self.assertIn("不分段", plan.segments[0].segment.__str__() + "不分段")


class TestAutoLightFollowsCamera(unittest.TestCase):
    """PMX 路线的自动补光：**跟着相机走**，并且角色有一份**不投影的自带光**。

    这两条都是啃掉画面问题之后立的规矩。

    **① 光必须跟相机。** 原来那盏 SUN 是固定方向
    （``rotation_euler = (0.9, 0, 0.35)``，约等于垂直向下），而相机是被
    镜头动作驱动的 —— 两者对不上，角色就是一坨近黑剪影。实测：
    固定朝下 energy 3 → 角色身上 **5.4/255**；沿相机方向 → **41.8/255**。

    **② 角色必须有一盏 ``use_shadow = False`` 的自带光。**
    用户要求「让角色自带打光，不受环境影响」。这条**不能靠普通太阳**实现 ——
    封闭舞台（观景车厢）会把阳光挡死。实测：

    ======================================== ==============
    做法 画面亮度
    ======================================== ==============
    原来（两盏太阳 + 世界 0.35） 48.5/255
    关掉世界、太阳从 15 加到 250 0.1/255（全黑）
    相机跟随光**开投影** 20 48.5/255（被挡住 = 白加）
    相机跟随光**不投影** 5 / 10 / 20 102 / 127 / 152 ✅
    ======================================== ==============

    ⚠️ 这些是**源文件级**的契约检查（不跑 Blender）：编译得起来、名字对得上、
       关键参数没被改回去。真机观感由 ``work/diag_self_lighting.py`` 量。
    """

    @classmethod
    def setUpClass(cls):
        import komaflow.adapters.scripts as _pkg # noqa: F401 （确保包可导入）

        cls.source = (Path(komaflow.core.__file__).parent.parent / "adapters"
                      / "scripts" / "build.py").read_text(encoding="utf-8")

    def test_light_direction_comes_from_camera(self):
        self.assertIn("_camera_forward", self.source,
                      "补光应当按相机朝向算，而不是写死一个方向")
        self.assertIn("_aim_sun", self.source)

    def test_no_hardcoded_light_rotation(self):
        """把那个"垂直向下"的写死角度钉死，别再回来。"""
        self.assertNotIn("rotation_euler = (0.9, 0.0, 0.35)", self.source,
                         "固定朝下的灯又要回来了 —— 角色会变成黑剪影")

    def test_key_energy_is_not_back_to_3(self):
        self.assertIn("light_data.energy = 15.0", self.source,
                      "主光能量被改回 3.0 的话，方向修好了也还是偏暗（41.8/255）")

    def test_there_is_a_fill_light(self):
        self.assertIn("KomaFlow_Fill", self.source,
                      "只有主光的话，背光那面会死黑")

    def test_character_has_a_shadowless_own_light(self):
        """角色自带光必须**不投影** —— 去掉这个开关，封闭舞台会把它一起挡掉。"""
        self.assertIn("KomaFlow_Cam", self.source)
        self.assertIn("cam_data.use_shadow = False", self.source,
                      "自带光一旦开投影，封闭场景里就等于没加（实测 152 → 48.5）")
        self.assertIn("cam_data.energy = 5.0", self.source)

    def test_lights_are_locked_to_camera_every_frame(self):
        """光必须**逐帧**绑死相机朝向，不能只在装配时算一次。

        「只在某一帧算一次」的隐患：镜头一动，光与相机的相对角度就变了，
        会出现"某个角度特别暗"的帧。所以注册 ``frame_change_post``，
        逐帧按当前相机重摆 —— 处理器会随 ``work.blend`` 存盘，
        长驻渲染进程渲每一帧都照做。
        """
        self.assertIn("_lock_lights_to_camera", self.source)
        self.assertIn("frame_change_post.append", self.source,
                      "没有逐帧处理器的话，镜头一动光照就跟着漂")
        self.assertIn("light_lock", self.source,
                      "装配报告里要能查到这一步做没做")

    def test_light_lock_runs_after_camera_is_settled(self):
        """锁方向的**调用**必须在相机就位之后 —— 否则锁的是个错方向。"""
        # ⚠️ 锚点要认"调用处"（带 report 赋值那一行），不能只搜函数名 ——
        # 函数定义在上面，一搜就命中定义，测试永远误判。
        call_at = self.source.index('report["light_lock"] = _lock_lights_to_camera()')
        settle_at = self.source.index('report["camera_fallback"]')
        self.assertGreater(call_at, settle_at,
                           "锁光应当在相机兜底之后才执行")

    def test_only_shadowless_light_follows_camera(self):
        """逐帧跟随的**只能是不投影的那盏**。

        用户报过"背景光莫名抽风闪烁"。根因：三盏灯都逐帧跟着相机转，
       而 Key / Fill **有投影** —— 相机一动，它们的影子就在背景上扫，
        每帧阴影图都要重算，64 采样的 EEVEE 压不住这种抖动，背景一亮一暗。

        所以现在的分工必须守住：
        * ``KomaFlow_Cam``（不投影）跟着相机 → 角色亮度恒定
        * ``KomaFlow_Key`` / ``KomaFlow_Fill``（有投影）**固定** → 背景不闪
        """
        # 取 `_follow` 的函数体（从定义到它被 append 的那行）
        start = self.source.index("def _follow(")
        end = self.source.index("bpy.app.handlers.frame_change_post.append(_follow)")
        body = self.source[start:end]
        self.assertIn('_lights.get("cam")', body,
                      "逐帧跟随的应当是那盏不投影的相机光")
        self.assertNotIn('_lights["key"]', body,
                         "带投影的主光一旦逐帧转，背景的阴影就会闪")
        self.assertNotIn('_lights["fill"]', body,
                         "带投影的补光一旦逐帧转，背景的阴影就会闪")


class TestLayerGuards(unittest.TestCase):
    """ / 用测试守住：核心层不得碰 Blender，也不得出现版本相关常量。"""

    IMPORT_BPY = re.compile(r"^\s*(?:import|from)\s+bpy\b", re.MULTILINE)

    def _core_sources(self) -> list[Path]:
        root = Path(komaflow.core.__file__).parent
        return sorted(root.glob("*.py"))

    def test_core_has_sources(self):
        self.assertGreaterEqual(len(self._core_sources()), 4)

    def test_core_never_imports_bpy(self):
        for path in self._core_sources():
            with self.subTest(file=path.name):
                self.assertIsNone(
                    self.IMPORT_BPY.search(path.read_text(encoding="utf-8")),
                    f"{path.name} 属于核心逻辑层，不得导入 bpy",
                )

    def test_core_has_no_version_specific_constants(self):
        """版本相关的写法差异只能出现在适配层。"""
        forbidden = ("BLENDER_EEVEE", "surface_render_method", "compositing_node_group", "FFMPEG")
        for path in self._core_sources():
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                with self.subTest(file=path.name, token=token):
                    self.assertNotIn(
                        token, text,
                        f"{token} 是 Blender 版本相关的写法，必须收在 adapters/",
                    )


class TestNoConsoleWindows(unittest.TestCase):
    """用户明确要求：**执行时后台不要弹出命令窗口**。

    这是最容易漏的一处 —— 只要有一个 subprocess 忘了带标志，用户就会看到黑框一闪。
    所以拿测试钉住：Blender 执行、Blender 探测、ffmpeg / ffprobe 四处都要带。
    """

    CREATE_NO_WINDOW = 0x08000000

    def test_blender_executor_sets_no_window(self):
        from komaflow.adapters.executor import _no_window_kwargs

        kwargs = _no_window_kwargs()
        if os.name == "nt":
            self.assertIn("creationflags", kwargs)
            self.assertTrue(kwargs["creationflags"] & self.CREATE_NO_WINDOW)
            self.assertIn("startupinfo", kwargs)
        else:
            self.assertEqual(kwargs, {})

    def test_blender_probe_sets_no_window(self):
        from komaflow.adapters.blender5 import _no_window

        if os.name == "nt":
            self.assertTrue(_no_window()["creationflags"] & self.CREATE_NO_WINDOW)
        else:
            self.assertEqual(_no_window(), {})

    def test_ffmpeg_sets_no_window(self):
        from komaflow.media.ffmpeg import _no_window

        if os.name == "nt":
            self.assertTrue(_no_window()["creationflags"] & self.CREATE_NO_WINDOW)
        else:
            self.assertEqual(_no_window(), {})


class TestJournal(unittest.TestCase):
    """日志只落盘、不上界面。"""

    def test_write_and_tail(self):
        from komaflow.core.journal import Journal

        with tempfile.TemporaryDirectory() as tmp:
            journal = Journal(Path(tmp))
            journal.write("第一条")
            journal.warn("第二条")
            journal.error("第三条")
            self.assertTrue(journal.path.is_file())
            text = journal.tail(10)
            self.assertIn("第一条", text)
            self.assertIn("WRN 第二条", text)
            self.assertIn("ERR 第三条", text)
            self.assertEqual(journal.path.parent.name, "logs")

    def test_broken_directory_does_not_raise(self):
        """日志失败绝不能影响主流程。"""
        from komaflow.core.journal import Journal

        journal = Journal()
        journal.write("没有绑定目录时静默丢弃")
        self.assertIsNone(journal.path)

    def test_progress_events_are_not_logged(self):
        """progress 事件刻意不落盘 —— 一段 1000 帧会打 40 条，纯噪音。"""
        import tempfile as _tempfile
        from komaflow.core.journal import Journal
        from komaflow.core.pipeline import make_sink

        with _tempfile.TemporaryDirectory() as tmp:
            journal = Journal(Path(tmp))
            seen: list[dict] = []
            sink = make_sink(seen.append, journal)
            sink({"type": "progress", "percent": 42.0})
            sink({"type": "stage", "stage": "render", "message": "开渲"})
            self.assertEqual(len(seen), 2) # 界面照收
            text = journal.tail(10)
            self.assertNotIn("42.0", text) # 但进度不落盘
            self.assertIn("阶段 render", text)


if __name__ == "__main__":
    unittest.main()
