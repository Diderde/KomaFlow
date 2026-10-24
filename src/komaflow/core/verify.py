"""产物校验与原子写入。

对应需求：设计取舍 / FR-8.10（**成败判定不得依赖 Blender 退出码**）·
FR-8.4（成片完整性校验）· K-2.6 ~ K-2.8（段级续渲的判定依据）· （写入原子化）。

为什么要这么小心
----------------
实测：用户机器上安装的**第三方插件在 Blender 退出时抛异常**，
导致**渲染成功但退出码是 1**。因此本工具一律**校验产物文件**来判定成败。

另一个坑是"半成品被误判为已完成"：崩溃时留下的半个 MP4 完全可能是
一个合法的、能打开的文件。对策是**先写临时文件、完成后再改名**，
这样"文件已存在"才真正等于"这一段完成了"。
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Protocol

from .errors import ErrorKind, KomaFlowError

#: 段产物临时后缀。写入期间叫 ``xxx.mp4.part``，完成后改名为 ``xxx.mp4``。
TEMP_SUFFIX: str = ".part"

#: 段产物最小可信体积。远小于任何真实视频，只用来挡住 0 字节与残片。
MIN_SEGMENT_BYTES: int = 1024

#: 段产物目录名（位于工具自有工作目录下，不散落到用户工程里 —— K-7.14）。
SEGMENTS_DIRNAME: str = "segments"


class ArtifactState(str, Enum):
    """一个段产物的状态。"""

    MISSING = "missing" # 还没有
    PARTIAL = "partial" # 残片 / 0 字节 / 探测不通过 → 视为**未完成**，须重跑
    UNVERIFIED = "unverified" # 文件在、体积像样，但还没验帧数与时长
    VERIFIED = "verified" # 已确认完整 → 可跳过（K-2.7 段级续渲）


@dataclass(frozen=True)
class VideoInfo:
    """视频探测结果。由适配层提供（需 Blender 的 ``bpy.data.movieclips``）。"""

    frame_count: int
    duration_seconds: float
    fps: float


class VideoProber(Protocol):
    """探测视频的函数签名。实现放适配层，核心层只依赖这个协议。"""

    def __call__(self, path: Path) -> VideoInfo: ...


# --------------------------------------------------------------------------
# 路径约定
# --------------------------------------------------------------------------


def segments_dir(work_dir: str | Path) -> Path:
    return Path(work_dir) / SEGMENTS_DIRNAME


def png_sequence_dir(work_dir: str | Path, segment, ext: str = "png") -> Path:
    """某一段的 PNG 序列**所在目录**（帧文件直接放这个目录里）。

    🚨 **不要给它加 ``_frames`` 子目录后缀。**
    Blender 渲染图像序列的命名约定是确定的::

        <filepath><帧号><扩展名>

    所以只要把 ``filepath`` 设成 ``<目录>/<段名>.png``，出来的就是
    ``<目录>/<段名>.png0000``、``.png0001`` …… **全都在同一个目录里**。

    早先这里返回的是 ``...<段名>.png_frames``（一个子目录），
    想让 Blender 把帧写进去 —— 但 Blender 不吃这一套：
    它会把那个名字当**文件名**，帧落在**旁边**、还不带扩展名。
    校验按"目录里的 PNG"去找 → **一张都找不到** → 整段判 MISSING →
    重试一次（白渲两遍）→ 报"产物missing（0/6 张）（退出码 0）"。
    **透明的 PNG 序列那条路就是这么废掉的。**
    """
    return segments_dir(work_dir)


#: 早先 PNG 序列放在 ``<段名>.png_frames/`` 子目录里，于是"段目录名去掉 ``_frames``"
#: 就等于"段名前缀"。那个子目录**早就不用了**（见 :func:`png_sequence_dir`）——
#: 谁还按这个后缀去切名字，就会把段名切掉一截。这个常量留着只是让"老约定"
#: 有个名字可指，**不要拿它做切片**。
LEGACY_FRAMES_SUFFIX: str = "_frames"


@dataclass(frozen=True)
class PngFrames:
    """一段 PNG 序列的**唯一权威定义**：去哪找 + 认哪个前缀。

    ``directory`` 给 ffmpeg / 校验当"去哪个目录找"，``prefix`` 是帧文件名
    的前缀（**带 ``.png``**，因为段名就以它结尾）。
    """

    directory: Path
    prefix: str

    def pattern(self) -> str:
        """``glob`` 用的模式（只认本段自己的帧）。"""
        return f"{self.prefix}*"

    def inputs(self) -> str:
        """喂给 ffmpeg 的图片序列模板。

        ⚠️ 只在**帧号从 0 开始**时才对得上！Blender 用的是**工程时间轴**的帧号，
           所以第 2 段起落盘的是 ``…png0006.png`` —— ``%04d`` 永远从 0 数起，
           一个都匹配不到（ffmpeg 报 "No such file or directory"，
           整段编码失败）。要喂 ffmpeg，先用 :func:`stage_frames_zero_based`。
        """
        return str(self.directory / f"{self.prefix}%04d.png")

    def describe(self) -> str:
        return f"{self.directory.name}/{self.prefix}<帧号>.png"


def png_frames_of(work_dir: str | Path, segment) -> PngFrames:
    """某一段的 PNG 序列定义。**三处（渲染 / 校验 / 编码）都调它。**

    为什么要专门有这么个函数
    ------------------------
    这三个地方原来各推导各的：

    * 渲染：``segment_path(work, seg, "png")`` 当 ``filepath`` 前缀
      → 落盘 ``seg_0000_000000-000005.png0000.png``
    * 校验：目录取 ``segments/``、前缀取 ``segment.filename("png")`` → 对得上
    * 编码：把上一个值当**目录**，又按老约定 ``name[:-len("_frames")]`` 切一刀
      → 前缀变成 ``seg_0000_000000-000``，模板拼出
      ``<segments>/seg_0000_000000-000005.png/seg_0000_000000-000.png%04d.png``
      —— 那个"目录"其实是个文件名，ffmpeg 一个输入帧都找不到，
      **不报错、不产出**，``xxx_parts/`` 空着，日志里也看不出问题。

    所以现在只留这一个出处：要目录、要前缀，都从这里拿。
    """
    return PngFrames(directory=png_sequence_dir(work_dir, segment),
                     prefix=segment.filename("png"))


def png_frame_prefix(work_dir: str | Path, segment, ext: str = "png") -> Path:
    """某一段 PNG 帧的**文件名前缀**（交给 Blender 当 ``filepath``）。

    Blender 会在这个前缀后面接 ``帧号 + .png``，所以最终文件名形如
    ``seg_0000_000000-000005.png0000.png``。

    ⚠️ 它跟 :func:`png_sequence_dir` **必须分开**：
    前者给渲染脚本当"往哪个文件写"，后者给校验当"去哪个目录找"。
    混用会导致传给 Blender 的是个目录名，帧就落到目录外面去了
    （实测：``out`` 被当成目录 → Blender 写出 ``segments0000.png``）。

    ⚠️ **别再让第二个人自己拼这个路径。** 编码那一步就是自己拼的，
       还按更老的 ``_frames`` 子目录约定切了一刀，结果成片一个都没有
       （见 :func:`png_frames_of`）。要目录和前缀，用它。
    """
    frames = png_frames_of(work_dir, segment)
    return frames.directory / frames.prefix


# --------------------------------------------------------------------------
# 帧序列 → ffmpeg 的暂存（帧号必须从 0 起）
# --------------------------------------------------------------------------


def stage_frames_zero_based(
    frames: "PngFrames",
    staging_dir: str | Path,
) -> tuple[Path, str]:
    """把一段的帧**按 0 起编号**复制到一个暂存目录，返回 ``(目录, 前缀)``。

    为什么非做这一步
    ----------------
    Blender 落盘用的是**工程时间轴**的帧号：第 1 段是
    ``<段名>.png0000.png``…``0005``，第 2 段是 ``…0006``…``0011``。
    而 ffmpeg 的图片序列模板（``<前缀>%04d.png``）**永远从 0 开始数** ——
    所以第 1 段侥幸能对上，**第 2 段起一个文件都匹配不到**：
    ffmpeg 报一句 `Error opening input: No such file or directory`，
    整段编码失败。分段透明成片就是这么只出得了第一段的。

    次选的几种做法都试过、也都不好：

    * ``-start_number 6`` —— 不解决问题。它只是把起始索引挪到 6，
      于是它去找 ``0006``…``0011``，可这个前缀下**只有 6 个文件**，
      越界之后照样断。
    * 改 Blender 侧编号从 0 起 —— 那样段名里的 ``000006-000011``
      就跟文件名对不上了，排查"这一帧是片子第几帧"时会额外绕一圈。

    复制而不是改名/硬链接：**原帧是"已完成"的凭据**（续渲判据数它），
    动它们会让"数张数"的语义变味；硬链接在跨盘、权限、杀毒软件面前都不稳。
    几百张 2K PNG 复制一下是秒级，不值得为这点开销冒险。

    ⚠️ 帧数对不上时**直接报错**，不糊弄过去。
    """
    source = Path(frames.directory)
    target = Path(staging_dir)
    target.mkdir(parents=True, exist_ok=True)
    files = list_png_frames(source, frames.prefix)
    if not files:
        raise KomaFlowError(
            ErrorKind.ASSET_CORRUPT,
            detail=f"没有可编码的帧：{frames.describe()}",
        )

    # 清掉上一次留下的（重试/续跑时目录可能还在）
    for stale in target.glob("frame_*.png"):
        try:
            stale.unlink()
        except OSError:
            pass

    prefix = "frame_"
    for index, path in enumerate(files):
        destination = target / f"{prefix}{index:04d}.png"
        try:
            shutil.copy2(path, destination)
        except OSError as exc:
            raise KomaFlowError(
                ErrorKind.ASSET_CORRUPT,
                detail=f"复制帧失败（{path.name}）：{exc}",
            ) from exc
    return target, prefix


def segment_path(work_dir: str | Path, segment, ext: str = "mp4") -> Path:
    """段产物的最终路径（不含临时后缀）。

    ``ext="png"`` 时返回的是**帧文件名前缀**（不是目录！）——
    因为那个值会被直接塞给 Blender 当 ``filepath``，而 Blender 会在它后面
    接 ``帧号 + .png``。要去哪个目录找帧，用 :func:`png_sequence_dir`。

    ⚠️ 这两个语义必须分清：把目录当文件名前缀传下去，帧就会落到目录**外面**
    （实测过：``out`` 是个目录名 → Blender 写出 ``segments0000.png``）。
    """
    if ext == "png":
        return png_frame_prefix(work_dir, segment, ext)
    return segments_dir(work_dir) / segment.filename(ext)


def temp_path_for(final: Path) -> Path:
    """最终路径对应的临时路径。"""
    return final.with_name(final.name + TEMP_SUFFIX)


def atomic_commit(temp: str | Path, final: str | Path) -> Path:
    """把临时文件改名成最终文件。

    同一文件系统内的改名是原子的：要么看到旧状态，要么看到完整产物，
    **不会**出现"半个文件被当成完成"。
    """
    temp_path = Path(temp)
    final_path = Path(final)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path.replace(final_path)
    return final_path


# --------------------------------------------------------------------------
# PNG 序列（透明背景那条路走这个）
# --------------------------------------------------------------------------

#: PNG 序列的帧号位数。Blender 默认补 4 位（``0001.png``）。
PNG_FRAME_DIGITS: int = 4


def png_frame_name(prefix: str, frame: int) -> str:
    """序列里某一帧的文件名。前缀就是段名（见 render.py 的说明）。"""
    return f"{prefix}{frame:0{PNG_FRAME_DIGITS}d}.png"


#: PNG 文件头（固定 8 字节）
PNG_SIGNATURE: bytes = b"\x89PNG\r\n\x1a\n"

#: PNG 结尾块 ``IEND`` 的类型字段。最后 12 字节 = 长度(4) + "IEND"(4) + CRC(4)。
PNG_IEND: bytes = b"IEND"

#: 单帧 PNG 的最小合理体积。远小于任何真实画面，只用来挡住空文件。
MIN_PNG_BYTES: int = 128


def looks_like_png(path: Path) -> bool:
    """结构上像不像一张写完的 PNG。

    比对体积阈值更靠谱：体积是个**代理指标**，小分辨率下完全可能误判
    （实测：160×120 的合法帧只有 400 字节，被 1024 的阈值打成了残片）。
    这里直接看两头 —— 开头的固定签名，结尾的 ``IEND`` 块。
    文件写到一半崩掉时，最后一条一定缺 ``IEND``。
    """
    try:
        size = path.stat().st_size
        if size < MIN_PNG_BYTES:
            return False
        with path.open("rb") as handle:
            if handle.read(len(PNG_SIGNATURE)) != PNG_SIGNATURE:
                return False
            handle.seek(max(0, size - 12))
            return PNG_IEND in handle.read(12)
    except OSError:
        return False


def list_png_frames(directory: str | Path, prefix: str = "") -> list[Path]:
    """列出目录里的 PNG 帧，按名字排序。

    ``prefix`` 用来只认本段自己的帧 —— 同一个目录理论上只放一段，
    但万一配置写错把两段写到一个目录里，加前缀能少认错。

    🚨 **不能靠 ``*.png`` 这个模式来认帧。** Blender 渲染序列时的命名是
    "把你给的 filepath 当**前缀**，后面直接接 4 位帧号"，
    而我们给它的前缀本身就以 ``.png`` 结尾（序列目录名是 ``xxx.png_frames``）::

        filepath = ".../seg_0000_000000-000005.png_frames"
        落盘 = ".../seg_0000_000000-000005.png_frames0000"
                     └──────────── 前缀 ────────────┘└帧号┘

    于是文件名里 **``.png`` 在中间、结尾反而是帧号** ——
    ``f"{prefix}*.png"`` 一个都匹配不到，整段会被判成 ``MISSING``。
    表现就是"渲染明明成功、产物却报缺失"，**透明的 PNG 序列那条路全军覆没**。

    所以改成：**先按前缀取候选，再用文件内容确认它真是 PNG**
    （:func:`looks_like_png` 查 PNG 魔数）。
    """
    target = Path(directory)
    if not target.is_dir():
        return []
    # 只按**前缀**认帧，**不要在这里做内容体检**。
    #
    # ⚠️ 早先这里顺手把"不像 PNG"的文件过滤掉了，结果是：一张**渲到一半的
    # 残片**会被悄悄从列表里拿掉，于是"张数对不上"变成了"张数没那么多"，
    # 判定的语义整个变了（该报 PARTIAL 的报了别的）。
    # 体检是 ``verify_png_sequence`` 的活 —— 它要**看见**那张坏文件，
    # 才能说出"张数够但有一张不完整"。
    #
    # ⚠️ 也不能只写 ``*.png``：Blender 落盘的是 ``<前缀>0000.png`` 这种，
    # 而前缀本身以 ``.png`` 结尾，用 ``prefix*`` 才是对的。
    pattern = f"{prefix}*" if prefix else "*"
    return sorted(p for p in target.glob(pattern) if p.is_file())


def verify_png_sequence(
    directory: str | Path,
    expected_frames: int,
    *,
    prefix: str = "",
) -> tuple[ArtifactState, int]:
    """PNG 序列的完整判定：张数对得上、且首尾两张结构完整。

    这是**透明路径下"段级续渲"的唯一判据**，对应视频路径的 :func:`verify_artifact`。
    原来用 ffprobe 验视频帧数，透明改走 PNG 序列之后只能数张数。

    :return: ``(状态, 实际张数)``
    """
    frames = list_png_frames(directory, prefix)
    if not frames:
        return ArtifactState.MISSING, 0

    # 张数不够就是残片：Blender 崩在中间时留下的正是"渲了一半的序列"
    if len(frames) != expected_frames:
        return ArtifactState.PARTIAL, len(frames)

    # ⚠️ 张数对不代表每张都写完：最后一张可能就是崩溃时留下的半截文件。
    # 查首尾两张就够 —— 中间那些早在写下一张的时候就落稳了。
    for candidate in (frames[0], frames[-1]):
        if not looks_like_png(candidate):
            return ArtifactState.PARTIAL, len(frames)

    return ArtifactState.VERIFIED, len(frames)


# --------------------------------------------------------------------------
# 判定
# --------------------------------------------------------------------------


def inspect_artifact(
    path: str | Path,
    *,
    min_bytes: int = MIN_SEGMENT_BYTES,
) -> ArtifactState:
    """只看文件本身，不做视频探测。"""
    target = Path(path)

    # 想判"完成"的那一段，却只剩一个 .part ⇒ 上次崩在写入途中
    if temp_path_for(target).exists():
        return ArtifactState.PARTIAL
    if not target.is_file():
        return ArtifactState.MISSING
    try:
        if target.stat().st_size < min_bytes:
            return ArtifactState.PARTIAL
    except OSError:
        return ArtifactState.MISSING
    return ArtifactState.UNVERIFIED


def verify_artifact(
    path: str | Path,
    expected_frames: int,
    prober: VideoProber,
    *,
    min_bytes: int = MIN_SEGMENT_BYTES,
) -> tuple[ArtifactState, VideoInfo | None]:
    """完整判定：文件存在 + 体积像样 + 帧数对得上。

    :param expected_frames: 该段应有的帧数（``Segment.count``）
    :param prober: 视频探测函数，由适配层提供
    :return: ``(状态, 探测结果)``；探测失败时结果为 ``None``

    这是"段级续渲"的唯一判据（K-2.8：**不做 manifest 断点簿记**）。
    """
    state = inspect_artifact(path, min_bytes=min_bytes)
    if state in (ArtifactState.MISSING, ArtifactState.PARTIAL):
        return state, None

    try:
        info = prober(Path(path))
    except Exception:
        # 文件在但读不出帧数 ⇒ 按残片处理，让该段重跑，不赌运气
        return ArtifactState.PARTIAL, None

    if info.frame_count != expected_frames:
        return ArtifactState.PARTIAL, info

    return ArtifactState.VERIFIED, info


def make_prober_from_table(table: dict[str, VideoInfo]) -> Callable[[Path], VideoInfo]:
    """造一个假探测器，仅供测试与干跑使用。"""
    def _probe(path: Path) -> VideoInfo:
        key = Path(path).name
        if key not in table:
            raise KeyError(f"没有为 {key} 准备探测结果")
        return table[key]

    return _probe
