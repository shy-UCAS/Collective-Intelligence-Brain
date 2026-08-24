---
type: "explanation"
date: "2026-08-24T09:01:06.181809+00:00"
question: "当前算法启动时是否调用类似 apitest/fetch_airspace_list.py 获取最新空域列表，以及如何选择默认地图"
contributor: "graphify"
source_nodes: ["refresh_default_map_from_airspace_api", "build_default_map_from_airspace_response", "get_default_map"]
---

# Q: 当前算法启动时是否调用类似 apitest/fetch_airspace_list.py 获取最新空域列表，以及如何选择默认地图

## Answer

以 main_situation_judgment_service.py 作为主程序启动时，__main__ 会调用 refresh_default_map_from_airspace_api。该函数并不调用 apitest/fetch_airspace_list.py，而是在 default_map_refresh.py 内独立请求 /basic/airspace/list 的全部分页数据。系统不会选择单个空域作为默认地图，而是把所有具备有效设施坐标且可生成圈层的空域记录合并成一张复合默认地图；每条记录的首个有效设施作为该记录圈层中心，空域记录 ID 写入 ring.airspaceId。刷新成功后安装为进程内默认地图并写入 default_map_agents02_apifox.json；失败时回退到上一份有效文件快照。只有请求未传地图或 facilities、rings、airspaces 均为空时才应用默认地图，调用方传入任一非空空间数据时优先使用请求地图。此刷新流程暂不拉取禁飞区，默认地图 airspaces 为空。

## Source Nodes

- refresh_default_map_from_airspace_api
- build_default_map_from_airspace_response
- get_default_map