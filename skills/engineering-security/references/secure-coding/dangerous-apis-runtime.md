# 危险 API 与运行时边界

## 目录

- [禁止默认使用](#禁止默认使用)
- [Process](#process)
- [临时文件](#临时文件)
- [Reflection / Dynamic Loading](#reflection-dynamic-loading)
- [Native / Unsafe](#native-unsafe)
- [Random](#random)
- [Integer / Size](#integer-size)
- [Parser Configuration](#parser-configuration)

## 禁止默认使用

高风险：

```text
eval
exec dynamic code
new Function
runtime expression engines
unsafe deserialization
shell=true
sh -c / cmd.exe /c with variable input
disable TLS verification
trust-all certificate manager
global CORS allow all with credentials
temporary auth bypass
```

使用需要安全评审。

## Process

调用进程：

- executable 固定；
- args 使用数组；
- 不通过 shell；
- 最小环境变量；
- cwd 固定；
- timeout；
- stdout/stderr 大小限制；
- exit status 明确。

## 临时文件

- 使用安全随机文件名；
- 原子创建；
- 最小权限；
- 不在 world-writable 目录使用可预测名称；
- 清理；
- 避免 TOCTOU；
- symbolic link 风险。

## Reflection / Dynamic Loading

不要让用户控制：

- class name；
- module name；
- assembly；
- plugin path。

使用 allowlist registry。

插件需要：

- 签名/来源；
- 权限边界；
- API compatibility；
- isolation。

## Native / Unsafe

FFI、unsafe memory、raw pointer、native library：

- 最小封装；
- 明确长度；
- ownership；
- lifetime；
- integer overflow；
- encoding；
- fuzz test。

## Random

安全 token/key 使用 CSPRNG。

普通业务抽样/测试随机可以使用普通 PRNG。

不要用时间戳、自增 ID、Math.random 生成安全 token。

## Integer / Size

处理：

- file size；
- allocation；
- offsets；
- money；
- length

防止：

- overflow；
- underflow；
- truncation；
- signed/unsigned conversion。

## Parser Configuration

YAML、XML、template、markdown、image 等 parser 使用安全模式。

例如 YAML 禁止任意对象构造，除非输入可信。
