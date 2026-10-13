# 仿真真值块导出规格

**对象**：`uav_strategy_pure_py` 导出
**truthVersion**：1.0
**依据**：《无人机集群设施趋向与抵达时间预测 实现设计 v1.0》§12 / §14.3

---

## 1. 为什么需要显式真值块

仿真过程中，生成器是唯一知道答案的一方。它此刻就持有每个 agent 的计划终点、任务类型和完成标志。让这些答案在导出时被写下来，成本几乎为零；让下游去反推，则是每个消费方都得把那套语义重新实现一遍，而且实现规则不在任何契约里。

| | 现状：隐式真值 | 目标：显式真值 |
|---|---|---|
| 目的地 | 藏在 `missionMeta.swarms[].target` | `destinationFacilityId` 直接给出 |
| 抵达时刻 | **根本不存在**，需取航迹末点 `ts` | `arrivalTimeMs` 直接给出 |
| 抵达判定规则 | 只写在 `behaviours.py:527-535` 的实现里 | `truthVersion` + `definition` 写进数据 |
| 结局 | 场景类别 `orderType` 与结局混用 | `outcome` 枚举，不是布尔 |

### 1.1 反推规则一旦改动，历史数据会静默失效

现在"该 agent 已抵达"这个判断，只存在于 `behaviours.py` 的 `_check_task_completion` 里（`lookahead >= max_idx` 且 `dist_to_target <= CLOSE_TH_SYNC`，阈值 0.5 m）。改一次阈值，此前所有导出的隐含真值都变了，而没有任何东西会报错。

### 1.2 关键：不能用 `uavs_coords_str` 反推抵达时刻

导出里的 `uavs_coords_str` 并不是完整航迹，而是经过 `select_analysis_trajectory`（`mission_orchestrator.py:92`）筛选后的**同步窗口**，只保留各成员在同一 `segment_key` 下共有的 `frame_id`。它的末点通常不是抵达时刻。

真值必须从完整的 `raw_trajs` 派生。这也是真值该由生成器写、而不该由下游从导出可见字段猜的直接理由。

---

## 2. 真值块结构

新增顶层键 `groundTruth`，与 `uavs_coords_str` 平级。时间一律用绝对 Unix 毫秒，与 `uavs_coords_str[].ts` 同一基准，使 ETA 真值退化为一次减法。

### 2.1 示例

```json
"groundTruth": {
  "truthVersion": "1.0",
  "definition": "ARRIVED = 群内全部成员抵达计划终点, dist<=CLOSE_TH_SYNC(0.5m)",
  "timeBasis": "SIM_MS_ABSOLUTE",
  "generatorMeta": {
    "seed": 42,
    "maxRounds": 200000,
    "reachedMaxRounds": false,
    "simulationStartTimeMs": 1786597931389,
    "dtMs": 500
  },
  "groups": [
    {
      "swarmId": "swarm1",
      "memberIds": ["agent_1_0", "agent_1_1"],
      "declaredOrderType": "detour",
      "destinationFacilityId": "shaoxing_1",
      "destinationLngLat": [116.376658, 39.899957],
      "routeEndLngLat": [116.376611, 39.899902],
      "routeEndDistanceToDestinationM": 6.4,
      "outcome": "ARRIVED_AT_PERIMETER",
      "arrivalTimeMs": 1786598412389,
      "firstMemberArrivalTimeMs": 1786598406389,
      "arrivalSpreadMs": 6000,
      "memberArrivalTimesMs": {
        "agent_1_0": 1786598412389,
        "agent_1_1": 1786598406389
      },
      "truthStatus": "VALID"
    },
    {
      "swarmId": "swarm2",
      "memberIds": ["agent_2_0"],
      "declaredOrderType": "routine",
      "destinationFacilityId": null,
      "destinationLngLat": null,
      "routeEndLngLat": [116.390112, 39.870441],
      "routeEndDistanceToDestinationM": null,
      "outcome": "NO_DESTINATION",
      "arrivalTimeMs": null,
      "firstMemberArrivalTimeMs": null,
      "arrivalSpreadMs": null,
      "memberArrivalTimesMs": { "agent_2_0": null },
      "truthStatus": "VALID"
    }
  ],
  "warnings": []
}
```

### 2.2 字段契约

