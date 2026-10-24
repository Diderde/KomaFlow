"""错误弹窗不能露出 traceback —— 这层保障要钉住。

背景
----
用户截过一个图：错误弹窗里**整屏英文堆栈**（mmd_tools 的 InvalidFileError），
真正的原因「File signature is invalid.」埋在中间。

根因有三层叠加：

1. mmd_tools 那个异常**消息里自带完整 traceback**（``str(exc)`` 就是多行堆栈）
2. ``build.py`` 拼成 ``f"{type(exc).__name__}: {exc}"``
3. ``KomaFlowError.human()`` 又把整个 detail 塞进用户消息

所以这些测试盯的是**用户可见的那一面**：不能出现 ``Traceback``、
不能出现大段英文路径、能认出常见错并翻成中文。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from komaflow.core.errors import ( # noqa: E402
    ErrorKind, KomaFlowError, collapse, friendly_reason, last_meaningful_line)

#: 真实遇到的那个错误串（缩略版，保留结构）
TRACEBACK = """Traceback (most recent call last):
  File "C:/Users/x/AppData/Roaming/Blender Foundation/Blender/5.2/extensions/blender_org/mmd_tools/operators/fileio.py", line 355, in execute
    self._do_execute(context)
    ~~~~~~~~~~~~~~~~~~~~~~~~
  File "C:/x/importer.py", line 915, in execute
    self._model = pmx.load(args["filepath"])
    ^^^^^^^^^^^^^^^^^
bl_ext.blender_org.mmd_tools.core.pmx.InvalidFileError: File signature is invalid."""


class TestErrorDialogIsHuman(unittest.TestCase):
    def test_last_line_is_the_real_reason(self):
        got = last_meaningful_line(TRACEBACK)
        self.assertIn("signature is invalid", got)
        self.assertNotIn("Traceback", got)

    def test_skips_decorator_lines(self):
        """末行是 `^^^` 这种装饰行时，要往上找真正的原因。"""
        text = ("Traceback (most recent call last):\n"
                " File \"a.py\", line 1\n"
                "RuntimeError: 真正的原因\n"
                " ^^^^^^^^^^^")
        self.assertEqual(last_meaningful_line(text), "RuntimeError: 真正的原因")

    def test_human_never_leaks_traceback(self):
        err = KomaFlowError(ErrorKind.ASSET_CORRUPT, detail=TRACEBACK)
        message = err.human()
        self.assertNotIn("Traceback", message)
        self.assertNotIn("File \"", message)
        # 但要说人话 + 给出建议
        self.assertIn("读不出来", message)
        self.assertIn("建议", message)

    def test_log_line_keeps_everything(self):
        """用户看不到的技术细节，日志里必须完整保留（排查全靠它）。"""
        err = KomaFlowError(ErrorKind.ASSET_CORRUPT, detail=TRACEBACK)
        self.assertIn("Traceback", err.log_line())
        self.assertIn("asset_corrupt", err.log_line())

    def test_known_reasons_translated(self):
        cases = (
            ("bl_ext.x.InvalidFileError: File signature is invalid.",
             "不是有效的 PMX"),
            ("FileNotFoundError: [Errno 2] No such file or directory",
             "找不到文件"),
            ("PermissionError: [Errno 13] Permission denied", "权限"),
        )
        for raw, want in cases:
            with self.subTest(raw=raw):
                self.assertIn(want, friendly_reason(raw))

    def test_unknown_reason_kept_verbatim(self):
        """不认识的错**不要瞎编中文** —— 原文留着，用户搜索时有用。"""
        got = friendly_reason("SomeWeirdError: 完全没见过的东西")
        self.assertIn("SomeWeirdError", got)

    def test_filename_survives(self):
        """带文件名的包装要能解析出文件名 —— 用户可能有好几个 PMX。"""
        raw = ("RuntimeError: 角色模型 文件「Miku.pmx」读不出来："
               "bl_ext.x.InvalidFileError: File signature is invalid.")
        got = friendly_reason(last_meaningful_line(raw))
        self.assertIn("Miku.pmx", got)
        self.assertIn("不是有效的 PMX", got)

    def test_short_detail_still_shown(self):
        """短的 detail（如"没有可编码的 PNG 序列"）应当原样出现在弹窗里。"""
        err = KomaFlowError(ErrorKind.ASSET_CORRUPT, detail="没有可编码的 PNG 序列")
        self.assertIn("没有可编码的 PNG 序列", err.human())

    def test_collapse_flattens_newlines(self):
        self.assertEqual(collapse("a\nb\nc"), "a b c")


if __name__ == "__main__":
    unittest.main()
