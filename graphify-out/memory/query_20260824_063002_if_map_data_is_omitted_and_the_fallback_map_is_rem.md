---
type: "query"
date: "2026-08-24T06:30:02.168414+00:00"
question: "If map data is omitted and the fallback map is removed, where does intent analysis fail, and do targets outside airspace receive no intent?"
contributor: "graphify"
source_nodes: ["get_default_map()", "normalize_v32_request()", "SituationEngine", "select_intent()"]
---

# Q: If map data is omitted and the fallback map is removed, where does intent analysis fail, and do targets outside airspace receive no intent?

## Answer

On the public v3.2 route, omitted or all-empty map fields trigger get_default_map in normalize_v32_request. If no runtime or bundled map exists this fails before SituationEngine and becomes HTTP 500 INTERNAL_ERROR; startup also fails if refresh fails and fallback loading fails. A target confirmed outside existing rings gets ringStatus outer but still evaluates all enabled intent rules. Only ring/no-fly and other map-dependent rules are suppressed; identity, altitude, trajectory, time, plan and whitelist rules may still emit intent. Missing map means spatial status is unavailable, not confirmed outside.

## Source Nodes

- get_default_map()
- normalize_v32_request()
- SituationEngine
- select_intent()