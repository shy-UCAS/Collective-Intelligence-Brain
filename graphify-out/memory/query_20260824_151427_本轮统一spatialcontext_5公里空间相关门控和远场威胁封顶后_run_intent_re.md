---
type: "analysis"
date: "2026-08-24T15:14:27.817366+00:00"
question: "本轮统一SpatialContext、5公里空间相关门控和远场威胁封顶后，run_intent_replay_visualizer可视化应如何适配？"
contributor: "graphify"
---

# Q: 本轮统一SpatialContext、5公里空间相关门控和远场威胁封顶后，run_intent_replay_visualizer可视化应如何适配？

## Answer

公共DTO未变，BAT与解析链无需兼容修改。P0应校验并显著显示ruleVersion/build，防止31607复用旧服务；后端重连或版本变化时清空按帧缓存并支持重新分析全部帧。P1应弱化最高威胁集群兼容摘要，改以clusterDtoList为主；把spatialSummary提升到空间分组，采用路径感知字段释义；区分targetAirspaceResults数据完整度与内部空间作用域，正确显示partial/unavailable/not_applicable；在集群摘要并列展示threatScore与hardRuleFloor；把主父空域、全量命中空域和禁飞区分开展示。地图应提供当前目标或关联区域视图与全地图视图，避免远隔复合空域导致全量autoscale压缩主体，可选叠加warning边界外5km参考带。当前DTO不能无损展示每个目标的内部scope、远场封顶前分数或主上下文成员，前端不得自行猜测。