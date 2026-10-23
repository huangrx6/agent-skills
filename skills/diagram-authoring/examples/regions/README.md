# 分区底色与节点重点独立

> [← 返回样例索引](../README.md)

虚构接入、处理、数据三分区；实心浅底色区分区域，普通节点保持白底。
`project.colors.json` 中的 by_group 可以自由指定已有色名与混色比例，不新增固定色板。
source 是项目自制示例，不包含用户业务资料。

```sh
python3 scripts/emit_excalidraw.py examples/regions/source.diagram.json --colors examples/regions/project.colors.json --preset doc-wide --quality showcase -o examples/regions/diagram.excalidraw
python3 scripts/emit_drawio.py examples/regions/source.diagram.json --colors examples/regions/project.colors.json --scheme classic --preset doc-wide --quality showcase -o examples/regions/diagram.drawio
```

官方输出与检查回执见本目录；目检属于作者自检，不代表完整无障碍认证。
