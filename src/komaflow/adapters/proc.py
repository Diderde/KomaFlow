"""渲染进程的暂停 / 恢复。

对应需求：K-5.4（支持暂停、继续、中断、终止）。

为什么需要它
------------
一段 1000 帧按 4 秒/帧要渲一个多小时。用户中途想看看片子对不对、或者要腾出
显卡干别的，就得能停下来、还能接着渲 —— 而不是只能中断重来。

实现
----
Windows 上用 ``ntdll.NtSuspendProcess`` / ``NtResumeProcess``（ctypes 调，
**不需要任何第三方包**）。其它平台退回 ``SIGSTOP`` / ``SIGCONT``。

⚠️ 挂起之后进度文件自然不会再更新，所以执行器必须同时**暂停心跳检测**，
否则会被判成"无响应"而误杀（这是挂起方案最容易踩的坑）。
"""

from __future__ import annotations

import os
import threading

#: Windows 的进程访问权限位
PROCESS_SUSPEND_RESUME = 0x0800

_NTDDLL = None
_KERNEL32 = None

if os.name == "nt":
    try:
        import ctypes

        _NTDDLL = ctypes.WinDLL("ntdll")
        _NTDDLL.NtSuspendProcess.argtypes = [ctypes.c_void_p]
        _NTDDLL.NtSuspendProcess.restype = ctypes.c_long
        _NTDDLL.NtResumeProcess.argtypes = [ctypes.c_void_p]
        _NTDDLL.NtResumeProcess.restype = ctypes.c_long
        _KERNEL32 = ctypes.WinDLL("kernel32")
        _KERNEL32.OpenProcess.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_uint]
        _KERNEL32.OpenProcess.restype = ctypes.c_void_p
        _KERNEL32.CloseHandle.argtypes = [ctypes.c_void_p]
    except Exception: # noqa: BLE001 - 拿不到就退化成"不支持暂停"
        _NTDDLL = None
        _KERNEL32 = None


def _open_process(pid: int):
    if _KERNEL32 is None:
        return None
    handle = _KERNEL32.OpenProcess(PROCESS_SUSPEND_RESUME, False, pid)
    return handle or None


def suspend_process(pid: int) -> bool:
    """挂起进程。成功返回 True；系统不支持或权限不足返回 False。"""
    if os.name == "nt":
        if _NTDDLL is None or _KERNEL32 is None:
            return False
        handle = _open_process(pid)
        if not handle:
            return False
        try:
            return _NTDDLL.NtSuspendProcess(handle) == 0
        finally:
            _KERNEL32.CloseHandle(handle)
    try:
        os.kill(pid, 19) # SIGSTOP
        return True
    except Exception: # noqa: BLE001
        return False


def resume_process(pid: int) -> bool:
    """恢复进程。"""
    if os.name == "nt":
        if _NTDDLL is None or _KERNEL32 is None:
            return False
        handle = _open_process(pid)
        if not handle:
            return False
        try:
            return _NTDDLL.NtResumeProcess(handle) == 0
        finally:
            _KERNEL32.CloseHandle(handle)
    try:
        os.kill(pid, 18) # SIGCONT
        return True
    except Exception: # noqa: BLE001
        return False


def pause_supported() -> bool:
    return os.name == "nt" and _NTDDLL is not None and _KERNEL32 is not None


class ProcessControl:
    """把"用户想暂停"翻译成"实际挂起进程"。

    界面只碰 :attr:`paused`（一个 ``threading.Event``）；
    执行器在轮询循环里调 :meth:`apply` 落实挂起/恢复。
    """

    def __init__(self) -> None:
        self.paused = threading.Event()
        self._pid: int | None = None
        self._suspended = False
        self.supported = pause_supported()

    # ---------------------------------------------------------------- 生命周期
    def register(self, pid: int) -> None:
        self._pid = pid
        self._suspended = False

    def clear(self) -> None:
        # 万一还挂着就被清了，先恢复回来，别把死掉的进程留下
        if self._suspended and self._pid is not None:
            resume_process(self._pid)
        self._pid = None
        self._suspended = False

    # ------------------------------------------------------------------- 动作
    def apply(self) -> None:
        """按当前 ``paused`` 状态落实挂起 / 恢复。执行器每轮调一次。"""
        if self._pid is None or not self.supported:
            return
        want = self.paused.is_set()
        if want and not self._suspended:
            if suspend_process(self._pid):
                self._suspended = True
        elif not want and self._suspended:
            if resume_process(self._pid):
                self._suspended = False

    def toggle(self) -> bool:
        """切换暂停状态，返回切换后是否处于暂停。"""
        if self.paused.is_set():
            self.paused.clear()
        else:
            self.paused.set()
        return self.paused.is_set()
