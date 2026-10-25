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

        # 目标只有在 facilities_str 里能解析为设施时才算目的地。
        # 必须先判字符串：坐标形态的 target 是 list，直接写 `target in dict`
        # 会抛 TypeError: unhashable type: 'list'
        dest_id = (target if isinstance(target, str) and target in facilities_str
                   else None)
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
| `DEGENERATE_ROUTE` | 声明意图是"要移动"，但**实际飞出的航迹**不足 2 个不同位置点 | 整条排除；这类样本连入模最小点数都过不了 |
| `INCOMPLETE_ROUTE` | `plannedRoutes[].complete == false` | 整条排除 |
| `UNRESOLVED_TARGET` | `target` 是设施类型名、坐标或 `aggregate_point`，不是具名设施 | 保留作 `NO_DESTINATION` 候选，但不可用作具名目的地正例 |
| `ENDPOINT_MISMATCH` | `routeEndDistanceToDestinationM > ROUTE_END_TOLERANCE_M` | 保留但标记：说明"路线终点即设施"这一假设在本场景不成立 |
| `VALID` | 以上均未触发 | 可进入标定与评测 |

> **为什么"要移动"这个前提不能省。**
> 单看几何无法区分"退化"和"刻意静止"。`execute_loiter` 的计划就是 `[pos, pos]`（`planning_lib.py:329-332`），它刻意不动，是 M3 最需要的悬停样本；而 `plan_escape` 在起点位于防护圈外时的分支（`planning_lib.py:228-231`）与 `_plan_point_target` 的兜底（`planning_lib.py:284`）同样产出原地不动的航迹。三者的"实际航迹不同位置点数"都是 1。
> 区分它们只能靠**声明意图**：`action_class == "support"` 且 `action == "standby"` 判为 `LOITER`（有效，保留）；其余"声明要移动却一步没挪"的判为 `DEGENERATE_ROUTE`（排除）。

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

在 digraph attrs 里加入没有对应具名设施的节点与边，或启用现成但未接线的 `orbit` / `loiter` / `escape`。具体写法见 §9。

**验收**：至少一个群产出 `outcome: NO_DESTINATION` 且 `truthStatus: VALID`。

### 04 加精简导出模式

只保留 `uavs_coords_str` 与 `groundTruth`，去掉每帧 `extras`。当前单文件百 MB 量级，标定循环会难以为继。

### 05 多 seed 跑，按 seed 划分

规范要求场景级划分，不能把同一航迹的滑动窗口随机分到标定与测试两侧。以 seed 为划分单位最省事，也符合现有 `--seed` 语义。

---

## 8. 不要越界宣称

这套数据是确定性脚本仿真，飞行平滑、任务单一，适合标定内核与跑通契约，**不足以支撑真实场景准确率结论**。规范要求：未通过独立动态轨迹验证前，只允许影子运行或人工复核。真值块让这件事可被验证，但不改变这条边界。

---

## 9. digraph 场景清单

补负例场景不需要新写规划器。生成器本来就是按 6 种任务类型建的，`height_range_value_set` 里 `orbit` / `loiter` / `routine` 的高度档位都已配好（`uav_agent.py:382-389`），只是当前 digraph 只用了 `breakthrough` 与 `detour`。

### 9.1 现有可用的规划开关

| 开关 | 取值 | 规划入口 | 产出 outcome |
|---|---|---|---|
| `order_type` | `breakthrough` / `singleton` | 直线飞向 `target` | `ARRIVED` |
| | `detour` | 沿设施周长 `move_along_border` | `ARRIVED_AT_PERIMETER` |
| | `routine` | 同 breakthrough，换高度档 | `ARRIVED` |
| | `escape` | 圈内 → 圈边界（向外） | `DEPARTED` |
| `action_class` | `recon` | `execute_orbit`（绕 80 m 圆、8 步） | `ORBIT` |
| | `support` + `action: "standby"` | `execute_loiter`（原地不动） | `LOITER` |
| | `assault` / `maneuver` | `execute_breakthrough` | `ARRIVED` |
| `order_mode` | `aggregate` + `target: "aggregate_point"` | 多群汇合到集结点 | 并群样本 |
| `target` 形态 | 具名设施 | `get_target_location` | — |
| | 设施类型名 `antiair` / `headquarter` / `prober` | `pick_random_target` 随机挑一个 | — |
| | 坐标 `[lng, lat]` | `planbreakthrough_target_location` | — |

### 9.2 三个必须先理解的机制

**(a) 节点 id 只是标签，路线由 `target` 决定。** `extract_uav_trajectories`（`mission_orchestrator.py:312`）把 `from`/`to` 当作不透明标签，只用于 `segment_key`、群归属和图链遍历。真正的几何来自 `attrs.target`（`planning_lib._plan_point_target`，`planning_lib.py:275`）。所以新增场景不需要为新节点配坐标。

**(b) 但起点是随机撒的，无法按场景控制。** `uav_agent.py:76-85`：未显式传 `init_pos` 时，在 `init_loc3`–`init_loc4` 为直径的圆上随机取一点。实测该圆直径 2169 m、半径 1084 m、圆心 (116.3580, 39.8780)。**任何依赖起点几何的场景（路过、已在圈内）都只能统计其分布，不能精确构造。**

