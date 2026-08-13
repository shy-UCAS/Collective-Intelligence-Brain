# agents02 与 SituationAwareness v3.2 对接：当前进展与新对话恢复指南

> 最后整理时间：2026-08-13（三阶段实施已完成；已同步19项首版规则、多候选、长短窗口、网关语义、v3.2契约和门禁结果）  
> 工作区根目录：`E:\CASIA\Drone_Swarm_SituationSensingAlgos\Collective Intelligence Brain`  
> Python/Conda环境：agents02 使用 `study`；latest 服务、测试与可视化使用 `study_flask`  
> 本文用途：在新对话中快速恢复当前任务、已完成修改、关键决策、未完成工作和推荐实施顺序。

---

## 1. 当前任务是什么

当前主任务是把 `uav_strategy` 中的 agents02 无人机群仿真数据，稳定转换为 `situationawareness latest` 的态势判读输入，并为当前没有真实来源的身份、合规和计划业务数据提供确定性模拟样本。

最终目标链路为：

```text
agents02
  ├─ 实际轨迹 uavs_coords_str
  ├─ 原始轨迹 uavs_coords_raw
  ├─ 完整计划航迹 plannedRoutes
  ├─ 统一仿真时间 simulationMeta
  ├─ 设施 facilities_str
  └─ 防护圈 defence_rings
           │
           ├─────────────────────────────────┐
           ▼                                 ▼
确定性业务数据生成器                    轨迹窗口适配
  ├─ targetId↔serialNo绑定
  ├─ realPersons
  ├─ dronesBySerialNos
  ├─ droneWhitelistDtos
  └─ flightPlansBySn
           │
           └─────────────────┬───────────────┘
                             ▼
                  唯一v3.2外部源数据请求
                             ▼
                   v3.2网关/适配器归一化
                    ├─ 内部targetAttributes
                    ├─ 内部baseData.whitelist
                    └─ 内部baseData.flightPlans
                             ▼
                    SituationEngine.analyze()
```

核心原则：agents02 只负责仿真和轨迹导出；身份、实名、白名单、计划元数据及协议归一化放在 latest 侧，不把 SituationEngine 耦合进 SPADE/Redis 主循环。

### 1.1 当前三条代码协同调用链（2026-08-12 实现状态）

当前代码分成三条相互配合的链路：**正式HTTP运行链路**负责执行对外算法服务，
**agents02模拟与离线回归链路**负责生成测试数据、组装请求和验证结果，
**PyQt实时回放与可视化链路**负责逐帧调用正式HTTP接口并展示结果。后两条最终都通过HTTP进入第一条；
只有定位算法问题时，离线适配器才允许绕过HTTP直连内部引擎。

#### A. 正式HTTP运行链路

```text
真实调用方或agents02请求组装器
        │  唯一v3.2外部请求
        ▼
main_situation_judgment_service.py
        │  创建Flask应用、注册路由、启动Waitress
        ▼
situation_judgment/service.py
        │  接收POST /api/v1/situation/analyze、统一HTTP错误
        ▼
situation_judgment/v32_gateway.py::normalize_v32_request()
        │  DTO校验、targetId→SN→设备→飞手/白名单/计划关联
        │  生成内部targetAttributes、baseData.whitelist/flightPlans
        ▼
situation_judgment/engine.py::SituationEngine.analyze()
        ├─ legacy_adapter.py       稳健轨迹对齐、可靠度感知聚类/编队、行为特征、ETA复用
        ├─ intention_catalog.py    I-01～I-30目录和标准意图对象
        ├─ defense_analysis.py     防御资源、成功率和薄弱性评估
        └─ event_mapper.py         内部集群结果→analysisResult输出DTO
        │
        ▼
v32_gateway.py::decorate_v32_response()
        │  补充identityDataDiagnostics和安全身份投影
        ▼
service.py返回v3.2 HTTP响应
```

正式链路各代码的边界：

| 调用顺序 | 代码 | 主要职责 | 不负责什么 |
|---|---|---|---|
| 1 | `main_situation_judgment_service.py` | 创建应用、调用`register_situation_routes()`、启动31607端口 | 不做业务校验和算法计算 |
| 2 | `situation_judgment/service.py` | HTTP路由编排、调用网关和引擎、把异常转换为HTTP状态及`reasonCode` | 不直接解析四类DTO业务关系 |
| 3 | `situation_judgment/v32_gateway.py` | 唯一外部v3.2校验和归一化入口；生成内部身份、白名单、计划和诊断 | 不做聚类、意图和威胁计算 |
| 4 | `situation_judgment/engine.py` | 轨迹清洗、逐目标豁免、聚类、意图、十维威胁、人工修正和结果汇总 | 不直接接收外部四类DTO |
| 5 | `situation_judgment/legacy_adapter.py` | 安全复用旧轨迹、DBSCAN、编队、行为和ETA能力；失败时降级 | 不直接采用旧意图名称作为v3.2结论 |
| 6 | `situation_judgment/intention_catalog.py` | 根据意图编码生成规范名称、类别和候选结构 | 不决定哪条规则命中 |
| 7 | `situation_judgment/defense_analysis.py` | 只根据请求提供的探测和防御资源进行评估 | 不虚构资源或库存 |
| 8 | `situation_judgment/event_mapper.py` | 把内部集群结果转换为协议输出DTO | 不创建或持久化正式业务事件 |

`service.py`中的核心编排关系可概括为：

```python
normalized = normalize_v32_request(payload)
response = SituationEngine.analyze(normalized.internal_payload)
public_response = decorate_v32_response(response, normalized)
```

#### B. agents02模拟与离线回归链路

```text
agents02仿真导出
  ├─ uavs_coords_str/uavs_coords_raw
  ├─ plannedRoutes
  ├─ simulationMeta
  └─ facilities/defence_rings
        │
        ├─ generate_agents02_orient_test_data.py
        │    → orient_data.json + expected_labels.json
        │
        └─ build_agents02_v32_requests.py
             ├─ 复用agents02_export_to_payload.py的轨迹过滤和滑窗能力
             ├─ 合并轨迹、空间数据、targetAttributes和四类DTO
             └─ 生成v3.2 requests[]，可选POST到正式HTTP链路
```

各测试脚本的关系：

| 代码 | 角色 | 是否属于正式服务 |
|---|---|---|
| `tools/generate_agents02_orient_test_data.py` | 在真实身份/合规来源缺失时，确定性生成四类DTO、SN绑定和预期标签 | 否；真实业务数据接入后可退出正式联调链路 |
| `tools/build_agents02_v32_requests.py` | 把agents02轨迹窗口和orient源数据组装为唯一v3.2外部请求，并可做HTTP回放 | 否；它模拟真实调用方 |
| `tools/agents02_export_to_payload.py` | 复用生产网关的`normalize_identity_source()`，可直连`SituationEngine`并做合规对照 | 否；仅限离线回归，不能作为第二种外部协议 |

标准运行顺序为：

```text
步骤1  agents02仿真运行（改仿真时才重跑）
步骤2  生成器读取agents02导出
        → orient_data.json + expected_labels.json
步骤3  请求组装器读取agents02导出和orient_data.json
        → 唯一v3.2 requests[]
步骤4  POST /api/v1/situation/analyze
        → service → v32_gateway → SituationEngine及内部模块
        → v32_gateway响应投影 → identityDataDiagnostics/态势结果
```

步骤2可以通过更换seed/场景独立重跑，步骤3可以通过更换窗口参数独立重跑，均不要求重新运行agents02。
需要快速定位算法问题时，才使用`agents02_export_to_payload.py`走离线内部回归。

#### C. PyQt实时HTTP回放与可视化链路（✅ 已完成）

可视化不读取旧结果来冒充推理，而是以 `agents02_v32_http_requests.json` 为主输入：

```text
上传 adapterMeta + requests[] 请求回放包
        ▼
visualization/replay_data.py
        │  校验请求包、提供帧/滑窗/累计轨迹
        ▼
visualization/engine_process.py
        │  OPTIONS无副作用探测；自动启动或复用31607服务
        │  AnalysisPostWorker异步逐帧POST
        ▼
POST /api/v1/situation/analyze
        ▼
responses[i].data
        ├─ analysisResult：总体与集群结论
        ├─ eventSuggestions[]：完整主/次意图候选、触发成员、证据与路由
        ├─ exemptTargetResults[]：豁免原因及可选合规意图
        ├─ map_renderer.py：长短窗口、历史轨迹、集群包络和候选触发成员高亮
        └─ intent_replay_visualizer.py：候选/诊断/豁免/集群树、趋势和批量导出
```

代码职责：

| 代码 | 职责 |
|---|---|
| `visualization/intent_replay_visualizer.py` | PyQt主窗口、回放控制、真实`eventSuggestions[]`多候选、诊断/豁免/集群树、趋势和批量导出 |
| `visualization/replay_data.py` | 严格区分请求包和结果包；动态帧索引、意图长窗/运动尾窗/累计轨迹、窗口契约告警及可选历史基线校验 |
| `visualization/engine_process.py` | 兼容服务探测、自动启停、只关闭自有进程、异步JSON POST和结构化网络错误 |
| `visualization/map_renderer.py` | 当前定位、意图长窗/运动尾窗/累计轨迹、设施/圈层/空域、稳定集群包络及候选实际触发成员高亮 |

