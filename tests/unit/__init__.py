"""单元测试包。

约定：**只用标准库 unittest**，不引入 pytest 等需要 pip 安装的依赖
（与 NFR-16 的精神一致，也让任何装了 Python 的机器都能跑测试）。

跑法::

    set PYTHONPATH=src
    python -m unittest discover -s tests -v
"""
