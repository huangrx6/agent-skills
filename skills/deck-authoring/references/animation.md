# 逐页动画与视频

`animate.py` 将 HTML deck 按既有时间轴捕获为 MP4 或 GIF。
它适合自动播放的逐页演示，不提供多镜头剪辑、配乐、字幕轨、3D 或 shader 效果库。

## 实际运行方式

| 场景 | 时钟与画面 |
| --- | --- |
| 默认滚动 HTML | 静态满态，供阅读、测量与 PDF |
| `?present` / P 键 | 实时时钟，当前页入场 |
| 动画取帧 | `window.__deck.seek(t)`，按确定时间点画同一套入场 |
| PNG 截图 | 取各页入场完成后的静帧 |

内部 paint 按语义角色编排：标题遮罩揭示并落定、条目小位移淡入、
图片横向揭示、分隔线延伸、图表容器淡入、页脚淡入。
当前 G2 图表内部动画关闭，**没有柱生长或折线逐段描画**；
不能因为运行时代码保留了图形动画钩子就宣称 G2 数据标记也会运动。

没有单独的 motion_intent、energy、Effect Registry、motion creativity 或自动效果评分字段。
本次方向通过 style.motion 控制速度与节奏，而非为每页发明未实现参数。

## Motion tokens

`style.json` 的 motion 对象需要以下七项：

| 键 | 含义 |
| --- | --- |
| `easing` | `expoOut` 或 `overshoot` |
| `cssEase` | CSS 缓动字符串 |
| `enterMs` | 单元素入场时间 |
| `staggerMs` | 相邻正文元素延迟 |
| `titleHoldMs` | 标题领先正文的停顿 |
| `holdMs` | 每页基础阅读时间 |
| `readPerItemMs` | 按条目/节点等数量增加的阅读时间 |

时间单位为毫秒。选择节奏时以内容能否读完为准：技术评审宜克制，
强调回弹仅在内容和风格适合时使用。同一套时间参数并不保证每页都好读，需抽帧与播放检查。
时间轴根据内容量追加阅读停顿，当前每页 hold 有上限；密集页不能靠无限停留补救，宜拆页或收短。

## 导出

依赖见 [README](../README.md)：Chrome + websockets；MP4 另需 macOS 的 swiftc/AVFoundation，
GIF 使用 Pillow。依赖不具备时报告缺项，不声称已导出或自动换成另一种格式。

```sh
python3 scripts/animate.py deck.html -o deck.mp4
python3 scripts/animate.py deck.html -o deck.gif --width 960
python3 scripts/animate.py deck.html -o deck.mp4 --width 1920 --fps 24 --keep-frames
```

MP4 默认宽 1920、24fps，GIF 默认宽 960，按 16:9 输出。
`--scale` 控制浏览器取帧密度，默认按输出宽度决定；需要超采样可显式给 2。
`--keep-frames` 保留 PNG 序列，便于复查或外部编码。

只检查关键时间点时使用 `--stills`（逗号分隔秒数）；时间从 HTML 的
`window.__deck_timeline` 取得，覆盖页初、入场完成、切页前后与结尾。
`--slow` 是排查 CDP 的慢路径，每帧启动浏览器，不作为日常模式。

## 验收

捕获等待字体、图片解码、图表 ready。资源失败或 pending 不能当成完整视频；
切页后的图表实际绘图区也要保持尺寸，不能只检查容器或 canvas 存在。

先抽帧再编码长视频，确认开头不是上一页残影、正文完整落定、图表/图例未挤窄，
末页停留可读。完成后回读帧数、时长与尺寸，再实际播放检查切页和阅读节奏。
静态页面通过 check 并不能证明运动阶段没有遮挡或裁切。
