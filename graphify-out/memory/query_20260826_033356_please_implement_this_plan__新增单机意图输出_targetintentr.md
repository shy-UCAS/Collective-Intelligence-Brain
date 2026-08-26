---
type: "query"
date: "2026-08-26T03:33:56.302983+00:00"
question: "PLEASE IMPLEMENT THIS PLAN: 新增单机意图输出 targetIntentResults[]"
contributor: "graphify"
source_nodes: ["SituationEngine", "Target"]
---

# Q: PLEASE IMPLEMENT THIS PLAN: 新增单机意图输出 targetIntentResults[]

## Answer

已实现 data.targetIntentResults[]：每个输入目标固定一条并按 targetId 排序，普通目标复用 targetThreats[targetId].intent；补齐豁免、人工排除、坏轨迹、非无人机和内部缺失状态。OpenAPI 升级为 3.2.1，新增可视化单机意图页签及帧/批次统计。核心接口63项、可视化28项通过；全量281项中278项通过，剩余为既有1项71/76帧基线失败和2项tests包遮蔽收集错误。

## Source Nodes

- SituationEngine
- Target