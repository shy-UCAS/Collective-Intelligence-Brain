---
type: "query"
date: "2026-08-26T05:42:36.630969+00:00"
question: "targetIntentResults针对豁免目标计算的意图有哪些"
contributor: "graphify"
source_nodes: ["SituationEngine", "evaluate_intent_candidates", "IntentCandidate"]
---

# Q: targetIntentResults针对豁免目标计算的意图有哪些

## Answer

当前豁免目标不运行普通目标完整19项意图库，只从enabledIntentCodes与I-01/I-02/I-03/I-05的交集评估合规候选：I-01有效巡检飞行计划，taskPurpose=0且planMatchScore>=0.85；I-02有效航拍/物流/测绘计划，taskPurpose为1/2/3且planMatchScore>=0.85；I-03有效白名单purpose=7或operationType=system_test；I-05有效白名单operationType为equipment_debug/maintenance，同时hoverSeconds>=30且trackSpanMeters<=50。DRILL_PLAN目前不产生I-04，因为I-04未启用；无特殊违规时返回no_match/DRILL_PLAN。普通白名单或飞行计划证据不足也返回no_match及对应reasonCode，reviewRequired=false。另有正交特殊违规NO_FLY_INTRUSION始终评估，豁免目标实际命中法定禁飞区时可能intentCode=null、specialViolationCode=NO_FLY_INTRUSION并status=matched。

## Source Nodes

- SituationEngine
- evaluate_intent_candidates
- IntentCandidate