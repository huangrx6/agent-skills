# Vendored read-only PingCode code

`config.py`、`client.py`、`compat.py` 和 `auth.py` 是内置的只读配置、HTTP 传输、
兼容处理和认证代码。

本目录只被 `pingcode-weekly` 用来读取 PingCode：

- 只使用项目、类型、状态、迭代、工作项和历史的读取操作。
- 不使用写工作项、评论、附件、工时等命令。
- 修改时只处理只读传输、分页、限流和认证修复，不引入写操作。
