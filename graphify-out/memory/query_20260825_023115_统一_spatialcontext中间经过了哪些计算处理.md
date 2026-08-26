---
type: "query"
date: "2026-08-25T02:31:15.361781+00:00"
question: "统一 SpatialContext中间经过了哪些计算处理"
contributor: "graphify"
source_nodes: ["SpatialContext", "AirspaceRelationAnalyzer", "SituationEngine", "DefenseAnalyzer"]
---

# Q: 统一 SpatialContext中间经过了哪些计算处理

## Answer

SpatialContext由targetAirspaceResults同一次逐目标几何评估伴生：先过滤有效圈层和禁飞区并规范化圆形/多边形与高度范围；再对每个目标计算AGL/AMSL高度匹配、当前点内外/边界、边界距离、最近边界点；用轨迹窗口回归边界距离趋势，推导进入退出、接近远离、预计穿越时间和置信度；命中任意有效区域始终相关，未命中只允许所属空域最外warning边界5km内成为候选，高度不可换算则unavailable；候选按命中优先、严重度或边界距离及ID稳定排序生成主SpatialContext；集群再从成员上下文确定主上下文，同一主空域成员才可驱动设施距离、空间意图硬规则、威胁下限、ETA、路由和防御评估。公共DTO不序列化SpatialContext。

## Source Nodes

- SpatialContext
- AirspaceRelationAnalyzer
- SituationEngine
- DefenseAnalyzer