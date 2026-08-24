---
type: "explanation"
date: "2026-08-24T11:39:08.948230+00:00"
question: "多个相邻空域重叠命中时当前如何返回、统一SpatialContext是否只选最高圈、5000米范围含义及能否保持输出结构"
contributor: "graphify"
source_nodes: ["AirspaceRelationAnalyzer", "_evaluate_target", "_ring_status", "build_analysis_result", "_spatial_summary", "_intent_feature_frame", "_threat"]
---

# Q: 多个相邻空域重叠命中时当前如何返回、统一SpatialContext是否只选最高圈、5000米范围含义及能否保持输出结构

## Answer

当前targetAirspaceResults按目标逐圈判断，matchedRings保留全部命中圈层，不因低等级被覆盖；代码按ringLevel升序再ringId排序，即低到高。highestRingLevel取最大值，highestRingTier给出单个最高等级，primaryRingIds包含所有达到最高等级的ringId，同级重叠不得丢弃。movementRelations则按areaKind、等级降序、边界距离升序、areaId排序。集群兼容字段ringStatus/zoneTier只保留所有成员和圈层中的最高严重级别；当前engine._ring_status未在普通ring命中时同步matched_airspace_id，cluster.airspaceId可能为空，详细归属应以targetAirspaceResults或spatialSummary为准。建议统一SpatialContext后仍保留全部matchedRings作为事实集合，只为标量威胁计算选择primary context：最高等级优先；同级时按更深命中或边界距离、再airspaceId稳定选一个，但同级全部保留在primaryRingIds。5000米airspaceAssessmentRangeMeters当前仅控制目标位于区域外时是否输出该区域的movementRelations，距离是到区域边界，不是到设施/圆心；命中区域无视该阈值，且它目前不约束意图、威胁、全局最近设施。建议改造后把它作为空间相关性门槛：圈内永远相关；圈外但距预警边界不超过5km可进行接近预测和空间型意图威胁；超过5km仅关闭空间型规则，行为、身份、载荷等非空间威胁仍计算。统一SpatialContext可完全作为内部重构，不增删公共字段：提前计算现有targetAirspaceResults并建立内部targetId到context映射，传给集群、意图和威胁，现有event_mapper继续输出原结构。字段结构不变但错误值会被纠正，例如远距离affectedFacilities/airspaceId为空。

## Source Nodes

- AirspaceRelationAnalyzer
- _evaluate_target
- _ring_status
- build_analysis_result
- _spatial_summary
- _intent_feature_frame
- _threat