主输入必须是 `*_http_requests.json`；`*_http_results.json` 只表示历史响应，不能作为实时推理输入。
2026-08-12旧导出曾用独立Waitress进程实测71/71帧网络请求成功；这是冻结历史基线。当前默认无时间戳请求/结果文件已切换为2026-08-13新导出的76帧样本。完成可视化增强后，当前76帧保存结果可解析152个事件建议、596个候选，候选协议一致性告警为0；可视化专项32/32通过。

注意：PyQt主界面目前不提供“加载历史结果并比较基线”的按钮；`replay_data.py`虽有严格基线校验API，但只接受带`runnerMeta + summaries[] + responses[]`且数量/顺序匹配的结果包。历史结果不能作为实时推理主输入。

数据契约边界：

| 交接 | 传递内容 | 关键约束 |
|---|---|---|
| agents02 → 生成器 | `plannedRoutes[].flightRoute`、`simulationMeta.startTimeMs`、`missionMeta.swarms[]`（2026-08-13新增：orderType/target/fleetNo/leaderId/memberIds） | flightRoute为`{lng,lat,alt}`，AMSL；missionMeta为任务设计真值 |
| 生成器 → 请求组装 | `orient_data.json`（targetAttributes绑定 + 四类DTO + requestSkeleton + 集群语义分配元数据） | flightRoute原样搬运，不随机；场景按集群任务语义分配 |
| 请求组装 → HTTP网关 | 唯一v3.2源数据请求；四类DTO顶层存在 | 外部`baseData`不包含`whitelist/flightPlans` |
| 网关 → 引擎 | v3.1内部格式（`registrationStatus`、`baseData.whitelist/flightPlans`） | 由四类DTO按§42转换，时间带时区 |

三条设计原则：

1. **数据单向流**：agents02 → 生成器/请求组装 → HTTP网关 → 引擎，无回环；网关是唯一生产归一化入口；
2. **真实数据不伪造**：轨迹/计划航迹/空间数据全部真实来源；生成器只补无来源的身份合规数据；组装器和网关只做确定性转换；
3. **静态/动态分离**：四类DTO是静态业务数据（一次生成、多窗口复用）；轨迹窗口按每快照`snapshotTime`动态切片，有效期判断逐窗口计算。

---

## 2. 当前总体进度

| 模块 | 状态 | 当前结论 |
|---|---|---|
| agents02统一仿真时钟 | ✅ 已完成 | 所有Agent使用全局round生成统一仿真时间，不再使用各自写Redis的墙钟作为轨迹时间 |
| agents02物理步进 | ✅ 已完成 | 水平、爬升、下降均有限速，消除了每500ms跨越约80m造成的160m/s瞬移 |
| 高度与轨迹阶段元数据 | ✅ 已完成 | 导出等长`alts`、`ts`、`extras`，明确`flight_phase/is_waiting` |
| raw/分析轨迹分层 | ✅ 已完成 | `uavs_coords_raw`保留完整生命周期；`uavs_coords_str`只保留同步任务飞行帧 |
| 初始化首点速度尖峰 | ✅ 已处理 | 初始化和定位阶段不进入`uavs_coords_str`，仅保留在raw中 |
| `is_waiting`字符串布尔问题 | ✅ 已处理 | Python/JSON端使用真布尔值；历史字符串仍兼容；不影响AgentSpeak逻辑 |
| 完整`flight_plan`导出 | ✅ 已完成 | 通过`flight_plan + nodes_pair_member_traj`重建`plannedRoutes`，不再依赖只保存当前航段的`cur_reference_traj` |
| agents02轨迹离线适配器 | ✅ 基础版已完成 | 已实现轨迹过滤、时间恢复、滑窗、多目标快照、设施/圈层映射和直连引擎 |
| v3.2四类业务DTO协议 | ✅ 文档已完成 | 已定义飞手实名、设备实名、白名单、按SN飞行计划及关联/校验规则 |
| v3.2完整输入结构树 | ✅ 文档已完成 | 协议第45章汇总完整外部请求结构 |
| v3.2唯一外部源数据格式 | ✅ 协议已固定 | 不再允许“规范模式/源数据模式”二选一 |
| 禁飞区/空域真实数据源 | ✅ 已接入 | Apifox测试地址 `/airspace/list`、`/nofly/list` 可拉取；空域→`facilities_str/defence_rings`，禁飞区→`airspaces[]`，agents02 `switch_config==6` 已在使用（详见§9.2.1） |
| 真实身份DTO样例 | ✅ 已获取 | 对接方提供四类DTO字段模板：`apitest/samples/v32_identity_source_sample.json`，与协议§37～§40一致（详见§10阶段A） |
| 四类DTO确定性数据生成器 | ✅ 已完成 | `tools/generate_agents02_orient_test_data.py`：13目标13场景、seed可复现、flightRoute取自plannedRoutes、23项单测通过（详见§10阶段A） |
| 集群任务语义导出（missionMeta） | ✅ 已完成（2026-08-13） | `save_trajectories()` 导出顶层`missionMeta.swarms[]`：orderType/target/fleetNo来自digraph边属性，memberIds按segmentKey分组，leaderId来自运行期extras；契约测试4项 |
| 生成器集群级语义分配 | ✅ 已完成（2026-08-13） | 场景按集群任务语义分配：13场景分三个家族（illegal/legal/gray），orderType→家族映射（breakthrough固定illegal，detour seed随机illegal/legal），集群内同场景，不再单机盲洗牌 |
| latest数据管线 | ✅ 已完成（2026-08-13） | `run_data_pipeline.ps1/.bat`：生成器→请求组装→回放+合规对照一条命令，按阶段切换study/study_flask；agents02仿真保持手动；旧导出可用`build_mission_meta_from_export.py`桥接 |
| `--orient-data`适配 | ✅ 已完成 | `agents02_export_to_payload.py`支持四类DTO校验+归一化内部targetAttributes/baseData.whitelist/flightPlans；端到端13/13合规对照全匹配（详见§10阶段B） |
| 长短轨迹窗口 | ✅ 代码与文档已更新 | 单请求默认自包含最近120秒/最多240点意图轨迹；运动/聚类只取尾部12点；不依赖跨HTTP请求隐藏状态 |
| 网关意图业务语义 | ✅ 代码与文档已更新 | 保留计划用途/性质/编码/申报时间/原始航点、白名单`purpose/operationType/organization`；派生飞手经验天数、登记年龄和身份完整度；敏感字段不下沉 |
| `exemptTargetResults[].intent` | ✅ 已完成并回归 | 采用可选公共Intent对象；只在证据足以区分I-01/I-02/I-03/I-05时输出，普通白名单不得默认视为I-03，也不会因轨迹行为附带非合规意图 |
| 意图topCandidates多候选 | ✅ 已完成并回归 | 19项独立候选、统一稳定排序、主意图=`topCandidates[0]`；无候选返回空意图且I-28不兜底 |
| 外部v3.2到内部引擎的归一化网关 | ✅ 已完成 | `v32_gateway.py`强制唯一源数据格式，生成内部身份/白名单/计划并补充`identityDataDiagnostics` |
| PyQt实时HTTP回放可视化 | ✅ 已完成 | 请求包驱动、服务自动启停、逐帧真实POST；分层显示意图长窗/运动尾窗/累计航迹，结构化呈现`eventSuggestions[]`多候选、成员级触发目标、空意图复核、诊断/数据质量、趋势和批量导出；专项32/32通过 |
| 聚类轨迹预处理与稳定性修复 | 🟡 历史基线通过、当前基线待收口 | 2026-08-12冻结71帧样本三个设计集群全程稳定；当前默认76帧样本在第49帧出现`agent_1`的1+3拆分，且旧测试仍硬编码71帧，须先决定冻结/迁移基线再收口 |
| v1意图范围开关/禁用红色意图 | ✅ 已完成并回归 | 默认精确19项；请求只能进一步收窄，I-28和十项暂缓意图不可启用 |
| HTTP端到端v3.2联调 | 🟡 本地独立进程完成 | 旧冻结包71/71成功、合规923/923；当前默认保存包76/76成功、合规988/988，且结果中152个事件建议/596个候选协议一致性告警为0；真实对接方联调仍留待阶段F |

重要边界：公共 `POST /api/v1/situation/analyze` 已通过 `v32_gateway.py` 支持并强制校验v3.2四类DTO；`SituationEngine` 本身仍消费内部v3.1规范结构。新对话必须区分“公共HTTP契约已实现”和“核心引擎并非原生DTO入口”。

---

## 3. agents02 已完成的代码改造

### 3.1 统一仿真时钟

统一时间公式：

```text
simTimeMs = sim_start_time_ms + round_id × sim_dt_ms
```

默认：

```text
DT = 0.5s
sim_dt_ms = 500ms
```

主要字段：

- `round_id`：统一仿真轮次；
- `simTimeMs`：轨迹业务时间，epoch毫秒；
- `recordedAtMs`：实际写Redis墙钟，只用于延迟诊断；
- `timestamp`：兼容旧可视化器的epoch秒。

涉及代码：

- `uav_strategy/examples/uavs_strategy/uav_dynamic_agents02.py`
  - `save_trajectories()`：约第938行；
  - 统一仿真时间初始化：约第1110行；
- `uav_strategy/examples/uavs_strategy/README_agents02.md`
  - 第7.1节。

### 3.2 有界物理步进

默认运动约束：

| 参数 | 默认值 | 500ms最大位移 |
|---|---:|---:|
| 水平速度 | 16m/s | 8m |
| 爬升速度 | 5m/s | 2.5m |
| 下降速度 | 5m/s | 2.5m |

涉及代码：