| 字段 | 类型 | 语义 |
|---|---|---|
| `truthVersion` | string | 真值定义版本。抵达判定规则改动时必须递增，供标定脚本判断历史结果是否需重跑。 |
| `definition` | string | 抵达判定的自然语言描述，与代码同源。避免规则只活在实现里。 |
| `timeBasis` | const | 固定 `SIM_MS_ABSOLUTE`。声明所有时刻可与 `uavs_coords_str[].ts` 直接相减。 |
| `generatorMeta.reachedMaxRounds` | bool | 本轮是否撞上 `--max-rounds` 而截断。为 `true` 时全部群自动降级为 `TRUNCATED`。 |
| `swarmId` | string | 与 `missionMeta.swarms[].swarmId` 一致，作为跨字段对齐键。 |
| `memberIds` | string[] | 与 `missionMeta` 一致，排序后确定顺序，避免输入顺序影响结果。 |
| `declaredOrderType` | string\|null | digraph 的 `order_type` 或 `action_class`，原样透传，不做语义归一。 |
| `destinationFacilityId` | string\|null | `target` 能在 `facilities_str` 中解析为设施时给出；解析不到（设施类型名、坐标目标、`aggregate_point`）时为 `null`。 |
| `destinationLngLat` | [num,num]\|null | 与 `facilities_str` 同源，避免下游再查一次。 |
| `routeEndLngLat` | [num,num]\|null | 计划航迹末点，取自 `plannedRoutes[].flightRoute[-1]`。 |
| `routeEndDistanceToDestinationM` | number\|null | 末点到声明目的地的距离，**用于自检**：超阈值即说明"路线终点 == 设施坐标"这条假设在本场景不成立，应降级 `truthStatus`。 |
| `outcome` | enum | 结局枚举，见 §5。不是布尔：布尔会把 H₀ 需要的负类与"路过"混为一谈。 |
| `arrivalTimeMs` | int\|null | **群终端时刻** = 最后一名成员完成时刻，对应规范的 `GROUP_TERMINAL_STATE`。 |
| `firstMemberArrivalTimeMs` | int\|null | 首名成员完成时刻，供协同性诊断。 |
| `arrivalSpreadMs` | int\|null | 两者之差。多机群若该值过大，说明"联合终端"这一假设本来就弱。 |
| `memberArrivalTimesMs` | object | `{agentId: ms\|null}`。逐成员时刻，便于按成员评测与排查。 |
| `truthStatus` | enum | 该条真值是否可用，见 §5。评测覆盖率依赖此字段。 |

### 2.3 null 与 0 不可互换

`destinationFacilityId: null` 且 `outcome: NO_DESTINATION`（确实没有目的地）与 `truthStatus: TRUNCATED`（仿真没跑完，无从得知）是两件完全不同的事。前者是有效的负样本，后者必须被排除在指标之外。混在一起会让替代模型的先验标定彻底跑偏。

---

## 3. 生成位置与可用变量

唯一改动点是 `MissionOrchestrator.save_trajectories()`（`mission_orchestrator.py:407`）。该方法在写文件之前，所需变量已经全部在手，不需要新增任何仿真阶段的采集。

| 变量 | 来源 | 用途 |
|---|---|---|
| `self.active_agents` | `save_trajectories` | 取每个 agent 的 `is_finished`、`is_final_task`，判定抵达与截断 |
| `raw_trajs` | `save_trajectories` | **完整**航迹 `(traj_utm, traj_extra)`；`traj_extra` 含逐点 `simTimeMs` |
| `trajectory_timestamps_ms(extras)` | 模块函数 `:27` | 把 `traj_extra` 转成毫秒时间戳数组，取末元素即抵达时刻 |
| `planned_routes` | `save_trajectories` | `flightRoute[-1]` 作 `routeEndLngLat`；`complete` 参与降级判定 |
| `mission_meta` | `:464` | 现成的群 → `target` / `memberIds` / `orderType` 映射，直接复用 |
| `facilities_str` | `save_trajectories` | 解析 `target` → `destinationLngLat` |
| `self.io.get_world_state(SIM_CLOCK_START_KEY)` | `InMemoryUavIO` | `simulationStartTimeMs` |

### 3.1 顺带修一处会误导人的输出

`run()` 的循环在 `current_round < max_rounds` 条件下退出（`mission_orchestrator.py:389`），但紧接着无条件打印 `"All persistent missions completed."`。撞上轮数上限时这句话是错的。

建议改为按 `any(not a.is_finished for a in self.active_agents.values())` 判定，并把结果写入 `io` 的 world state，让 `save_trajectories` 能读到它去填 `reachedMaxRounds`。

---

## 4. 生成函数草图

