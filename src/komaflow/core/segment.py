"""分段、帧号、预热偏移与抽帧规则（纯逻辑）。

对应需求：K-1（预热）· K-2（分段与续渲）· K-3（抽帧）· 设计取舍 / 11 / 13。

本模块是核心逻辑层中最"干净"的一块：**不导入 bpy、不碰文件系统、不依赖 GUI**。
所有函数都是**确定性纯函数** —— 同输入必得同输出，直接支撑 NFR-7（可复现性）。

帧号的唯一基准
--------------
**所有帧号一律为「工程时间轴」帧号，自第 0 帧起算，且含预热帧**（设计取舍 / K-2.1）。
需要与 VMD 内部帧号换算时，用 :func:`vmd_to_scene_frame`。
"""

from __future__ import annotations

from dataclasses import dataclass

#: 单段上限默认值（设计取舍）。它是**天花板，不是固定切分单位**。
DEFAULT_SEGMENT_LIMIT: int = 1000

#: 物理预热帧数默认值（设计取舍）。0 ~ 300 可配，**工程级参数**（设计取舍）。
DEFAULT_PREROLL_FRAMES: int = 30

#: 预热帧数合法上限（K-1.1）。
MAX_PREROLL_FRAMES: int = 300

#: 抽帧数量硬上限（设计取舍：>5000 帧时用户自选，上限 100）。
MAX_SAMPLE_FRAMES: int = 100


# --------------------------------------------------------------------------
# 分段
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Segment:
    """一个渲染段。

    段是**续渲的最小粒度**（K-2.7）：已完成的段不重跑，段内失败则整段重跑。
    ``start`` / ``end`` 均为闭区间端点，且都是工程时间轴帧号。
    """

    index: int
    start: int
    end: int

    @property
    def count(self) -> int:
        """本段帧数。"""
        return self.end - self.start + 1

    def filename(self, ext: str = "mp4") -> str:
        """段产物文件名。

        K-2.6 要求每段独立落盘、独立可识别；命名里带上起止帧，便于人工核对
        与"段级续渲"时判断是否缺失（K-2.8 只看产物文件）。
        """
        return f"seg_{self.index:04d}_{self.start:06d}-{self.end:06d}.{ext}"

    def __str__(self) -> str: # pragma: no cover - 仅用于日志/CLI
        return f"第 {self.index + 1} 段：帧 {self.start} ~ {self.end}（{self.count} 帧）"


def plan_segments(
    total_frames: int,
    limit: int | None = DEFAULT_SEGMENT_LIMIT,
    *,
    first_frame: int = 0,
) -> list[Segment]:
    """切分渲染段。

    规则（K-2.1 ~ K-2.3）：

    * 从 ``first_frame`` 起按 ``limit`` 顺序切分，**含预热帧一起计数**
    * ``total_frames <= limit`` → **不分段，一次渲完**（不切、不补齐）
    * 末段为剩余帧数，**不做补齐**
    * ``limit=None`` → 强制不分段（K-2.4 的"不分段"高级选项）

    ⚠️ ``first_frame`` 是界面「只渲这一段 30 到 330」的起点。
       以前这里**永远从 0 开始切**，于是那个设置被完全忽略 ——
       用户填了 30 到 330，实际还是从头渲到尾
       （实测：设 120~127，结果渲了 128 帧）。
       段号仍从 0 起，但段的帧号是**工程时间轴的绝对帧号**。

    :raises ValueError: 总帧数或上限不是正整数。
    """
    if total_frames <= 0:
        raise ValueError(f"总帧数必须为正整数，收到 {total_frames!r}")
    base = max(0, int(first_frame))
    last = base + total_frames - 1

    if limit is None:
        return [Segment(0, base, last)]
    if limit <= 0:
        raise ValueError(f"单段上限必须为正整数或 None，收到 {limit!r}")

    if total_frames <= limit:
        return [Segment(0, base, last)]

    segments: list[Segment] = []
    start = base
    index = 0
    while start <= last:
        end = min(start + limit - 1, last)
        segments.append(Segment(index, start, end))
        index += 1
        start = end + 1
    return segments


# --------------------------------------------------------------------------
# 预热与帧号换算（K-1）
# --------------------------------------------------------------------------


