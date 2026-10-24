"""错误分类体系与人话文案。

对应需求：FR-8.5（错误按类归口）· K-6.3（报错必须说人话）· K-6.4（绝不自动改用户设置）。

设计要点
--------
* **给用户看人话，给排查看完整日志**。本模块只产出前者，技术细节走 ``detail``。
* 每条错误都带**修复建议**，但只是建议 —— 本工具**绝不自动修改用户设置**（K-6.4）。
* ``blocking`` 区分"启动前就该拦住"与"运行中才可能发生"。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class ErrorKind(str, Enum):
    """错误归口。字符串值便于写日志与做测试断言。"""

    # —— 环境类：启动前就能查出来 ——
    BLENDER_MISSING = "blender_missing"
    BLENDER_VERSION_UNSUPPORTED = "blender_version_unsupported"
    MMD_TOOLS_MISSING = "mmd_tools_missing"

    # —— 输入类 ——
    BLEND_VERSION_TOO_NEW = "blend_version_too_new"
    ASSET_CORRUPT = "asset_corrupt"
    TEXTURE_MISSING = "texture_missing"

    # —— 资源类：运行中才暴露 ——
    OUT_OF_VRAM = "out_of_vram"
    OUT_OF_MEMORY = "out_of_memory"
    OUT_OF_DISK = "out_of_disk"

    # —— 渲染类 ——
    PHYSICS_FAILED = "physics_failed"
    FRAME_FAILED = "frame_failed"
    RENDER_PROCESS_DIED = "render_process_died"

    # —— 用户操作 ——
    USER_CANCELLED = "user_cancelled"


@dataclass(frozen=True)
class ErrorSpec:
    """一类错误的用户可读描述。"""

    kind: ErrorKind
    title: str
    suggestion: str
    blocking: bool


#: 全部错误的人话文案。新增错误类时必须在此登记，否则 :class:`KomaFlowError` 会 KeyError。
CATALOG: dict[ErrorKind, ErrorSpec] = {
    ErrorKind.BLENDER_MISSING: ErrorSpec(
        ErrorKind.BLENDER_MISSING,
        "没有找到可用的 Blender。",
        "本工具不自带 Blender，请先自行安装 Blender 5.x，然后在设置里指定 blender.exe 的路径。",
        blocking=True,
    ),
    ErrorKind.BLENDER_VERSION_UNSUPPORTED: ErrorSpec(
        ErrorKind.BLENDER_VERSION_UNSUPPORTED,
        "你选择的 Blender 版本不在支持范围内。",
        "当前只支持 Blender 5.x。请改用 5.x 版本，或安装后重新探测。",
        blocking=True,
    ),
    ErrorKind.MMD_TOOLS_MISSING: ErrorSpec(
        ErrorKind.MMD_TOOLS_MISSING,
        "这个 Blender 里没有装 mmd_tools 扩展。",
        "mmd_tools 是导入 PMX/VMD 的必需依赖。可用本工具随包附带的副本一键离线安装。",
        blocking=True,
    ),
    ErrorKind.BLEND_VERSION_TOO_NEW: ErrorSpec(
        ErrorKind.BLEND_VERSION_TOO_NEW,
        "这个 .blend 工程是用更新版本的 Blender 保存的，当前版本打不开。",
        "请换用不低于该工程写入版本的 Blender，或让工程作者另存为较低版本。",
        blocking=True,
    ),
    ErrorKind.ASSET_CORRUPT: ErrorSpec(
        ErrorKind.ASSET_CORRUPT,
        "某个素材文件读不出来或已损坏。",
        "请确认该文件完整（重新解压 / 重新下载），并检查路径里是否含特殊字符。",
        blocking=True,
    ),
    ErrorKind.TEXTURE_MISSING: ErrorSpec(
        ErrorKind.TEXTURE_MISSING,
        "模型引用的贴图找不到，相关材质会渲染成白模或黑块。",
        "PMX 里存的是作者机器的绝对路径。请把贴图与模型放在同一目录，或用「重新定位贴图」指认目录。",
        blocking=False,
    ),
    ErrorKind.OUT_OF_VRAM: ErrorSpec(
        ErrorKind.OUT_OF_VRAM,
        "显存不足，渲染无法继续。",
        "可以降低分辨率（如 4K→2K）、减小单段上限，或关掉一些特效后重试。本工具不会替你改设置。",
        blocking=False,
    ),
    ErrorKind.OUT_OF_MEMORY: ErrorSpec(
        ErrorKind.OUT_OF_MEMORY,
        "内存不足，渲染无法继续。",
        "请关闭其他占内存的程序，或减小单段上限以更早释放内存，然后重试。",
        blocking=False,
    ),
    ErrorKind.OUT_OF_DISK: ErrorSpec(
        ErrorKind.OUT_OF_DISK,
        "磁盘剩余空间不足。",
        "长片渲染很占空间（尤其出 PNG 序列时）。请清理输出目录所在磁盘，或改到空间更大的盘。",
        blocking=True,
    ),
    ErrorKind.PHYSICS_FAILED: ErrorSpec(
        ErrorKind.PHYSICS_FAILED,
        "物理运算出错了（头发 / 裙摆 / 饰品等）。",
        "可尝试增大物理预热帧数让物理先收敛后重试。",
        blocking=False,
    ),
    ErrorKind.FRAME_FAILED: ErrorSpec(
        ErrorKind.FRAME_FAILED,
        "有少数帧渲染失败。",
        "失败帧号已记入日志，可单独重试这些帧；成片必须补齐全部失败帧才算完成。",
        blocking=False,
    ),
    ErrorKind.RENDER_PROCESS_DIED: ErrorSpec(
        ErrorKind.RENDER_PROCESS_DIED,
        "渲染进程意外结束了。",
        "已自动重试 1 次；若仍失败，请把日志导出后反馈。已完成的段不会白渲。",
        blocking=False,
    ),
    ErrorKind.USER_CANCELLED: ErrorSpec(
        ErrorKind.USER_CANCELLED,
        "任务已被中断。",
        "已完成的段会保留。重新开始时会自动跳过这些段，从断掉的那一段继续。",
        blocking=False,
    ),
}


#: ``build.py`` 给底层异常套的包装：``角色模型 文件「Miku.pmx」读不出来：<原始错误>``
#: 解析它才能把**文件名**留下、把**原始错误**拿去翻译。
#: ⚠️ 前面那截允许有空格和 ``RuntimeError: `` 这类前缀，所以用非贪婪的 ``.*?``；
#: 写成 ``[^：:]{0,8}?`` 会因为有空格而匹配不上（踩过）。
_WRAPPED = re.compile(r"^.*?文件「(?P<name>[^」]+)」读不出来[：:](?P<inner>.*)$", re.S)


def friendly_reason(raw: str) -> str:
    """把底层库报的英文原因翻成**用户能看懂**的一句。

    不认识的错误就原样返回（压成一行）—— 与其编一句可能误导人的中文，
    不如把原文给他，至少搜索时有用。

    ⚠️ 这里只做"认得出来的常见错"，不追求覆盖全部。
    每一条都对应真遇到过的情况，别凭想象往里加。
    """
    text = collapse(raw, limit=200)
    if not text:
        return ""

    # 先剥掉 build.py 那层包装，把文件名和真正的错误分开
    name = ""
    match = _WRAPPED.match(text)
    if match:
        name = match.group("name")
        text = match.group("inner").strip()

    low = text.lower()
    reason = ""
    # PMX / PMD 签名不对 —— 最常见的是把别的格式改名成 .pmx，或者文件没下全
    if "signature" in low and "invalid" in low:
        reason = "这个文件不是有效的 PMX 模型 —— 可能拖错文件了，或者文件本身损坏"
    elif "no such file" in low or "filenotfounderror" in low:
        reason = "找不到文件，可能已被移动或删除"
    elif "permission denied" in low or "permissionerror" in low:
        reason = "没有权限读这个文件，检查是不是被占用或只读"
    elif "not a blend" in low:
        reason = "这个文件不是 Blender 工程（.blend）"
    else:
        reason = text

    if name:
        # 文件名是关键线索（用户模型里可能有好几个 PMX），一定留住
        return f"「{name}」{reason}"
    return reason


def last_meaningful_line(text: str, limit: int = 160) -> str:
    """从一段可能带 traceback 的文字里，挑出**真正有用的那一行**。

    为什么需要
    ----------
    有些库抛的异常**消息里自带完整 traceback** —— 实测 mmd_tools 的
    ``InvalidFileError`` 就是这样，``str(exc)`` 是一整段多行堆栈。
    而 `build.py` 那层拼成 ``f"{type(exc).__name__}: {exc}"``、
    `pipeline` 再前缀一个"装配失败："，最后 ``human()`` 整个塞进弹窗 ——
    用户看到的是一屏英文堆栈（用户直接截图来问）。

    这里做的是：**取最后一行像错误信息的内容**（traceback 的末行通常就是真正的原因），
    并限长。碰到 `^^^^` / `~~~` / `...<15 lines>...` 这种堆栈装饰行就往上找。
    """
    if not text:
        return ""
    lines = [row.strip() for row in str(text).splitlines() if row.strip()]
    if not lines:
        return ""

    def is_noise(row: str) -> bool:
        return (set(row) <= set("^~ ") or row.startswith("...<")
                or row in ("Traceback (most recent call last):",))

    tail = lines[-1]
    if is_noise(tail):
        for row in reversed(lines[:-1]):
            if not is_noise(row):
                tail = row
                break
    return tail[:limit] + ("…" if len(tail) > limit else "")


def collapse(text: str, limit: int = 160) -> str:
    """把多行文字压成一行，给弹窗用。

    短内容原样保留（只去掉换行），长内容才截末行 ——
    这样"路径不存在"这类短 detail 不会被吃掉。
    """
    if not text:
        return ""
    flat = " ".join(str(text).split())
    if len(flat) <= limit:
        return flat
    return last_meaningful_line(text, limit)


class KomaFlowError(Exception):
    """带归类与人话文案的异常。

    抛给上层时用它自带的人话；技术细节放 ``detail``，只进日志。
    """

    def __init__(self, kind: ErrorKind, detail: str = "") -> None:
        self.kind = kind
        self.detail = detail
        super().__init__(self.human())

    @property
    def spec(self) -> ErrorSpec:
        return CATALOG[self.kind]

    @property
    def blocking(self) -> bool:
        """True = 启动前就应阻断，不该放行。"""
        return self.spec.blocking

    def human(self) -> str:
        """面向用户的一句话（含建议）。

        ⚠️ **不要把 ``detail`` 原样拼进来**。它经常是整段 traceback
        （见 :func:`last_meaningful_line`），拼上去弹窗就成一屏英文堆栈了。
        这里只在 detail **短到能当一句话读**时才附上；长了就丢掉，让它留在日志里
        （`log_line()` 保留完整内容）。
        """
        spec = self.spec
        message = spec.title
        # 认识的原因翻成中文；不认识的压成一行原文（短才附上，长了只进日志）
        short = friendly_reason(self.detail) if self.detail else ""
        if short and len(short) <= 90 and "Traceback" not in short:
            message += f"（{short}）"
        if spec.suggestion:
            message += f" 建议：{spec.suggestion}"
        return message

    def log_line(self) -> str:
        """面向日志的一行（含错误代号，便于 grep 与工单对照）。

        这里保留**完整** detail —— 排查全靠它。
        """
        return f"[{self.kind.value}] {self.spec.title} detail={self.detail!r}"

#: 向后兼容别名。历史上叫 KomaFlowError，改名时保留，免得外部脚本炸掉。
KomaFlowError = KomaFlowError
