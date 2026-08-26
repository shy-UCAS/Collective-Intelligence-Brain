---
type: "query"
date: "2026-08-24T16:02:33.386567+00:00"
question: "为什么 trajectory_data_v32_replay_bundle_20260824_141443.json 会把所有成员判成一个 random 集群？"
contributor: "graphify"
source_nodes: ["SituationEngine._clusters", "LegacyAlgorithmAdapter._prepare_tracks", "UnifyCoordinates._common_timestamps", "SituationEngine._formation"]
---

# Q: 为什么 trajectory_data_v32_replay_bundle_20260824_141443.json 会把所有成员判成一个 random 集群？

## Answer

已通过同一输入实际运行确认：根因一是 SituationEngine._clusters 在目标数大于10时进入 cKDTree 分支，直接使用经纬度度数坐标，却把 clusterDistanceMeters=250 当作树查询半径，导致相距数十至上百公里的12个目标被连成一个集群；同数据 N=10 时为10个单目标集群，N=11 时突变为一个集群。根因二是队形识别仅取每条轨迹尾部12点，所有轨迹不存在公共时间区间，UnifyCoordinates._common_timestamps 返回空，LegacyAlgorithmAdapter._prepare_tracks 降级，PointNet没有运行。随后 _formation 使用经纬度包围盒的2比1启发式，整体宽高比约1.46，因而输出 random。random不是此次模型分类结果，也不是所有成员合并的原因。

## Source Nodes

- SituationEngine._clusters
- LegacyAlgorithmAdapter._prepare_tracks
- UnifyCoordinates._common_timestamps
- SituationEngine._formation