# 群智大脑 · 工程总览（Collective Intelligence Brain）

> 本目录聚合了"无人机集群态势感知与判读"相关的三个工程：**uav_strategy**（集群轨迹生成/仿真）、**situationawareness latest**（态势判读算法服务，现行版）、**SituationAwareness Origin**（态势判读旧版，Latest 的前身）。
>
> 本文档描述三个工程之间的**关系与协作方式**；各工程内部细节见各自的 README。

---

## 1. 工程关系总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                      Collective Intelligence Brain                  │
│                                                                     │
│  ┌──────────────────────┐        ┌───────────────────────────────┐  │
│  │   uav_strategy        │        │   situationawareness latest   │  │
│  │   （轨迹生成/仿真）     │ ──轨迹──▶ │   （态势判读算法服务，现行版）  │  │
│  │   agent02 集群轨迹     │  JSON  │   SituationEngine.analyze()  │  │
│  │   SPADE+BDI+Redis     │        │   聚类→编队→意图→威胁→防御      │  │
│  └──────────────────────┘        └──────────────┬────────────────┘  │
│                                                  │ 同源演进（改进版）  │
│                                                  ▼                  │
│                              ┌───────────────────────────────┐      │
│                              │   SituationAwareness Origin    │      │
│                              │   （旧版，Latest 的前身）        │      │
│                              │   + 后续新增：队形识别算法/       │      │
│                              │     队形数据生成                │      │
│                              └───────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────┘
```

三个工程的角色一句话：

- **uav_strategy**：造"世界"——多无人机集群在防御区域内按航段图执行任务，生成符合真实行为的集群轨迹。
- **situationawareness latest**：读"世界"——把某时刻的飞行目标轨迹 + 设施/圈层基础数据，判读出集群、编队、意图（I-01~I-30）、威胁和防御建议。
- **SituationAwareness Origin**：Latest 的旧版本地基，Latest 在其上改进；Origin 侧后续增量以**队形识别算法**与**队形数据生成**为主。

---

## 2. uav_strategy（集群轨迹生成/仿真）

**定位**：多无人机集群任务仿真主程序。所有无人机作为独立 BDI Agent（SPADE + spade_bdi + Redis），按航段图拆分为航段任务，同步编队飞行。

- 主程序：`uav_strategy/examples/uavs_strategy/uav_dynamic_agents02.py`（agent02，`switch_config` 1~6 切换场景，config 6 为 shaoxing 地图）
- 核心能力：航段规划（detour/breakthrough/escape/orbit/loiter）、编队成员轨迹生成（`FormationGenerator3D`）、round 同步 barrier、航段依赖闸、轨迹导出（UTM↔经纬度自动转换）
- 详细说明见：`uav_strategy/examples/uavs_strategy/README_agents02.md`

**产出**：`data/raw_data/uav_trajectories_persistent_*.json`（每架无人机的 lng/lat 轨迹 + 逐帧 extras），以及运行期间的 Redis 实时数据。

## 3. situationawareness latest（态势判读算法服务，现行版）

**定位**：v3.2单接口态势判读算法服务。调用方把“同一快照的全部飞行目标自包含轨迹 + 源业务数据 + 有效人工修正”一次性传入；公共网关先完成四类源DTO校验、SN关联和内部归一化，再执行轨迹清洗、DBSCAN聚类、编队识别、首批19项意图独立候选评分、十维威胁和防御评估。

- 核心入口：`situationawareness latest/situation_judgment/engine.py` → `SituationEngine.analyze()`
- 公共网关：`situationawareness latest/situation_judgment/v32_gateway.py`（唯一外部v3.2源数据格式 → 内部算法格式）
- 接口协议：`situationawareness latest/文档/态势判读算法单接口协议-v3.2.md`（`POST /api/v1/situation/analyze`）
- 接口与规则测试：`situationawareness latest/tests/test_v32_gateway.py`、`situationawareness latest/tests/test_situation_judgment.py`、`situationawareness latest/tests/test_v1_intent_rules.py`
- agents02接入工具：`situationawareness latest/tools/generate_agents02_orient_test_data.py`、`situationawareness latest/tools/build_agents02_v32_requests.py`、`situationawareness latest/tools/replay_v32_request_bundle.py`
- 实时批量可视化：双击`run_intent_replay_visualizer.bat`，加载`adapterMeta + requests[]`请求包

## 4. uav_strategy ↔ latest：如何协作

**协作链路**：agent02生成集群轨迹和`missionMeta`任务语义 → 独立生成器补齐四类源业务DTO → 请求组装器生成滑动窗口请求包 → v3.2公共HTTP网关 → `SituationEngine.analyze()`。**uav_strategy是轨迹与任务真值生产者，latest是请求构建、归一化和态势判读消费者。**

```text
agent02 仿真运行（Redis / 导出 JSON）
        │  uavs_coords_raw/uavs_coords_str + plannedRoutes + missionMeta
        ▼
