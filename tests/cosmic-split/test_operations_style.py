"""操作词表、句式与命名提示：默认提议不改变计量，提示不阻塞。"""

# 测试通过 sys.path 挂载 skill 的 scripts 目录，静态分析器找不到这些同级模块。
# pyright: reportMissingImports=false

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / 'skills/cosmic-split/scripts'
sys.path.insert(0, str(SCRIPTS))

import builder  # noqa: E402
import checks  # noqa: E402
import cosmic  # noqa: E402
import operation_types as ops  # noqa: E402
import spec  # noqa: E402
import style  # noqa: E402


def fixture():
    return copy.deepcopy(cosmic.STARTER_SPEC)


def build(value, order="spec"):
    return builder.build(spec.load_from_dict(value), order=order)


class TestOperationTypes(unittest.TestCase):
    def test_按名称后缀识别操作类型(self):
        cases = {
            '订单列表查询': 'queryList',
            '订单详情查询': 'queryDetail',
            '订单新增': 'insert',
            '订单导出': 'export',
            '订单导入模板下载': 'export',
            '订单导入文件上传': 'import',
            '订单导入数据预览': 'queryList',
            '订单导入确认执行': 'insert',
            '调用量数据采集': 'collect',
            '调用量数据统计': 'stat',
            '调用量查看图表': 'chart',
            '审批通过': 'pass',
            '订单状态启用': 'enable',
            '无法判断的动作': None,
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(ops.infer(name), expected)

    def test_指标顺序采集在统计之前图表最后(self):
        self.assertLess(ops.order_key('collect'), ops.order_key('stat'))
        self.assertLess(ops.order_key('stat'), ops.order_key('chart'))
        self.assertLess(ops.order_key('queryList'), ops.order_key('collect'))
        self.assertLess(ops.order_key('insert'), ops.order_key('query'))

    def test_声明op偏离默认序列且无说明时提示(self):
        value = fixture()
        value['processes'][0].pop('op_note')
        hints = checks.hints(build(value).rows)
        self.assertTrue(any('op=insert 的默认序列' in hint for hint in hints), hints)

    def test_op_note说明依据后不再提示偏离(self):
        value = fixture()
        value['processes'][0]['op_note'] = '新增前查重属于同一触发'
        self.assertFalse(any('默认序列' in hint for hint in checks.hints(build(value).rows)))

    def test_声明op必须来自词表(self):
        value = fixture()
        value['processes'][0]['op'] = '不存在的类型'
        with self.assertRaises(spec.SpecError):
            build(value)

    def test_采集统计提示定时任务(self):
        value = fixture()
        process = value['processes'][0]
        process.update(op='collect', op_note='按批次采集')
        process['movements'] = process['movements'][:2]
        hints = checks.hints(build(value).rows)
        self.assertTrue(any('通常由定时任务触发' in hint for hint in hints), hints)
        process['user'] = '定时任务'
        value['measurement']['functional_users'].append('定时任务')
        self.assertFalse(any('通常由定时任务触发' in hint
                             for hint in checks.hints(build(value).rows)))


class TestStyle(unittest.TestCase):
    def test_按op推导默认描述(self):
        self.assertEqual(style.describe('E', '订单', 'queryList'), '输入订单查询请求')
        self.assertEqual(style.describe('R', '订单', 'queryList'), '读取订单信息')
        self.assertEqual(style.describe('W', '订单', 'insert'), '保存订单信息')
        self.assertEqual(style.describe('W', '订单', 'update'), '更新订单信息')
        self.assertEqual(style.describe('W', '订单', 'delete'), '删除订单信息')
        self.assertEqual(style.describe('X', '订单', 'export'), '返回订单导出结果')

    def test_省略描述时自动推导且不覆盖已有描述(self):
        value = fixture()
        first = value['processes'][0]['movements'][0]
        first['description'] = '人工写的触发说明'
        del value['processes'][0]['movements'][1]['description']
        rows = build(value).rows
        self.assertEqual(rows[0].desc, '人工写的触发说明')
        self.assertEqual(rows[1].desc, '读取地址信息')

    def test_旧模板句改写(self):
        cases = [
            ('接收订单保存请求并校验输入数据', 'E', '输入订单保存请求'),
            ('从数据存储读取订单数据', 'R', '读取订单数据'),
            ('将订单数据写入数据存储', 'W', '保存订单数据'),
            ('保存变更后的订单数据', 'W', '更新订单数据'),
            ('向用户返回订单结果', 'X', '返回订单结果'),
        ]
        for old, move, expected in cases:
            with self.subTest(old=old):
                self.assertEqual(style.rewrite_description(old, move), expected)

    def test_我的不会被删掉(self):
        self.assertEqual(style.rewrite_description('从数据存储读取我的待办数据', 'R'), '读取我的待办数据')

    def test_改写不由业务名推断删除或截断对象(self):
        for old, name, expected in (
            ('将退款申请数据写入数据存储', '退款申请新增', '保存退款申请数据'),
            ('将订单数据写入数据存储', '订单取消', '保存订单数据'),
            ('将元数据写入数据存储', '元数据修改', '保存元数据'),
            ('将目的地数据写入数据存储', '目的地新增', '保存目的地数据'),
        ):
            with self.subTest(old=old):
                self.assertEqual(style.rewrite_description(old, 'W', name), expected)

    def test_连续重复词被收敛(self):
        self.assertEqual(style.clean('查询查询请求'), '查询请求')
        self.assertEqual(style.clean('数据数据'), '数据')

    def test_行业缩写保留_普通英文标出(self):
        glossary = style.load_glossary()
        self.assertEqual(style.english_tokens('API Token KPI', glossary), [])
        self.assertEqual(style.english_tokens('Download状态', glossary), ['Download'])

    def test_英文替换不拆字段标识(self):
        glossary = style.load_glossary()
        text, changes = style.replace_english('用户ID与download状态，addressID保留', glossary)
        self.assertIn('用户编码', text)
        self.assertIn('下载状态', text)
        self.assertIn('addressID', text)
        self.assertEqual([source for source, _ in changes], ['download', 'ID'])

    def test_命名与描述提示(self):
        value = fixture()
        process = value['processes'][0]
        process['trigger'] = process['name']
        process['movements'][0]['description'] = '接收入口并校验输入数据'
        value['modules'][0]['l3'] = '地址列表'
        process['l3'] = '地址列表'
        hints = checks.hints(build(value).rows)
        self.assertTrue(any('触发事件与功能过程同名' in hint for hint in hints))
        self.assertTrue(any('操作后缀' in hint for hint in hints))
        self.assertEqual([hint for hint in hints if '并校验输入数据' in hint][:1],
                         ['子过程描述用了旧模板句「并校验输入数据」 地址新增/E'])

    def test_不同过程描述完全相同只提示不改写(self):
        value = fixture()
        second = copy.deepcopy(value['processes'][0])
        second.update(id='FP-002', name='地址修改', op='update')
        value['processes'].append(second)
        rows = build(value).rows
        before = [row.desc for row in rows]
        hints = checks.hints(rows)
        self.assertTrue(any('完全相同' in hint for hint in hints))
        self.assertEqual(before, [row.desc for row in rows])


if __name__ == "__main__":
    unittest.main()
