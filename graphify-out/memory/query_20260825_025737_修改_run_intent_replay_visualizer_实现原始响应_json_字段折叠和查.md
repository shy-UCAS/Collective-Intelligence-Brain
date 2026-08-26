---
type: "query"
date: "2026-08-25T02:57:37.746690+00:00"
question: "修改 run_intent_replay_visualizer 实现原始响应 JSON 字段折叠和查询"
contributor: "graphify"
source_nodes: ["JsonTreeViewer", "JsonResponseViewer", "IntentReplayWindow", "intent_replay_visualizer.py"]
---

# Q: 修改 run_intent_replay_visualizer 实现原始响应 JSON 字段折叠和查询

## Answer

已在 intent_replay_visualizer.py 增加 JsonTreeViewer 与 JsonResponseViewer。原始响应页现在包含结构树和格式化文本双视图；树按需加载对象/数组节点，支持字段名、完整路径和值的模糊搜索、上一个/下一个跳转、自动展开祖先、一级/三级/全部展开和全部折叠，以及右键复制路径、值和节点JSON。超过6000节点时全部展开先确认。JsonResponseViewer 保留 setPlainText/toPlainText 兼容旧刷新流程，正常响应改由 set_json 注入。新增3项查看器测试，既有26项可视化器测试全部通过，py_compile和diff check通过；接口DTO、算法和bat启动方式未改。

## Source Nodes

- JsonTreeViewer
- JsonResponseViewer
- IntentReplayWindow
- intent_replay_visualizer.py