在模块级新增一个纯函数，由 `save_trajectories` 在组装 `final_data` 之前调用一次。时间取 `traj_extra` 的 `simTimeMs` 而不是 UTM 航迹索引，因为前者是权威仿真时钟。

```python
# 抵达判定阈值与 behaviours.CLOSE_TH_SYNC 必须同源，禁止各写一份
CLOSE_TH_SYNC = 0.5
ROUTE_END_TOLERANCE_M = 50.0   # 巡飞/盘旋末点不落在设施点，需容忍

def build_ground_truth(active_agents, raw_trajs, planned_routes,
                       mission_meta, facilities_str, io, reached_max_rounds):
    groups = []
    for swarm in mission_meta.get("swarms", []):
        members = swarm.get("memberIds") or []
        target = swarm.get("target")

        # 目标只有在 facilities_str 里能解析为设施时才算目的地
        dest_id = target if target in facilities_str else None
        dest_ll = facilities_str.get(dest_id) if dest_id else None

        # 逐成员抵达时刻：完整航迹的末点 simTimeMs
        member_times = {}
        for name in members:
            agent = active_agents.get(name)
            _, extras = raw_trajs.get(name, ([], []))
            if agent is not None and agent.is_finished and extras:
                member_times[name] = trajectory_timestamps_ms(extras)[-1]
            else:
                member_times[name] = None

        # 计划航迹末点，用于自检"终点即设施"这一假设
        route = planned_routes.get(members[0]) if members else None
        route_pts = (route or {}).get("flightRoute") or []
        route_end = ([route_pts[-1]["lng"], route_pts[-1]["lat"]]
                     if route_pts else None)

        end_dist = None
        if route_end and dest_ll:
            end_dist = haversine_m(route_end, dest_ll)

        outcome, status = _classify(swarm, member_times, route, end_dist,
                                    reached_max_rounds)
        times = [t for t in member_times.values() if t is not None]
        groups.append({
            "swarmId": swarm.get("swarmId"),
            "memberIds": sorted(members),
            "declaredOrderType": swarm.get("orderType"),
            "destinationFacilityId": dest_id,
            "destinationLngLat": dest_ll,
            "routeEndLngLat": route_end,
            "routeEndDistanceToDestinationM": end_dist,
            "outcome": outcome,
            "arrivalTimeMs": (max(times)
                              if times and len(times) == len(members)
                              else None),
            "firstMemberArrivalTimeMs": min(times) if times else None,
            "arrivalSpreadMs": (max(times) - min(times)
                                if len(times) > 1 else None),
            "memberArrivalTimesMs": member_times,
            "truthStatus": status,
        })
    return {"truthVersion": TRUTH_VERSION, "definition": TRUTH_DEFINITION,
            "timeBasis": "SIM_MS_ABSOLUTE", "generatorMeta": ...,
            "groups": groups, "warnings": []}
```

调用点放在 `final_data` 组装处（`mission_orchestrator.py:538`），加一行顶层键即可：

```python
final_data = {
    "simulationMeta": simulation_meta,
    "uavs_coords_str": uavs_coords,
    "uavs_coords_raw": uavs_coords_raw,
    "plannedRoutes": planned_routes,
    "facilities_str": facilities_str,
    "defence_rings": defence_rings,
    "airspaces": airspaces,
    "missionMeta": mission_meta,
    "groundTruth": ground_truth,      # 新增
}
```

### 4.1 抵达时刻有 0.5 秒量化

仿真每轮 `DT = 0.5` 秒（`behaviours.py:16`），抵达时刻只能精确到轮次。这是真值的分辨率上限：评测 ETA 时不要宣称优于 0.5 秒的精度，也不要把这个量化误差算进模型误差。

---

## 5. 结局与有效性判定

`outcome` 与 `truthStatus` 是两个独立维度：前者说"发生了什么"，后者说"这条记录能不能用"。

### 5.1 `outcome` 枚举

| 取值 | 判定来源 | 用途 |
|---|---|---|
| `ARRIVED` | 全部成员完成，且航迹末点落在声明目的地容差内 | 条件 ETA 正例；当前生成器唯一稳定产出的类别 |
| `ARRIVED_AT_PERIMETER` | `order_type == "detour"`，沿设施周边 `move_along_border` 收尾 | 仍然抵达，但终点在周长上而非中心，ETA 语义需单独说明 |
| `NO_DESTINATION` | `target` 解析不到设施 | **替代模型 H₀ 的唯一负样本来源**。今天不会出现，需扩场景后才有 |
| `DEPARTED` | `order_type == "escape"`，航迹由圈内向圈外 | 否定样本：有明确运动意图但不指向设施 |
| `ORBIT` | `action_class == "recon"` 或 `"support"` | 绕飞样本，检验模型不把盘旋判成趋向 |
| `LOITER` | `action_class == "support"` 且 `action == "standby"` | 悬停样本，专测"距离 ÷ 速度"类方法失效 |
| `ROUTE_INCOMPLETE` | `plannedRoutes[].complete == false` | 计划本身残缺，真值不可信 |

