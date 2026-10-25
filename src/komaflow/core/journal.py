"""后台日志。

需求口径（用户明确）：**日志不给用户看**。界面上只留两样东西 ——

* **步骤状态**（哪一步在跑、哪一步完了）
* **一句人话报错**（说什么坏了、建议怎么办）

完整的技术记录一律落盘，需要排查时再去看文件。这样界面干净，
而排障信息一条不少。

落盘位置：``<work_dir>/logs/KomaFlow.log``，与各段 Blender 的原始日志同目录。
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

DEFAULT_FILENAME = "KomaFlow.log"

#: 日志级别，只用于打标记，不做过滤（全都要留）
LEVELS = ("debug", "info", "warn", "error")


class Journal:
    """线程安全的文件日志器。

    设计原则：**日志失败绝不能影响主流程**。任何 IO 异常都被吞掉 ——
    没写成日志是小事，因为日志报错把渲染搞崩是大事。
    """

    _lock = threading.Lock()

    def __init__(self, directory: str | Path | None = None,
                 filename: str = DEFAULT_FILENAME) -> None:
        self._filename = filename
        self._directory: Path | None = None
        self._path: Path | None = None
        if directory is not None:
            self.bind(directory)

    # ------------------------------------------------------------------ 绑定
    def bind(self, directory: str | Path) -> Path | None:
        """把日志切到新目录（通常就是工作目录）。返回最终的文件路径。"""
        try:
            target = Path(directory)
            if target.name != "logs":
                target = target / "logs"
            target.mkdir(parents=True, exist_ok=True)
            self._directory = target
            self._path = target / self._filename
            self.write("=" * 60)
            self.write(f"日志开始：{time.strftime('%Y-%m-%d %H:%M:%S')}")
            return self._path
        except OSError:
            self._directory = None
            self._path = None
            return None

    @property
    def path(self) -> Path | None:
        return self._path

    @property
    def directory(self) -> Path | None:
        return self._directory

    #: 单个日志文件的上限；超了就切成 .1 / .2 / .3（最多留 3 份）
    MAX_BYTES = 5 * 1024 * 1024
    KEEP = 3

    def _rotate_if_needed(self) -> None:
        """日志轮转。

        C4：原来只有 ``open(path, "a")`` 一路追加，跑久了能到几百 MB 甚至 GB，
        排查时打不开、也拖慢程序。这里超过 5 MB 就把当前文件挪成 ``.1``，
        依次把旧的往后推，最老的丢掉。
        """
        try:
            if self._path is None or not self._path.is_file():
                return
            if self._path.stat().st_size < self.MAX_BYTES:
                return
            for index in range(self.KEEP - 1, 0, -1):
                older = self._path.with_suffix(self._path.suffix + f".{index}")
                newer = self._path.with_suffix(self._path.suffix + f".{index + 1}")
                if newer.exists():
                    newer.unlink(missing_ok=True)
                if older.exists():
                    older.replace(newer)
            self._path.replace(
                self._path.with_suffix(self._path.suffix + ".1"))
        except OSError:
            # 轮转失败不该影响正常写日志
            pass

    # ------------------------------------------------------------------ 写入
    def write(self, message: str, level: str = "info") -> None:
        if self._path is None:
            return
        stamp = time.strftime("%H:%M:%S")
        tag = {"debug": "DBG", "info": "INF", "warn": "WRN", "error": "ERR"}.get(level, "INF")
        line = f"[{stamp}] {tag} {message}\n"
        with self._lock:
            self._rotate_if_needed()
            try:
                with open(self._path, "a", encoding="utf-8", errors="replace") as handle:
                    handle.write(line)
            except OSError:
                pass # 见类文档：日志失败不影响主流程

    def debug(self, message: str) -> None:
        self.write(message, "debug")

    def warn(self, message: str) -> None:
        self.write(message, "warn")

    def error(self, message: str) -> None:
        self.write(message, "error")

    # ------------------------------------------------------------------ 读取
    def tail(self, lines: int = 60) -> str:
        """取末尾若干行。仅供排障与"复制日志"用，不往界面上摆。"""
        if self._path is None or not self._path.is_file():
            return ""
        try:
            content = self._path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        return "\n".join(content.splitlines()[-lines:])


#: 全局默认实例。界面和管线都用它，省得到处传。
JOURNAL = Journal()
