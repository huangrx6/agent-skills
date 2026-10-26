"""同一个文件在多个 skill 里各存一份时，必须逐字相同。

为什么要这条
------------
skill 之间不许互相 import（每个目录都要能单独安装），所以有些小工具只能复制。
复制本身没问题，**单边修改**才是问题：改了一个 skill 的 `vault_path.py`，
另一个还在用旧逻辑，而两边读的是同一份 Obsidian 配置。

这和 `pingcode-weekly/scripts/_pingcode/` 是同一类风险，那边用 VENDOR.json 记来源；
这里两份额外要求「完全一致」，所以直接比字节。
"""

from __future__ import annotations

import hashlib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# 同一份实现的多个副本：要么逐字相同，要么在这里登记为「有意分叉」并说明理由。
IDENTICAL_GROUPS = {
    "vault_path.py": (
        "skills/obsidian-wiki/scripts/vault_path.py",
        "skills/obsidian-work/scripts/vault_path.py",
    ),
}


class SharedFileTest(unittest.TestCase):
    def test_copies_are_byte_identical(self):
        for name, paths in IDENTICAL_GROUPS.items():
            with self.subTest(file=name):
                hashes = {}
                for rel in paths:
                    path = ROOT / rel
                    self.assertTrue(path.is_file(), f"缺少文件：{rel}")
                    hashes[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
                unique = set(hashes.values())
                self.assertEqual(
                    1, len(unique),
                    f"{name} 的各份副本已经不同：{sorted(hashes)}。"
                    f"确认哪份是对的，然后同步其余副本（它们必须逐字相同）")

    def test_groups_point_at_existing_files(self):
        """路径写错时上面那条会报“缺少文件”，这里额外交代清单本身别写歪。"""
        for name, paths in IDENTICAL_GROUPS.items():
            with self.subTest(file=name):
                self.assertGreaterEqual(len(paths), 2, f"{name} 至少要两处才需要这条检查")


if __name__ == "__main__":
    unittest.main()
