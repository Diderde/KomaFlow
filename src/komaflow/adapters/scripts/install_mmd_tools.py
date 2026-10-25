"""在用户的 Blender 里**联网安装** mmd_tools 扩展。

用户定的路线
------------
> 不随（包）,但是告诉用户：该插件不...，因为...，所以需要联网

所以这里**不打包、不自带**，直接调 Blender 自己的扩展安装操作符：
它会把插件装到用户的扩展目录里，并顺手启用。

⚠️ 为什么用 ``bpy.ops.extensions.package_install`` 而不是自己下载 zip：
* Blender 已经内置了官方仓库配置（``extensions.blender.org``），
  不需要我们维护 URL、版本号、校验
* 官方仓库会跟随 Blender 版本给合适的版本
* 自己下载还得处理"仓库改版 / 断点 / 校验失败"一堆事

操作符实测参数（Blender 5.2.2，见 ``work/_ext_api.py``）::

    bpy.ops.extensions.package_install(
        repo_directory=..., # 仓库目录（从用户偏好里取）
        repo_index=..., # 第几个仓库（0 = 官方那个）
        pkg_id="mmd_tools", # 包 id
        enable_on_install=True,
        do_legacy_replace=False,
    )

失败时**必须把话说清楚** —— 常见的失败就是断网或没允许联网。
"""

from __future__ import annotations

import sys

SCRIPT = r'''
import bpy, json, traceback

report = {"ok": False, "message": "", "stage": "start"}

EXT_ID = "mmd_tools"
REPO_HOST = "extensions.blender.org"


def _repos():
    prefs = bpy.context.preferences
    ext = getattr(prefs, "extensions", None)
    if ext is None:
        return []
    return list(getattr(ext, "repos", []) or [])


try:
    # ① 先看是不是已经装好了（用户可能自己装过）
    import addon_utils
    try:
        from bl_ext.blender_org import mmd_tools # noqa: F401
        report.update(ok=True, stage="already",
                      message="mmd_tools 已经装好了，不用再装。")
        print("RESULT " + json.dumps(report, ensure_ascii=False))
        raise SystemExit(0)
    except ImportError:
        pass

    # ② 找到官方仓库的位置
    repos = _repos()
    if not repos:
        report.update(stage="no_repo",
                      message="这台 Blender 里没有配置插件仓库，装不了。"
                              "可以在 Blender 的「偏好设置 → 获取扩展」里加一个。")
        print("RESULT " + json.dumps(report, ensure_ascii=False))
        raise SystemExit(0)

    index = None
    for i, repo in enumerate(repos):
        url = str(getattr(repo, "remote_url", "") or "")
        if REPO_HOST in url:
            index = i
            break
    if index is None:
        index = 0
        report["note"] = "没找到官方仓库，改用第 0 个仓库试试"

    repo_dir = str(getattr(repos[index], "directory", "") or "")

    # ③ 联网安装（这一步需要网络）
    report["stage"] = "installing"
    result = bpy.ops.extensions.package_install(
        repo_directory=repo_dir,
        repo_index=int(index),
        pkg_id=EXT_ID,
        enable_on_install=True,
        do_legacy_replace=False,
    )
    report["operator"] = str(result)

    # ④ 装完验一遍：能不能 import 进来
    import importlib
    importlib.invalidate_caches()
    try:
        import bl_ext.blender_org.mmd_tools # noqa: F401
        report.update(ok=True, stage="done",
                      message="装好了，也已经启用。回去点「重新检测」就能用。")
    except Exception as exc:
        report.update(stage="installed_but_unloadable",
                      message=f"装是装上了，但载入失败：{exc}。"
                              f"可以重启 Blender 再试。")
except SystemExit:
    pass
except Exception as exc:
    report.update(stage="error",
                  message=f"{type(exc).__name__}: {exc}")
    report["traceback"] = traceback.format_exc()[-1200:]

print("RESULT " + json.dumps(report, ensure_ascii=False))
'''


def main() -> int:
    """命令行自检入口：把脚本打进 Blender 跑一遍。

    正常运行时由适配层调用（见 ``adapters/blender5.py::install_mmd_tools``）；
    这里保留一个可单独执行的入口，方便排查。
    """
    import subprocess
    import tempfile
    from pathlib import Path

    if len(sys.argv) < 2:
        print("用法：python -m komaflow.adapters.scripts.install_mmd_tools <blender.exe>")
        return 2
    exe = sys.argv[1]
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                     encoding="utf-8") as handle:
        handle.write(SCRIPT)
        path = Path(handle.name)
    log = Path(tempfile.gettempdir()) / "install_mmd_tools.txt"
    with open(log, "w", encoding="utf-8") as sink:
        subprocess.run([exe, "--background", "--python-exit-code", "0",
                        "--python", str(path)],
                       stdout=sink, stderr=subprocess.STDOUT, timeout=600)
    text = log.read_text(encoding="utf-8", errors="replace")
    for row in text.splitlines():
        if row.startswith("RESULT "):
            print(row[len("RESULT "):])
            return 0
    print(text[-1500:])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
