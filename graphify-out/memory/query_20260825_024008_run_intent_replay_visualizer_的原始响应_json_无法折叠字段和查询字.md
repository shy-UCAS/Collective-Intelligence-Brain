---
type: "query"
date: "2026-08-25T02:40:08.292953+00:00"
question: "run_intent_replay_visualizer 的原始响应 JSON 无法折叠字段和查询字段，有办法实现吗"
contributor: "graphify"
source_nodes: ["IntentReplayWindow", "_build_analysis_panel", "_display_record", "intent_replay_visualizer.py"]
---

# Q: run_intent_replay_visualizer 的原始响应 JSON 无法折叠字段和查询字段，有办法实现吗

## Answer

可以。当前 intent_replay_visualizer.py 在原始响应页使用只读 QPlainTextEdit，并通过 json.dumps 整体写入，因此只能滚动纯文本。建议在同一页签内增加无第三方依赖的 JsonTreeViewer：用 QTreeWidget 按 dict/list 生成可折叠节点，顶部提供路径/字段名/值搜索、上一个下一个、展开指定层级、全部折叠、复制路径和值；保留原纯文本作为二级页签。针对大响应使用惰性展开，并建立轻量 path/key/value 搜索索引，搜索命中后自动展开祖先节点并定位高亮。无需修改算法接口、响应 DTO、批处理启动方式或 Python 依赖。

## Source Nodes

- IntentReplayWindow
- _build_analysis_panel
- _display_record
- intent_replay_visualizer.py