### 5.2 `truthStatus` 降级规则（按顺序短路，命中即停）

| 取值 | 触发条件 | 下游处理 |
|---|---|---|
| `TRUNCATED` | 撞上 `--max-rounds`，或该群有成员 `is_finished == false` | 整条排除出评测；`arrivalTimeMs` 置 `null` |
| `DEGENERATE_ROUTE` | 计划末点与起点重合（`_plan_point_target` 兜底 `planning_lib.py:284` 与 `plan_escape` 的圈外分支 `:228-231` 都返回 `[start, start]`） | 整条排除；这类样本连入模最小点数都过不了 |
| `INCOMPLETE_ROUTE` | `plannedRoutes[].complete == false` | 整条排除 |
| `UNRESOLVED_TARGET` | `target` 是设施类型名、坐标或 `aggregate_point`，不是具名设施 | 保留作 `NO_DESTINATION` 候选，但不可用作具名目的地正例 |
| `ENDPOINT_MISMATCH` | `routeEndDistanceToDestinationM > ROUTE_END_TOLERANCE_M` | 保留但标记：说明"路线终点即设施"这一假设在本场景不成立 |
| `VALID` | 以上均未触发 | 可进入标定与评测 |

### 5.3 `ENDPOINT_MISMATCH` 顺便替你验证一个未证假设

"计划航迹的终点就是目标设施坐标"这条链路，是当前从 digraph 的 `target` 字段推断出来的，尚未逐场景实测。把 `routeEndDistanceToDestinationM` 写进真值块后，每一次导出都会自动给出这层验证：若该距离长期远大于容差，说明推断不成立，届时需要回到 `planning_lib` 重新确认节点→设施坐标的绑定。

---

## 6. 与在线输入的隔离

规范 §12 是硬约束：真值只进入离线评测，不进入在线输入。现在 `target` 混在 `missionMeta` 里，而 `missionMeta` 与 `uavs_coords_str` 同层同文件，构建请求时只要有人图省事把整个 payload 传下去，真值就泄漏了。

- **构建请求按白名单取字段。** 只取 `uavs_coords_str`、`facilities_str`、`defence_rings`、`airspaces`，显式排除 `groundTruth`。
- **标定与回放脚本分目录存放。** `groundTruth` 只被评测侧读取，模型侧代码不 import 任何真值读取函数。
- **把这条写成断言。** 在请求构建处加一句"payload 中不得出现 `groundTruth` 键"的检查，成本一行，能挡住未来所有误传。

---

## 7. 落地顺序与验收

### 01 先写真值块，不动场景

只加 `build_ground_truth` 与导出键。此时 `outcome` 只会出现 `ARRIVED` / `ARRIVED_AT_PERIMETER`。

**验收**：与现有导出对比，群数、`swarmId`、`memberIds` 与 `missionMeta` 完全一致。

### 02 用 `routeEndDistanceToDestinationM` 验证终点假设

跑一次小规模导出（调小 `--max-rounds`），检查每群的末点—目的地距离。若普遍偏大，先解决节点绑定问题，再往下走。

### 03 补负例场景

在 digraph attrs 里加入没有对应具名设施的节点与边，或启用现成但未接线的 `orbit` / `loiter` / `escape`。

**验收**：至少一个群产出 `outcome: NO_DESTINATION` 且 `truthStatus: VALID`。

### 04 加精简导出模式

只保留 `uavs_coords_str` 与 `groundTruth`，去掉每帧 `extras`。当前单文件百 MB 量级，标定循环会难以为继。

### 05 多 seed 跑，按 seed 划分

规范要求场景级划分，不能把同一航迹的滑动窗口随机分到标定与测试两侧。以 seed 为划分单位最省事，也符合现有 `--seed` 语义。

---

## 8. 不要越界宣称

这套数据是确定性脚本仿真，飞行平滑、任务单一，适合标定内核与跑通契约，**不足以支撑真实场景准确率结论**。规范要求：未通过独立动态轨迹验证前，只允许影子运行或人工复核。真值块让这件事可被验证，但不改变这条边界。
