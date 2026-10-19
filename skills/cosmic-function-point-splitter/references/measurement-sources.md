# 标准与参考来源

核对日期：2026-10-15。规则优先采用 COSMIC 官方手册；工具示例和研究仅供实现参考。
本 skill 的自动校验覆盖部分结构规则，不声称实现全部规范或获得认证。

| 来源 | 用途 |
| --- | --- |
| [COSMIC 官方计量流程](https://cosmic-sizing.org/cosmic-sizing/intro/measurement-process/) | 度量策略、映射、计量三个阶段；解释为何先确定边界和功能用户 |
| [COSMIC v5.0 手册合集，2024-09 文件](https://cosmic-sizing.org/wp-content/uploads/2022/11/Combination-of-Parts-v5.0-Sep-2024.pdf) | Part 1 规则 10—15：过程、数据组和移动；尤其核查唯一性与实例重复 |
| [COSMIC v5.0 第一部分中文手册，2020-05](https://cosmic-sizing.org/wp-content/uploads/2020/09/COSMIC%E5%BA%A6%E9%87%8F%E6%89%8B%E5%86%8CV5.0-part-1-%E5%8E%9F%E5%88%99%E3%80%81%E5%AE%9A%E4%B9%89%E4%B8%8E%E8%A7%84%E5%88%99.pdf) | 中文术语；第 3 章范围与边界、第 4 章映射。引用时注明版本，不按网页抓取日期判断版本 |
| [ScopeMaster 官方 API：Requirements](https://help.scopemaster.com/article/49-requirements) | 借鉴需求、兴趣对象、逐项数据移动与质量提示的可追溯结构；不是标准定额 |
| [COSMIC 官网介绍 CosMet 研究](https://cosmic-sizing.org/2026/04/30/31737/) | 采用独立专家基准与解释性评估；论文效果不能视作本 skill 的测试成绩 |
| GB/T 42452-2023《系统与软件工程 功能规模测量 COSMIC 方法》 | 国内送审常用依据；与手册 v4.0/v5.0 的术语对应，具体条款以标准原文为准 |

## 本地惯例不是标准

句式、列顺序、模块命名、增删改查排序、双行功能用户写法，都是**项目送审惯例**：
它们让表更好读、更接近评审习惯，但不改变功能规模，也不应反过来决定拆分。
本 skill 把这些放在 [命名与写法](naming-and-style.md) 与 [操作类型词表](operation-types.md)，
默认只提示；`--strict` 时才作为交付门槛。

明确不采纳的做法：按操作名固定 CFP、每行强制三个属性、F/G/H/J/K 全表唯一、
为达到目标行数补功能。它们会违反“不得编造”的红线，也与唯一性/实例重复规则冲突。

## 本地规则定位

- 识别过程与数据组：`splitting-rules.md`。
- 可追溯规格：`spec-format.md`。

不能从接口数量、物理表数量、字段数量或目标预算反向推出标准规模。
来源字符串存在只是可追溯入口；是否支持该拆分、重复移动例外是否成立，需要阅读原需求判断。