- `uav_strategy/examples/uavs_strategy/behaviors_modules/uav_periodic_behaviours.py`
  - 常量：文件开头；
  - `bounded_motion_step()`：约第49行；
- `uav_strategy/examples/uavs_strategy/README_agents02.md`
  - 第7.2节。

该改造保持最终参考航迹效果不变，只改变真实墙钟运行多久才能完成相同仿真飞行。

仿真墙钟加速（已实现）：`uav_dynamic_agents02.py` 顶部新增 `SIM_SPEEDUP` 倍率（默认
`1.0`）。它只把 `APFStep` 和 `GlobalRoundCoordinator` 的真实调度周期从 `DT` 缩短为
`DT / SIM_SPEEDUP`，**不修改** `DT` 代表的仿真时间步长，也**不修改**每个 round 的物理
位移上限，因此 `simTimeMs`、轨迹点和速度上限均保持不变，只是生成相同仿真数据所需的
真实墙钟时间约缩短 `SIM_SPEEDUP` 倍。实际加速上限受 Redis 往返、每轮物理计算和 agent
数量影响，不等同于严格线性倍率。需要加速时把 `SIM_SPEEDUP` 改为 `10.0`、`20.0` 等，
并重新运行 agents02 导出，随后仍走同一套 `run_data_pipeline` 生成请求包。

### 3.3 `is_waiting`与飞行阶段

新契约：

```text
is_waiting      JSON boolean
waiting_reason  string|null
flight_phase    initializing|positioning|sync_wait|task_flight
```

进入分析轨迹的条件：

```text
flight_phase == "task_flight" and is_waiting == false
```

`uav_key_path.asl`中不存在`is_waiting(...)`信念，因此Python/JSON布尔修复不改变SPADE-BDI规划逻辑。不要全局替换ASL中的`"False"`或AgentSpeak Literal。

### 3.4 两层实际轨迹

- `uavs_coords_raw`：完整审计、回放和排错；包含初始化、定位、等待和任务飞行；
- `uavs_coords_str`：latest分析轨迹；只保留公共同步帧中的任务飞行样本。

`uavs_coords_str`还会：

- 排除字符串frame_id和`frame_id<=0`；
- 按航段取多Agent公共`frame_id`交集；
- 同一frame内存在多个物理中间点时取最后一个点；
- 兼容历史字符串`"False"`。

v3.2滑动轨迹窗口和HTTP回归必须选择500ms连续采样的`uavs_coords_raw`，再由适配器按`flight_phase == "task_flight" and is_waiting == false`过滤生命周期阶段。`uavs_coords_str`只用于公共航路点级分析，不能配合500ms快照新鲜度阈值生成连续窗口。

### 3.5 完整计划航迹

`cur_reference_traj`和Redis的`uav:{uid}:ref_traj`只保存当前航段，不能代表完整飞行计划。

当前实现使用：

```text
agent.flight_plan
  + nodes_pair_member_traj
  → build_complete_flight_plan_export()
  → plannedRoutes[targetId].flightRoute
```

涉及代码：

- `uav_strategy/examples/uavs_strategy/uav_dynamic_agents02.py`
  - `build_complete_flight_plan_export()`：约第208行；
  - `save_trajectories()`：约第938行。

计划航迹`plannedRoutes`与实际飞行结果`uavs_coords_str/uavs_coords_raw`始终独立，不能用实际飞行结果反推计划，否则无法测试偏航。

### 3.6 集群任务语义导出（missionMeta，2026-08-13 新增）

agents02 按集群（swarm）规划任务，latest 生成器需要这一语义真值做一致的合规数据分配。
`save_trajectories()` 新增导出顶层 `missionMeta`：

```json
{
  "missionMeta": {
    "source": "digraph_attrs",
    "swarms": [
      {"swarmId": "swarm1", "fleetNo": "sx1.1", "orderType": "detour",
       "target": "shaoxing_1", "segmentKey": "0_3",
       "leaderId": "agent_1_0",
       "memberIds": ["agent_1_0", "agent_1_1", "agent_1_2", "agent_1_3"]}
    ]
  }
}
```

| 字段 | 来源 | 说明 |
|---|---|---|
| `orderType/target/fleetNo` | digraph 边属性（`order_type/target/fleet_no`） | 任务设计真值，不从轨迹反推 |
| `memberIds` | `plannedRoutes[].flightPlan` 按 `segmentKey` 分组 | 比 digraph `members_num` 权威（后者历史上一度不含主机） |
| `leaderId` | 运行期 extras 的 `leader_id` | 缺失时回落首个成员 |

无 digraph 边的目标进兜底条目（`orderType=null` + `note`）。`build_mission_meta()` 只组装导出
数据，不修改仿真逻辑、Redis 内容或 Agent 状态。契约测试 4 项（agents02 合计 15 项通过）。

涉及代码：

- `uav_strategy/examples/uavs_strategy/uav_dynamic_agents02.py`
  - `build_mission_meta()`：约第 293 行；
  - `save_trajectories()`：约第 1081 行挂入、约第 1173 行写入 `final_data`；
- `uav_strategy/tests/test_agents02_trajectory_contract.py`
  - `MissionMetaExportTests`：4 项；
- `uav_strategy/examples/uavs_strategy/README_agents02.md`
  - §7.5.1、§7.9、§7.11。

---

## 4. 最新agents02实际输出状态

最新用户运行输出：

`uav_strategy/examples/uavs_strategy/data/raw_data/uav_trajectories_persistent_20260812_131556.json`

当前核对结果：

| 项目 | 结果 |
|---|---:|
| 文件大小 | 18,553,537字节 |
| `uavs_coords_str`目标数 | 13 |
| `uavs_coords_raw`目标数 | 13 |
| `plannedRoutes`目标数 | 13 |
| 完整计划航路 | 13 |
| 不完整计划航路 | 0 |
| `simulationMeta.dtMs` | 500 |
| `simulationMeta.timeBasis` | `SIMULATION_ROUND` |
| 最大水平速度 | 16m/s |

顶层结构：

```text
simulationMeta
uavs_coords_str
uavs_coords_raw
plannedRoutes
facilities_str
defence_rings
```

> 该样本（20260812_131556）早于 missionMeta 导出改造（2026-08-13），不含 `missionMeta`。
> 2026-08-13 之后重跑仿真的新导出会自带顶层 `missionMeta`（见 §3.6）；旧样本继续用
> `build_mission_meta_from_export.py` 桥接（§13）。

这个文件是下一步模拟数据生成器和v3.2适配器的首个真实回归样本。不要手工通读18MB JSON；只需抽查顶层键、目标数、一个目标轨迹和一个`plannedRoutes`条目。

---

## 5. 当前轨迹适配器已经能做什么

文件：

`situationawareness latest/tools/agents02_export_to_payload.py`

已实现：

- 消费`uavs_coords_str`或`uavs_coords_raw`；
- 过滤初始化、定位、等待帧；
- 兼容`ts/simTimeMs/round_id`；
- 默认最近120秒且最多240点的意图长窗口、步幅6；运动/聚类使用尾部12点；
- 单目标最少6点；
- 共同快照截止时间；
- 剔除超过`maxSnapshotSkewMs`的陈旧目标；
- 映射`facilities_str → baseData.facilities`；
- 映射`defence_rings → baseData.rings`；
- 输出`adapterMeta + payloads[]`；
- 使用`--call-engine`直连`SituationEngine.analyze()`。

主要入口：

- `normalize_track()`：约第151行；
- `build_base_data()`：约第333行；
- `_target_attributes()`：约第353行；
- `convert_export_to_payloads()`：约第431行；
- CLI：约第580行。

v3.2扩展（阶段B，2026-08-12已完成）：

- `--orient-data`：解析生成器输出的四类DTO+SN绑定，校验（数组存在/ID唯一/SN规范化/外键/时间关系）后按协议§42归一化为内部`targetAttributes`/`baseData.whitelist`/`baseData.flightPlans`，逐窗口按快照时间判断有效期；
- `--expected-compliance-output` + `--compliance-report`：逐快照逐目标对照预期标签，不匹配返回非0；
- 不传`--orient-data`时仍走旧默认值（`_target_attributes()`填`registrationStatus="unregistered"`等），此时身份合规数据全部按未登记处理，不能用于v3.2验收；
- 敏感字段（`idCard/phone/contactPhone/responsiblePhone/certificateNo`）不进入内部结构、诊断和日志。

v3.2公共HTTP链路（阶段C/D，2026-08-12已完成）：

- `situation_judgment/v32_gateway.py`：公共请求级校验、四类DTO关联、逐快照状态计算、内部`targetAttributes/whitelist/flightPlans`生成和`identityDataDiagnostics`；
- `situation_judgment/service.py`：`POST /api/v1/situation/analyze`默认强制经过v3.2网关，内部v3.1式payload不能绕过公共入口；
- `tools/build_agents02_v32_requests.py`：默认消费500ms连续采样的`uavs_coords_raw`，合并agents02轨迹窗口与orient源数据，输出唯一v3.2外部`requests[]`，并支持`--post-url`逐快照HTTP回放；
- 请求级错误返回HTTP 400和稳定`reasonCode`；孤儿飞手、未匹配SN、过期记录进入诊断；完整身份证、电话和证书号不进入响应或诊断；
- 公共网关已校验飞手姓名、设备业务ID、飞行计划编码等协议必填字段，并强制单次请求内`planCode`唯一；多条计划同时命中时按横向偏差、申报时间和记录ID确定性择优并返回诊断；
- 最新13目标已通过Flask公共入口回归，合规对照13/13匹配。

