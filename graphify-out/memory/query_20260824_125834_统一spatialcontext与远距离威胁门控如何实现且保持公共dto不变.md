---
type: "implementation"
date: "2026-08-24T12:58:34.048146+00:00"
question: "统一SpatialContext与远距离威胁门控如何实现且保持公共DTO不变？"
contributor: "graphify"
---

# Q: 统一SpatialContext与远距离威胁门控如何实现且保持公共DTO不变？

## Answer

公共v3.2 DTO字段、层级、类型和可空性不变。单机空间几何只计算一次并生成内部SpatialContext；未命中时只按所属空域warning边界5000米判相关；主空域、锚点设施、距离和ETA原子绑定；混合集群只允许主上下文成员触发空间硬规则；空间不相关时设施和ETA为空、hardRuleFloor为0、威胁分封顶mediumThreatThreshold-1、本地探测与拦截均not_applicable；动态地图始终以每个data.list[i].facilityList[0]为三级半径圆心。规则版本situation-rule-v2.3.0。