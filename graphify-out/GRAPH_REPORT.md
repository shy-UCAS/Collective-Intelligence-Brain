# Graph Report - F:\CASIA\Drone Swarm Situational Awareness Algorithm\Collective Intelligence Brain\situationawareness latest\situation_judgment  (2026-08-24)

## Corpus Check
- Corpus is ~20,990 words - fits in a single context window. You may not need a graph.

## Summary
- 316 nodes · 898 edges · 10 communities
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 47 edges (avg confidence: 0.53)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Situation Decision Engine|Situation Decision Engine]]
- [[_COMMUNITY_Intent Rules|Intent Rules]]
- [[_COMMUNITY_Default Map Lifecycle|Default Map Lifecycle]]
- [[_COMMUNITY_Legacy Feature Adapter|Legacy Feature Adapter]]
- [[_COMMUNITY_V32 Identity Gateway|V32 Identity Gateway]]
- [[_COMMUNITY_Airspace Relations|Airspace Relations]]
- [[_COMMUNITY_Flask Service Routes|Flask Service Routes]]
- [[_COMMUNITY_Event Result Mapping|Event Result Mapping]]
- [[_COMMUNITY_Defense Vulnerability Analysis|Defense Vulnerability Analysis]]
- [[_COMMUNITY_Default Map Data|Default Map Data]]

## God Nodes (most connected - your core abstractions)
1. `SituationEngine` - 51 edges
2. `Any` - 47 edges
3. `IntentFeatureFrame` - 29 edges
4. `IntentCandidate` - 25 edges
5. `SituationError` - 24 edges
6. `Target` - 24 edges
7. `_candidate()` - 23 edges
8. `LegacyAlgorithmAdapter` - 20 edges
9. `normalize_identity_source()` - 19 edges
10. `Any` - 18 edges

## Surprising Connections (you probably didn't know these)
- `IntentFeatureFrame` --uses--> `AirspaceRelationAnalyzer`  [INFERRED]
  situationawareness latest/situation_judgment/engine.py → situationawareness latest/situation_judgment/airspace_analysis.py
- `SituationError` --uses--> `AirspaceRelationAnalyzer`  [INFERRED]
  situationawareness latest/situation_judgment/engine.py → situationawareness latest/situation_judgment/airspace_analysis.py
- `SituationEngine` --uses--> `DefenseAnalyzer`  [INFERRED]
  situationawareness latest/situation_judgment/engine.py → situationawareness latest/situation_judgment/defense_analysis.py
- `SituationError` --uses--> `DefenseAnalyzer`  [INFERRED]
  situationawareness latest/situation_judgment/engine.py → situationawareness latest/situation_judgment/defense_analysis.py
- `Target` --uses--> `DefenseAnalyzer`  [INFERRED]
  situationawareness latest/situation_judgment/engine.py → situationawareness latest/situation_judgment/defense_analysis.py

## Import Cycles
- 1-file cycle: `situationawareness latest/situation_judgment/service.py -> situationawareness latest/situation_judgment/service.py`
- 1-file cycle: `situationawareness latest/situation_judgment/airspace_analysis.py -> situationawareness latest/situation_judgment/airspace_analysis.py`
- 1-file cycle: `situationawareness latest/situation_judgment/engine.py -> situationawareness latest/situation_judgment/engine.py`
- 1-file cycle: `situationawareness latest/situation_judgment/v32_gateway.py -> situationawareness latest/situation_judgment/v32_gateway.py`

## Communities (10 total, 0 thin omitted)

### Community 0 - "Situation Decision Engine"
Cohesion: 0.09
Nodes (33): AirspaceRelationAnalyzer, Build the additive per-target v3.2 airspace result collection., _active(), _angle_delta(), _candidate_from(), _clamp(), _distance(), _heading() (+25 more)

### Community 1 - "Intent Rules"
Cohesion: 0.14
Nodes (42): _candidate(), candidate_evidence(), _clamp(), empty_intent(), _eval_i01(), _eval_i02(), _eval_i03(), _eval_i05() (+34 more)