---

## 6. v3.2协议当前最终决策

协议文件：

`situationawareness latest/态势判读算法单接口协议-v3.2.md`

### 6.1 外部只允许一种源数据格式

外部完整请求固定包含：

```text
requestId
snapshotTime
uavs_coords_str
targetAttributes
baseData
realPersons
dronesBySerialNos
droneWhitelistDtos
flightPlansBySn
corrections
options
```

四类业务数组每次都必须存在，没有记录时传`[]`，不能省略或传`null`。

### 6.2 外部`targetAttributes`的职责

外部只提供：

- `targetId → serialNo`绑定；
- `targetType`；
- `remoteId`；
- 载荷感知事实；
- 高度基准和地面高程；
- `isCooperative`；
- `releaseEvent`；
- `electronicInterference`。

外部禁止直接提交以下适配器内部结论：

```text
registrationStatus
registrationNo
droneId
droneRegistrationId
pilotId
model
pilotRiskLevel
sourceConflict
```

### 6.3 内部 `baseData.whitelist/flightPlans`

为了兼容当前引擎六数组结构，网关在内部请求中生成：

```json
{
  "baseData": {
    "whitelist": ["由droneWhitelistDtos归一化"],
    "flightPlans": ["由flightPlansBySn归一化"]
  }
}
```

公共HTTP请求的`baseData`中不再暴露这两个字段。适配器内部根据：

```text
droneWhitelistDtos → internal baseData.whitelist
flightPlansBySn    → internal baseData.flightPlans
```

外部只要提交这两个字段，即使值为`[]`，也返回`READ_ONLY_NORMALIZED_BASE_DATA_FIELD`。

### 6.4 唯一关联链

```text
targetId
  └─ targetAttributes[targetId].serialNo
       ├─ dronesBySerialNos[].serialNo
       │    └─ personId → realPersons[].id
       ├─ droneWhitelistDtos[].droneSn
       └─ flightPlansBySn[].aircraftSn
```

禁止用数组下标、姓名、手机号或相同机型进行主关联。

### 6.5 当前代码边界

`SituationEngine.analyze()`仍是v3.1式内部规范入口；`service.py`中的公共
`POST /api/v1/situation/analyze`已固定先经过`v32_gateway.py`。离线引擎单测可以注入内部测试网关，
但生产服务默认配置不存在v3.1外部直通路径。

### 6.6 聚类与合规成员语义（待会议决定）

当前代码仍先执行逐目标白名单/有效飞行计划豁免，再把剩余目标送入聚类，豁免目标返回在
`exemptTargetResults[]`且`excludedFromClustering=true`。因此当前公共响应中的集群表示“参与分析的非豁免成员”，
不一定等于仿真设计中的完整物理编队。

是否改为先计算完整物理集群，再拆分`physicalMembers`与`analysisMembers`，留待会议确定。
在决定形成前：

- 不修改现有聚类成员字段和豁免顺序；只为豁免元素增加向后兼容的可选`intent`对象；
- 不把豁免成员直接塞回现有威胁计算；
- 聚类回归同时保留“当前公共接口结果”和“无合规过滤的纯轨迹聚类结果”两种门禁；
- 当前用每请求自包含长轨迹解决意图历史，不启用`SplitClusters.memory_len`跨HTTP持久化；`clusterDistanceMeters`主聚类化另立设计任务。

### 6.7 长短轨迹窗口（2026-08-13已决定）

公共请求不增加第二套轨迹字段。`uavs_coords_str.<targetId>`默认携带最近120秒且最多240点的自包含长轨迹；500ms采样时实际覆盖约119.5秒。早期快照历史不足时使用已有全部历史，但至少6点。

```text
同一条请求轨迹
  ├─ 尾部12点：运动/聚类/队形
  └─ 完整有界轨迹：悬停、绕飞、往复、扫描和计划贴合等意图特征
```

构建工具允许`--intent-window-seconds 60～120`，`--window-size`现在表示长轨迹最大点数，允许6～240、默认240，不再表示运动短窗。`adapterMeta`记录`motionWindowSize/intentWindowSeconds/intentWindowMaxPoints/windowPolicy`。每个HTTP请求结果不依赖前一请求留下的服务端轨迹状态。

### 6.8 网关非敏感语义与豁免意图（2026-08-13已决定）

- 内部飞行计划完整保留`planCode/taskNature/taskPurpose/declaredTime/airspaceRoute/approvalStatus/flightRoute`；
- 外部白名单兼容新增`operationType=normal/system_test/equipment_debug/maintenance/other`，内部完整保留`purpose/operationType/organization`；I-03认`purpose=7`或`system_test`，I-05只认`equipment_debug/maintenance`，不得凭`purpose=8`推断；I-05首版只能使用最长120秒长窗判断“本窗已悬停≥30秒”，无法排除窗口前已持续并超过300秒；
- `purpose`、`taskNature`、`taskPurpose`如提供必须分别是严格JSON整数1～8、0～1、0～4；JSON boolean、字符串数字或范围外值与非法`operationType`统一返回HTTP 400和`INVALID_SOURCE_ENUM`；
- 目标派生`pilotExperienceDays/registrationAgeDays/identityCompleteness`，并在`identitySummary`中镜像；
- `identityCompleteness`仅表示SN、Remote ID、设备记录、飞手记录四项是否可用，不代表记录有效；
- `idCard/phone/contactPhone/responsiblePhone/certificateNo`等敏感字段不下沉到引擎、证据链或普通日志；
- `exemptTargetResults[]`兼容增加可选`intent`对象，复用公共Intent DTO；只有证据足以区分I-01/I-02/I-03/I-05时返回，普通白名单可只有豁免原因而没有具体意图。

同一目标同时命中白名单和合规飞行计划时，外层主豁免原因可保持`WHITELIST`，但全部命中记录仍参与合规意图评估，因此计划支持的I-01/I-02不会被白名单遮蔽；多计划诊断在白名单/演练主原因分支同样保留。普通白名单不会因超高等轨迹行为附带I-12。

I-01/I-02使用内部`planMatchScore`：长窗口内同时命中水平航线走廊和可比高度范围的有效轨迹点比例，首版门槛0.85；但`FLIGHT_PLAN`豁免仍要求最终当前点合规，历史高贴合不能掩盖当前偏航。

---

## 7. 当前意图范围

范围真值文件：

`意图与威胁算法研发表-v2.0.1.xlsx`

Excel“意图大类”列中红色填充的十项当前暂缓：

```text
I-04 应急演练
I-06 航线偏离（定位故障类）
I-07 航线偏离（风力漂移）
I-09 设备失控（飞丢）
I-16 持续悬停监视
I-19 载荷异常
I-20 跨境走私
I-23 载荷投掷
I-25 电子干扰
I-27 窥探窃密
```

当前v1首版已实现并默认启用的19项：

```text
I-01、I-02、I-03、I-05、I-08、I-10、I-11、I-12、I-13、
I-14、I-15、I-17、I-18、I-21、I-22、I-24、I-26、I-29、I-30
```

另外：

- `I-28 行为模式异常`本轮明确保持禁用；无19项候选通过门槛时返回结构完整的空意图、`topCandidates=[]`和`reviewRequired=true`，不再用I-28兜底；
- “入侵禁飞区”特殊候选固定`priorityRank=0`，命中时成为`topCandidates[0]`并保留`specialViolationCode=NO_FLY_INTRUSION`；I-13/I-30/禁飞候选的`triggerTargetIds`只列实际命中圈层的成员；
- `enabledIntentCodes`默认精确启用上述19项；公共请求只能配置为19项的子集，不能开启I-28或十项暂缓意图；该范围门禁已通过定向规则和公共HTTP回归。

本轮阶段E已把原`engine.py::_intent()`首条命中方式迁移为19项独立评估器：先构建统一特征，再做必要条件门控、动态规则评分、互斥处理和统一稳定排序。排序键固定为`priorityRank`升序→`confidence`降序→内部`dataCompleteness`降序→`intentCode`字典序；主意图必须与`topCandidates[0]`一致。十维威胁只消费主意图，其他候选用于解释/复核。

19项属于首版确定性/几何规则算法，v1规则与轨迹特征定向测试26/26通过（含19项直接正例），并通过当前全量回归。I-10/I-21/I-22等依赖景点、监所、敏感测绘区语义；必要数据缺失时不产生候选。模拟数据只验证字段链、阈值、候选排序和冲突行为，不能代表真实感知准确率验收完成。

首版已冻结的三个易误读门槛是：I-08有`pilotExperienceDays`时只按其是否≤90天判断，只有该字段缺失时才使用`registrationAgeDays≤90`代理，`pilotRiskLevel=high`不能单独证明新手；I-18固定将快照转换到UTC+08:00后按20:00～06:00判断；I-21速度必须在0.5～12m/s闭区间内。

---

## 8. 暂时不需要生成的数据

以下数据只服务于暂缓意图，当前可不实现生成：

| 暂缓意图 | 暂不生成内容 | 当前协议处理 |
|---|---|---|
| I-04 | 演练编号、允许目标、演练时间窗 | `baseData.drillPlans=[]` |
| I-06 | GPS故障状态、定位质量、定位跳点标签 | 不扩展专用字段 |
| I-07 | 气象网格、风向风速 | 不生成 |
| I-09 | 链路状态、失联、返航状态 | 不生成 |
| I-16 | 起降点、备降点、观景点等悬停豁免热点 | 不生成 |
| I-19 | 视觉载荷异常结论和识别置信度 | `payloadClass`暂用`normal/unknown` |
| I-20 | 国境/海岸边界及区域开关 | 不生成 |
| I-23 | 抛落物、分离证据 | `releaseEvent=false` |
| I-25 | 频谱异常事件和目标归因 | `electronicInterference=false` |
| I-27 | 相机朝向、视线、敏感立面和凝视时长 | 不生成 |

