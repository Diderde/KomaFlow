"""磁盘估算与预检的单元测试。

纯 stdlib（NFR-16：运行时零第三方依赖），跟其它测试一样用 ``unittest``。
"""

from __future__ import annotations

import unittest

from komaflow.core.budget import (BYTES_PER_FRAME_PER_MEGAPIXEL, SizeRange,
                                describe, estimate, format_size, free_space,
                                per_frame_bytes, preflight, total)


class TestFormatSize(unittest.TestCase):
    def test_gb(self) -> None:
        self.assertEqual(format_size(2 * 1024 ** 3), "2.0 GB")

    def test_mb(self) -> None:
        self.assertEqual(format_size(300 * 1024 ** 2), "300 MB")

    def test_small_never_zero(self) -> None:
        # 1 字节也别说"0"，说"1 KB"更不容易被当成没算
        self.assertEqual(format_size(1), "1 KB")

    def test_negative_is_zero(self) -> None:
        self.assertEqual(format_size(-5), "0")


class TestPerFrame(unittest.TestCase):
    def test_scales_with_pixels(self) -> None:
        small = per_frame_bytes("prores", 1280, 720)
        big = per_frame_bytes("prores", 2560, 1440)
        # 像素多 4 倍，单帧大约也该多 4 倍
        self.assertAlmostEqual(big[0] / small[0], 4.0, delta=0.05)

    def test_qtrle_bigger_than_prores(self) -> None:
        # 这是选编码器的核心依据：无损 RLE 比 ProRes 大得多
        self.assertGreater(per_frame_bytes("qtrle", 2560, 1440)[0],
                           per_frame_bytes("prores", 2560, 1440)[0])

    def test_unknown_codec_is_empty(self) -> None:
        self.assertEqual(per_frame_bytes("nope", 100, 100), (0, 0))

    def test_always_a_range(self) -> None:
        for codec in BYTES_PER_FRAME_PER_MEGAPIXEL:
            low, high = per_frame_bytes(codec, 1920, 1080)
            self.assertLess(low, high, f"{codec} 应该给区间而不是单点")


class TestEstimate(unittest.TestCase):
    def test_two_tracks_when_alpha(self) -> None:
        ranges = estimate(100, 1280, 720, alpha_codec="qtrle", also_mp4=True)
        self.assertEqual(set(ranges), {"qtrle", "h264"})

    def test_single_track_without_alpha(self) -> None:
        ranges = estimate(100, 1280, 720, alpha_codec="", also_mp4=True)
        self.assertEqual(set(ranges), {"h264"})

    def test_zero_frames_is_zero(self) -> None:
        self.assertEqual(total(estimate(0, 1280, 720)).high, 0)

    def test_2k_3min_qtrle_is_tens_of_gb(self) -> None:
        # 用户会拿这个数做决定，锚住它：2K 30fps 三分钟（5400 帧）
        # QTRLE 应该是几十 GB 量级，不能算出个几 GB 就完事
        size = total(estimate(5400, 2560, 1440, alpha_codec="qtrle"))
        self.assertGreater(size.high, 20 * 1024 ** 3)
        self.assertLess(size.high, 120 * 1024 ** 3)

    def test_prores_is_far_smaller(self) -> None:
        qtrle = total(estimate(5400, 2560, 1440, alpha_codec="qtrle"))
        prores = total(estimate(5400, 2560, 1440, alpha_codec="prores"))
        self.assertLess(prores.high, qtrle.high * 0.5)


class TestSizeRange(unittest.TestCase):
    def test_add(self) -> None:
        self.assertEqual(SizeRange(1, 2) + SizeRange(10, 20), SizeRange(11, 22))

    def test_str_range(self) -> None:
        self.assertIn("~", str(SizeRange(1024 ** 3, 2 * 1024 ** 3)))


class TestPreflight(unittest.TestCase):
    def test_can_read_this_drive(self) -> None:
        # 拿当前目录当靶子：任何一台机器上它都存在
        self.assertIsNotNone(free_space("."))

    def test_missing_path_walks_up(self) -> None:
        # 输出目录往往还没建，得往上找父目录而不是直接失败
        self.assertIsNotNone(free_space("./definitely/not/here/yet"))

    def test_empty_path_is_none(self) -> None:
        self.assertIsNone(free_space(""))

    def test_ok_when_void_is_huge(self) -> None:
        check = preflight(".", SizeRange(1, 2))
        self.assertTrue(check.ok)

    def test_shortfall_reported(self) -> None:
        # 故意要 1 PB：一定不够，且必须说清差多少
        check = preflight(".", SizeRange(0, 1024 ** 5))
        self.assertFalse(check.ok)
        self.assertGreater(check.shortfall, 0)
        self.assertIn("还差", check.message())

    def test_message_has_no_jargon(self) -> None:
        text = preflight(".", SizeRange(0, 1)).message()
        for word in ("codec", "buffer", "bitrate", "bytes"):
            self.assertNotIn(word, text)


class TestDescribe(unittest.TestCase):
    def test_lists_both_tracks(self) -> None:
        text = describe(5400, 2560, 1440, alpha_codec="qtrle", path=".")
        self.assertIn("预计占用", text)
        self.assertIn("5400 帧", text)
        self.assertIn("GB", text)

    def test_no_frames_is_blank(self) -> None:
        self.assertEqual(describe(0, 2560, 1440, also_mp4=False, path="."), "")


if __name__ == "__main__":
    unittest.main()
