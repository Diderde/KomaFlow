"""分段 / 帧号 / 预热 / 抽帧的单元测试。

对应需求：（分段计算、帧号换算、预热偏移的单元测试）。
用例数字**直接取自需求书的表格**，便于与文档逐条对照。
"""

from __future__ import annotations

import unittest

from komaflow.core.segment import (
    DEFAULT_PREROLL_FRAMES,
    MAX_PREROLL_FRAMES,
    MAX_SAMPLE_FRAMES,
    Segment,
    delivery_start_frame,
    motion_start_frame,
    pick_sample_frames,
    plan_segments,
    project_total_frames,
    sample_policy,
    vmd_to_scene_frame,
)


class TestPlanSegments(unittest.TestCase):
    """K-2.1 ~ K-2.3 的切分规则。"""

    def test_at_or_below_limit_is_single_segment(self):
        """K-2.2：总帧数 ≤ 上限 → 不分段，一次渲完（不切、不补齐）。"""
        for total in (1, 2, 800, 999, 1000):
            with self.subTest(total=total):
                plan = plan_segments(total, 1000)
                self.assertEqual(len(plan), 1, f"{total} 帧不该分段")
                self.assertEqual((plan[0].start, plan[0].end), (0, total - 1))

    def test_just_over_limit(self):
        """1001 帧 → 1000 + 1，末段 1 帧不补齐。"""
        plan = plan_segments(1001, 1000)
        self.assertEqual([(s.start, s.end) for s in plan], [(0, 999), (1000, 1000)])
        self.assertEqual([s.count for s in plan], [1000, 1])

    def test_requirement_doc_table(self):
        """需求书 K-2 的切分示例表，逐行核对。"""
        cases = {
            800: [(0, 799)],
            1000: [(0, 999)],
            1001: [(0, 999), (1000, 1000)],
            1530: [(0, 999), (1000, 1529)], # 动作 1500 + 预热 30
            3000: [(0, 999), (1000, 1999), (2000, 2999)],
            5000: [(0, 999), (1000, 1999), (2000, 2999), (3000, 3999), (4000, 4999)],
            7000: [(i * 1000, i * 1000 + 999) for i in range(7)],
        }
        for total, expected in cases.items():
            with self.subTest(total=total):
                plan = plan_segments(total, 1000)
                self.assertEqual([(s.start, s.end) for s in plan], expected)

    def test_coverage_is_contiguous_and_lossless(self):
        """不重不漏：所有段拼起来正好是 0..total-1，且段与段首尾相接。"""
        for total in (1, 999, 1000, 1001, 2500, 7000, 7001):
            with self.subTest(total=total):
                plan = plan_segments(total, 1000)
                self.assertEqual(plan[0].start, 0)
                self.assertEqual(plan[-1].end, total - 1)
                self.assertEqual(sum(s.count for s in plan), total)
                for previous, current in zip(plan, plan[1:]):
                    self.assertEqual(current.start, previous.end + 1)

    def test_segment_index_is_zero_based_and_ordered(self):
        plan = plan_segments(3000, 1000)
        self.assertEqual([s.index for s in plan], [0, 1, 2])

    def test_no_segmentation_option(self):
        """K-2.4 的"不分段"高级选项：limit=None。"""
        plan = plan_segments(7000, None)
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0].count, 7000)

    def test_smaller_limit_reduces_loss_window(self):
        """K-2.4：调小上限可压低单次失败最多白费的时长。"""
        self.assertEqual(len(plan_segments(7000, 500)), 14)
        self.assertEqual(len(plan_segments(7000, 300)), 24)

    def test_rejects_invalid_input(self):
        with self.assertRaises(ValueError):
            plan_segments(0, 1000)
        with self.assertRaises(ValueError):
            plan_segments(-5, 1000)
        with self.assertRaises(ValueError):
            plan_segments(1000, 0)
        with self.assertRaises(ValueError):
            plan_segments(1000, -1)

    def test_segment_filename_carries_range(self):
        """K-2.6：每段独立落盘、可独立识别。"""
        seg = Segment(index=1, start=1000, end=1999)
        self.assertEqual(seg.filename(), "seg_0001_001000-001999.mp4")
        self.assertEqual(seg.filename("mov"), "seg_0001_001000-001999.mov")


