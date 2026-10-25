# Vendored read-only PingCode code

`config.py`、`client.py`、`compat.py` 和 `auth.py` 是内置的只读配置、HTTP 传输、
兼容处理和认证代码，来源是同一仓库的 `skills/pingcode/scripts/`。

本目录只被 `pingcode-weekly` 用来读取 PingCode：

- 只使用项目、类型、状态、迭代、工作项和历史的读取操作。
- 不使用写工作项、评论、附件、工时等命令。
- 修改时只处理只读传输、分页、限流和认证修复，不引入写操作。

## 为什么单独拷一份

`pingcode-weekly` 要能单独安装：只装周报也要能认证和读数据，不能反过来依赖
`pingcode` 这个 skill 在场。代价是两份代码会各自演化，所以来源记在 `VENDOR.json` 里。

## 改这里的流程

1. 先看上游 `skills/pingcode/scripts/` 对应文件是否也改了。是的话，先决定要不要
   把改动同步过去（这类修复通常两边都要），而不是只改这一份。
2. 改完运行 `python3 -m unittest discover -s tests/pingcode-weekly -p "test_vendor_sync.py"`。
   它按 `VENDOR.json` 里的哈希对账：
   - 上游变了 → 提示重新评估同步；
   - 这一份没登记就变了 → 提示更新哈希和 note，避免"悄悄改过"。
3. 确认后把两个哈希和一句 note 写回 `VENDOR.json`。哈希是**派生值**，不要手抄。

`note` 要写清与上游的实质差异。当前已知差异：

- `auth.py`：只保留只读认证，没有 OAuth 回调服务器和交互式授权。
- `client.py`：行为一致（http/https 白名单两边都有）；差异只在 boundary 前缀与少量写法。
- `config.py`：只改常量名，行为一致。
- `compat.py`：与上游逐字相同。
