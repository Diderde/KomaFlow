# -*- coding: utf-8 mode: python -*-
"""KomaFlow 的 PyInstaller 打包配置。

怎么用
------
    pyinstaller --noconfirm --clean tools/KomaFlow.spec

**为什么是 onedir（一个文件夹）而不是 onefile（单文件 exe）**：

* onefile 每次启动都要把几十 MB 解包到临时目录 —— 启动更慢，
  而且杀毒软件对"自解压 exe"更敏感，容易误报
* 我们要分发的本来就是一个"程序目录"（里面还要放便携 FFmpeg、许可文件、
  使用说明），onedir 正好对上

**⚠️ 绝不打包 Blender**（见 `docs/` 与 `AGENTS.md` 的硬约束）：
Blender 与 mmd_tools 都是 GPL 系，打进安装包就要履行 GPL 义务
（附源码）。本工具**只调用用户自己装的那一份**，走子进程 —— 不传染。
所以这个包**不含 Blender**，用户机器上要有 Blender 5.x + mmd_tools。

**⚠️ 绝不打包任何模型 / 贴图 / 成片**：MMD 模型普遍禁止二次配布，
版权属角色原作者。本 spec 只收代码与自绘资源。
"""

import sys
from pathlib import Path

#: 仓库根（本文件在 tools/ 下）
ROOT = Path(SPECPATH).parent
#: ⚠️ **喂给打包的是"素版"源码**：``build_installer.py`` 先把它复制到这里，
#: 顺手剥掉了全部注释与 docstring（用户要求"纯代码，不需要让人了解"）。
#:
#: 这个目录**故意不放在 ``build/`` 下** —— ``pyinstaller --clean`` 会删掉
#: 整个 ``build/``，那样这里就没了、会**静默回退到带注释的原始源码**
#: （踩过一次：报告说剥了 33 个文件，实际进包的全是原版）。
#:
#: 没先跑 build_installer 时这里不存在 —— 退回原始源码，照样能打包。
STAGED = ROOT / ".build_stage"
SRC = STAGED if (STAGED / "komaflow").is_dir() else (ROOT / "src")

#: 要随包带的**数据文件**：``(源, 包内目标目录)``。
#:
#: ⚠️ 三个目录都必须显式列出来，PyInstaller 的静态分析**看不到它们**：
#: * ``ui/assets`` 是图片，只能当数据带
#: * ``adapters/scripts`` 是**注入 Blender 执行的脚本**（不是被 import 的模块）
#: * ``adapters/vendor`` 是随包分发的第三方渲染器（MIT），同理
#: ⚠️ **不进包的清单**（用户要求「确保完全干净，没有本机隐私」）。
#:
#: PyInstaller 会把整个 ``ui/assets`` 目录搬进去，而里面有两份**只给开发期看**的：
#:
#: * ``README.md`` —— 开发笔记，写着**本机的私有路径**
#: （素材设定集放在哪、用什么脚本抠的图）。随包发出去等于把我们机器的
#: 目录结构告诉别人 —— 这就是"本机隐私"。
#: * ``logo_40_alt.png`` —— 备选图，没必要发。
#:
#: 这里是**明确的排除名单**（而不是"记得别放"）：拷数据时按名字过一遍。
EXCLUDE_FROM_ASSETS = frozenset({"README.md", "logo_40_alt.png"})

#: 🚨 **任何 ``__pycache__`` / ``.pyc`` / ``.pyo`` 都不许进包。**
#:
#: 这是最阴的一处隐私泄漏，**差点漏过去**：Python 编译字节码时会往
#: ``code.co_filename`` 里写**编译时的绝对路径**，于是
#: ``adapters/scripts/__pycache__/build.cpython-312.pyc`` 里躺着
#: ``<项目根>\\src\\...`` —— 我们的工作区根目录、项目名、
#: 用户名全在里面。而且这种 `.pyc` 什么都不用（源码已经随包带了），
#: 纯粹是**多带了一份带隐私的垃圾**。
#:
#: 注意它有两个来源：① 我们本地 `compileall` 出来的；
#: ② PyInstaller 的 ``datas`` 收目录时**整目录搬运**带进去的。
#: 所以两个入口都要过滤（见 :func:`_is_private_junk` 与 ``_clean_assets``）。
JUNK_NAMES = frozenset({"__pycache__"})
JUNK_SUFFIXES = (".pyc", ".pyo", ".pyd")