注意：`detectionDevices`是防御探测覆盖数据，不等于I-25的频谱异常事件，不能因为I-25暂缓就把二者混为一类。

---

## 9. 目前仍然缺失、需要生成的数据

### 9.1 第一优先级：身份与合规链

必须实现：

```text
targetAttributes[targetId].serialNo
realPersons
dronesBySerialNos
droneWhitelistDtos
flightPlansBySn
```

原因：它们共同支撑I-01、I-02、I-03、I-05、I-08、I-10、I-11、I-18、I-29，以及威胁中的合规、机型和飞手维度。

`flightPlansBySn[].flightRoute`不随机生成，直接读取对应目标的`plannedRoutes[targetId].flightRoute`；生成器只补计划编号、SN、任务目的、起降时间、申报信息和审批状态。

### 9.2 第二优先级：空间语义和高度

禁飞区/空域已有真实来源（见§9.2.1），其余当前没有真实来源：

- 地标/景点类型；
- 监所类型；
- 敏感测绘区域；
- 地面高程和AGL换算；
- 机型能力参数。

这些数据分别支撑禁飞链、I-10、I-12、I-14、I-15、I-21、I-22、I-24和威胁维度。

协议已于2026-08-13补齐最小语义枚举：`facilities[].facilityType=landmark/scenic_spot/prison`，`airspaces[].airspaceType=sensitive_mapping`。当前缺口从“字段未定义”变为“真实业务源尚未接入”；没有可靠数据时相关意图不得产生候选，模拟数据仅用于规则和接口验收。

#### 9.2.1 禁飞区/空域真实来源：Apifox 测试地址（已确认可用）

数据源接口（测试环境 `http://125.35.101.132:8888/basic`，当前无鉴权、无需Apifox令牌）：

```text
GET /airspace/list   防控区/空域列表
GET /nofly/list      禁飞区列表
```

拉取脚本与样本：

- `apitest/fetch_airspace_list.py`、`apitest/fetch_nofly_list.py`；
- 空域响应样例：`apitest/samples/airspace_list_sample.json`（共6条）；
- 禁飞区响应样例：`apitest/samples/nofly_list_sample.json`（当前1条，圆形、`geom=null`）。

agents02 已实际使用该数据：

- `switch_config == 6` 时读取 `uav_strategy/examples/uavs_strategy/data/facilities_shaoxing.json`（见`uav_dynamic_agents02.py`约第391行）；
- 该文件由 `data/gen_facilities_shaoxing.py` 从空域 `2086742451469029376`（"20260810"）生成：`facilityList`→`facilities_str`；facilityList[0] 圆心+三级半径（countermeasure/alert/warning）→正十二边形离散化→`defence_rings`；同时读取 `nofly_list_sample.json`，把圆形禁飞区（圆心+半径、`geom=null`）离散成正十二边形顶点→`airspaces[]`（`airspaceType=no_fly`）。
- `uav_dynamic_agents02.py` 导出时会透传 `facilities_shaoxing.json` 的 `airspaces` 到 `uav_trajectories_persistent_*.json` 顶层，随后适配器 `build_base_data` 原样放入 `baseData.airspaces`。

与 v3.2 协议的映射：

| Apifox 空域字段 | v3.2 目标结构 | 说明 |
|---|---|---|
| `id` | `airspaceId` | 雪花ID字符串 |
| `name` | `name` | |
| `zoneType=1`圆形：`countermeasure/alert/warningRadius`+facilityList[0]圆心 | `baseData.rings`（ringType=1 圆形） | 可直接用，无需离散化 |
| `zoneType=2`多边形：`countermeasureGeom/alertGeom/warningGeom` | `airspaces[].geometry`（多边形） | v3.2的`airspaces[]`只支持多边形（协议§12） |
| `altitudeMax/altitudeMin` | 暂不映射 | v3.2当前主要计算平面区域，未实现三维空域 |

禁飞区（`/nofly/list`）映射：

| `/nofly/list` 字段 | v3.2 目标结构 | 说明 |
|---|---|---|
| `id` | `airspaceId` | |
| `name` | `name` | |
| `zoneType=1`圆形：`lng/lat/radius` | `airspaces[].geometry`（正多边形顶点） | `geom=null` 时由 `circle_to_ngon` 离散；后端提供 `geom` 多边形时直接透传 |
| `zoneType=2`多边形：`geom` | `airspaces[].geometry` | 直接透传顶点 |
| `airspaceType` | 固定 `no_fly` | 触发 `NO_FLY_INTRUSION` |

限制：当前列表接口返回的 `countermeasureGeom/alertGeom/warningGeom` 均为 null，只有设施点+半径可用，因此实际能获取的是圆形防控区（圆心+半径）；多边形禁飞区需后端创建带 geom 的记录后才能获取。

### 9.3 第三优先级：防御评估

若当前里程碑包含防御评估，再生成：

```text
baseData.defenseResources
baseData.detectionDevices
```

若暂时只验收意图和威胁，可以不提供并接受防御结果`unavailable`，但必须明确这是未验收，不是计算结果为0。

### 9.4 不应随机制造的派生特征

以下内容应由适配器/算法从轨迹计算：

```text
速度、航向、下降率、悬停时长、绕飞角、轨迹重复度、
计划偏离距离、计划匹配分、ETA、扫描覆盖度、编队同步程度、
候选意图置信度
```

随机生成派生结果会造成“字段声称悬停但轨迹实际高速移动”等自相矛盾。

---

## 10. 已完成阶段记录与下一步

### 阶段A：实现确定性业务数据生成器（✅ 已完成）

已新增：

`situationawareness latest/tools/generate_agents02_orient_test_data.py`

输入：

```text
agents02导出JSON
固定seed
场景配置
```

输出字段级清单（生成方式标注：【生成】=确定性生成、【固定】=常量、【真实】=取自真实来源、【不生成】=本轮不产出）：

```text
targetAttributes[targetId]（每目标）
  ├─【生成】serialNo（targetId↔SN绑定，场景分配）、remoteId
  ├─【固定】targetType=uav、payloadType=unknown、payloadClass=normal、
  │          altitudeReference=AMSL、isCooperative=false、
  │          releaseEvent=false（I-23暂缓）、electronicInterference=false（I-25暂缓）
  └─【不生成】groundElevationMeters（无真实来源，AMSL基准免AGL换算）

realPersons[]（全【生成】）
  id(10xxx)、name(虚构)、idCard(模拟)、phone(模拟)、unitType、unit、
  qualificationType、certificateNo、qualificationStartDate、qualificationEndDate、
  creditScore(字符串)、status —— 有效期与状态由场景决定

dronesBySerialNos[]（全【生成】）
  id(20xxx)、droneId(30xxx)、personId(→realPersons.id)、complianceStatus、
  serialNo、manufacturer、model、droneType、owner、ownerUnit、contactPhone、
  responsiblePilot、insuranceExpireTime、status、registerTime、expireTime

droneWhitelistDtos[]（全【生成】，只给部分目标）
  id(40xxx)、droneSn、model、purpose、operationType、organization、responsibleName、
  responsiblePhone、effectiveDate、expireDate、status、remark

flightPlansBySn[]
  ├─【生成】id(50xxx)、planCode、taskNature、organization、aircraftCode、aircraftSn、
  │          takeoffTime、landingTime、declaredBy、declaredTime、pilot、taskPurpose、
  │          airspaceRoute、approvalStatus、remark
  └─【真实】flightRoute ← plannedRoutes[targetId].flightRoute 原样放置（AMSL，不随机）

请求骨架（派生/固定，不随机）
  ├─【派生】requestId（生成器meta派生）、snapshotTime（←simulationMeta.startTimeMs）
  ├─【固定】外部baseData不含whitelist/flightPlans；drillPlans=[]（I-04暂缓）、
  │          corrections=[]、
  │          options={returnEvidenceChain:true, returnDebug:false}、ruleConfig默认
  └─【元数据】generatorMeta（seed、场景分配表）+ 每个targetId的预期合规结论
```

不生成清单（真实来源或暂缓，见§9）：`uavs_coords_str`（agents02）、`plannedRoutes`（agents02）、`facilities_str/defence_rings`（agents02，源自Apifox空域）、`airspaces/rings`（Apifox `/airspace/list`、`/nofly/list`）、`defenseResources/detectionDevices`（本轮不做）、地标/监所/敏感测绘/机型能力/地面高程（本轮不做）。

首批场景：

```text
valid_whitelist
valid_flight_plan
registered_only
unregistered
unknown_identity
expired_registration
abnormal_pilot
expired_whitelist
rejected_plan
off_route
sn_mismatch
night_unplanned
```

参考样本（字段级模板，2026-08-12 由输入结构对接方提供）：

`apitest/samples/v32_identity_source_sample.json`

