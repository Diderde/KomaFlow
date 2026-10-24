"""Blender 侧探针：报告版本、mmd_tools 可用性与导入算子。

用法::

    blender.exe --background --factory-startup --python probe.py -- <输出JSON>

设计约束（对应需求 K-10.2 / K-10.3 / K-10.10）：

* 本脚本**只读**，不修改 Blender 的任何配置与偏好
* 结果写成 JSON 文件交回工具，**不依赖解析屏幕输出**
* 用 ``--factory-startup`` 运行时，要实测扩展系统能否正常启用 mmd_tools
  （K-10.10 明确要求实测这一点）
* ``print(..., flush=True)`` —— 崩溃时缓冲区输出会全丢
"""

from __future__ import annotations

import json
import sys
import traceback


def _argv_after_ddash() -> list[str]:
    argv = sys.argv
    if "--" in argv:
        return argv[argv.index("--") + 1:]
    return []


def _safe(fn, *args, **kwargs):
    """跑一段可能失败的探测，把异常变成可读文本而不是让整个探针崩掉。"""
    try:
        return fn(*args, **kwargs)
    except Exception as exc: # noqa: BLE001 - 探针要尽量多收集信息
        return {"__error__": f"{type(exc).__name__}: {exc}", "__tb__": traceback.format_exc()[-800:]}


def collect() -> dict:
    import bpy

    report: dict = {
        "blender_version": bpy.app.version_string,
        "blender_version_tuple": list(bpy.app.version),
        "factory_startup": "--factory-startup" in sys.argv,
        "background": bpy.app.background,
        "binary": bpy.app.binary_path,
    }

    # ── 扩展仓库 ──
    def repos():
        prefs = bpy.context.preferences
        return {r.name: {"enabled": r.use_remote_url, "url": getattr(r, "remote_url", None)}
                for r in prefs.extensions.repos}

    report["extension_repos"] = _safe(repos)

    # ── addon_utils 能看到的 mmd 模块 ──
    import addon_utils

    def mmd_modules():
        found = []
        for module in addon_utils.modules():
            name = getattr(module, "__name__", "")
            if "mmd" in name.lower():
                found.append(name)
        return found

    report["mmd_modules"] = _safe(mmd_modules)

    # ── 尝试启用（多种可能的模块名都试）──
    candidates = (
        "bl_ext.blender_org.mmd_tools", # 5.x 扩展系统的模块名
        "mmd_tools",
    )
    attempts: dict = {}
    for candidate in candidates:
        def try_enable(name=candidate):
            result = addon_utils.enable(name, default_set=True, persistent=False)
            return str(result)

        attempts[candidate] = _safe(try_enable)
    report["enable_attempts"] = attempts

    # ── 启用后是否真的可用 ──
    report["mmd_in_sys_modules"] = [k for k in sys.modules if "mmd" in k.lower()]
    report["has_mmd_ops"] = hasattr(bpy.ops, "mmd_tools")
    if report["has_mmd_ops"]:
        report["mmd_ops"] = sorted(
            name for name in dir(bpy.ops.mmd_tools) if not name.startswith("_")
        )

    # ── 已启用的插件里有没有 mmd_tools ──
    def enabled_addons():
        return [module.__name__ for module in addon_utils.modules()
                if addon_utils.check(module.__name__)[1]]

    report["enabled_addons"] = _safe(enabled_addons)

    # ── mmd_tools 版本（从 manifest 读，不改任何配置）──
    def mmd_tools_version():
        import os
        from pathlib import Path
        root = Path(os.environ.get("APPDATA", "")) / "Blender Foundation" / "Blender" / \
            ".".join(str(x) for x in bpy.app.version[:2]) / "extensions" / "blender_org" / "mmd_tools"
        manifest = root / "blender_manifest.toml"
        if not manifest.is_file():
            return None
        for line in manifest.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("version"):
                return line.split("=", 1)[1].strip().strip('"')
        return None

    report["mmd_tools_version"] = _safe(mmd_tools_version)

    return report


def main() -> None:
    out = None
    rest = _argv_after_ddash()
    if rest:
        out = rest[0]

    report = _safe(collect)
    payload = json.dumps(report, ensure_ascii=False, indent=2)

    if out:
        with open(out, "w", encoding="utf-8") as handle:
            handle.write(payload + "\n")
        print(f"PROBE_WROTE {out}", flush=True)
    else:
        print(payload, flush=True)


main()
