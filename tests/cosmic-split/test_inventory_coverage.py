"""接口/页面清单与规格的双向覆盖：不猜关系，只报差异。"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parents[1] / 'skills/cosmic-split/scripts'
sys.path.insert(0, str(SCRIPTS))

import cosmic  # noqa: E402
import inventory as inventory_module  # noqa: E402
import spec  # noqa: E402

# 静态分析器看不到 sys.path 挂载的同级模块。
# pyright: reportMissingImports=false


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = cosmic.main(list(argv))
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
    return code, out.getvalue(), err.getvalue()


def payload():
    return {
        "version": 1,
        "source": "OpenAPI + 前端路由",
        "pages": [
            {"id": "p1", "name": "订单列表", "endpoints": ["api-1"]},
            {"id": "p2", "name": "订单详情", "endpoints": ["api-2"]},
            {"id": "p3", "name": "空占位", "endpoints": []},
        ],
        "endpoints": [
            {"id": "api-1", "method": "GET", "path": "/api/orders", "summary": "订单列表查询"},
            {"id": "api-2", "method": "GET", "path": "/api/orders/{id}", "summary": "订单详情查询"},
            {"id": "api-3", "method": "PATCH", "path": "/api/orders/{id}", "summary": "订单状态修改"},
        ],
    }


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="cosmic-inventory-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.spec_path = self._write("spec.json", cosmic.STARTER_SPEC)
        self.inventory_path = self._write("inventory.json", payload())

    def _write(self, name, value):
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf8") as handle:
            json.dump(value, handle, ensure_ascii=False)
        return path

    def test_未覆盖与悬空证据分别报告(self):
        spec_value = spec.load(self.spec_path)
        spec_value['processes'][0]['evidence'] = ['api-1', 'api-不存在']
        result = inventory_module.coverage(spec_value, inventory_module.load(self.inventory_path))
        self.assertEqual(result.claimed, 1)
        self.assertEqual([item['id'] for item in result.uncovered], ['api-2', 'api-3'])
        self.assertEqual(result.dangling, ['api-不存在'])
        self.assertFalse(result.ok)
        text = inventory_module.render(result)
        self.assertIn('未覆盖接口', text)
        self.assertIn('悬空证据', text)

    def test_接口侧声明过程也算覆盖(self):
        value = payload()
        value['endpoints'][0]['process'] = 'FP-001'
        inventory_path = self._write("inventory-claim.json", value)
        result = inventory_module.coverage(spec.load(self.spec_path), inventory_module.load(inventory_path))
        self.assertEqual(result.claimed, 1)

    def test_不存在的过程不能冒充已覆盖(self):
        value = payload()
        for item in value['endpoints']:
            item['process'] = 'FP-不存在'
        path = self._write('orphan.json', value)
        result = inventory_module.coverage(spec.load(self.spec_path), inventory_module.load(path))
        self.assertEqual(result.claimed, 0)
        self.assertFalse(result.ok)
        self.assertEqual(len(result.ownership_issues), 3)
        rendered = inventory_module.render(result)
        self.assertIn('不存在的过程', rendered)
        self.assertIn('有接口但均未被过程认领的页面', rendered)
        self.assertEqual(run('coverage', self.spec_path, path)[0], 1)

    def test_输出报告不能覆盖清单和规格及其链接(self):
        for source in (self.spec_path, self.inventory_path):
            original = Path(source).read_bytes()
            alias = Path(self.dir) / 'alias.json'
            alias.symlink_to(source)
            for output in (source, str(alias)):
                self.assertEqual(run('coverage', self.spec_path, self.inventory_path, '-o', output)[0], 1)
                self.assertEqual(Path(source).read_bytes(), original)
            alias.unlink()

    def test_build和report保护新增辅助输入(self):
        glossary = self._write('glossary.json', {'map': {}})
        original = {path: Path(path).read_bytes() for path in (glossary, self.inventory_path)}
        for protected in original:
            for command in ('build', 'report'):
                with self.subTest(command=command, path=protected):
                    self.assertEqual(run(command, self.spec_path, '-o', protected,
                                         '--inventory', self.inventory_path, '--glossary', glossary)[0], 1)
                    self.assertEqual(Path(protected).read_bytes(), original[protected])

    def test_两侧声明不同过程时不自动选一个(self):
        value = payload()
        value['endpoints'][0]['process'] = 'FP-999'
        inventory_path = self._write("conflict.json", value)
        spec_value = spec.load(self.spec_path)
        spec_value['processes'][0]['evidence'] = ['api-1']
        result = inventory_module.coverage(spec_value, inventory_module.load(inventory_path))
        self.assertEqual(result.claimed, 0)
        self.assertEqual([item['id'] for item in result.uncovered], ['api-1', 'api-2', 'api-3'])

    def test_空页面与低于九成时提示素材可能不完整(self):
        value = payload()
        value['pages'].append({"id": "p4", "name": "另一个空页面", "endpoints": []})
        inventory_path = self._write("empty.json", value)
        result = inventory_module.coverage(spec.load(self.spec_path), inventory_module.load(inventory_path))
        self.assertEqual([page['id'] for page in result.empty_pages], ['p3', 'p4'])
        self.assertLess(result.page_ratio, 0.9)
        self.assertIn('素材可能不完整', inventory_module.render(result))

    def test_未覆盖接口给出可能对应的过程但不自动认领(self):
        spec_value = spec.load(self.spec_path)
        spec_value['processes'][0]['name'] = '订单详情查询'
        spec_value['processes'][0]['evidence'] = ['api-1']
        result = inventory_module.coverage(spec_value, inventory_module.load(self.inventory_path))
        self.assertIn(('api-2', 'FP-001'), result.suggestions)
        self.assertIn('可能对应 FP-001', inventory_module.render(result))

    def test_清单结构错误直接拒绝(self):
        bad = self._write("bad.json", {"version": 1, "endpoints": []})
        with self.assertRaises(SystemExit):
            inventory_module.load(bad)
        bad = self._write("bad2.json", {
            "version": 1,
            "endpoints": [{"id": "a", "path": "/a"}],
            "pages": [{"id": "p", "endpoints": ["不存在"]}],
        })
        with self.assertRaises(SystemExit):
            inventory_module.load(bad)

    def test_coverage命令按缺口返回非零(self):
        code, out, _err = run("coverage", self.spec_path, self.inventory_path)
        self.assertEqual(code, 1)
        self.assertIn("接口覆盖 0/3", out)

        value = payload()
        for item in value['endpoints']:
            item['process'] = 'FP-001'
        complete = self._write("complete.json", value)
        code, out, _err = run("coverage", self.spec_path, complete)
        self.assertEqual(code, 0, out)
        self.assertIn("接口覆盖 3/3", out)

    def test_coverage_json与写文件(self):
        output = os.path.join(self.dir, "coverage.json")
        code, out, _err = run("coverage", self.spec_path, self.inventory_path, "--json", "-o", output)
        self.assertEqual(code, 1)
        self.assertIn("已写出覆盖报告", out)
        data = json.loads(Path(output).read_text(encoding="utf8"))
        self.assertEqual(data['endpoints'], 3)
        self.assertEqual(len(data['uncovered']), 3)

    def test_build的自检报告带覆盖章节(self):
        output = os.path.join(self.dir, "out.xlsx")
        code, _out, _err = run("build", self.spec_path, "-o", output, "--inventory", self.inventory_path)
        self.assertEqual(code, 0)
        report = Path(output + ".selfcheck.md").read_text(encoding="utf8")
        self.assertIn("## 接口与页面覆盖", report)
        self.assertIn("未覆盖接口", report)

    def test_strict把覆盖缺口当失败且不写表(self):
        output = os.path.join(self.dir, "strict.xlsx")
        code, _out, err = run("build", self.spec_path, "-o", output, "--inventory",
                              self.inventory_path, "--strict")
        self.assertEqual(code, 1)
        self.assertFalse(os.path.exists(output))
        self.assertIn("未写出文件", err)


if __name__ == "__main__":
    unittest.main()
