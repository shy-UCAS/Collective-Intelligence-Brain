---
type: "query"
date: "2026-08-24T17:40:23.788537+00:00"
question: "run_intent_replay_visualizer.bat 这个可视化的前端在无人机的周围添加的圆圈是什么意思呢"
contributor: "graphify"
source_nodes: ["render_frame", "_single_cluster_radius", "_cluster_members", "_assessment_range_geometry"]
---

# Q: run_intent_replay_visualizer.bat 这个可视化的前端在无人机的周围添加的圆圈是什么意思呢

## Answer

紧贴无人机的半透明彩色小圆是单成员集群的可视化包络。map_renderer先读取clusterDtoList[].targetDtoList成员并求凸包：三架及以上画凸包，两架或共线画胶囊，只有一架时以该无人机当前位置为圆心画Circle。它仅用于显示该目标本身构成一个集群，不表示250米聚类阈值、雷达探测范围、威胁范围或5公里空域评估范围。当前样本修复后为12个单机集群，因此每架周围都有一个小圆。圆的大小按当前地图全部目标分布范围动态计算，颜色由成员ID稳定生成，线宽随威胁等级变化。如果看到蓝色虚线大边界，那是父防控空域最外层warning边界外扩airspaceAssessmentRangeMeters的5km评估参考边界；黄橙红设施圈则是三级防御圈。

## Source Nodes

- render_frame
- _single_cluster_radius
- _cluster_members
- _assessment_range_geometry