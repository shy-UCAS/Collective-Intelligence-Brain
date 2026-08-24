---
type: "diagnostic"
date: "2026-08-24T07:00:38.337099+00:00"
question: "为什么刚生成的轨迹样本中 clusterDto.intentLabel 和 intentName 都为 null，是否因为离设施和圈层太远？"
contributor: "graphify"
source_nodes: ["select_intent", "empty_intent", "evaluate_intent_candidates", "SituationEngine._intent_feature_frame", "DEFAULT_MAP_APPLIED"]
---

# Q: 为什么刚生成的轨迹样本中 clusterDto.intentLabel 和 intentName 都为 null，是否因为离设施和圈层太远？

## Answer

直接原因是 topCandidates 为空，select_intent 按协议返回 empty_intent。复跑特征：12 架均为 outer，距默认设施最近约7845m，确实挡住 I-13/I-14/I-15/I-24/I-30 等空间规则，但不是唯一原因。其他19项规则也均未满足：无计划白名单，AGL不可用，悬停/抖动/重复不足，14:14非夜间，无景点监所敏感区语义，I-26 的 approachFraction=0.333、航向离散122度、ETA离散128秒均不达标。样本给每个目标填了 remoteId，所以 I-29 身份不可辨也不成立。请求地图数组全空，网关应用2设施6圈层的内置默认地图；targetName只表示最近设施。eta=21来自直线匀速估计，部分轨迹因时间间隔导致数百m/s异常速度，不能说明目标很近。

## Source Nodes

- select_intent
- empty_intent
- evaluate_intent_candidates
- SituationEngine._intent_feature_frame
- DEFAULT_MAP_APPLIED