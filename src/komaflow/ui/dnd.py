"""Windows 原生文件拖放（**纯 ctypes，零 pip 依赖**）。

需求背景：用户要求"文件可以直接拖进窗口"。tkinter 自己不带拖放，
社区方案 ``tkinterdnd2`` 需要 pip 安装 —— 这违反 NFR-16（绝不引入需要 pip
安装的依赖）。所以这里直接用 Windows 自己的 API：

1. ``shell32.DragAcceptFiles(hwnd, True)`` 声明这个窗口接受拖放
2. 用 ``SetWindowLongPtrW`` 换掉窗口过程，拦 ``WM_DROPFILES``
3. 从消息里取出文件路径与落点，再交回 Tk（**必须回主线程**，用 ``after(0)``）

风险与兜底
----------
换窗口过程属于底层操作。所以：

* 旧的窗口过程一定保存下来，其它消息原样 ``CallWindowProcW`` 转发回去
* 回调对象存在类变量里，防止被 Python GC 掉（GC 掉必崩）
* 任何一步失败都只是返回 ``False``，**不抛异常** —— 界面上的"浏览"按钮始终可用
"""

from __future__ import annotations

import os
import sys

IS_WINDOWS = os.name == "nt"

WM_DROPFILES = 0x0233
GWLP_WNDPROC = -4

#: 单个路径缓冲。Windows 路径上限 32767，给足。
_BUF_SIZE = 32768

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _LRESULT = ctypes.c_ssize_t
    _WNDPROC = ctypes.WINFUNCTYPE(
        _LRESULT, wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t
    )

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _shell32 = ctypes.WinDLL("shell32", use_last_error=True)

    # 64 位用 SetWindowLongPtrW，32 位只有 SetWindowLongW
    _set_wndproc = getattr(_user32, "SetWindowLongPtrW", None) or _user32.SetWindowLongW
    _set_wndproc.argtypes = [wintypes.HWND, ctypes.c_int, _WNDPROC]
    _set_wndproc.restype = ctypes.c_void_p

    _user32.CallWindowProcW.argtypes = [
        ctypes.c_void_p, wintypes.HWND, wintypes.UINT,
        ctypes.c_size_t, ctypes.c_ssize_t,
    ]
    _user32.CallWindowProcW.restype = _LRESULT
    _user32.GetParent.argtypes = [wintypes.HWND]
    _user32.GetParent.restype = wintypes.HWND

    _shell32.DragAcceptFiles.argtypes = [wintypes.HWND, wintypes.BOOL]
    _shell32.DragAcceptFiles.restype = None
    _shell32.DragQueryFileW.argtypes = [
        wintypes.HANDLE, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT
    ]
    _shell32.DragQueryFileW.restype = wintypes.UINT
    _shell32.DragQueryPoint.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.POINT)]
    _shell32.DragQueryPoint.restype = wintypes.BOOL
    _shell32.DragFinish.argtypes = [wintypes.HANDLE]
    _shell32.DragFinish.restype = None


def available() -> bool:
    """当前平台能不能用原生拖放。"""
    return IS_WINDOWS


class DropTarget:
    """把一个 HWND 变成可接收文件拖放的窗口。"""

    #: ⚠️ 必须持有引用：回调被 GC 掉之后系统再调用就是访问非法内存
    _alive: list["DropTarget"] = []
    #: ⚠️ 已经换过窗口过程的 HWND。
    #: **同一个窗口不能装两次** —— 第二次会把"我们的 WndProc"当成 old_proc
    #: 再套一层，链越套越长；更糟的是旧的那层可能已经被回收，
    #: 之后系统回调到它就是访问非法内存（表现是 0xC0000409 闪退）。
    _installed_hwnds: set[int] = set()

    def __init__(self, hwnd: int, callback, label: str = "") -> None:
        self.hwnd = hwnd
        self.label = label
        self.callback = callback
        self.old_proc = None
        self.installed = False
        self._proc_ref = None

    def install(self) -> bool:
        if not available() or not self.hwnd:
            return False
        if self.hwnd in DropTarget._installed_hwnds:
            # 已经装过：**直接算成功**，别再换一次窗口过程
            self.installed = True
            return True
        try:
            _shell32.DragAcceptFiles(self.hwnd, True)
            self._proc_ref = _WNDPROC(self._wndproc)
            self.old_proc = _set_wndproc(self.hwnd, GWLP_WNDPROC, self._proc_ref)
            if not self.old_proc:
                return False
            self.installed = True
            DropTarget._installed_hwnds.add(self.hwnd)
            DropTarget._alive.append(self)
            return True
        except Exception: # noqa: BLE001 - 拖放装不上不该影响程序能用
            self.installed = False
            return False

    # ------------------------------------------------------------------ 内部
    def _wndproc(self, hwnd, msg, wparam, lparam):
        """窗口过程。

        ⚠️ **这里面的任何东西崩了都是整个进程崩**，没有 Python traceback 可看
        （异常码会是 ``0xC0000409``）。所以：

        * 整个函数体套在 ``try`` 里，**绝不让异常逃出去**
        * 只做纯 Windows API + 纯 Python 操作，**绝不碰 Tcl/Tk**
          （在窗口过程里调 Tcl 会重入消息处理，把 wndproc 链搞坏）
        * 无论成败都要 ``CallWindowProcW`` 转发回去，除非是我们处理掉的消息
        """
        if msg == WM_DROPFILES:
            try:
                paths, point = self._read_drop(wparam)
                if paths:
                    self.callback(paths, point)
            except Exception: # noqa: BLE001
                # 拖放出问题也不能把进程带走：吞掉，交回默认处理
                try:
                    return _user32.CallWindowProcW(
                        self.old_proc, hwnd, msg, wparam, lparam)
                except Exception: # noqa: BLE001
                    return 0
            return 0 # 已处理
        return _user32.CallWindowProcW(self.old_proc, hwnd, msg, wparam, lparam)

    def _read_drop(self, hdrop) -> tuple[list[str], tuple[int, int]]:
        count = _shell32.DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0)
        buffer = ctypes.create_unicode_buffer(_BUF_SIZE)
        paths: list[str] = []
        for index in range(count):
            if _shell32.DragQueryFileW(hdrop, index, buffer, _BUF_SIZE):
                paths.append(buffer.value)
        point = wintypes.POINT()
        _shell32.DragQueryPoint(hdrop, ctypes.byref(point))
        _shell32.DragFinish(hdrop)
        return paths, (int(point.x), int(point.y))


def install(root, callback, *, extra_windows: int = 1) -> list[DropTarget]:
    """给 Tk 根窗口装拖放。

    Tk 的顶层窗口在 Windows 上是一层套一层：``winfo_id()`` 拿到的是里面那个，
    外面还有一层 wrapper。两层都装，覆盖面积最大。

    :param callback: ``callback(paths: list[str], point: tuple[int, int])``，
        其中 point 是**被拖放窗口的客户区坐标**；调用方通常要 ``root.after(0, ...)``。
    """
    targets: list[DropTarget] = []
    if not available():
        return targets

    try:
        hwnd = int(root.winfo_id())
    except Exception: # noqa: BLE001
        return targets

    targets.append(DropTarget(hwnd, callback, label="tk"))
    if extra_windows:
        try:
            parent = _user32.GetParent(hwnd)
            if parent:
                targets.append(DropTarget(int(parent), callback, label="wrapper"))
        except Exception: # noqa: BLE001
            pass
    return [target for target in targets if target.install()]


if __name__ == "__main__": # pragma: no cover - 人工自检用
    print("拖放可用:", available(), "| Python:", sys.version.split()[0])
