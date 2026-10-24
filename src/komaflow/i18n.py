"""可选的英文语言包（运行时翻译层）。

设计目标
--------
**不改动现有界面代码。** 全部通过运行时拦截实现：

1. 拦截 ``tkinter.Misc._options`` —— 所有控件的 `text=` / `title=` / `values=`
   在真正交给 Tk 之前替换成英文（控件创建与 ``configure`` 都走这里）。
2. 拦截 ``OptionMenu`` 的选中回调 —— 屏幕上显示英文，内部变量仍是中文，
   逻辑判断（比如 ``transparent.get() == "关"``）不受影响。
3. 拦截 ``messagebox`` 的标题与正文。
4. 动态拼接的句子（含数字、文件名）走**模板**：把 `{...}` 之外的中文片段
   按最长匹配替换，匹配不到就保留中文。

语言包位置（任选其一，先找到先用）：
    <程序目录>/locales/en.json
    %APPDATA%/KomaFlow/locales/en.json
    <程序目录>/locales_en.json

文件格式：``{"界面文字": "English"}`` 的扁平字典。
"""

from __future__ import annotations

import json
import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox
from typing import Any

#: 中文 → 英文
_CATALOG: dict[str, str] = {}
_KEYS_BY_LEN: list[str] = []
_INSTALLED = False


def _candidate_paths() -> list[Path]:
    paths: list[Path] = []
    exe_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else \
        Path(__file__).resolve().parent.parent.parent
    paths.append(exe_dir / "locales" / "en.json")
    paths.append(exe_dir / "locales_en.json")
    appdata = os.environ.get("APPDATA")
    if appdata:
        paths.append(Path(appdata) / "KomaFlow" / "locales" / "en.json")
    return paths


def load() -> bool:
    """找并加载语言包；没有就什么都不做（界面保持中文）。"""
    global _CATALOG, _KEYS_BY_LEN
    for path in _candidate_paths():
        try:
            if not path.is_file():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                continue
            _CATALOG = {str(k): str(v) for k, v in data.items() if k}
            _KEYS_BY_LEN = sorted(_CATALOG, key=len, reverse=True)
            return True
        except (OSError, ValueError):
            continue
    return False


#: 这些词**只做整句匹配**，不参与句子内的碎片替换 ——
#: 否则「拖入角色模型」会变成「拖入Character模型」这种半中半英。
_NO_FRAGMENT = {
    "角色", "动作", "镜头", "舞台", "表情", "工程", "模型", "材质",
    "开", "关", "是", "否", "界面", "就绪",
}


def translate(text: str) -> str:
    """精确匹配 → 失败则做**片段替换**（用于 f-string 拼出来的句子）。"""
    if not text or not _CATALOG:
        return text
    exact = _CATALOG.get(text)
    if exact is not None:
        return exact
    out = text
    for zh in _KEYS_BY_LEN:
        if zh in _NO_FRAGMENT or len(zh) < 2:
            continue
        if zh in out:
            out = out.replace(zh, _CATALOG[zh])
    return out


def _translate_values(values: Any) -> Any:
    if values is None:
        return None
    if isinstance(values, str):
        # Tk 允许把列表写成 "{a b c}"
        inner = values.strip()
        if inner.startswith("{") and inner.endswith("}"):
            return "{" + translate(inner[1:-1]) + "}"
        return translate(values)
    if isinstance(values, (list, tuple)):
        return type(values)(translate(str(v)) for v in values)
    return values


def install() -> bool:
    """打补丁。返回是否真的装了语言包。"""
    global _INSTALLED
    if _INSTALLED:
        return bool(_CATALOG)
    if not load():
        _INSTALLED = True
        return False

    # ── ① 控件文字 ──
    original_options = tk.Misc._options

    def patched_options(self, cnf=None, kw=None):
        cnf = dict(cnf or {})
        kw = dict(kw or {})
        for mapping in (cnf, kw):
            for key in ("text", "title", "message"):
                if isinstance(mapping.get(key), str):
                    mapping[key] = translate(mapping[key])
            if "values" in mapping:
                mapping["values"] = _translate_values(mapping["values"])
        return original_options(self, cnf, kw)

    tk.Misc._options = patched_options

    # ── ② 下拉框：显示英文，变量仍存中文 ──
    original_optionmenu_init = tk.OptionMenu.__init__

    def patched_optionmenu_init(self, master, variable, value, *values, **kwargs):
        # 反查：英文显示值 → 中文原值
        reverse = {translate(zh): zh for zh in _CATALOG}
        raw_values = (value,) + values
        display = [translate(str(v)) for v in raw_values]
        original_optionmenu_init(self, master, variable, display[0], *display[1:], **kwargs)

        def _set(selected_en: str) -> None:
            variable.set(reverse.get(selected_en, selected_en))

        # 把菜单项的 command 换成"翻回中文再写变量"
        menu = self["menu"]
        end = menu.index("end")
        if end is not None:
            for index in range(int(end) + 1):
                label = menu.entrycget(index, "label")
                menu.entryconfigure(index, command=lambda v=label: _set(v))

    tk.OptionMenu.__init__ = patched_optionmenu_init

    # ── ③ 弹窗 ──
    for name in ("showinfo", "showwarning", "showerror", "askyesno", "askokcancel"):
        original = getattr(messagebox, name, None)
        if original is None:
            continue

        def make_wrapper(fn):
            def wrapper(title=None, message=None, **kw):
                return fn(translate(title or ""), translate(message or ""), **kw)
            return wrapper

        setattr(messagebox, name, make_wrapper(original))

    _INSTALLED = True
    return True


def active() -> bool:
    return bool(_CATALOG)
