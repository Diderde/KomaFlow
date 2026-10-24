"""把界面里写死的像素尺寸批量包进 ``T.S()``。

⚠️ **一次性工具**（跑完就该删或归档）。它的作用是完成 DPI 改造里那 100 多处机械劳动。

为什么要脚本
------------
手改 100 多处必然漏、必然手滑。这种纯机械替换就该交给脚本，改完再看结果。

⚠️ **只包"像素单位"的参数**，这是关键：
* ``padx=`` / ``pady=`` / ``wraplength=`` / ``minsize=`` —— 永远是像素 ✅
* ``width=`` / ``height=`` —— **要看是哪个控件**：
  * ``tk.Frame`` / ``tk.Canvas`` / 我们自绘的控件（FlatButton、HelperCard…）→ 像素 ✅
  * ``tk.Entry`` / ``tk.Label`` → **字符数**！包了就错 ❌
  所以只对"白名单构造函数所在的那一行"动手。

两个坑（第一版就死在这上面）
----------------------------
1. **元组**：代码里大量 ``padx=(0, 12)``。第一版的正则只认单个数字，
   实测 104 处只改到 2 处 —— 必须支持 ``(a, b)``。
2. **不要跨行**：构造函数名和 width/height 基本都在同一行；跨行的漏掉不会出事，
   只是那个控件保持原尺寸，之后人工补一眼即可（比乱改安全得多）。

用法::

    python tools/apply_dpi_scaling.py # 预演，只报告不写
    python tools/apply_dpi_scaling.py --write # 真写
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "src" / "komaflow" / "ui"

#: width/height 是"像素"的构造函数（其余如 tk.Entry / tk.Label 是字符数，绝不动）
PIXEL_CTORS = (
    "tk.Tk", "tk.Toplevel", "tk.Frame", "tk.Canvas",
    "FlatButton", "ThinProgress", "HelperCard", "TitleBar", "Select", "Card",
    "Pill", "CardPanel", "BatchProgress", "MaterialList",
)

#: 永远按像素处理的参数
ALWAYS_PIXEL = ("padx", "pady", "wraplength", "minsize", "ipadx", "ipady")

#: 只在白名单行里处理的参数
CTOR_PIXEL = ("width", "height")

#: 已经包过的就别再包
GUARD = re.compile(r"=\s*T\.S\(")

#: 单个整数：``padx=12``
SINGLE = r"\d+"
#: 两元组：``padx=(0, 12)`` —— 允许负号与空格
PAIR = r"\(\s*-?\d+\s*,\s*-?\d+\s*\)"


def _wrap_single(match: re.Match, name: str) -> str:
    return f"{name}=T.S({match.group(1)})"


def _wrap_pair(match: re.Match, name: str) -> str:
    first, second = match.group(1), match.group(2)
    return f"{name}=(T.S({first}), T.S({second}))"


def _sub(line: str, name: str) -> str:
    """把 ``name=12`` 与 ``name=(0, 12)`` 两种写法都包上。"""
    pair = re.compile(rf"\b{name}\s*=\s*\(\s*(-?\d+)\s*,\s*(-?\d+)\s*\)")
    line = pair.sub(lambda m, n=name: _wrap_pair(m, n), line)
    single = re.compile(rf"\b{name}\s*=\s*(\d+)\b")
    return single.sub(lambda m, n=name: _wrap_single(m, n), line)


def _sub_always(line: str) -> str:
    for name in ALWAYS_PIXEL:
        line = _sub(line, name)
    return line


def _sub_ctor(line: str) -> str:
    if not any(ctor in line for ctor in PIXEL_CTORS):
        return line
    for name in CTOR_PIXEL:
        line = _sub(line, name)
    return line


#: 数"改了几处"用的：包完之后 ``=T.S(`` 的个数
COUNT = re.compile(r"=\s*T\.S\(")


def transform(text: str) -> tuple[str, int, int]:
    """返回 ``(新内容, 本次改了几处, 文件里原本已包了几处)``。"""
    out = []
    changed = 0
    already = 0
    for line in text.splitlines(keepends=True):
        if GUARD.search(line):
            already += len(GUARD.findall(line))
            out.append(line)
            continue
        new = _sub_ctor(_sub_always(line))
        if new != line:
            # 逐行对比"包了 T.S("的个数增量，比 diff 简单也更准
            changed += (len(COUNT.findall(new)) - len(COUNT.findall(line)))
        out.append(new)
    return "".join(out), changed, already


def main() -> int:
    write = "--write" in sys.argv
    total = 0
    for path in sorted(ROOT.glob("*.py")):
        original = path.read_text(encoding="utf-8")
        updated, count, already = transform(original)
        if count or already:
            total += count
            print(f" {path.name:16s} 本次 {count:4d} 处"
                  f"（文件里已包 {already:4d} 处）")
            if write:
                path.write_text(updated, encoding="utf-8")
    print(f"{'已写入' if write else '预演'}：合计 {total} 处")
    if not write:
        print("加 --write 才会真改")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