**(c) `order_mode` 与 `target` 是必填键。** `uav_agent.py:240-241` 用直接下标读取（`digraph_attr["attrs"]["order_mode"]`），缺键会抛 `KeyError`。loiter 要写 `"target": null`，不能省略这个键。

**(d) 新增场景要同时改两处。** 除了 digraph attrs 文件，还要把新场景的 `from` 节点加进 `--key-paths`（默认 `[[0,3],[1,4],[2,5]]`），因为 `extract_uav_trajectories` 只从 `key_paths` 的起始节点开始遍历（`mission_orchestrator.py:324`）。

### 9.3 A 档：零代码，只改配置

**A1 · `NO_DESTINATION`（最重要）** —— H₀ 替代模型的唯一标定来源。用坐标形态的 target，落在无设施区域：

```json
{
  "from": 6, "to": 9,
  "attrs": {"order_mode": "singleton", "order_type": "routine",
            "target": [116.4000, 39.8600], "fleet_no": "sx4.1"},
  "members_num": 20
}
```

机制：`_is_coordinate_target` 为真 → `planbreakthrough_target_location` 直接飞向该坐标（`planning_lib.py:102`）。因为是真实飞行而非退化路径，轨迹有效；`target` 不是具名设施，真值块给出 `destinationFacilityId: null`、`outcome: NO_DESTINATION`。

**A2 · `LOITER`（悬停）** —— 专测"距离 ÷ 速度"类方法失效：

```json
{
  "from": 7, "to": 10,
  "attrs": {"order_mode": "singleton", "action_class": "support",
            "action": "standby", "target": null, "fleet_no": "sx5.1"},
  "members_num": 12
}
```

机制：调度器在 `action_class` 分支命中 `support` + `standby` → `execute_loiter(start_h, end_h)`（`planning_lib.py:270-272`），该函数**根本不读 target**。

**A3 · `ORBIT`（绕飞）** —— `destinationFacilityId` 有值但永不抵达，是"趋向但不终端"的对照：

```json
{
  "from": 8, "to": 11,
  "attrs": {"order_mode": "singleton", "action_class": "recon",
            "order_type": "orbit", "target": "shaoxing_2", "fleet_no": "sx6.1"},
  "members_num": 15
}
```

**A4 · 并群** —— 覆盖规范 §14.2 的"并群"一行。让多个群的 `to` 指向同一节点并走 `aggregate`：

```json
{
  "from": 9, "to": 12,
  "attrs": {"order_mode": "aggregate", "order_type": "breakthrough",
            "target": "aggregate_point", "fleet_no": "sx7.1"},
  "members_num": 10
}
```

机制：`order_mode == "aggregate"` 且 `target == "aggregate_point"` 时收集同 `to` 节点的其他成员为 `merge_peers`（`uav_agent.py:243-250`），再飞向 `io.get_rendezvous_point(...)`。

### 9.4 B 档：需要几何设计，不改代码

**B1 · 路过** —— `target` 取一个位于某设施**延长线之外**的坐标，使直线航段从该设施附近掠过但终点不是它。

注意：起点随机（见 9.2b），所以掠过距离会随撒点变化，**必须实测分布，不能假定**。若要严格控制掠过距离，只能先做 9.5 的起点配置化。

**B2 · 多候选歧义** —— **不需要构造，现有场景天然就是。** 实测：以起点圆（半径 1084 m，圆心 116.3580/39.8780）上 72 个采样点计算：

| 设施对 | 方位角差 最小 | 中位 | 最大 | 差 < 5° 的比例 |
|---|---|---|---|---|
| shaoxing_1 vs shaoxing_2 | 0.12° | 4.56° | 9.53° | **56%** |
| shaoxing_1 vs shaoxing_3 | 13.75° | 16.83° | 29.53° | 0% |
| shaoxing_2 vs shaoxing_3 | 9.90° | 15.76° | 27.34° | 0% |

也就是说：**超过一半的起点位置上，swarm1（→s1）与 swarm2（→s2）在整个航程的大部分时间里几乎共线**，只在最后几百米才分得开。s1 与 s2 相距 1350 m，而从起点看它们分别在 3.1 km 与 4.4 km 处，角度自然就小。这正是规范 §14.2"多个接近方向相似的设施：证据不足时保持歧义，不强行唯一识别"最理想的压力测试，而且零成本。

**B3 · 同址设施** —— 复制一条 facility 记录，坐标相同、`id` 不同，测"相位不可分辨性"。规范要求两设施不得靠任意排序宣称识别成功。

**顺带一个已实测的设施布局事实**：本 fixture 里**只有 `shaoxing_1` 有防护圈**，`shaoxing_2` / `shaoxing_3` 没有。三级圈都是正圆、圆心与设施偏差 0.0 m：

| 圈 | 半径 |
|---|---|
| `shaoxing_1_countermeasure` | 1000 m |
| `shaoxing_1_alert` | 2000 m |
| `shaoxing_1_warning` | 3000 m |

