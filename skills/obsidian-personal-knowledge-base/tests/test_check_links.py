#!/usr/bin/env python3
"""check_links.py 的回归测试。

为什么需要:check_links.py 里的每个设计决定都来自踩过的坑 —— 代码块里的
`[[ ]]`、只索引 .md 导致图片嵌入假失效、路径/别名/锚点/表格转义的处理。
这些是经验,而经验会随时间淡忘。没有测试的话,未来重构很容易无意中
重新引入同一批误报,而且不会立刻有人发现(这类 bug 表现为"安静地漏报",
比报错难察觉得多)。

fixture 在 setUpClass 里生成到临时目录,不落盘成 .md 文件 —— 那些故意
写坏的链接会被编辑器/语法检查当成真坏链报警,而它们本来就是用来测
"坏链能被报出来"的。

跑法:
    python3 -m unittest discover -s tests -v
    python3 tests/test_check_links.py
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
CHECK_LINKS = os.path.join(SCRIPTS, "check_links.py")

# ── fixture 内容 ───────────────────────────────────────────────
# 每个文件对应一类要守住的行为,注释写清"防的是什么"

FIXTURES: dict[str, str] = {
    # 坑 1:代码块里的方括号不是 wikilink。
    # 真实来源:bash 的 [[ ]] 条件判断、Python 的 Callable[[P], T]、TOML 片段。
    "代码块陷阱.md": """---
type: resource
---

# 代码块陷阱

```sh
if [[ "$FILE_PATH" == *"$pattern"* ]]; then
  echo "[[这个也不是链接]]"
fi
```

行内形式:`[[ "$a" == *"$b"* ]]`

```python
from typing import Callable


def deco(f: Callable[[int], str]) -> Callable[[int], str]:
    return f
```

```toml
[plugins."io.containerd.snapshotter.v1"]
  driver-type = "overlayfs"
```

不在代码块里的裸方括号也不算:a[b] 与 a[b[c]] 里 `[[` 不相邻。
""",
    # 坑 2/3/4:别名、锚点、路径、相对路径、表格转义、附件嵌入。
    "可解析的引用.md": """---
type: resource
---

# 可解析的引用

- 短链接:[[目标笔记]]
- 带别名:[[目标笔记|换个显示名]]
- 带锚点:[[目标笔记#某个小节]]
- 带子目录路径:[[子目录/深层目标]]
- 嵌入附件:![[存在的图片.png]]

| 列一 | 列二 |
| --- | --- |
| [[目标笔记\\|表格里的链接]] | ![[存在的图片.png]] |
""",
    # 真坏链:用来确认检查器真的会报,而不是永远全绿
    "失效引用.md": """---
type: resource
---

# 失效引用

- 不存在的笔记:[[绝不存在的笔记 ABC123]]
- 不存在的图片:![[不存在的图片 XYZ789.png]]
- 混一个正常的,确认不会连带误报:[[目标笔记]]
""",
    "目标笔记.md": """---
type: resource
---

# 目标笔记

## 某个小节
""",
    "子目录/深层目标.md": """---
type: resource
---

# 深层目标
""",
    # 相对当前笔记解析(../),不是从 vault 根算
    "子目录/相对引用.md": """---
type: resource
---

- 上级笔记:[[../目标笔记]]
""",
    # 空文件即可:检查器只按文件名索引附件,不读内容
    "90 Assets/Attachments/存在的图片.png": "",
}

EXPECTED_BROKEN = {
    "失效引用.md": {
        ("绝不存在的笔记 ABC123", "link"),
        ("不存在的图片 XYZ789.png", "embed"),
    },
}


def _load_check_links():
    """按路径加载 check_links.py(scripts/ 不是包,不能用 import 语句)。"""
    spec = importlib.util.spec_from_file_location("check_links_under_test", CHECK_LINKS)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {CHECK_LINKS}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CheckLinksTest(unittest.TestCase):
    tmp: str

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_check_links()
        cls.tmp = tempfile.mkdtemp(prefix="check-links-fixture-")
        for rel, content in FIXTURES.items():
            path = os.path.join(cls.tmp, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
        cls.broken = cls.mod.scan(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        import shutil

        shutil.rmtree(cls.tmp, ignore_errors=True)

    def broken_in(self, note: str) -> set[tuple[str, str]]:
        return {(b["target"], b["kind"]) for b in self.broken if b["file"] == note}

    # ── 防线 1:代码块不是 wikilink ──
    def test_code_blocks_are_ignored(self):
        self.assertEqual(
            self.broken_in("代码块陷阱.md"),
            set(),
            "代码块/行内代码里的 [[ ]] 被误判成 wikilink",
        )

    # ── 防线 2:各种合法链接形式都要解析成功 ──
    def test_resolvable_forms_are_not_reported(self):
        self.assertEqual(
            self.broken_in("可解析的引用.md"),
            set(),
            "别名 / 锚点 / 子目录路径 / 表格转义 / 附件嵌入 里有被误报的",
        )

    # ── 防线 3:相对路径 ──
    def test_relative_path_resolves(self):
        self.assertEqual(
            self.broken_in("子目录/相对引用.md"),
            set(),
            "[[../目标笔记]] 没有被按相对当前笔记解析",
        )

    # ── 防线 4:真坏链必须报出来(防止永远全绿) ──
    def test_real_breakage_is_reported(self):
        self.assertEqual(
            self.broken_in("失效引用.md"),
            EXPECTED_BROKEN["失效引用.md"],
            "失效链接没有被报出,或 link/embed 分类不对",
        )

    def test_total_count(self):
        self.assertEqual(len(self.broken), 2, f"期望恰好 2 个失效引用,实得 {len(self.broken)}")

    # ── CLI 行为:退出码契约 ──
    def test_cli_exit_code_is_1_when_broken(self):
        proc = subprocess.run(
            [sys.executable, CHECK_LINKS, "--vault", self.tmp, "--quiet"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 1, "有坏链时退出码应为 1")

    def test_cli_exit_code_is_0_when_clean(self):
        with tempfile.TemporaryDirectory(prefix="check-links-clean-") as clean:
            with open(os.path.join(clean, "只有一篇.md"), "w", encoding="utf-8") as fh:
                fh.write("# 干净\n")
            proc = subprocess.run(
                [sys.executable, CHECK_LINKS, "--vault", clean, "--quiet"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, "无坏链时退出码应为 0")

    def test_cli_exit_code_is_2_when_vault_missing(self):
        proc = subprocess.run(
            [sys.executable, CHECK_LINKS, "--vault", "/definitely/not/here", "--quiet"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 2, "vault 不存在时退出码应为 2")


if __name__ == "__main__":
    unittest.main(verbosity=2)
