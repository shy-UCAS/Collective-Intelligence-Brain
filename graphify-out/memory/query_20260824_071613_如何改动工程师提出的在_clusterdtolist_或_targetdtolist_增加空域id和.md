---
type: "design"
date: "2026-08-24T07:16:13.581534+00:00"
question: "如何改动工程师提出的在 clusterDtoList 或 targetDtoList 增加空域ID和禁飞区ID的需求？"
contributor: "graphify"
source_nodes: ["SituationEngine._ring_status", "AirspaceRelationAnalyzer._evaluate_target", "build_analysis_result"]
---

# Q: 如何改动工程师提出的在 clusterDtoList 或 targetDtoList 增加空域ID和禁飞区ID的需求？

## Answer

现状：clusterDtoList[].airspaceId 已存在，但 engine._ring_status 只保存第一个命中的法定禁飞区ID，是旧版兼容字段，不是圈层所属父防控空域ID；targetDtoList无空间字段。规范结果在根级 targetAirspaceResults[]：matchedRings[].airspaceId 是防控圈父空域ID，matchedNoFlyZones[].airspaceId 是禁飞区ID，二者均可能多值。建议不要增加含义不清的单值ID，而在 Cluster 增加 spatialSummary={status, defenseAirspaceIds[], noFlyZoneIds[]}，数组去重稳定排序；若业务还需成员归属，则在 targetDtoList[].spatialSummary 同样输出单机摘要并以其为权威，Cluster仅做成员并集。保留旧 airspaceId 原语义以兼容，不重命名或复用。实现上应先计算 AirspaceRelationAnalyzer 结果，再按 targetNo 建索引传入 event_mapper，构建 TargetDto摘要并聚合集群摘要；同步更新OpenAPI、接口文档、README、可视化字段解释和测试。available且无命中返回空数组；partial/unavailable加status，避免把空数组误解为确定不在区域。当前默认地图airspaces为空时无法产生禁飞区ID，新增字段不能凭空补值。

## Source Nodes

- SituationEngine._ring_status
- AirspaceRelationAnalyzer._evaluate_target
- build_analysis_result