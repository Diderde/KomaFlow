"""渲染前的磁盘占用估算与空间预检。

为什么需要
----------
带透明通道的交付（MOV / PNG 序列）**非常占磁盘**：2K 三分钟大约 6~50GB，
取决于编码器。用户的意见很明确：

    磁盘是用户自己的，**不要替他省，但要提前把数字算出来告诉他**。

所以这里只做两件事 —— **估算**和**预检**，不做任何"帮你缩小体积"的决定。
编码器仍然由用户选。

估算 vs 实测
------------
下面的系数是「**每帧每百万像素的字节数**」，来自典型 MMD 画面（大量渐变、
软阴影、头发丝）的经验值：

* **QTRLE** 是行程编码，这种画面上几乎压不动，系数接近原始像素体积
* **ProRes / H.264** 小得多

一律**给区间不给单点** —— 画面复杂度差异很大，给一个数就是骗人。
界面上要写成"预计 18~42GB"，不要写成"预计 30GB"。
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

#: 百万像素
MEGAPIXEL = 1_000_000

#: 编码器 → (每帧每百万像素的字节数下限, 上限)
BYTES_PER_FRAME_PER_MEGAPIXEL: dict[str, tuple[int, int]] = {
    # 无损 RLE：MMD 画面里几乎找不到连续相同像素，等于近乎不压缩
    "qtrle": (1_080_000, 2_440_000),
    # ProRes 4444：视觉无损 + 带 alpha，后期行业标准
    "prores": (300_000, 760_000),
    # PNG 序列：无损 + 带 alpha，最通用但文件最琐碎
    "png": (540_000, 1_600_000),
    # H.264 成品（不带 alpha）
    "h264": (12_000, 40_000),
}

#: 给人看的名字。措辞刻意避开行话（用户看着费劲）。
CODEC_LABELS: dict[str, str] = {
    "qtrle": "透明 MOV（无损，体积最大）",
    "prores": "透明 MOV（ProRes，体积小得多）",
    "png": "透明 PNG 序列（一个文件夹的图）",
    "h264": "普通 MP4（不带透明）",
}

#: 透明成片**默认用哪个**。
#: 用户的要求是"磁盘是用户自己的，别替他省、但要提前告知"，
#: 所以这里只是给个**更划算的默认值**，不是替他把路堵死 ——
#: 换了编码器，界面上的预估数字会跟着变，他看得见。
#:
#: 选 ProRes 的理由：2K 三分钟约 6~15GB，只有无损 RLE（QTRLE）的 1/3，
#: 肉眼看不出画质差别，后期软件（AE/PR/达芬奇）还更认它。
DEFAULT_ALPHA_CODEC = "prores"


@dataclass(frozen=True)
class SizeRange:
    """一段占用空间的估算区间。"""

    low: int
    high: int

    def __str__(self) -> str:
        if self.high <= 0:
            return "0"
        if self.low == self.high:
            return format_size(self.high)
        return f"{format_size(self.low)} ~ {format_size(self.high)}"

    def __add__(self, other: "SizeRange") -> "SizeRange":
        return SizeRange(self.low + other.low, self.high + other.high)


def format_size(count: int) -> str:
    """把字节数写成中文习惯的大小。"""
    if count < 0:
        return "0"
    giga = 1024 ** 3
    mega = 1024 ** 2
    if count >= giga:
        return f"{count / giga:.1f} GB"
    if count >= mega:
        return f"{count / mega:.0f} MB"
    return f"{max(1, round(count / 1024))} KB"


def per_frame_bytes(codec: str, width: int, height: int) -> tuple[int, int]:
    """某个编码器在给定分辨率下单帧的字节数区间。"""
    low, high = BYTES_PER_FRAME_PER_MEGAPIXEL.get(codec, (0, 0))
    megapixels = max(1, width * height) / MEGAPIXEL
    return round(low * megapixels), round(high * megapixels)


def estimate(frames: int, width: int, height: int, *,
             alpha_codec: str = DEFAULT_ALPHA_CODEC, also_mp4: bool = False,
             ) -> dict[str, SizeRange]:
    """按每条输出轨分别估算。

    返回 ``{编码器: SizeRange}``。``frames`` 是总帧数（含预热帧之后的正片）。

    ⚠️ ``also_mp4`` 默认 **False**：老版本在透明路径上会**额外**编一条
       垫底色的 MP4，现在不再那样做了（用户要求"选什么就出什么"）。
       估算要是还按两条轨算，就会把磁盘占用报成两倍，用户会被吓到。
    """
    frames = max(0, int(frames))
    result: dict[str, SizeRange] = {}
    if alpha_codec:
        low, high = per_frame_bytes(alpha_codec, width, height)
        result[alpha_codec] = SizeRange(low * frames, high * frames)
    if also_mp4:
        low, high = per_frame_bytes("h264", width, height)
        result["h264"] = SizeRange(low * frames, high * frames)
    return result


def total(ranges: dict[str, SizeRange]) -> SizeRange:
    """把各条轨加总。"""
    low = high = 0
    for item in ranges.values():
        low += item.low
        high += item.high
    return SizeRange(low, high)


def estimate_total(frames: int, width: int, height: int, *,
                   alpha_codec: str = DEFAULT_ALPHA_CODEC,
                   also_mp4: bool = False) -> SizeRange:
    """所有输出轨**加总**后的占用区间（界面上那句"预计 5.8 ~ 14.8 GB"）。

    上面 :func:`total` 收的是"已经算好的字典"，这里是"直接给参数就要总数"——
    界面只想报一个总数时不用自己绕两圈。
    """
    return total(estimate(frames, width, height, alpha_codec=alpha_codec,
                          also_mp4=also_mp4))


def compact_range(size: SizeRange) -> str:
    """紧凑写法：``5.8~14.8GB``（不带空格、不带"预计"）。

    用来把区间塞进一行摘要条。**仍然是区间不是单点** —— 给一个数就是骗人。
    """
    if size.high <= 0:
        return "0"
    low = format_size(size.low).replace(" ", "")
    high = format_size(size.high).replace(" ", "")
    if low == high:
        return high
    return f"{low}~{high}"


def free_space(path: str | Path | None) -> int | None:
    """查目标盘剩余空间；查不到返回 ``None``（不能让预检把程序搞崩）。"""
    if not path:
        return None
    target = Path(path)
    # 目录可能还不存在，就往上找到第一个存在的父目录
    while not target.exists() and target.parent != target:
        target = target.parent
    try:
        return shutil.disk_usage(str(target)).free
    except OSError:
        return None


@dataclass(frozen=True)
class DiskCheck:
    """预检结果。"""

    free: int | None
    needed: int
    needed_low: int

    @property
    def ok(self) -> bool:
        """按**上限**判断：宁可按最坏情况拦，也不要渲染到一半写满盘。"""
        return self.free is None or self.free >= self.needed

    @property
    def shortfall(self) -> int:
        return max(0, self.needed - (self.free or 0))

    def message(self) -> str:
        """一句人话。够用就报数，不够就说清还差多少、怎么办。"""
        if self.free is None:
            return ""
        if self.ok:
            return (f"磁盘够用：预计占用 {format_size(self.needed_low)} ~ "
                    f"{format_size(self.needed)}，所在盘剩余 {format_size(self.free)}。")
        return (f"磁盘可能不够：预计最多要 {format_size(self.needed)}，"
                f"但所在盘只剩 {format_size(self.free)}，"
                f"还差约 {format_size(self.shortfall)}。"
                f"可以把「输出目录」换到别的盘，或者改用体积小的编码。")

    def as_dict(self) -> dict:
        return {"free": self.free, "needed": self.needed,
                "needed_low": self.needed_low, "ok": self.ok}


def preflight(path: str | Path | None, size: SizeRange) -> DiskCheck:
    """渲染前查一次盘。"""
    return DiskCheck(free=free_space(path), needed=size.high,
                     needed_low=size.low)


def describe(frames: int, width: int, height: int, *,
             alpha_codec: str = DEFAULT_ALPHA_CODEC,
             also_mp4: bool = True, path: str | Path | None = None) -> str:
    """给界面用的一句话：预计占用 + 盘够不够。"""
    ranges = estimate(frames, width, height, alpha_codec=alpha_codec,
                      also_mp4=also_mp4)
    check = preflight(path, total(ranges))
    detail = "，".join(f"{CODEC_LABELS.get(codec, codec)} {size}"
                       for codec, size in ranges.items() if size.high > 0)
    if not detail:
        return ""
    head = f"预计占用（{frames} 帧）：{detail}"
    return f"{head}　|　{check.message()}" if check.message() else head