### Community 2 - "Default Map Lifecycle"
Cohesion: 0.11
Nodes (35): Path, RuntimeError, clear_runtime_default_map(), get_default_map(), install_runtime_default_map(), _load_default_map(), Load and manage the default map used by the public gateway., Validate a bundled or runtime map without requiring a no-fly zone. (+27 more)

### Community 3 - "Legacy Feature Adapter"
Cohesion: 0.11
Nodes (14): LegacyAlgorithmAdapter, Safe adapters around the reusable algorithms in ``formation_recognition``.  Th, Extract behavior features using vectorized or legacy approach.          Contro, Legacy loop-based feature extraction (original implementation)., Vectorized feature extraction using NumPy batch operations (6-8x faster)., Eagerly load heavy dependencies so the first request is not slow.          The, Return the cached formation recognizer, loading it on first use., Vectorized behavior feature extraction using NumPy batch operations.  This modul (+6 more)

### Community 4 - "V32 Identity Gateway"
Cohesion: 0.19
Nodes (32): _drone_valid_at(), _elapsed_days_since(), _fail(), _identity_completeness(), IdentityNormalization, _iso(), _normalize_flight_plan_record(), normalize_flight_plan_records() (+24 more)

### Community 5 - "Airspace Relations"
Cohesion: 0.20
Nodes (21): Point, _active(), _angle_delta(), _Area, _clamp(), _distance(), _empty_result(), _finite_optional() (+13 more)

### Community 6 - "Flask Service Routes"
Cohesion: 0.18
Nodes (18): Exception, Flask, _enum_attribute(), SituationError, _strict_bool(), Rule-based situation judgement service for the phase-one closed loop.  Keep the, register_situation_routes(), Flask routes for the phase-one situation judgement APIs. (+10 more)

### Community 7 - "Event Result Mapping"
Cohesion: 0.26
Nodes (20): _arrival_time(), _as_int(), _assessment_basis(), build_analysis_result(), _build_cluster(), _build_target(), _cluster_location(), _event_realname_status() (+12 more)

### Community 8 - "Defense Vulnerability Analysis"
Cohesion: 0.25
Nodes (5): IntentFeatureFrame, DefenseAnalyzer, Resource-backed defense and coverage assessment for analyzed clusters., Calculate only from supplied live resources; never invent capacity., Any

### Community 9 - "Default Map Data"
Cohesion: 0.25
Nodes (7): airspaces, facilities, mapId, name, rings, source, sourceBundle

## Knowledge Gaps
- **9 isolated node(s):** `mapId`, `name`, `source`, `sourceBundle`, `facilities` (+4 more)
  These have ≤1 connection - possible missing edges or undocumented components.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `SituationEngine` connect `Situation Decision Engine` to `Defense Vulnerability Analysis`, `Intent Rules`, `Legacy Feature Adapter`, `Flask Service Routes`?**
  _High betweenness centrality (0.180) - this node is a cross-community bridge._
- **Why does `LegacyAlgorithmAdapter` connect `Legacy Feature Adapter` to `Defense Vulnerability Analysis`, `Situation Decision Engine`, `Flask Service Routes`?**
  _High betweenness centrality (0.155) - this node is a cross-community bridge._
- **Why does `IntentFeatureFrame` connect `Intent Rules` to `Defense Vulnerability Analysis`, `Situation Decision Engine`, `Flask Service Routes`?**
  _High betweenness centrality (0.090) - this node is a cross-community bridge._
- **Are the 8 inferred relationships involving `SituationEngine` (e.g. with `Flask` and `AirspaceRelationAnalyzer`) actually correct?**
  _`SituationEngine` has 8 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `Any` (e.g. with `AirspaceRelationAnalyzer` and `DefenseAnalyzer`) actually correct?**
  _`Any` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `IntentFeatureFrame` (e.g. with `IntentFeatureFrame` and `SituationEngine`) actually correct?**
  _`IntentFeatureFrame` has 6 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `SituationError` (e.g. with `Flask` and `AirspaceRelationAnalyzer`) actually correct?**
  _`SituationError` has 8 INFERRED edges - model-reasoned connections that need verification._