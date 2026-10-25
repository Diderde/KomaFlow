"""文件名净化：成片名只许是一段文件名，不许带路径。

用户报过 / 审计发现：成片名直接拼进输出路径，
写上 ``..\\..\\foo`` 就能把文件写到自己没选的目录里去。
Windows 上还有一批非法字符与保留名（CON / PRN / NUL …），
一并处理掉，越界与"写不出来"两种情况一起解决。
"""

from __future__ import annotations

import re

#: Windows 文件名里非法的字符
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
#: Windows 保留设备名（不区分大小写，带扩展名也不行）
_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *{f"COM{i}" for i in range(1, 10)},
    *{f"LPT{i}" for i in range(1, 10)},
}
#: 目录名最长 255 字节左右，留一点余量给后缀（_frames / _0000.png / .mp4）
_MAX_LEN = 120


def safe_basename(name: str | None, fallback: str = "KomaFlow") -> str:
    """把用户填的成片名净化成**一段安全的文件名**。

    * 去掉路径分隔符与 ``..`` → 不可能写出输出目录
    * 去掉 Windows 非法字符
    * 去掉首尾空格与结尾的点（Windows 会把 "名字." 当 "名字"）
    * 空 / 全是点 → 用 ``fallback``
    * 保留字（CON、NUL…）加个下划线
    """
    raw = str(name or "").strip()
    # 只取最后一段：\a\b\c → c；..\x → x；直接传 "../../x" 也一样
    raw = raw.replace("\\", "/").split("/")[-1]
    raw = _ILLEGAL.sub("_", raw)
    raw = raw.strip(" .")
    raw = re.sub(r"_+", "_", raw)
    if not raw:
        raw = fallback
    if raw.split(".")[0].upper() in _RESERVED:
        raw = "_" + raw
    if len(raw) > _MAX_LEN:
        raw = raw[:_MAX_LEN].rstrip(" .") or fallback
    return raw
