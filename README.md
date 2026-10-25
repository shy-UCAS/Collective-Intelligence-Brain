# 群智大脑 · 工程总览（Collective Intelligence Brain）

> 文档同步日期：2026-10-22。本文描述本地工作树中的已实现功能、工程关系与设计进展；在线部署版本应另核对服务元数据和镜像身份。
>
> 当前分析接口为v3.2，OpenAPI契约为3.2.2，规则版本为 `situation-rule-v2.3.0`。

## 1. 工程关系与当前进展

| 工程或资料 | 角色 | 当前状态 |
|---|---|---|
| `uav_strategy/` | 原agents02集群任务仿真，使用SPADE、BDI、Redis | 生成轨迹、计划航线和任务语义 |
| `uav_strategy_pure_py/` | agents02纯Python实现，使用内存状态与中央轮次循环 | 已实现；不依赖SPADE、XMPP或Redis，导出可供latest管线消费 |
| `situationawareness latest/` | 当前态势判读服务、请求组装、测试与回放 | 已实现v3.2分析链路、19项规则意图、单机/集群结果、十维威胁和基础防御评估 |
| `SituationAwareness Origin/` | 旧版算法、队形训练与数据生成参考 | 历史工程，不作为v3.2公共服务入口 |
| `uav_facility_bridge_design_v1/` | 设施趋向与抵达时间预测设计包 | 已形成设计、Schema及数学/契约核验；完整预测服务尚未实现 |
| `uav_strategy_pure_py/GROUND_TRUTH_EXPORT_SPEC.md` | 显式仿真真值导出规格 | 已形成规格；当前导出代码尚未写入 `groundTruth` |

```text
原agents02（SPADE/Redis） ─┐
                         ├─ 轨迹 + plannedRoutes + missionMeta
纯Python仿真（内存状态） ─┘                 │
                                         ▼
                             latest业务DTO生成与请求组装
                                         │ v3.2 requests[]
                                         ▼
                            网关 → SituationEngine.analyze()
                                         │
                         集群/单机意图、威胁、空间关系与防御建议
                                         ▼
                              HTTP回放、PyQt展示与结果导出

真实HTTP入参日志 / 完整原始请求轨迹 → 日志转换 / 长轨迹切片 → 同一分析与回放入口
```

latest由Origin旧版代码演进而来，正式编队识别现使用 **PointNet**，诊断名称为 `pointnet_model`；旧RNN模块的存在不代表当前服务仍使用RNN。

## 2. 两条仿真生产路径

原版入口为 `uav_strategy/examples/uavs_strategy/uav_dynamic_agents02.py`，通过航段图执行绕行、突防、逃逸、绕飞和等待等任务，包含成员编队轨迹生成、轮次同步与航段依赖控制。详细说明见 [README_agents02.md](./uav_strategy/examples/uavs_strategy/README_agents02.md)。

纯Python入口为 `uav_strategy_pure_py/main.py`，用普通Python对象、内存字典和确定性中央轮次循环替代Agent调度与Redis。**从本仓库根目录**在PowerShell 7执行：

```powershell
conda run -n llm --no-capture-output python -m uav_strategy_pure_py.main --seed 42
```

输出为 `uav_strategy_pure_py/outputs/uav_trajectories_pure_<时间戳>.json`。两条路径都提供以下数据，供下游按用途选取：

- `uavs_coords_raw`：完整生命周期轨迹；请求组装默认使用它。
- `uavs_coords_str`：筛选后的同步任务轨迹，不应将末点直接当作任务抵达时刻。
- `plannedRoutes`、`missionMeta`：计划航线与集群任务语义。
- `simulationMeta`、`facilities_str`、`defence_rings`、`airspaces`：仿真时钟与空间数据。

详细说明见 [纯Python仿真 README](./uav_strategy_pure_py/README.md)。其中尚未同步的旧 `study` 命令，以本仓库环境规则和本页命令为准。

## 3. latest 已实现能力

| 能力 | 当前实现与边界 |
|---|---|
| 公共网关 | 校验四类源DTO，完成 `targetId → serialNo → 设备/飞手/白名单/飞行计划` 关联；公共 `baseData` 不直接接收内部 `whitelist/flightPlans` |
| 轨迹处理 | 最低有效点数读取 `config/service.ini` 的 `least_point`，范围2至240，本机当前为2、缺项默认6；重复时间戳保留最后一条记录，倒序仍拒绝，去重和截窗后再次检查点数 |
| 窗口 | 默认最近120秒且最多240点用于意图，尾部最多12点用于运动与聚类；每请求自包含历史，不依赖上次请求留下的轨迹记忆 |
| 聚类与编队 | 可靠度感知DBSCAN、PointNet与失败降级；当前集群ID随成员集合变化，尚非跨请求持续群体身份 |
| 意图 | 首版19项独立候选评估与稳定排序；单机读取 `data.targetIntentResults[]`，集群读取 `data.analysisResult.clusterDtoList[]` 或 `data.eventSuggestions[]`；I-28禁用，无候选时返回空意图并要求复核 |
| 时间判据 | I-05/I-10/I-15悬停门槛为10秒；I-24在请求内重算5个时刻，至少3次有效且3次命中，并检查最新仍抵近；其专属历史要求不随通用点数门槛降低 |
| 空间与威胁 | 统一内部SpatialContext；默认关联范围按距候选空域最外层warning边界5000米判断；空间不相关时威胁默认封顶35，空间未知时保守复核；提供集群和成员独立十维评分 |
| 业务输出 | 单机圈层/禁飞区结果、豁免、人工修正、事件建议及基础防御资源评估；事件建议不等于后端正式事件 |
| 回放工具 | 仿真请求包回放、真实日志转包、长轨迹按多机统一时间轴切片、单机/集群结果展示和结果导出 |
| 部署 | Docker镜像与外部INI挂载；同进程分析/元数据端口31607、地图刷新端口31608；地图参数下一轮刷新生效，轨迹最低点数修改需重启 |

