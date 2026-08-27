# developer-readme-design

A Pi / Agent Skills-compatible skill for designing and rewriting GitHub READMEs in a restrained, production-grade developer-tooling style.

## Install for Pi

Unzip or copy this directory to one of Pi's skill locations, for example:

```bash
mkdir -p ~/.pi/agent/skills
cp -R developer-readme-design ~/.pi/agent/skills/
```

Pi will discover the `SKILL.md` automatically. You can let the agent invoke it when relevant or explicitly run:

```text
/skill:developer-readme-design
```

Typical prompts:

```text
/skill:developer-readme-design 重构这个仓库的 README，直接修改文件。
```

```text
/skill:developer-readme-design 只评审这个 README 的视觉和信息架构，不改文件。
```

## Contents

```text
developer-readme-design/
├── SKILL.md
├── README.md
├── references/
│   ├── style-guide.md
│   └── quality-checklist.md
└── assets/
    └── project-brief-template.md
```