generate_agents02_orient_test_data.py
        │  targetAttributes + 四类源DTO + 场景预期标签
        ▼
build_agents02_v32_requests.py
        │  adapterMeta + requests[]（默认120秒/240点意图长窗）
        ▼
POST /api/v1/situation/analyze → v32_gateway → SituationEngine.analyze()
        ▼
集群分析结果（clusterDtoList / eventSuggestions / 意图/威胁/防御）
```

**协作要点**（细节见[当前进展与恢复指南](./agents02与SituationAwareness-v3.2对接_当前进展与新对话恢复指南.md)、[latest tools说明](./situationawareness%20latest/tools/README.md)和[历史接入清单](./situationawareness%20latest/文档/agents02_to_situation_judgment_接入清单.md)；历史清单部分内容早于v3.2最终契约）：

| 事项 | 说明 |
|---|---|
| 坐标口径 | 两边都基于 **UTM zone 51** 往返转换经纬度，协议已知边界与 agent02 硬编码一致，坐标系零适配 |
| 轨迹契约 | 每目标≥6点、`ts` epoch毫秒严格递增、`alts`可选；默认每请求保留最近120秒且最多240点，引擎只取尾部12点做运动与聚类 |
| 目标 ID | agent02 的 `agent_x_y` 直接作为稳定 `targetId`，跨快照复用 |
| 多目标快照 | 一次 analyze = 一个时刻的全部在飞目标；agent02 的 round 同步保证同段成员步调一致，天然适合集群/蜂群意图（如 I-26）识别 |
| 源业务DTO | 外部固定使用`realPersons/dronesBySerialNos/droneWhitelistDtos/flightPlansBySn`四类数组；公共`baseData`不直接接收内部`whitelist/flightPlans` |
| 集群任务语义 | 新导出携带`missionMeta.swarms[]`；旧导出可用`situationawareness latest/tools/build_mission_meta_from_export.py`桥接，避免同一设计集群内合法/非法场景混编 |
| 一键管线 | `situationawareness latest/run_data_pipeline.ps1/.bat`串联生成器、请求组装、HTTP回放和合规对照；agents02仿真本身仍手动运行 |

**队形识别的衔接点**：uav_strategy 的编队轨迹生成（`planning_modules/formation_generator.py` 的 `Formation_Elements`/`FormationGenerator3D`）与 Origin 侧 `formation_recognition/formation_generator.py` 类名与参数一致（疑似同源迁移），而 latest 引擎的编队识别走 `legacy_rnn_model`（协议 §29 algorithmDiagnostics）——**生产者（uav_strategy）的编队几何 ↔ 消费者（latest）的编队识别模型**之间可形成训练/回灌闭环（详见 §6）。

## 5. situationawareness latest ↔ SituationAwareness Origin：同源演进

**关系**：latest 是在 Origin 旧版本的基础上重构改进的（两者共享同名模块骨架：`formation_recognition/`、`simulated_environment/`、`test_main0x_*.py` 系列等；latest 的 `README.md` 甚至保留了 Origin 版旧文档开头）。latest 的改进方向是**单接口化**：把分散的多接口（get_uavs_clusters 等）收敛为 `POST /api/v1/situation/analyze` 单接口，并补齐协议化校验、人工修正（corrections）、豁免（白名单/飞行计划/演练计划）、防御评估等能力。

**Origin 侧后续新增的两块核心内容**（Latest 尚未完整吸收的部分）：

### 5.1 队形识别算法 — `SituationAwareness Origin/test_main01_clusters.py`

队形识别（训练/测试/推理）的主入口，通过 `func_sw` 开关切换多种模式：手工聚类数据绘制、聚类划分、单个队形类别可视化、**队形识别训练数据生成**、独立测试已训练权重（不参与梯度/早停/LR）、参数加载验证等。

- 依赖：`formation_recognition/formation_recognition.py`（RNN 队形识别模型）、`clusters_recognition.py`（聚类划分）、`simulated_environment/sim_swarm_formation_generate.py`（队形仿真生成）
- 权重：`pretrained_weights/`

### 5.2 队形数据生成方法 — `SituationAwareness Origin/formation_recognition/formation_generator.py`

队形样本生成器，核心为 `Formation_Elements`（队形参数：成员数/半径/角度/偏移/噪声/队形类型 `vshape/circular/...`）与 `FormationGenerator3D`（基于基准轨迹生成 3D 队形成员轨迹）。**该模块与 uav_strategy 侧 `planning_modules/formation_generator.py` 同源**——uav_strategy 在仿真中生成编队轨迹用的就是同一套参数体系。

### 5.3 Origin ↔ Latest ↔ uav_strategy 的三方关系

```text
Origin（旧版地基）
 ├─ 队形识别算法（test_main01_clusters.py + formation_recognition/）  ─┐
 ├─ 队形数据生成（formation_generator.py: Formation_Elements） ───────┼─▶ 迁移到
 └─ 旧版多接口服务（get_uavs_clusters 等）                             │    uav_strategy
                                                                      │    （planning_modules/formation_generator.py）
        ▼ 重构改进                                                            │