def _is_private_junk(path: Path) -> bool:
    """这个文件是不是"带本机路径的编译垃圾"。"""
    return (path.name in JUNK_NAMES
            or path.suffix.lower() in JUNK_SUFFIXES
            or any(part in JUNK_NAMES for part in path.parts))


def _clean_assets(source: Path, target: Path) -> list[tuple[str, str]]:
    """把 assets 拆成"能进包的每个文件"，排除名单与编译垃圾都跳过。

    ⚠️ 返回的是**逐个文件**的 ``(源, 目标目录)``，不是整个目录 ——
       只有这样才排得掉目录里的个别文件。
    """
    items: list[tuple[str, str]] = []
    for path in sorted(source.iterdir()):
        if path.name in EXCLUDE_FROM_ASSETS or _is_private_junk(path):
            continue
        if path.is_file():
            items.append((str(path), target.as_posix()))
        elif path.is_dir():
            items.extend(_clean_assets(path, target / path.name))
    return items


def _clean_tree(source: Path, target: str) -> list[tuple[str, str]]:
    """把一整棵源码目录收成数据文件（过滤编译垃圾）。"""
    items: list[tuple[str, str]] = []
    for path in sorted(source.rglob("*")):
        if not path.is_file() or _is_private_junk(path):
            continue
        items.append((str(path), target))
    return items


datas = [
    *_clean_assets(SRC / "komaflow" / "ui" / "assets",
                   Path("komaflow/ui/assets")),
    # ⚠️ 这两个以前是**整目录**塞进去的 —— 于是把目录里的 __pycache__ 一起带了进去。
    # 现在逐个文件收，编译垃圾全部过滤掉。
    *_clean_tree(SRC / "komaflow" / "adapters" / "scripts",
                 "komaflow/adapters/scripts"),
    *_clean_tree(SRC / "komaflow" / "adapters" / "vendor",
                 "komaflow/adapters/vendor"),
    # MIT 许可要求保留声明 —— 放到包根上，用户一眼能看到。
    # ⚠️ NOTICE 与 VERSION 是渲染器 v2.0.0 起上游要求随包带的
    # （致谢 + "拷过来的是哪个版本"，排查时要先看后者）。
    (str(SRC / "komaflow" / "adapters" / "vendor" / "LICENSE_MMD渲染.txt"),
     "."),
    (str(SRC / "komaflow" / "adapters" / "vendor" / "NOTICE_MMD渲染.md"), "."),
        # ⚠️ 发的是**对外版**声明（含 Python / Tcl-Tk / PyInstaller / FFmpeg 的标注）；
    # vendor 里那份是给开发者看的上游维护说明，不随包发。
(str(ROOT / "第三方来源与许可_发布版.md"), "."),
]

#: 明确的隐藏导入。都是**运行时动态取用**、静态分析看不出来的：
#: ``ctypes.windll`` 那一串、以及各适配器脚本本身是外部文件不是模块。
hiddenimports = [
    "tkinter",
    "tkinter.filedialog",
    "tkinter.messagebox",
    "tkinter.font",
]

a = Analysis(
    [str(ROOT / "tools" / "KomaFlow_launch.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # ⚠️ 排掉明确用不到的重量级库，包能小不少
    excludes=[
        "numpy", "PIL", "scipy", "matplotlib", "pandas",
        "pytest", "setuptools", "pip", "unittest",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="KomaFlow",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False, # ⚠️ 不用 UPX：压缩后的 exe 更容易被杀毒误报
    console=False, # 无控制台 —— 界面程序不该弹黑窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "src" / "komaflow" / "ui" / "assets" / "logo.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="KomaFlow",
)