这既确认了"父空域半径以设施为圆心"这条映射在本 fixture 中成立，也说明**区域类场景（首入圈、已在区域内）只能在 `shaoxing_1` 上测**。

### 9.5 C 档：需要改配置语义

**C1 · `DEPARTED`（escape）与"已在区域内"** —— 两者都要求起点落在防护圈内。起见 9.2b，起点随机圆到 `shaoxing_1` 的距离实测为 1834–4002 m（中位 3133 m），而警戒圈半径 3000 m，**约半数起点在圈内**。

所以 `escape` 现在可用但会**混合产出**：圈内起点得到真实的 `DEPARTED`，圈外起点退化为原地不动、被真值块正确标为 `DEGENERATE_ROUTE`。这反而是 `truthStatus` 字段价值的一个现成演示。若要产出干净的 `DEPARTED` 与"已在区域内"样本，需要让起点位置可配置（见 §10.4）。

**C2 · 中途转向** —— 多跳路径可以表达（图遍历支持 `0→X→Y`，`flightPlan` 本就是段列表），但会触发 §10.1 的群成员重叠问题，需先定语义。

### 9.6 与设计规范 §14.2 的对照

| 规范要求的场景 | 本清单对应 | 状态 |
|---|---|---|
| 单机/多机共同目的地 | 现有 breakthrough | 已有 |
| 一个设施但轨迹路过 | B1 | 需设计几何 |
| 多个接近方向相似的设施 | **B2** | **已有，且很强** |
| 非零终端速度 | B1 的掠过几何 | 需设计 |
| 悬停/绕行 | A2 / A3 | 零代码可得 |
| 中途转向 | C2 | 需先定语义 §10.1 |
| 异步/缺测/重复请求 | 导出侧不涉及，由回放侧注入 | 待定 |
| 分群/并群/成员换序 | A4 并群；换序由排序保证 | 并群零代码 |
| 同址设施/重叠区域 | B3 | 需造数据 |
| 时域外到达/已在区域内 | C1 | 需起点可配置 |
| 多群多设施并发 | 现有 3 群 | 已有 |

---

## 10. 三个待拍板的分歧

### 10.1 多跳路径会让群成员重叠

`build_mission_meta`（`mission_orchestrator.py:226`）是**按边建群**的：一个 agent 只要路径包含某条边，就进那个 swarm 的 `memberIds`。所以一旦加多跳路径，同一个 agent 会同时出现在两个 swarm 里。

这直接撞上设计规范 §3.3 的假设："同一分组批次默认是互斥划分。成员缺失、重复归属、空群分别报告诊断。"

- **(a) 接受按边建群 + 允许重叠**，把重叠本身当作 M3 的输入之一（规范要求"重复归属"要报诊断，正好有素材）
- **(b) 把"群"重新定义成按最终目的地分组**，多跳的中间边不单独建群

倾向 (b)：M3 的推断单位是"集群"，而"在某条航段上"不等于"是一个集群"。但这会改动 `missionMeta` 的现有语义，需确认下游有无依赖。

### 10.2 三种"终点"语义要区分到什么程度

| 场景 | 终点在哪 | `destinationFacilityId` | `outcome` |
|---|---|---|---|
| breakthrough | 设施坐标 | 有 | `ARRIVED` |
| detour | 设施**周长**上 | 有 | `ARRIVED_AT_PERIMETER` |
| orbit | 绕设施转圈，**永不抵达** | 有 | `ORBIT` |

设计规范的 `GROUP_TERMINAL_STATE` 是**终端状态**（论文式 18：终端位置服从以目的地为均值的高斯），既不是"进入圈"，也不是"绕到附近"。所以必须先定：**M3 要预测的"抵达"对标哪一种。**

建议：第一版只把 `ARRIVED`（终点 = 设施坐标）当作 `GROUP_TERMINAL_STATE` 的正例；`ARRIVED_AT_PERIMETER` 与 `ORBIT` 单列，作为"趋向但不终端"的对照，不混进 ETA 误差统计。

### 10.3 真值怎么和快照对齐

一个导出是**一整段仿真的逐帧轨迹**，而 M3 是**每个快照推断一次**。所以同一条航迹切出的多个快照**共享同一个真值**，规范要求的场景级划分在实现上就意味着"整条航迹只能归标定侧或测试侧"。

需要定：**一个导出切成几个快照**（窗口长度、步长）。若要复用现有服务口径，可对齐它的 120 s / 240 点（`engine.py:33-34`）；但要注意实测航程为 1.8–5.3 km，按 16 m/s 约需 115–335 s，**120 s 窗口不足以覆盖全程**，切窗时要保证快照仍带有足够的初始化和评价段。

### 10.4 附带一件（写 §9 时冒出来的）

`escape` 与"已在区域内"都卡在起点不可控上（§9.5 C1）。**要不要让起点位置可配置？** 这需要给 `init_loc3` / `init_loc4` 或 `_spawn_agents` 加一个参数入口，属于本次改造范围之外，但不做的话这两类场景只能靠随机撒点碰运气。
