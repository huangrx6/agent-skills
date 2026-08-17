# 标准与权威参考

## 目录

- [格式与编辑器](#格式与编辑器)
- [许可证与文件头](#许可证与文件头)
- [版本](#版本)
- [代码评审](#代码评审)
- [使用原则](#使用原则)

## 格式与编辑器

- EditorConfig Specification  
  https://spec.editorconfig.org/

EditorConfig 用于在不同编辑器和 IDE 之间共享基础编码风格。具体语言格式仍应由语言格式化器负责。

## 许可证与文件头

- SPDX：Handling License Info  
  https://spdx.dev/learn/handling-license-info/

使用标准 `SPDX-License-Identifier` 表达文件许可证，避免自定义许可证缩写和大段重复文本。

## 版本

- Semantic Versioning 2.0.0  
  https://semver.org/

语义化版本适用于明确声明公共 API 的软件发布物。普通源文件不因此需要独立版本字段。

## 代码评审

- Google Engineering Practices：Code Review  
  https://google.github.io/eng-practices/review/

其评审维度包括设计、功能、复杂度、测试、命名、注释、样式和文档。使用时应结合本组织上下文，不把特定公司的流程术语视为通用强制要求。

## 语言官方风格指南

- Java：Google Java Style Guide https://google.github.io/styleguide/javaguide.html ；Checkstyle https://checkstyle.sourceforge.io/
- Python：PEP 8 https://peps.python.org/pep-0008/ ；Ruff https://docs.astral.sh/ruff/
- Go：Effective Go https://go.dev/doc/effective_go ；gofmt https://pkg.go.dev/cmd/gofmt
- JavaScript/TypeScript：ESLint https://eslint.org/ ；Prettier https://prettier.io/ ；typescript-eslint https://typescript-eslint.io/
- Rust：rustfmt https://rust-lang.github.io/rustfmt/ ；Clippy https://doc.rust-lang.org/clippy/
- C#：.NET 设计准则 https://learn.microsoft.com/dotnet/standard/design-guidelines/ ；Roslyn 分析器
- C/C++：clang-format https://clang.llvm.org/docs/ClangFormat.html ；clang-tidy https://clang.llvm.org/extra/clang-tidy/
- SQL：SQL Style Guide https://www.sqlstyle.guide/

## 使用原则

- 优先引用规范发布方和语言官方文档。
- 在输出中区分“标准要求”“生态惯例”和“团队决策”。
- 工具版本和语言规则可能变化；实施附录应跟随项目支持版本维护。
- 不把单一公司的样式指南描述为所有项目必须遵守的官方标准。
