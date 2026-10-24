"""按需下载 FFmpeg（不自带、不分发，只在用户点“下载”时抓取官方构建）。

为什么要下载而不是随包带：FFmpeg 是 LGPL/GPL，随包分发要履行再分发义务；
“替用户下载”则不涉及再分发，义务留在上游。程序会自动尝试多个来源
（含国内可用的 GitHub 镜像），把 ffmpeg.exe / ffprobe.exe 放到
``%LOCALAPPDATA%\\KomaFlow\\ffmpeg`` 下，之后自动被 ``find_ffmpeg`` 找到。
"""

from __future__ import annotations

import os
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

#: 候选下载源（按顺序尝试）。GitHub 资产走国内镜像前缀，直连放最后。
_MIRROR_PREFIXES = [
    "https://ghfast.top/",
    "https://ghproxy.net/",
    "https://gh-proxy.com/",
    "",
]

_GH_ASSET = ("https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
             "ffmpeg-master-latest-win64-gpl.zip")

#: 备用：gyan.dev 的 essentials 构建（直连，无需镜像）
_EXTRA_SOURCES = [
    "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
]


def install_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return Path(base) / "KomaFlow" / "ffmpeg"


def sources() -> list[str]:
    urls = [prefix + _GH_ASSET for prefix in _MIRROR_PREFIXES]
    return urls + _EXTRA_SOURCES


def _download(url: str, target: Path,
              on_progress: Callable[[str, int, int], None] | None = None) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "KomaFlow"})
    with urllib.request.urlopen(request, timeout=60) as response:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        with target.open("wb") as handle:
            while True:
                chunk = response.read(262144)
                if not chunk:
                    break
                handle.write(chunk)
                done += len(chunk)
                if on_progress:
                    on_progress(url, done, total)
    if target.stat().st_size < 1_000_000:
        raise RuntimeError("下载内容过小，可能被拦截")


def _extract(zip_path: Path, dest: Path) -> list[Path]:
    """从压缩包里挑出 ffmpeg.exe / ffprobe.exe 放平到 dest。"""
    dest.mkdir(parents=True, exist_ok=True)
    wanted = {"ffmpeg.exe", "ffprobe.exe"}
    found: list[Path] = []
    with zipfile.ZipFile(zip_path) as zf:
        bad = zf.testzip()
        if bad is not None:
            raise RuntimeError(f"压缩包损坏：{bad}")
        for item in zf.infolist():
            name = Path(item.filename).name.lower()
            if name in wanted:
                target = dest / Path(item.filename).name
                with zf.open(item) as src, target.open("wb") as out:
                    shutil.copyfileobj(src, out)
                found.append(target)
    if len(found) < 2:
        raise RuntimeError("压缩包里没找到 ffmpeg/ffprobe")
    return found


def fetch(on_progress: Callable[[str, int, int], None] | None = None,
          on_note: Callable[[str], None] | None = None) -> Path:
    """下载并解压 FFmpeg，返回安装目录。全部源都失败时抛 :class:`RuntimeError`。"""
    dest = install_dir()
    dest.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    for url in sources():
        try:
            if on_note:
                on_note(f"正在从 {url.split('/')[2]} 下载 FFmpeg …")
            with tempfile.TemporaryDirectory() as tmp:
                zip_path = Path(tmp) / "ffmpeg.zip"
                _download(url, zip_path, on_progress)
                _extract(zip_path, dest)
            if (dest / "ffmpeg.exe").is_file() and (dest / "ffprobe.exe").is_file():
                if on_note:
                    on_note(f"FFmpeg 已就绪：{dest}")
                return dest
            errors.append(f"{url}：解压后缺少可执行文件")
        except Exception as exc:                    # noqa: BLE001
            errors.append(f"{url.split('/')[2]}：{exc}")
            continue
    raise RuntimeError("所有下载源都失败了：\n" + "\n".join(errors))


if __name__ == "__main__":
    def _p(url: str, done: int, total: int) -> None:
        pct = (done / total * 100) if total else 0
        print(f"\r{done/1048576:6.1f} MB / {total/1048576:6.1f} MB  {pct:5.1f}%", end="")

    print(fetch(on_progress=_p, on_note=print))
