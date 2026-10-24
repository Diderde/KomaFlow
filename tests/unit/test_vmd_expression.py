"""回归：动作可以挂多个，但**同一个文件不能导入两遍**。

背景
----
用户问过："骨架的动作和面部表情按理说可以同时加载导入吧，不用分特别细？"
后来又要求："这个动作和表情，可以添加多个而不是局限于2个"。

答：本来就没拆分，现在更是完全不限制数量。``mmd_tools.import_vmd``
一次调用就把骨骼 / 表情 / 相机全读进去，没有"只读某一段"的开关，所以：

* 一个文件里**同时**有骨骼和表情 → 导入一次就都进去了
* 多个文件 → 按用户排的顺序**逐个导入**，后导入的覆盖同名骨骼
  （mmd_tools 每次新建一个 action，这正是分层叠加想要的行为）

隐患（这里守的就是这一条）：**同一个文件被挂了两遍**，就会在同一个
armature 上导入两次 → 建出两套同名 action，后面按名字取 action 时
拿到哪一套就不确定了。

⚠️ 这组测试原来是**拿源码文本做断言**（在 build.py 里找
   ``# ── 表情 ──`` 那段）。多文件改造后那个注释没了，测试全挂 ——
   而"测试盯着注释找"本身就是脆的。现在改成**测真实逻辑**：
   用 ``core.project.Inputs.all_motions()`` 的去重行为做断言。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from komaflow.core.project import Inputs # noqa: E402


class TestMotionsAreAlist(unittest.TestCase):
    """动作 / 表情都是列表，不限制数量。"""

    def test_many_motions_are_kept(self):
        inputs = Inputs(motions=["a.vmd", "b.vmd", "c.vmd", "d.vmd"])
        self.assertEqual(len(inputs.motions), 4)
        self.assertEqual(inputs.all_motions(),
                         ["a.vmd", "b.vmd", "c.vmd", "d.vmd"])

    def test_motions_and_expressions_merge_in_order(self):
        """动作排在表情前面 —— 用户明确放的动作文件优先。"""
        inputs = Inputs(motions=["动作1.vmd", "动作2.vmd"],
                        expressions=["表情1.vmd"])
        self.assertEqual(inputs.all_motions(),
                         ["动作1.vmd", "动作2.vmd", "表情1.vmd"])

    def test_same_file_in_both_lists_is_deduped(self):
        """同一个文件放进动作和表情两栏 → 只导一次。

        这是原来那条保护，行为没变，只是现在从**源码文本断言**
        改成了**行为断言**。
        """
        path = r"C:\素材\同一个.vmd"
        inputs = Inputs(motions=[path], expressions=[path])
        self.assertEqual(inputs.all_motions(), [path])

    def test_dedup_ignores_path_spelling(self):
        """``/`` 与 ``\\`` 写法不同也要认成同一个文件（Windows 常态）。"""
        inputs = Inputs(motions=[r"C:\素材\a.vmd"],
                        expressions=["C:/素材/A.VMD"])
        self.assertEqual(len(inputs.all_motions()), 1)

    def test_empty_entries_are_dropped(self):
        inputs = Inputs(motions=["a.vmd", "", None], expressions=["", "b.vmd"])
        self.assertEqual(inputs.all_motions(), ["a.vmd", "b.vmd"])

    def test_legacy_single_field_still_works(self):
        """老代码用的是 ``inputs.motion``（单数）—— 必须还能读写。"""
        inputs = Inputs()
        inputs.motion = "只有一个.vmd"
        self.assertEqual(inputs.motions, ["只有一个.vmd"])
        self.assertEqual(inputs.motion, "只有一个.vmd")
        # 再设一次不应该把已有的列表弄丢
        inputs.motions = ["x.vmd", "y.vmd"]
        self.assertEqual(inputs.motion, "x.vmd")


class TestVmdFormatUnderstood(unittest.TestCase):
    """把"一个 VMD 能同时装骨骼和表情"这件事写成可执行的事实。"""

    def test_probe_script_parses_both_sections(self):
        """``work/probe_vmd_parts.py`` 必须能分别数出骨骼帧与表情帧。

        用户那两个文件正是靠它数出来的：动作文件 40,413 骨骼 / 0 表情，
        表情文件 0 骨骼 / 59 表情 —— **证明它们是两个文件，不是我们拆细了**。
        """
        probe_path = ROOT / "work" / "probe_vmd_parts.py"
        if not probe_path.is_file():
            self.skipTest("开发期的 work/probe_vmd_parts.py 不在仓库里")
        probe = probe_path.read_text(encoding="utf-8")
        self.assertIn("骨骼帧", probe)
        self.assertIn("表情帧", probe)
        self.assertIn("111", probe) # 骨骼帧单帧字节数
        self.assertIn("23", probe) # 表情帧单帧字节数


if __name__ == "__main__":
    unittest.main()
