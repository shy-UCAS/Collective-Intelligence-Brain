# -*- coding: utf-8 -*-
"""
获取空域列表 (GET /airspace/list)

后端服务: basic —— 测试环境地址 http://125.35.101.132:8888/basic
注意: 该接口当前无鉴权，无需 Apifox 令牌。
真实响应样例见: samples/airspace_list_sample.json

用法:
    python fetch_airspace_list.py                      # 默认第一页 20 条
    python fetch_airspace_list.py --page 1 --page-size 50
    python fetch_airspace_list.py --name 防控 --prevention-mode 1
    python fetch_airspace_list.py --enabled true       # 只看可用的
    python fetch_airspace_list.py -o airspace.json     # 结果保存为 JSON 文件

返回数据格式 (响应体 JSON):
{
  "code": 0,              # 业务码, 0=成功
  "message": "ok",        # 提示信息
  "data": {               # 分页结果集
    "total": 6,           # 总条数 (所有页合计)
    "list": [             # 当前页数据数组 (每页最多 pageSize 条)
      {
        "id": "2086994528669667328",   # 主键 (雪花 ID, 字符串)
        "name": "新建防控区",           # 空域名称
        "scene": 1,                    # 场景
        "controlLevel": 1,             # 防控级别
        "zoneType": 1,                 # 划设类型: 1=圆形 2=多边形
        "countermeasureGeom": null,    # 反制区几何 (GeoJSON/WKT, 多边形时)
        "alertGeom": null,             # 警戒区几何
        "warningGeom": null,           # 预警区几何
        "countermeasureRadius": 1000,  # 反制半径(米), 圆形时有效
        "alertRadius": 2000,           # 警戒半径(米)
        "warningRadius": 3000,         # 预警半径(米)
        "altitudeMax": 1000,           # 高度上限(米)
        "altitudeMin": 0,              # 高度下限(米)
        "preventionMode": 1,           # 防控模式: 1=平时 2=战时
        "facilityList": [              # 关联防控设施 (可能为空数组)
          {
            "id": "2086994528673861632",
            "airspaceId": "2086994528669667328",
            "name": "bbb",             # 设施名称
            "lng": 116.52636,          # 设施经度
            "lat": 39.990041           # 设施纬度
          }
        ]
      }
    ]
  }
}

注意:
  - 列表返回的空域记录本身没有中心点坐标 (lng/lat 或 geom 均为 null)!
    geom 需要创建空域时写入 (见 POST /airspace 的入参 geom 边界GeoJSON)。
  - 因此列表数据的空间参考只能依赖 facilityList 里的设施坐标。
"""

import argparse
import json

import requests

BASE_URL = "http://125.35.101.132:8888/basic"  # 测试环境
PATH = "/airspace/list"


def str2bool(value):
    """把命令行 true/false/1/0 转成布尔值。"""
    if value.lower() in ("true", "1", "yes"):
        return True
    if value.lower() in ("false", "0", "no"):
        return False
    raise argparse.ArgumentTypeError("需要 true 或 false")


def fetch_airspace_list(base_url=BASE_URL, page=1, page_size=20, name=None,
                        enabled=None, prevention_mode=None, zone_type=None,
                        timeout=15):
    """调用分页查询空域列表接口，返回响应 JSON。"""
    params = {"pageNum": page, "pageSize": page_size}
    if name:
        params["name"] = name
    if enabled is not None:
        params["enabled"] = str(enabled).lower()
    if prevention_mode is not None:
        params["preventionMode"] = prevention_mode
    if zone_type is not None:
        params["zoneType"] = zone_type

    resp = requests.get(base_url + PATH, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def main():
    parser = argparse.ArgumentParser(description="查询空域列表")
    parser.add_argument("--base-url", default=BASE_URL,
                        help="后端 base URL（默认测试环境）")
    parser.add_argument("--page", type=int, default=1, help="页码（从 1 开始）")
    parser.add_argument("--page-size", type=int, default=20, help="每页条数")
    parser.add_argument("--name", help="名称（模糊匹配）")
    parser.add_argument("--enabled", type=str2bool, help="是否可用 (true/false)")
    parser.add_argument("--prevention-mode", type=int,
                        help="防控模式 1=平时模式 2=战时模式")
    parser.add_argument("--zone-type", type=int,
                        help="防护区划设类型 1=圆形 2=多边形")
    parser.add_argument("-o", "--output", help="结果另存为 JSON 文件")
    args = parser.parse_args()

    data = fetch_airspace_list(args.base_url, args.page, args.page_size,
                               args.name, args.enabled, args.prevention_mode,
                               args.zone_type)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("\n已保存到: %s" % args.output)


if __name__ == "__main__":
    main()