- 四份DTO字段与协议§37～§40逐字段一致，作为生成器输出的模板合规基准（阶段D可断言：生成字段⊆样本字段）；
- 生成器设计要点：
  - ID段位：飞手`10xxx`、设备登记`20xxx`、无人机业务`30xxx`、白名单`40xxx`、计划`50xxx`，ID本身可解释；
  - SN风格：`厂商-机型-大写序列`（如`DJI-M300-SN001`），规范化ASCII大写；
  - 日期两类格式：资质/白名单用`YYYY-MM-DD`，登记/保险/起降用`YYYY-MM-DDTHH:MM:SS`（无时区）；
  - `creditScore`为字符串（如`"92.5"`），数值归一化由适配器完成；
  - 白名单`droneSn`与设备实名`serialNo`在真实数据中可以是两本账（样本中`DJI-M300-2BF7A`≠`DJI-M300-SN001`），生成器必须支持SN不匹配场景，不能默认三者同SN；
- `flightPlansBySn[].flightRoute`的`{lng,lat,alt}`与agents02 `plannedRoutes[].flightRoute`结构完全一致（均AMSL），生成器原样搬运，不随机生成航迹点。

要求：

- 固定seed必须得到相同ID、场景分配和标签；
- 影响算法结论的状态由场景配置决定，不能无约束随机；
- 不能给所有Agent都生成有效白名单或有效飞行计划，否则全部在聚类前被豁免；
- 所有有效期相对`simulationMeta.startTimeMs`生成，不使用服务器墙钟；
- 不使用真实个人信息；
- 空域/禁飞区不随机生成：直接读取Apifox响应（`apitest/fetch_airspace_list.py`、`fetch_nofly_list.py`）或现有`facilities_shaoxing.json`链路（来源见§9.2.1）。

### 阶段B：扩展轨迹适配器（✅ 已完成）

已扩展：

`situationawareness latest/tools/agents02_export_to_payload.py`

新增CLI：

```text
--orient-data <模拟或真实四类DTO JSON>
--expected-compliance-output <JSON>
```

新增能力：

1. 校验四个源数组始终存在且为数组；
2. 校验DTO ID唯一；
3. 规范化SN：字符串化、去首尾空格、ASCII字母大写；
4. 校验`targetId↔serialNo`唯一绑定；
5. 校验日期、审批状态和外键；
6. 生成内部完整`targetAttributes`；
7. 归一化内部`baseData.whitelist/flightPlans`；
8. 按每个窗口的`snapshotTime`判断有效期；
9. 调用当前`SituationEngine`并对照预期标签；
10. 日志中不输出完整身份证号、电话和资质证号；
11. 归一化Apifox空域/禁飞区响应→`baseData.rings`/`airspaces`：圆形区（圆心+半径）映射ringType=1；多边形区（geom）映射`airspaces[].geometry`；读取方式兼容"直接拉取"与"已保存样本文件"两种（映射规则见§9.2.1）。

推荐把转换逻辑拆成可测试的纯函数，不要只写在CLI `main()`中。

### 阶段C：实现v3.2唯一外部网关（✅ 已完成）

目标：外部只能提交v3.2源数据结构，网关归一化后再调用当前内部引擎。

必须验证：

- 四类数组缺失、`null`或非数组返回400；
- 外部直接提交内部`registrationStatus/pilotRiskLevel/sourceConflict`等字段返回400；
- 外部只要出现`baseData.whitelist/flightPlans`（包括空数组）就返回`READ_ONLY_NORMALIZED_BASE_DATA_FIELD`；
- 未匹配SN、孤儿飞手、过期记录进入诊断而不是拖垮其他目标；
- 当前`SituationEngine.analyze()`不能绕过网关直接作为v3.2公共入口。

实现文件：`situation_judgment/v32_gateway.py`、`situation_judgment/service.py`、
`tools/build_agents02_v32_requests.py`。重复有效设备实名SN按协议§31.1作为请求级400；
孤儿飞手、未匹配SN和过期记录按目标级诊断处理。

### 阶段D：增加回归测试（✅ 已完成）

已新增或扩展测试：

```text
test_agents02_orient_generator.py
test_v32_source_adapter.py
test_agents02_export_adapter.py
test_situation_judgment.py
test_v32_gateway.py
test_agents02_v32_request_builder.py
test_cluster_preprocessing_regression.py
test_cluster_feature_regression.py
test_agents02_cluster_replay_regression.py
```

必须覆盖：

- 固定seed可重复；
- 13个最新真实目标全部绑定；
- 白名单有效/过期/禁用/SN不匹配；
- 飞行计划批准/驳回/时间外/航内/偏航；
- 一名飞手关联多机；
- 设备实名找不到飞手；
- 重复有效SN冲突；
- 混合快照中只移除豁免目标，其他目标继续聚类；
- 外部唯一格式的禁止字段与固定空数组校验；
- 敏感信息不出现在普通日志和响应；
- 不同时间戳下坐标相同的悬停点不能被删除；
- 对齐不得在目标原始时间范围之外外插；
- 单帧转弯、低速和启停过渡不能造成设计集群瞬时假拆分；
- 冻结71帧纯轨迹回放中三个设计集群必须完整且不得跨群误合并；迁移到新76帧基线时，必须先解决第49帧拆分并同步测试的动态帧数契约。

历史冻结版本全套回归200/200通过；当前工作区为201/202，唯一失败是上述聚类回放基线漂移。v1规则与轨迹特征定向测试26/26通过（含19项直接正例），可视化专项32/32通过。agents02工程另有11项前序基线，
但本轮没有重新运行完整SPADE/Redis/XMPP仿真。

### 阶段E：落实意图范围（✅ 已完成）

2026-08-13三阶段代码与文档任务已一次连续完成，并通过门禁：

1. 结构门禁：可选`exemptTargetResults[].intent`、短运动/长意图双窗口、网关完整保留/派生非敏感业务语义；
2. 架构门禁：默认精确19项、19项独立候选评估器、动态规则置信度、冲突矩阵、稳定统一选择；`facilities[].facilityType`增加`landmark/scenic_spot/prison`，`airspaces[].airspaceType`增加`sensitive_mapping`，白名单增加可选`operationType`；
3. 算法门禁：迁移/优化已有8项，补齐I-01/I-02/I-03/I-05和新增I-08/I-10/I-14/I-17/I-18/I-21/I-22首版算法；
4. 协议门禁：所有输入输出结构变化同步更新v3.2协议、README、工具/可视化说明、样例与测试；
5. 验收门禁：每项至少正例、反例、边界、冲突/缺数据测试，并重新执行公共HTTP回放。

当前可称为“19项首版确定性规则已实现并通过代码回归”；仍不得写成“19项真实准确率已验收”。

### 阶段F：HTTP联调（🟡 本地完成，真实对接方待联调）

已用Flask测试客户端验证公共HTTP入口；2026-08-12新增的PyQt回放台已经自动启动独立Waitress进程，
并通过同一个接口完成历史71/71帧和当前保存76/76帧真实网络回放。阶段F剩余工作是与真实对接方通过：

```text
POST /api/v1/situation/analyze
```

联调唯一外部源数据格式，验证部署网络、HTTP错误码、诊断结构和逐快照行为。

---

## 11. 新对话建议阅读顺序

按以下顺序阅读，可以最快恢复当前状态。

### 第一层：5分钟恢复结论

1. 本文：`agents02与SituationAwareness-v3.2对接_当前进展与新对话恢复指南.md`
2. `situationawareness latest/文档/态势判读算法单接口协议-v3.2.md`
   - §5～§9：完整请求、轨迹、外部`targetAttributes`、`baseData`；
   - §35～§43：四类DTO、SN关联、归一化；
   - §44：agents02模拟数据与适配方案；
   - §45：完整结构树和唯一外部输入格式；
   - §46：完整输出数据结构树，含多候选、空意图和可选`exemptTargetResults[].intent`。
3. `uav_strategy/examples/uavs_strategy/README_agents02.md`
   - 重点阅读§7.1～§7.10。

### 第二层：15分钟恢复实现状态

4. v3.2公共网关与请求组装
   - `situationawareness latest/situation_judgment/v32_gateway.py`：唯一外部格式校验、归一化和诊断；
   - `situationawareness latest/situation_judgment/service.py`：公共HTTP入口；
   - `situationawareness latest/tools/build_agents02_v32_requests.py`：agents02外部请求组装与HTTP回放；
   - `situationawareness latest/tools/agents02_export_to_payload.py`：阶段B离线内部回归入口；
   - `situationawareness latest/visualization/`：实时HTTP回放界面的数据、服务、地图和PyQt主窗口；
5. latest 测试文件（最新全套数字见§13）
   - `tests/test_agents02_orient_generator.py`：生成器seed可复现、场景矩阵、字段模板、13目标绑定；
   - `tests/test_v32_source_adapter.py`：四类DTO校验、归一化、端到端豁免/聚类、偏航用例、对照报告；
   - `tests/test_agents02_export_adapter.py`：基础轨迹适配7类回归；
   - `tests/test_v32_gateway.py`：唯一外部格式、HTTP错误、诊断、冲突和隐私12项回归；
   - `tests/test_agents02_v32_request_builder.py`：请求体结构与最新13目标公共HTTP 13/13回归；
   - `tests/test_v1_intent_rules.py`：19项直接正例、边界/缺数据、多候选稳定选择、禁用范围和空意图定向门禁；
   - `tests/test_intent_replay_data.py`、`test_intent_engine_process.py`、`test_intent_map_renderer.py`、`test_intent_replay_visualizer.py`：可视化、豁免意图和空意图展示链路；
   - `tests/test_cluster_preprocessing_regression.py`、`test_cluster_feature_regression.py`：悬停/时间对齐、低速/转弯运动特征11项；
   - `tests/test_agents02_cluster_replay_regression.py`：冻结71帧三个设计集群完整性与跨群误合并门禁；当前需要迁移为显式基线或动态帧数契约；