def vmd_to_scene_frame(
    vmd_frame: int,
    preroll_frames: int = DEFAULT_PREROLL_FRAMES,
) -> int:
    """VMD 帧号 → 工程时间轴帧号：``场景帧 = VMD帧 + N``（K-1.7）。

    实测证据：VMD 键范围 0–708 → 导入后场景帧 30–738，**时长不变**。

    ✅ **K-1.8 已定论**（见 docs/architecture.md 第 11 节）：默认 margin=0 时 mmd_tools 不会自己加偏移；
    还是须由本工具主动施加？两种可能的实现路径完全不同 ——
    若是自动，我们只需**校验**；若须主动，我们要写**偏移逻辑**。
    因此本函数目前只提供**换算**，不表达"由谁施加"。
    """
    if preroll_frames < 0:
        raise ValueError(f"预热帧数不能为负，收到 {preroll_frames!r}")
    return vmd_frame + preroll_frames


def motion_start_frame(preroll_frames: int = DEFAULT_PREROLL_FRAMES) -> int:
    """动作生效帧（预热结束后的第一帧）。

    K-9.1：音频默认从这里开始；K-9.8：预热帧数变更时音频偏移必须自动跟随，
    因此音频起点**永远**用本函数现算，不得缓存成常量。
    """
    if preroll_frames < 0:
        raise ValueError(f"预热帧数不能为负，收到 {preroll_frames!r}")
    return preroll_frames


def project_total_frames(
    motion_length: int,
    preroll_frames: int = DEFAULT_PREROLL_FRAMES,
) -> int:
    """工程总帧数 = 动作时长（帧） + 预热帧数。

    与需求书 K-2 的示例一致：动作 1500 + 预热 30 = 工程 1530 帧 → 切成 1000 + 530。
    这个总数就是喂给 :func:`plan_segments` 的 ``total_frames``。
    """
    if motion_length <= 0:
        raise ValueError(f"动作时长必须为正整数，收到 {motion_length!r}")
    if preroll_frames < 0:
        raise ValueError(f"预热帧数不能为负，收到 {preroll_frames!r}")
    return motion_length + preroll_frames


def delivery_start_frame(
    preroll_frames: int = DEFAULT_PREROLL_FRAMES,
    strip_preroll: bool = False,
) -> int:
    """成片的第一个帧号。

    K-1.5：提供"裁掉预热帧"开关，成片从动作起始处开始，方便交付；
    **默认不裁**（预热帧保留在成片中，暂按"保留 + 开关可选"）。

    K-9.7：裁掉预热帧时，音频对齐关系必须保持不变 ——
    音频与动作**同步前移**，两者仍严格对齐。调用方须一并使用本函数的返回值。
    """
    return preroll_frames if strip_preroll else 0


# --------------------------------------------------------------------------
# 抽帧取样（K-3 / 设计取舍）
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SamplePolicy:
    """某总帧数下允许的抽帧数量区间。"""

    minimum: int
    maximum: int
    user_choice: bool

    def describe(self) -> str:
        if self.user_choice:
            return f"用户自选（建议 {self.minimum} 帧起，上限 {self.maximum} 帧）"
        return f"{self.minimum} ~ {self.maximum} 帧"


def sample_policy(total_frames: int) -> SamplePolicy:
    """按设计取舍 的分级规则给出抽帧数量：

    ================ ==================
    总帧数 抽帧数
    ================ ==================
    < 3000 5 ~ 10
    3000 ~ 5000 10 ~ 20
    > 5000 用户自选，上限 100
    ================ ==================
    """
    if total_frames <= 0:
        raise ValueError(f"总帧数必须为正整数，收到 {total_frames!r}")
    if total_frames < 3000:
        return SamplePolicy(5, 10, user_choice=False)
    if total_frames <= 5000:
        return SamplePolicy(10, 20, user_choice=False)
    return SamplePolicy(10, MAX_SAMPLE_FRAMES, user_choice=True)


def pick_sample_frames(total_frames: int, count: int) -> list[int]:
    """挑出要抽帧渲染的帧号（K-3.1）。

    做法：在 ``[0, total_frames - 1]`` 上**分层均匀取点**，首尾必取。
    满足三点要求：

    * **覆盖全片**首尾与中段
    * **相邻抽样帧间隔均匀**，不扎堆
    * **确定性** —— 不用随机数，同一工程每次抽同一批帧（NFR-7 可复现性）
    """
    if total_frames <= 0:
        raise ValueError(f"总帧数必须为正整数，收到 {total_frames!r}")
    if count <= 0:
        raise ValueError(f"抽帧数必须为正整数，收到 {count!r}")
    if count > total_frames:
        raise ValueError(f"抽帧数（{count}）不能超过总帧数（{total_frames}）")
    if count == 1:
        return [0]

    span = total_frames - 1
    return [round(span * i / (count - 1)) for i in range(count)]
