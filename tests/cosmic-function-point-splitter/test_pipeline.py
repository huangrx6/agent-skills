"""显式规格的装配、边界与输入校验。"""
import copy
import os
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / 'skills/cosmic-function-point-splitter/scripts'
sys.path.insert(0, str(SCRIPTS))
import builder
import checks
import cosmic
import spec

FIXTURE = copy.deepcopy(cosmic.STARTER_SPEC)
FIXTURE['measurement']['functional_users'].append('管理员')
FIXTURE['modules'].append({'l2': '维护服务', 'l3': '维护管理'})
second = copy.deepcopy(FIXTURE['processes'][0])
second.update(id='FP-002', name='地址修改', l3='维护管理', user='管理员')
FIXTURE['processes'].append(second)


def build(value=None):
    return builder.build(spec.load_from_dict(value or FIXTURE))


class TestPipeline(unittest.TestCase):
    def test_模块与过程数量(self):
        result = build()
        self.assertEqual(result.process_count, 2)
        self.assertEqual(result.total_cfp, 8)
        self.assertEqual(checks.check(result.rows), [])

    def test_保留声明顺序和描述(self):
        result = build()
        heads = [r for r in result.rows if r.is_process_head]
        self.assertEqual([r.process_id for r in heads], ['FP-001', 'FP-002'])
        self.assertEqual(result.rows[0].desc, FIXTURE['processes'][0]['movements'][0]['description'])

    def test_过程单移动不被接受(self):
        value = copy.deepcopy(FIXTURE)
        value['processes'][0]['movements'] = value['processes'][0]['movements'][:1]
        with self.assertRaises(spec.SpecError):
            build(value)

    def test_重复过程编号被拒绝(self):
        value = copy.deepcopy(FIXTURE)
        value['processes'][1]['id'] = value['processes'][0]['id']
        with self.assertRaises(spec.SpecError):
            build(value)

    def test_引用不存在模块被拒绝(self):
        value = copy.deepcopy(FIXTURE)
        value['processes'][0]['l3'] = '未声明模块'
        with self.assertRaises(spec.SpecError):
            build(value)

    def test_缺少范围被拒绝(self):
        value = copy.deepcopy(FIXTURE)
        del value['measurement']['boundary']
        with self.assertRaises(spec.SpecError):
            build(value)

    def test_没有输出或写入不能通过(self):
        value = copy.deepcopy(FIXTURE)
        value['processes'][0]['movements'] = value['processes'][0]['movements'][:2]
        self.assertTrue(any('缺少 W 或 X' in x for x in checks.check(build(value).rows)))

    def test_同一过程区间不连续会报错(self):
        rows = build().rows
        scrambled = rows[:2] + rows[4:] + rows[2:4]
        self.assertTrue(any('区间不连续' in x for x in checks.check(scrambled)))
