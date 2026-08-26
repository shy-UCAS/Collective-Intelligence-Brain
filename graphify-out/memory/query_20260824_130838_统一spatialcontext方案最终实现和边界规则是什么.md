---
type: "implementation"
date: "2026-08-24T13:08:38.038844+00:00"
question: "统一SpatialContext方案最终实现和边界规则是什么？"
contributor: "graphify"
---

# Q: 统一SpatialContext方案最终实现和边界规则是什么？

## Answer

规则situation-rule-v2.3.0已实现且公共v3.2 DTO字段、层级、类型和可空性不变。单机空间几何一次计算并生成内部SpatialContext；未命中时按所属空域warning边界5000米判相关，旧地图无warning时兼容最低等级圈；水平可能命中或接近但高度不可换算时内部scope=unavailable并强制复核。主空域、锚点设施、距离和ETA原子绑定；混合集群仅主上下文成员触发空间硬规则，其他上下文触发的空间型意图使用中性意图分18。irrelevant时设施和ETA为空、hardRuleFloor=0、威胁分封顶mediumThreatThreshold-1、本地探测与拦截not_applicable。动态地图每个data.list[i]以facilityList[0]为三级半径圆心，重复空域ID或冲突设施ID使刷新回退。核心89/89通过；全量233/236，三项为既有回放基线和tests包遮蔽问题。