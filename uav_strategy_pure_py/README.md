# uav_strategy_pure_py

这是一个不依赖 SPADE、spade_bdi、agentspeak、XMPP 和 Redis 的
`uav_dynamic_agents02.py` 纯 Python 平替实现。

原版代码中的 SPADE 只负责 Agent 生命周期和周期调度，BDI/ASL 只实现了一个
很薄的“逐航段推进 + `can_task_start` 闸门”状态机。本目录把这两层替换为普通
Python 类和确定性中央轮次循环，并把 Redis 共享状态替换为进程内内存字典。

## 目录结构

```text
uav_strategy_pure_py/
├── main.py                     # 入口
├── memory_io.py                # InMemoryUavIO，替代 Redis
├── behaviours.py               # SyncAPFStepEnhance 纯 Python 移植
├── uav_agent.py                # PureBlueUAVAgent
├── mission_orchestrator.py     # MissionOrchestrator 与轨迹导出
├── planning_lib.py             # PlanningLib 纯 Python 版本
├── planning_modules/           # 从原工程复制的纯算法模块
├── data/                       # 复制过来的输入数据
└── outputs/                    # 仿真导出 JSON
```

`planning_modules/` 中的几何、插值和队形生成模块是从原工程复制的纯算法代码，
仅把内部 import 从 `examples.uavs_strategy.*` 改为本包相对 import，没有修改原工程。

## 运行

使用原工程相同的 Conda 环境 `study`：

```powershell
conda run -n study python -m uav_strategy_pure_py.main --seed 42
```

常用参数：

```text
--seed 42            随机种子，便于复现
--max-rounds 200000  最大仿真轮数
--output-dir         导出目录，默认 uav_strategy_pure_py/outputs
--digraph-attrs      航段图 JSON
--facilities         设施 JSON
--key-paths          可选 key_paths JSON
```

默认使用 `data/manual_plan_graph/manual_plan_graph_shaoxing_digraph_attrs.json`
和 `data/facilities_shaoxing.json`，对应原版 `switch_config == 6`。

## 与原版的主要差异

- 不启动 SPADE Agent，不连接 XMPP。
- 不加载 ASL 文件。
- 不使用 Redis；所有位置、轨迹、同步状态都放在 `InMemoryUavIO` 的内存字典中。
- 轨迹追加改为原生 `list.append()`，不再每轮 JSON 序列化整条轨迹。
- 全局 round 由 `MissionOrchestrator.run()` 的确定性中央循环推进。

## 输出

导出文件仍保持原版顶层结构：

```text
simulationMeta
uavs_coords_str
uavs_coords_raw
plannedRoutes
facilities_str
defence_rings
airspaces
missionMeta
```

因此 `situationawareness latest` 的数据管线仍可以继续消费新的导出文件。

## 优化后的回放器

`visualize/pyqt_visualize.py` 是基于原版 PyQt 回放器的优化副本：

- 静态地图、设施和防御圈只作为背景绘制一次。
- 无人机轨迹、当前点、标签和 lookahead 使用持久 Artist 更新，不再每帧 `ax.clear()`。
- 加载数据时会丢弃每帧重复的大字段 `logs` 和 `cur_siblings_ids`。
- 拖动进度条时对右侧信息面板做节流，降低文本重建频率。

回放生成文件时，`behaviours.py` 也已移除每帧重复的 `logs` 和
`cur_siblings_ids`，文件体积会明显下降。

## 队形同步修复（2026-08-13）

### 问题诊断

仿真中编队队形出现"有先有后"、不同步、切换航点时队形错乱的现象。经分析发现两个根本原因：

#### 1. 随机噪声破坏队形一致性 ⭐ 主要原因

**位置**: `formation_generator.py:169-173`

原代码在每个轨迹点都添加独立的随机噪声：
```python
p_w = Rm.dot(p_body) + base + np.random.normal(scale=self.noise_scale, size=3)
```

**问题**:
- 每个轨迹点的噪声独立、不相关
- 噪声在时间上累积，导致队形逐渐变形
- 不同成员的噪声破坏相对位置关系
- 即使同步机制正常工作，物理位置已经错乱

V形队形的角度噪声（±3°）也过大，导致两翼不对称。

#### 2. 预瞄点切换时的"起跑线不齐" ⭐ 次要原因

**位置**: `behaviours.py:25`

原代码使用 `CLOSE_TH_SYNC = 3.0` 米作为"到达"判定阈值：

```python
CLOSE_TH_SYNC = 3.0  # 3米范围内就认为"到达"
```

**问题**:
- Agent A 距离目标 0.1 米时认为"到达" ✓
- Agent B 距离目标 2.9 米时也认为"到达" ✓
- 但他们的实际位置相差 **2.8 米**！
- 当同时切换到下一个航点时，起跑线不齐，队形瞬间错乱

**切换过程示意**:
```
Round N: 飞向航点5
  agent_1: 距离 0.5m → 标记到达，等待
  agent_2: 距离 2.8m → 标记到达，等待  
  agent_3: 距离 1.2m → 标记到达，等待
  ✓ 所有人都到达 → latch release

Round N+1: 消费release，切换到航点6
  agent_1: 从 0.5m处 开始 → 起点不同！
  agent_2: 从 2.8m处 开始 → 起点不同！
  agent_3: 从 1.2m处 开始 → 起点不同！
  → 队形瞬间错乱
```

### 修复方案

#### 1. 调整噪声到合理水平

**V形角度噪声**: 从 ±3° 减小到 **±0.5°**
```python
# formation_generator.py:69
α = self.angle + np.random.uniform(-0.5, 0.5)  # 原来是 ±angle_noise_scale (±3°)
```

**位置噪声**: 降低到原来的 **10%**
```python
# formation_generator.py:172
noise = np.random.normal(scale=self.noise_scale * 0.1, size=3)
p_w = Rm.dot(p_body) + base + noise
```

原始噪声规模 `0.00001-0.00005` 米（0.01-0.05mm），现在缩小到 `0.000001-0.000005` 米（0.001-0.005mm），100个航点累积偏差仅约 0.1-0.5mm。

#### 2. 减小同步阈值

```python
# behaviours.py:25
CLOSE_TH_SYNC = 0.5  # 从 3.0 改为 0.5 米
```

现在要求所有成员在 **0.5 米**范围内才算到达，切换时起跑线对齐，队形保持整齐。

### 修复效果

- ✅ 队形几何关系保持精确（圆形、V形、横线等）
- ✅ 切换预瞄点时队形不再错乱
- ✅ "有先有后"现象消失
- ✅ 保留轻微噪声，增加自然真实感

### 参数调优

如需进一步调整，可修改：

**角度噪声** (`formation_generator.py:69`):
- 更自然: `±1.0°`
- 更精确: `±0.2°`
- 完全移除: `α = self.angle`

**位置噪声倍率** (`formation_generator.py:172`):
- 更明显: `0.2` (原来的 20%)
- 更精确: `0.05` (原来的 5%)
- 完全移除: `noise = np.zeros(3)`

**同步阈值** (`behaviours.py:25`):
- 更严格（队形更整齐）: `0.3` 或 `0.2` 米
- 稍微放松（减少等待时间）: `0.8` 或 `1.0` 米

详细分析见 [`FORMATION_SYNC_BUG_ANALYSIS.md`](FORMATION_SYNC_BUG_ANALYSIS.md)。

## 说明

实时 Redis 可视化器 `redis_data_visualize.py` 不适用于本内存版。可以先使用
导出 JSON 和离线回放工具；如果后续需要实时可视化，再单独加一个可选的
Redis 镜像层。
