---
type: "query"
date: "2026-08-24T06:39:35.414299+00:00"
question: "Are clusterDto.getIntentLabel() and getIntentName() null when a trajectory is outside defense rings?"
contributor: "graphify"
source_nodes: ["build_analysis_result()", "select_intent()", "SituationEngine"]
---

# Q: Are clusterDto.getIntentLabel() and getIntentName() null when a trajectory is outside defense rings?

## Answer

Not necessarily. Outside rings only produces zoneTier outside. Intent rules still run. If another rule matches, intentLabel and intentName contain that intent label, for example I-12 gives 超高飞行. They are JSON null, and normally Java null, only when no enabled intent candidate matches. A verified outside/no-rule case returned both null, while an outside/high-altitude case returned 超高飞行 for both.

## Source Nodes

- build_analysis_result()
- select_intent()
- SituationEngine