6. `uav_strategy/examples/uavs_strategy/uav_dynamic_agents02.py`
   - `build_complete_flight_plan_export()`；
   - `save_trajectories()`；
   - 统一时钟初始化；
7. `uav_strategy/examples/uavs_strategy/behaviors_modules/uav_periodic_behaviours.py`
   - 常量与`bounded_motion_step()`；
8. `uav_strategy/tests/test_agents02_trajectory_contract.py`
   - 统一时钟、轨迹阶段、物理步进和完整计划航迹测试。

### 第三层：恢复算法与范围

9. `意图与威胁算法研发表-v2.0.1.xlsx`
   - 意图目录和数据依赖的源真值；红色为暂缓，黄色记录I-28原待定状态；当前v1执行范围以协议19项白名单为准，I-28已明确禁用；
10. `群智大脑原型-AI态势研判-意图与威胁规则.md`
    - 规则背景；若与Excel范围冲突，以用户指定的v2.0.1 Excel为准；
11. `situationawareness latest/situation_judgment/engine.py`和`intent_rules.py`
    - `SituationEngine.analyze()`：长短窗口、豁免、聚类、意图与威胁主链；
    - `_intent_feature_frame()`：从目标/空间/群体/合规数据构建统一内部特征；
    - `intent_rules.py`：19项独立评估器、`IntentCandidate`、空意图和统一选择；
    - `_threat()`：只消费选中的主意图；
12. `situationawareness latest/tests/test_situation_judgment.py`和`tests/test_v1_intent_rules.py`
    - 前者覆盖引擎契约、豁免、威胁、防御、修正和公共意图结构；后者覆盖首批19项独立规则与统一选择。

### 辅助文档

- `situationawareness latest/agents02_to_situation_judgment_接入清单.md`
  - 记录基础轨迹适配器的完成过程；
  - 其中默认`registrationStatus="unregistered"`及旧六数组说明反映的是当前基础代码，不是最新v3.2外部协议最终状态；
- `situationawareness latest/文档/HANDOVER.md`
  - latest服务整体交接；
- `situationawareness latest/README.md`
  - **latest项目当前入口**：v3.2单接口、代码职责、聚类修复、启动/回放/测试和当前未决事项；**§3.1 标准输入输出使用示例**（真实请求+真实响应，2026-08-12 实测）；§9 部署与交付（测试方）；文末`/get_*`与HAProxy内容仅作兼容参考；
- `situationawareness latest/tools/README.md`
  - **生成器与适配器脚本说明**：工具链总览、各自职责/用法/参数、数据契约、测试命令、参考文档位置（2026-08-12 新建）；
- `situationawareness latest/visualization/README.md`
  - **实时HTTP回放界面说明**：正确输入文件、服务自动启停、回放操作、结果面板、导出和测试；
- `situationawareness latest/README.md` §9（部署与交付）
  - **测试部署交付章节**（2026-08-12 并入主README）：交付内容/可删目录、conda建环境、启动31607服务、curl验证、批量回放71请求命令、常见问题；跨城市交付时连同协议文档一起发给测试方；原独立《部署说明-测试环境.md》已删除；
- `situationawareness latest/hunter_feed_adapter.py`
  - 可参考`build_analyze_payload()`，但不要绕过最新v3.2源数据约束；
- `uav_strategy/examples/uavs_strategy/uav_key_path.asl`
  - 只在检查SPADE-BDI规划时阅读；`is_waiting`不是其信念变量；
- `apitest/fetch_airspace_list.py`、`apitest/fetch_nofly_list.py`
  - Apifox测试地址空域/禁飞区拉取脚本（当前无鉴权）；空域样例见`apitest/samples/airspace_list_sample.json`；
- `apitest/samples/v32_identity_source_sample.json`
  - 对接方提供的飞手实名/设备实名/白名单/飞行计划字段模板；生成器输出对齐该结构，字段与协议§37～§40一致；
- `uav_strategy/examples/uavs_strategy/data/gen_facilities_shaoxing.py`
  - 演示"Apifox空域→facilities_shaoxing.json→agents02 facilities/defence_rings"的已有转换，可参考其圆形离散化方式。

---

## 12. 文档与代码的真值优先级

出现不一致时按以下顺序判断：

1. `意图与威胁算法研发表-v2.0.1.xlsx`：意图范围、暂缓项、规则依赖；
2. `态势判读算法单接口协议-v3.2.md`：唯一外部请求和四类DTO协议目标；
3. 当前Python代码和测试：判断“现在是否真的能运行”；
4. `situationawareness latest/README.md`：latest当前功能、调用链、启动、回放、聚类修复和验证摘要；
5. `README_agents02.md`：agents02改造事实和验证记录；
6. `agents02_to_situation_judgment_接入清单.md`：基础适配历史，部分内容可能落后于v3.2最终协议；
7. 其他旧版v3.1文档或早期输出：仅作兼容参考。

不要把核心引擎函数声称为原生v3.2 DTO入口；公共v3.2能力由网关实现。也不要因为基础适配器能直连引擎，就把它当作另一种合规的外部格式。

---

## 13. 环境与验证命令

根目录`.conda-env`内容为：

```text
study
```

环境分工（2026-08-12 实测验证）：

| 环境 | 用途 | 验证情况 |
|---|---|---|
| `study` | agents02（uav_strategy）测试与一般脚本 | 11项agents02测试通过 |
| `study_flask` | latest 服务、测试与PyQt可视化 | 已装完整科学计算/Flask/PyQt依赖；最新全套结果见§13 |

注意：`study` 环境缺少 flask，latest 测试会报 `ModuleNotFoundError: No module named 'flask'`，必须在 `study_flask` 中执行，不要据此误判依赖缺失。也不要为 `study` 额外安装 flask，避免两个环境职责重叠。

agents02逻辑测试：

```powershell
Set-Location "E:\CASIA\Drone_Swarm_SituationSensingAlgos\Collective Intelligence Brain\uav_strategy"
conda run -n study python -m unittest discover -s tests -p "test*.py" -v
```

latest适配器测试：

```powershell
Set-Location "E:\CASIA\Drone_Swarm_SituationSensingAlgos\Collective Intelligence Brain\situationawareness latest"
conda run -n study_flask python -m unittest tests.test_agents02_export_adapter -v
```

latest核心测试：

```powershell
conda run -n study_flask python -m unittest tests.test_situation_judgment -v
```

生成器单测（无需flask，用study）：

```powershell
conda run -n study python -m unittest tests.test_agents02_orient_generator -v
```

v3.2源数据适配测试（study_flask）：

```powershell
conda run -n study_flask python -m unittest tests.test_v32_source_adapter -v
```

生成器示例（旧导出无 missionMeta 时加 `--mission-meta outputs/agents02_mission_meta.json`；
seed=7 为混合语义基线：合法detour豁免+非法集群入簇；seed=42 时 detour 随机全为对抗）：

```powershell
conda run -n study python tools/generate_agents02_orient_test_data.py `
  --export "../uav_strategy/examples/uavs_strategy/data/raw_data/uav_trajectories_persistent_20260812_131556.json" `
  --seed 7 --mission-meta outputs/agents02_mission_meta.json `
  --output outputs/agents02_orient_data.json `
  --expected-output outputs/agents02_expected_labels.json
```

**数据管线（2026-08-13新增，一条命令跑生成器→请求组装→回放+合规对照；agents02仿真保持手动）：**

```powershell
powershell -ExecutionPolicy Bypass -File run_data_pipeline.ps1 `
  -Export "../uav_strategy/examples/uavs_strategy/data/raw_data/uav_trajectories_persistent_20260813_015307.json" `
  -Seed 7
```

新导出自动携带 missionMeta，无需 `-MissionMeta`（旧导出才加 `-MissionMeta outputs/agents02_mission_meta.json`）。
管线输出文件名带 **`<导出时间戳>_seed<seed>` 标签**（如
`outputs/agents02_v32_http_requests_20260813_015307_seed7.json`），不同样本或不同 seed 的运行互不覆盖。

旧导出补 missionMeta 桥接文件（在 uav_strategy 目录执行）：

```powershell
python "../situationawareness latest/tools/build_mission_meta_from_export.py" `
  "examples/uavs_strategy/data/raw_data/uav_trajectories_persistent_20260812_131556.json" `
  --digraph "examples/uavs_strategy/data/manual_plan_graph/manual_plan_graph01_digraph_attrs.json" `
  --output "../situationawareness latest/outputs/agents02_mission_meta.json"
```

基础轨迹适配器示例：

```powershell
conda run -n study python tools/agents02_export_to_payload.py `
  "../uav_strategy/examples/uavs_strategy/data/raw_data/uav_trajectories_persistent_20260812_131556.json" `
  --output outputs/agents02_analyze_payloads.json `
  --require-all-targets `
  --call-engine
```

v3.2端到端（生成器→适配器→引擎→合规对照，2026-08-12验证13/13匹配）：

```powershell
conda run -n study python tools/generate_agents02_orient_test_data.py `
  --export "../uav_strategy/examples/uavs_strategy/data/raw_data/uav_trajectories_persistent_20260812_131556.json" `
  --seed 42 --output outputs/agents02_orient_data.json `
  --expected-output outputs/agents02_expected_labels.json
conda run -n study python tools/agents02_export_to_payload.py `
  "../uav_strategy/examples/uavs_strategy/data/raw_data/uav_trajectories_persistent_20260812_131556.json" `
  --output outputs/agents02_v32_payloads.json `
  --orient-data outputs/agents02_orient_data.json `
  --expected-compliance-output outputs/agents02_expected_labels.json `
  --require-all-targets --call-engine --compliance-report outputs/agents02_compliance_report.json
