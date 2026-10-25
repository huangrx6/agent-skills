"""`pingcode-weekly` 内置的只读 PingCode 客户端与上游是否还对得上。

为什么要这条
------------
`skills/pingcode-weekly/scripts/_pingcode/` 是 `skills/pingcode/scripts/` 的只读子集：
周报要能单独安装，就不能依赖另一个 skill。代价是两份代码会各自演化 ——
上游修了分页或限流、这边收不到通知，而两边跑的其实是同一套接口。

所以来源写进 `VENDOR.json`，这里只做对账，不判断该不该同步。
"""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parents[1] / "skills" / "pingcode-weekly"
VENDOR = SKILL / "scripts" / "_pingcode"
UPSTREAM = SKILL.parents[1] / "skills" / "pingcode" / "scripts"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class VendorSyncTest(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((VENDOR / "VENDOR.json").read_text(encoding="utf-8"))
        self.files = self.manifest["files"]

    def test_manifest_covers_every_python_file(self):
        """新增或删除文件都要登记，否则清单会悄悄过期。"""
        on_disk = {p.name for p in VENDOR.glob("*.py")} - {"__init__.py"}
        self.assertEqual(sorted(self.files), sorted(on_disk),
                         "VENDOR.json 的文件列表与 _pingcode/ 不一致")

    def test_upstream_unchanged_since_vendoring(self):
        """上游改了就该重新评估同步 —— 失败是提醒，不是「把哈希改掉」就完事。"""
        for name, meta in sorted(self.files.items()):
            with self.subTest(file=name):
                upstream = UPSTREAM / name
                self.assertTrue(upstream.is_file(), f"上游文件不存在：{upstream}")
                self.assertEqual(
                    meta["upstream_sha256"], _sha256(upstream),
                    f"上游 {name} 已变化：先在 pingcode 里确认改动是否需要同步到 "
                    f"_pingcode/，再更新 VENDOR.json 的两个哈希")

    def test_vendored_files_match_their_record(self):
        """这一份改了却没登记，说明 note 与哈希已经不能代表实际差异。"""
        for name, meta in sorted(self.files.items()):
            with self.subTest(file=name):
                vendored = VENDOR / name
                self.assertTrue(vendored.is_file(), f"内置文件丢失：{vendored}")
                self.assertEqual(
                    meta["vendored_sha256"], _sha256(vendored),
                    f"_pingcode/{name} 改了但 VENDOR.json 没更新："
                    f"补上 vendored_sha256，并把实质差异写进 note")

    def test_identical_files_are_recorded_as_identical(self):
        """标记为「逐字相同」的文件真的相同；这一条就是漂移的哨兵。"""
        for name, meta in sorted(self.files.items()):
            if "逐字相同" not in meta.get("note", ""):
                continue
            with self.subTest(file=name):
                self.assertEqual(_sha256(UPSTREAM / name), _sha256(VENDOR / name),
                                 f"{name} 登记为逐字相同，实际已经不同")

    def test_every_entry_explains_its_divergence(self):
        """note 不能空着：哈希能证明「变了」，只有 note 能说明「为什么」。"""
        for name, meta in sorted(self.files.items()):
            with self.subTest(file=name):
                self.assertTrue(meta.get("note", "").strip(),
                                f"VENDOR.json 里 {name} 缺 note")


if __name__ == "__main__":
    unittest.main()
