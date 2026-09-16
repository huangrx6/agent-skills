"""布局层：几何模型与安全盒碰撞（Layout Engine 的数学与验收层）。

分工（与仓库其余部分一致）：
- ``render.py`` 产出几何（DOM 流式布局 + 壳 CSS）；
- ``measure.py`` 实测产物（真浏览器）；
- 本包只做**确定性计算与验收**：矩形运算、安全盒扩张、相交判定、
  碰撞政策（deny / decorative / intentional）。

本包不做审美决策、不选版式、不生成几何 —— 那些是作者（spec）与渲染层的事。

加载：``scripts/`` 不是包，各脚本按文件路径加载本包（同 ``_load_sibling``
的机制）。先声明 ``__path__`` 再导入子模块，相对导入才解析得了。
"""
import os as _os

__path__ = [_os.path.dirname(_os.path.abspath(__file__))]

from . import model, collision  # noqa: E402,F401  （依赖上面的 __path__）