latest（现行版）
 ├─ 单接口 SituationEngine.analyze()  ←── 消费 uav_strategy 的集群轨迹 ──┘
 └─ 编队识别使用 legacy_rnn_model（从 Origin 继承）
```

## 6. 目录速查

| 顶层内容 | 说明 |
|---|---|
| `uav_strategy/` | 集群轨迹生成/仿真工程（agent02 等） |
| `situationawareness latest/` | 态势判读算法服务（现行版），含协议文档与接入清单 |
| `SituationAwareness Origin/` | 态势判读旧版（Latest 前身），含队形识别算法与队形数据生成 |
| `apitest/` | 空域/禁飞区接口联调工具与样本 |
| `outputs/` | 意图覆盖矩阵、数据交接等分析产物 |
| `意图与威胁算法研发表-v2.0.1.xlsx`、`群智大脑原型-AI态势研判-意图与威胁规则.md` | 顶层需求/规则文档 |

## 7. 建议的协作工作流

1. **跑轨迹**：`uav_strategy`运行agent02，导出包含实际轨迹、计划航迹和`missionMeta`的JSON。
2. **生成业务数据**：运行`generate_agents02_orient_test_data.py`，按集群任务语义生成身份、白名单、计划和预期标签。
3. **组装与回放**：优先运行latest根目录`run_data_pipeline.ps1/.bat`；也可分步执行请求组装与HTTP回放。
4. **查看结果**：双击`run_intent_replay_visualizer.bat`，加载`*_http_requests.json`，查看多候选、触发成员、诊断、长短窗口和趋势。
5. **回灌（可选）**：用uav_strategy/Origin的`FormationGenerator3D`生成带标注队形数据，训练或更新latest复用的队形识别模型。