```

唯一v3.2外部请求体生成（阶段C/D）：

```powershell
conda run -n study python tools/build_agents02_v32_requests.py `
  "../uav_strategy/examples/uavs_strategy/data/raw_data/uav_trajectories_persistent_20260812_131556.json" `
  --orient-data outputs/agents02_orient_data.json `
  --track-source uavs_coords_raw --require-all-targets `
  --output outputs/agents02_v32_http_requests.json
```

标准单次请求示例（读单个请求体 → POST → 打印响应摘要，可选保存；2026-08-12 实测 HTTP 200/code 0、3 集群）：

```powershell
conda run -n study python tools/send_single_v32_request.py `
  outputs/agents02_http_request_sample.json `
  --output outputs/agents02_single_request_result.json
```

已保存请求包的本地公共路由回放与结果收集：

```powershell
conda run -n study_flask python tools/replay_v32_request_bundle.py `
  outputs/agents02_v32_http_requests.json `
  --output outputs/agents02_v32_http_results.json `
  --expected-compliance-output outputs/agents02_expected_labels.json `
  --compliance-report outputs/agents02_v32_http_compliance.json
```

冻结历史raw轨迹基线保存了71个完整响应，71/71请求成功、0失败，目标级合规对照923/923匹配；当前默认无时间戳请求/结果包已切换为76帧，76/76请求成功、合规对照988/988。单次标准样例实测HTTP 200/code 0，13个输入目标中10个进入分析、3个豁免，共形成3个集群。这些数字验证接口链路与合规语义，不代表19项真实意图准确率。

PyQt实时HTTP回放界面（会自动启动或复用31607算法服务）：

```powershell
run_intent_replay_visualizer.bat
```

也可以启动后直接载入`requests[]`请求包；当前默认包为76帧，界面不依赖固定帧数：

```powershell
conda run --no-capture-output -n study_flask python visualization/intent_replay_visualizer.py `
  outputs/agents02_v32_http_requests.json
```

可视化模块回归：

```powershell
$env:QT_QPA_PLATFORM="offscreen"
conda run -n study_flask python -m unittest discover -s tests -p "test_intent_*.py" -v
```

公共网关与真实13目标HTTP回归（study_flask）：

```powershell
conda run -n study_flask python -m unittest tests.test_v32_gateway -v
conda run -n study_flask python -m unittest tests.test_agents02_v32_request_builder -v
```

历史基线：2026-08-12聚类稳定性修复后当时latest全套141/141通过；该数字只是当时快照，不是当前总数。

业务回放保留两组可追溯证据：旧冻结raw轨迹为71个13目标请求、923/923合规且71/71成功；当前默认保存包为76帧、988/988合规且76/76成功。
另有14个初始候选快照因尚未形成全目标有效窗口而跳过。本轮未重新运行完整SPADE/Redis/XMPP仿真。

2026-08-13集群语义分配改造后的历史中间快照曾为latest全套178项、agents02契约15项通过；随后冻结阶段曾达到200/200。当前工作区共202项，201项通过、1项失败：旧聚类回放门禁硬编码71帧，而默认包已为76帧；将断言改为动态后还会暴露第49帧`agent_1`的1+3拆分。因此200/200只能作为历史冻结证据，不能表述为当前全量门禁。
管线以 seed=7 + missionMeta 重生成保存基线：swarm1（detour→合法绕飞）每帧整组WHITELIST豁免，
swarm2（detour→对抗）/swarm3（breakthrough突防）全部入簇——逐帧2集群、共142集群、0豁免混编，
集群成员逐帧与设计集群完全一致；71/71成功、合规对照923/923。seed=42时detour随机均为对抗：
0豁免、逐帧3集群、共213集群。纯轨迹聚类回归（不带合规数据）不受seed影响，仍为逐帧3集群213。
当前保存的`outputs/`基线为两组带时间戳的 seed=7 混合语义版（管线输出名含
`<导出时间戳>_seed<seed>`，互不覆盖）：旧导出`20260812_131556`（71帧、923/923）与
新导出`20260813_015307`（76帧、988/988）。

---

## 14. 新对话可直接使用的开场提示

```text
请先阅读根目录《agents02与SituationAwareness-v3.2对接_当前进展与新对话恢复指南.md》，
再阅读 situationawareness latest/文档/态势判读算法单接口协议-v3.2.md 的§7、§9.3、§13、§22.2、§35～§46，
以及 uav_strategy/examples/uavs_strategy/README_agents02.md 的§7。

阶段A～E与本轮三阶段代码任务均已完成：生成器提供四类DTO+SN绑定+预期标签；离线适配器复用生产归一化；
v32_gateway.py已接入POST /api/v1/situation/analyze并强制唯一源数据格式；
build_agents02_v32_requests.py默认从uavs_coords_raw生成requests[]。PyQt回放台以requests[]为输入，自动启动/复用31607服务，
逐帧真实POST并显示轨迹、集群包络和analysisResult。聚类已修复悬停点删除、时间外插、单步运动特征和低速方向问题；
轨迹现为每请求自包含最近120秒/240点长意图窗口，运动/聚类默认只取尾部12点。网关完整保留/派生算法需要的非敏感业务语义；
`exemptTargetResults[].intent`已作为可选兼容字段落地，只评估I-01/I-02/I-03/I-05。v1默认精确19项`enabledIntentCodes`，每项独立评分后统一稳定选择；
I-28明确禁用，无候选返回空意图并要求人工复核。法定禁飞候选固定最高优先；成员级空间候选只列实际命中成员。v1规则与轨迹特征定向26/26、可视化专项32/32通过；
历史冻结全量为200/200、raw样本HTTP 71/71且合规923/923。当前默认保存包为76帧，HTTP 76/76且合规988/988；当前全量为201/202，剩余1项是聚类回放基线漂移（旧71帧断言及第49帧拆分），不得误写为算法全绿。白名单/计划成员是否参与物理聚类仍等待会议决定，当前保持聚类前豁免。
模拟数据验证不能等同于真实感知准确率，后续仍需真实标注数据校准和精度验收。
阶段F的本地独立服务联调已完成，剩余真实调用方/部署网络联调。

2026-08-13另完成语义一致性改造：agents02导出新增missionMeta（集群任务语义：orderType/target/fleetNo/leaderId/memberIds）；
生成器改为集群级语义分配——13场景分illegal/legal/gray三家族，breakthrough固定illegal、
detour由seed随机illegal/legal、未知回落gray，集群内所有成员同场景，不再单机盲洗牌；
新增run_data_pipeline.ps1/.bat数据管线（生成器→请求组装→回放+合规对照一条命令，agents02仿真保持手动），
旧导出用build_mission_meta_from_export.py桥接。保存基线：seed=7混合语义（swarm1合法detour整组豁免、
swarm2对抗detour与swarm3突防入簇，142集群）；该冻结版本全量200/200，71帧HTTP回放与923个目标级合规对照全部通过。当前默认76帧包的HTTP与合规为76/76、988/988，但聚类回放门禁仍有上述1项待收口。
```

---

## 15. 下一阶段完成标准

完成下一阶段时至少应满足：

- 生成器固定seed重复运行输出一致；
- 场景分配与missionMeta集群任务语义一致：同一设计集群内所有目标同场景且同家族，不出现合法/非法混编；
- breakthrough集群固定illegal家族，detour集群在illegal/legal内由seed确定性选择，未知orderType回落gray并诊断；
- 旧导出无missionMeta时按plannedRoutes segmentKey回落分组，或经build_mission_meta_from_export.py桥接；
- 数据管线run_data_pipeline.ps1一条命令完成生成→组装→回放+合规对照，失败即停；agents02仿真不在管线内；
- 最新13个agents02目标都有可解释的SN和场景标签；
- 四类DTO外键全部可解释，冲突有诊断；
- `flightPlansBySn.flightRoute`来自`plannedRoutes`；
- 唯一v3.2外部请求通过网关校验；
- 适配器生成内部`targetAttributes/baseData.whitelist/baseData.flightPlans`；
- 白名单和计划的有效、过期、驳回、偏航、SN不匹配正反例都符合预期；
- `baseData.rings/airspaces`可由Apifox空域/禁飞区响应归一化得到（圆形→ringType=1，多边形→airspaces.geometry），且与agents02 `facilities_str/defence_rings`空间一致；
- 混合快照中豁免目标被单独移除，其他目标仍进入聚类；
- 证据充分的豁免目标通过可选`exemptTargetResults[].intent`输出I-01/I-02/I-03/I-05；普通白名单不误标I-03；
- 请求轨迹自包含60～120秒意图历史且有最大点数约束，运动/聚类只消费尾部短窗；
- 19项各有直接正反例、边界和冲突/缺数据测试，主意图与`topCandidates[0]`一致；
- 无合格候选返回空意图、`topCandidates=[]`和人工复核，不输出I-28；
- 暂缓意图不会被当前v1范围错误输出；
- 日志和响应不泄露个人敏感信息；
- 将来用真实GetOrientParam响应替换模拟JSON时，后续归一化和SituationEngine调用无需重写。
