"""自动探测用户电脑里的 Blender。

对应需求：K-7.4（启动时自动探测：常见安装目录 / 注册表 / PATH / 用户手动指定）·
K-7.5（多个时列出由用户选，并标注统一基准版本）· K-7.8（缺失时给指引）。

原则
----
* **只读探测**，绝不修改用户任何配置
* 探测到多个时**不代选**，全部列出来交给用户（设计取舍）
* 结果里带上"是不是统一基准版本"，供界面标注
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from .registry import ADAPTERS, adapter_by_key

#: 允许用环境变量显式指定 Blender 路径（优先级最高）
ENV_BLENDER = "KomaFlow_BLENDER"

#: 每个盘符下面值得找的几个位置（模板里的 ``{d}`` 换成盘符）。
#:
#: ⚠️ 原来是**写死 C/D/E 三条路 + 两个 Steam 默认目录**，结果：
#: Steam 装在别的盘、便携版解在别处、装到自定义目录 —— 一律找不到。
#: 现在改成"所有盘符 × 常见子目录"，再加注册表与 Steam 库表两条线索。
_DRIVE_PATTERNS = (
    r"{d}\Program Files\Blender Foundation\Blender*\blender.exe",
    r"{d}\Program Files (x86)\Blender Foundation\Blender*\blender.exe",
    r"{d}\Blender Foundation\Blender*\blender.exe",
    r"{d}\Blender*\blender.exe",
    r"{d}\Steam\steamapps\common\Blender\blender.exe",
    r"{d}\SteamLibrary\steamapps\common\Blender\blender.exe",
    r"{d}\Games\Steam\steamapps\common\Blender\blender.exe",
    r"{d}\Program Files\Steam\steamapps\common\Blender\blender.exe",
    # 微软商店版（目录受 ACL 保护，glob 可能返回空 —— 失败就跳过）
    r"{d}\Program Files\WindowsApps\*Blender*\blender.exe",
)

#: 用户目录下的位置（免安装版 / 便携版常见）
_USER_PATTERNS = (
    r"%LOCALAPPDATA%\Programs\Blender Foundation\Blender*\blender.exe",
    r"%LOCALAPPDATA%\Programs\Blender*\blender.exe",
    r"%APPDATA%\Blender Foundation\Blender*\blender.exe",
    # 便携版（解压即用）最常被扔在这两个地方
    r"%USERPROFILE%\Desktop\Blender*\blender.exe",
    r"%USERPROFILE%\Downloads\Blender*\blender.exe",
    r"%USERPROFILE%\Desktop\**\blender.exe",
)


@dataclass(frozen=True)
class Candidate:
    """一个候选 Blender。"""

    exe: Path
    source: str

    def display(self) -> str:
        return str(self.exe)


#: 上一次扫描的痕迹（"没找到"时给用户看，避免只说一句找不到）
LAST_SCAN: dict = {"tried": [], "hits": [], "errors": []}


def discover_blender(extra_paths: list[str | Path] | None = None) -> list[Candidate]:
    """列出所有找到的 Blender。**不代选**，顺序只是建议顺序。"""
    LAST_SCAN["tried"].clear()
    LAST_SCAN["hits"].clear()
    LAST_SCAN["errors"].clear()
    found: list[Candidate] = []
    seen: set[str] = set()

    def add(path: Path, source: str) -> None:
        LAST_SCAN["tried"].append(f"{source}: {path}")
        try:
            key = str(path.resolve()).lower()
        except OSError:
            key = str(path).lower()
        if key in seen or not path.is_file():
            return
        seen.add(key)
        found.append(Candidate(path, source))
        LAST_SCAN["hits"].append(str(path))

    for raw in (extra_paths or []):
        add(Path(raw), "用户指定")

    env_value = os.environ.get(ENV_BLENDER)
    if env_value:
        add(Path(env_value), f"环境变量 {ENV_BLENDER}")

    LAST_SCAN["tried"].append("PATH 里的 blender")
    from_path = shutil.which("blender")
    if from_path:
        add(Path(from_path), "PATH")

    # ① 注册表（安装版会把路径记在这里）+ Steam 库表
    LAST_SCAN["tried"].append("注册表（卸载项 / Blender 版本键 / Steam 库表）")
    for hint, source in _registry_hints():
        add(hint, source)

    # ② 所有盘符 × 常见子目录
    drives = _drive_letters()
    LAST_SCAN["tried"].append(
        "盘符 %s × %d 个常见位置（Program Files / Steam / SteamLibrary / WindowsApps 等）"
        % (",".join(drives) or "无", len(_DRIVE_PATTERNS)))
    for pattern in _DRIVE_PATTERNS:
        for drive in _drive_letters():
            try:
                for hit in _glob_absolute(pattern.format(d=drive)):
                    add(hit, "常见安装目录")
            except Exception as exc: # noqa: BLE001 - 探测失败不应影响启动
                LAST_SCAN["errors"].append(f"{pattern.format(d=drive)}: {exc}")
                continue

    # ③ 用户目录下的便携版
    LAST_SCAN["tried"].append("用户目录（LocalAppData / AppData / 桌面 / 下载）")
    for pattern in _USER_PATTERNS:
        try:
            expanded = os.path.expandvars(pattern)
            if "%" in expanded: # 变量没展开（变量不存在）
                continue
            for hit in _glob_absolute(expanded):
                add(hit, "用户目录")
        except Exception: # noqa: BLE001
            continue

    return found


def last_scan_summary(limit: int = 12) -> str:
    """把上一次扫描的摘要压成几行（给日志用）。"""
    hits = LAST_SCAN.get("hits") or []
    if hits:
        return "扫描命中 %d 个：%s" % (len(hits), "; ".join(hits[:limit]))
    lines = ["扫描没找到任何 Blender。查过："]
    lines.extend(" · " + item for item in (LAST_SCAN.get("tried") or [])[:limit])
    errors = LAST_SCAN.get("errors") or []
    if errors:
        lines.append("出错的位置（可能是权限/ACL，不是没装）：")
        lines.extend(" ! " + item for item in errors[:limit])
    lines.append("如果确定装了，请确认装的是 blender.exe（不是快捷方式），"
                 "并把它拖进「自己选路径…」。")
    return "\n".join(lines)


def _drive_letters() -> list[str]:
    """当前**存在**的盘符（找不到的盘不去 glob，免得卡住）。"""
    letters: list[str] = []
    for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        root = f"{letter}:\\"
        try:
            if Path(root).exists():
                letters.append(f"{letter}:")
        except OSError:
            continue
    return letters


def _registry_hints() -> list[tuple[Path, str]]:
    """从注册表与 Steam 库表里挖出 Blender 的候选路径。

    三条线索：
      * 卸载项里的 ``InstallLocation`` / ``DisplayIcon``（**安装版**）
      * ``HKCU\\Software\\Blender Foundation\\Blender`` 下的版本键
      * Steam 的 ``SteamPath`` + ``libraryfolders.vdf``（**Steam 版**，可以装在任意盘）

    全部只读；任何一步失败都静默跳过 —— 探测不该让程序起不来。
    """
    hints: list[tuple[Path, str]] = []
    try:
        import winreg
    except ImportError:
        return hints

    def _read(root, key_path: str, value: str) -> str:
        try:
            with winreg.OpenKey(root, key_path) as key:
                data, _ = winreg.QueryValueEx(key, value)
                return str(data)
        except OSError:
            return ""

    def _subkeys(root, key_path: str) -> list[str]:
        out: list[str] = []
        try:
            with winreg.OpenKey(root, key_path) as key:
                index = 0
                while True:
                    try:
                        out.append(winreg.EnumKey(key, index))
                    except OSError:
                        break
                    index += 1
        except OSError:
            pass
        return out

    # ---- 卸载项 ----
    uninstall = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for sub in _subkeys(hive, uninstall):
            display = _read(hive, f"{uninstall}\\{sub}", "DisplayName")
            if "blender" not in display.lower():
                continue
            location = _read(hive, f"{uninstall}\\{sub}", "InstallLocation")
            icon = _read(hive, f"{uninstall}\\{sub}", "DisplayIcon")
            for raw in (location, icon):
                if not raw:
                    continue
                candidate = Path(raw.strip('"').split(",")[0])
                if candidate.suffix.lower() == ".exe":
                    hints.append((candidate, "注册表"))
                else:
                    hints.extend((hit, "注册表") for hit in _exe_under(candidate))

    # ---- Blender 自己的版本键 ----
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for sub in _subkeys(hive, r"SOFTWARE\Blender Foundation\Blender"):
            for raw in (
                _read(hive, f"SOFTWARE\\Blender Foundation\\Blender\\{sub}", "InstallDir"),
                _read(hive,
                      f"SOFTWARE\\Blender Foundation\\Blender\\{sub}\\{sub}", "InstallDir"),
            ):
                if raw:
                    hints.extend((hit, "注册表") for hit in _exe_under(Path(raw)))

    # ---- Steam ----
    steam_roots: list[Path] = []
    for hive, key in ((winreg.HKEY_CURRENT_USER, r"SOFTWARE\Valve\Steam"),
                      (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
                      (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam")):
        for value in ("SteamPath", "InstallPath"):
            raw = _read(hive, key, value)
            if raw:
                steam_roots.append(Path(raw))
    for steam in steam_roots:
        hints.extend((hit, "Steam") for hit in _steam_blender(steam))

    return [(path, source) for path, source in hints if path is not None]


def _exe_under(folder: Path) -> list[Path]:
    """在某个目录里找 blender.exe（本身是 exe 就直接返回）。"""
    if folder.suffix.lower() == ".exe":
        return [folder] if folder.is_file() else []
    if not folder.is_dir():
        return []
    direct = folder / "blender.exe"
    if direct.is_file():
        return [direct]
    return list(folder.glob("Blender*/blender.exe")) + list(folder.glob("*/blender.exe"))


def _steam_blender(steam_root: Path) -> list[Path]:
    """Steam 可能装了多个库，逐个库去找 ``steamapps\\common\\Blender``。"""
    hits: list[Path] = []
    candidates = [steam_root]
    vdf = steam_root / "steamapps" / "libraryfolders.vdf"
    if vdf.is_file():
        try:
            text = vdf.read_text(encoding="utf-8", errors="replace")
            import re
            for raw in re.findall(r'"path"\s+"([^"]+)"', text):
                candidates.append(Path(raw.replace("\\\\", "\\")))
        except OSError:
            pass
    for root in candidates:
        exe = root / "steamapps" / "common" / "Blender" / "blender.exe"
        if exe.is_file():
            hits.append(exe)
    return hits


def _glob_absolute(pattern: str) -> list[Path]:
    """在绝对路径里做 glob（``Path.glob`` 不支持绝对模式，这里交给 glob 模块）。"""
    import glob

    return [Path(p) for p in glob.glob(pattern)]


def describe_candidate(candidate: Candidate) -> str:
    """一行说明，标注是否落在统一基准版本范围内。"""
    version = parse_version_from_path(candidate.exe)
    if version is None:
        return f"{candidate.exe}（{candidate.source}）"
    for adapter in ADAPTERS:
        if adapter.supports(version):
            mark = "（统一基准版本）" if adapter.is_baseline else ""
            return f"Blender {'.'.join(map(str, version))}{mark} {candidate.exe}"
    return f"Blender {'.'.join(map(str, version))}（不在支持范围内） {candidate.exe}"


def parse_version_from_path(exe: Path) -> tuple[int, ...] | None:
    """从安装路径里猜版本号，例如 ``...\\Blender 5.2\\blender.exe``。

    只是**展示用**的快速判断；真正的版本以 :meth:`BlenderAdapter.probe` 实测为准。
    """
    import re

    for part in reversed(exe.parts):
        match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", part)
        if match:
            return tuple(int(g) for g in match.groups() if g is not None)
    return None
