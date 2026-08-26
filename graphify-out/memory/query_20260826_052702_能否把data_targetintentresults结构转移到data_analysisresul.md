---
type: "query"
date: "2026-08-26T05:27:02.052137+00:00"
question: "能否把data.targetIntentResults结构转移到data.analysisResult.clusterDtoList[].targetDtoList[]，如何匹配"
contributor: "graphify"
source_nodes: ["SituationEngine", "build_analysis_result"]
---

# Q: 能否把data.targetIntentResults结构转移到data.analysisResult.clusterDtoList[].targetDtoList[]，如何匹配

## Answer

可以对进入集群的目标按稳定targetId一对一匹配，clusterId只做同响应内一致性校验，不能按数组下标。当前targetDtoList由cluster.targetIds和targetThreats构建，targetIntentResults则遍历全部输入targetId并额外覆盖skipped、MANUALLY_EXCLUDED、豁免和NON_UAV等状态。因此完全移除顶层数组会丢失不进入聚类的白名单/计划豁免、人工排除和坏轨迹目标；合法NON_UAV当前仍有单成员B3集群，可匹配。推荐保留顶层targetIntentResults作为全量权威索引，并在targetDtoList[]增加单数intentResult快捷视图；先构建最终targetIntentResults，再按targetId Map注入，复用结果不重算意图，并校验clusterId。若必须彻底迁移，需要为未聚类目标另设容器，属于破坏性契约变更。returnTargetIntentCandidates应同时控制嵌套topCandidates。

## Source Nodes

- SituationEngine
- build_analysis_result