正式入口为 `main_situation_judgment_service.py` → `situation_judgment/service.py` → `v32_gateway.py` → `SituationEngine.analyze()`。详细边界见 [latest README](<./situationawareness latest/README.md>)、[完整v3.2协议](<./situationawareness latest/文档/态势判读算法单接口协议-v3.2.md>)及 [HANDOVER](<./situationawareness latest/文档/HANDOVER.md>)。

## 4. 数据管线、运行环境与交付

仿真先独立运行；在 `situationawareness latest/` 目录启动下游管线：

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File ./run_data_pipeline.ps1 `
  -Export "../uav_strategy_pure_py/outputs/uav_trajectories_pure_<时间戳>.json" `
  -Seed 42
```

将占位文件名替换为实际导出。流水线依次生成四类业务DTO及预期标签、组装请求、使用进程内Flask正式路由回放并做合规对照；第三阶段无需另起HTTP服务。需要真实网络回放时使用 `tools/replay_v32_http_bundle.py`，或者运行 `run_intent_replay_visualizer.bat` 加载请求包。

| 执行范围 | 环境 |
|---|---|
| 根目录工具、原agents02、纯Python仿真 | `llm` |
| latest与Origin的Python服务、测试和可视化 | `study_flask` |
| `run_data_pipeline.ps1` 阶段1/2与阶段3 | 启动器分别选择 `llm`、`study_flask` |
| Docker交付接收方 | 运行镜像，无需本机Python/Conda |

Python使用 `conda run -n <环境> --no-capture-output python ...`；Windows命令使用PowerShell 7。按最近的 `.conda-env` 和项目AGENTS执行，不向 `llm` 安装Flask来修复服务环境。

开发机服务启动命令（在latest目录）：

```powershell
conda run -n study_flask --no-capture-output python main_situation_judgment_service.py 31607
```

Docker交付保留镜像TAR、校验文件、交付版Compose、完整 `config/` 和部署说明；正式交付另附匹配该镜像的开源材料。完整清单与验证步骤见 [latest README §9](<./situationawareness latest/README.md#9-部署与交付测试环境>)及 [deploy/README.md](<./situationawareness latest/deploy/README.md>)。

## 5. 设计成果与尚未完成项

- 五类专家技术路线及PPT脚本已形成；其中时序模型、关系图、角色推断、可信融合等目标路线应与已运行的确定性规则分开汇报。
- [设施趋向与抵达时间预测设计包](./uav_facility_bridge_design_v1/README.md)提供实现规范、Schema及局部核验，不代表完整预测器已完成或性能已验收。
- [仿真真值导出规格](./uav_strategy_pure_py/GROUND_TRUTH_EXPORT_SPEC.md)规定未来显式真值块；当前导出尚无 `groundTruth`。
- 完整预测轨迹、持续群体跟踪、正式违规解除、单成员威胁人工改档、真实标注数据校准及精度验收仍需后续工作，详细清单见HANDOVER。
- [开源材料制作工具](<./situationawareness latest/docs/OSS_DELIVERY.md>)及审查资料已存在于本地工作树；此次核对时相关新增文件尚未全部提交，不能把本地文件存在等同于发布或正式审核完成。

Origin中的训练、推理和队形样本生成入口仍可用于算法研究及训练数据准备。生产者的 `FormationGenerator3D` 与当前PointNet消费者之间的样本/模型更新，需要单独验证类别、坐标和输入约定，不能仅凭同名模块认定已形成训练闭环。

## 6. 文档导航与验证状态

| 需要了解的内容 | 入口 |
|---|---|
| 当前实现、接口、部署与已知缺口 | [latest README](<./situationawareness latest/README.md>)、[HANDOVER](<./situationawareness latest/文档/HANDOVER.md>) |
| 接口字段与业务语义 | [OpenAPI](<./situationawareness latest/文档/openapi-situation-analyze-v3.2.yaml>)、[v3.2协议](<./situationawareness latest/文档/态势判读算法单接口协议-v3.2.md>) |
| 十维评分的当前实现 | [SituationEngine威胁值计算详解](<./situationawareness latest/文档/SituationEngine威胁值计算详解.docx>) |
| 仿真接入与回放操作 | [tools说明](<./situationawareness latest/tools/README.md>)、[visualization说明](<./situationawareness latest/visualization/README.md>)；旧环境示例需按§4核对 |
| 原始需求、意图目录与设计定义 | 根目录及latest文档目录中的规则规格书、研发Excel；原定义保留，不能直接当作当前实现阈值或启用清单 |
| 早期接入过程 | [8月阶段恢复指南](./agents02与SituationAwareness-v3.2对接_当前进展与新对话恢复指南.md)和历史接入清单，仅作追溯 |
| 文档差异清单 | [2026-10-22对齐审查](./代码与文档对齐审查_2026-10-22.md)，记录修订前发现；本页和latest README已据此更新 |

根目录与latest的规则规格书、研发Excel并非完全相同：原定义和原有立项记录应保留，当前行为应另行注释，并依据代码、测试及v3.2协议核对。

2026-10-22已运行I-24、轨迹配置、时间戳去重、首版意图规则、地图刷新五组定向测试，**56/56通过**。此次README修订不改变算法，也没有重跑全量测试。HANDOVER记载的2026-10-11全量检查仍有1项71/76帧断言失败、2项测试导入错误；不能将定向通过写成全量全绿，不能将规则回归通过写成真实准确率达标。
