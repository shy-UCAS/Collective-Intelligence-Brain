---
type: "query"
date: "2026-08-26T04:02:57.609418+00:00"
question: "在请求级 options 中增加 returnTargetIntentCandidates，省略时默认 true，false 时仅隐藏 targetIntentResults[].topCandidates，同时 candidateCount 常驻；需要改哪些代码、OpenAPI、文档、脚本和可视化？"
contributor: "graphify"
source_nodes: ["SituationEngine", "select_intent"]
---

# Q: 在请求级 options 中增加 returnTargetIntentCandidates，省略时默认 true，false 时仅隐藏 targetIntentResults[].topCandidates，同时 candidateCount 常驻；需要改哪些代码、OpenAPI、文档、脚本和可视化？

## Answer

已实现请求级 returnTargetIntentCandidates：省略或 true 时返回每目标完整合格 topCandidates，显式 false 时仅省略该字段；candidateCount 始终存在，未评估或不可用为 null。公开结果直接复用 targetThreats 内部候选，不重新运行意图规则，不改变主意图、排序、集群意图或威胁。OpenAPI 升级到 3.2.2，并同步请求脚本、文档、可视化及专项测试。

## Source Nodes

- SituationEngine
- select_intent