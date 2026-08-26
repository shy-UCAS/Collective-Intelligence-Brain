---
type: "implementation"
date: "2026-08-24T15:44:52.154996+00:00"
question: "SpatialContext与5公里空间门控改动后，回放可视化如何完整适配并防止旧服务或跨实例结果混用？"
contributor: "graphify"
---

# Q: SpatialContext与5公里空间门控改动后，回放可视化如何完整适配并防止旧服务或跨实例结果混用？

## Answer

已实现：POST JSON DTO保持不变；新增GET metadata与每个分析响应的实例/构建/规则/地图指纹HTTP头；UI规则版本硬校验、周期身份复查、逐响应身份核对、缓存原子失效及全帧重算；clusterDtoList逐集群为主视图，顶层字段仅作最高威胁集群兼容摘要；展示spatialSummary、hardRuleFloor与not_applicable等路径语义；地图默认关联区域，可切全图，按有效圈层绘制warning边界外扩airspaceAssessmentRangeMeters的虚线参考边界；导出保存规则、服务和地图追溯信息。验证：可视化/网络63/63，元数据/响应头4/4，受影响核心89/89；全量260/263，剩余3项均为既有71/76帧基线及tests包遮蔽问题。