class TestPreroll(unittest.TestCase):
    """K-1 预热的帧号换算。"""

    def test_vmd_to_scene_frame_matches_measured_evidence(self):
        """实测证据：VMD 0–708 → 场景 30–738（时长不变）。"""
        self.assertEqual(vmd_to_scene_frame(0, 30), 30)
        self.assertEqual(vmd_to_scene_frame(708, 30), 738)
        self.assertEqual(vmd_to_scene_frame(708, 30) - vmd_to_scene_frame(0, 30), 708)

    def test_motion_start_frame(self):
        """K-9.1：动作生效帧 = 预热结束后的第一帧 = 音频起点。"""
        for preroll in (0, 10, 30, 60):
            with self.subTest(preroll=preroll):
                self.assertEqual(motion_start_frame(preroll), preroll)

    def test_project_total_frames(self):
        """K-2 示例：动作 1500 + 预热 30 = 工程 1530 帧。"""
        self.assertEqual(project_total_frames(1500, 30), 1530)
        self.assertEqual(project_total_frames(709, 30), 739)
        self.assertEqual(project_total_frames(1000, 0), 1000)

    def test_delivery_start_frame(self):
        """K-1.5：默认保留预热帧；开了开关才从动作起始处开始。"""
        self.assertEqual(delivery_start_frame(30, strip_preroll=False), 0)
        self.assertEqual(delivery_start_frame(30, strip_preroll=True), 30)

    def test_defaults_match_requirement(self):
        self.assertEqual(DEFAULT_PREROLL_FRAMES, 30) # 设计取舍
        self.assertEqual(MAX_PREROLL_FRAMES, 300) # K-1.1

    def test_rejects_negative_preroll(self):
        with self.assertRaises(ValueError):
            vmd_to_scene_frame(0, -1)
        with self.assertRaises(ValueError):
            motion_start_frame(-1)
        with self.assertRaises(ValueError):
            project_total_frames(100, -1)
        with self.assertRaises(ValueError):
            project_total_frames(0, 30)


class TestSampling(unittest.TestCase):
    """K-3 / 设计取舍 的抽帧规则。"""

    def test_policy_boundaries(self):
        """设计取舍：<3000 → 5~10；3000~5000 → 10~20；>5000 → 用户自选，上限 100。"""
        cases = [
            (1, (5, 10, False)),
            (2999, (5, 10, False)),
            (3000, (10, 20, False)),
            (5000, (10, 20, False)),
            (5001, (10, MAX_SAMPLE_FRAMES, True)),
            (7000, (10, MAX_SAMPLE_FRAMES, True)),
        ]
        for total, (low, high, user) in cases:
            with self.subTest(total=total):
                policy = sample_policy(total)
                self.assertEqual((policy.minimum, policy.maximum), (low, high))
                self.assertEqual(policy.user_choice, user)

    def test_pick_covers_first_and_last(self):
        """K-3.1：抽样要覆盖全片首尾。"""
        frames = pick_sample_frames(3000, 10)
        self.assertEqual(frames[0], 0)
        self.assertEqual(frames[-1], 2999)
        self.assertEqual(len(frames), 10)

    def test_pick_is_strictly_increasing_and_unique(self):
        frames = pick_sample_frames(7000, 100)
        self.assertEqual(frames, sorted(set(frames)))

    def test_pick_is_deterministic(self):
        """NFR-7 可复现性：同一工程每次抽同一批帧，不引入随机数。"""
        self.assertEqual(pick_sample_frames(4321, 17), pick_sample_frames(4321, 17))

    def test_pick_single_frame(self):
        self.assertEqual(pick_sample_frames(1000, 1), [0])

    def test_pick_rejects_invalid(self):
        with self.assertRaises(ValueError):
            pick_sample_frames(0, 5)
        with self.assertRaises(ValueError):
            pick_sample_frames(100, 0)
        with self.assertRaises(ValueError):
            pick_sample_frames(100, 101)

    def test_sample_policy_rejects_invalid(self):
        with self.assertRaises(ValueError):
            sample_policy(0)


if __name__ == "__main__":
    unittest.main()
