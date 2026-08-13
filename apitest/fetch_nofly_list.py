# -*- coding: utf-8 -*-
"""
获取禁飞区列表 (GET /nofly/list)

后端服务: basic —— 测试环境地址 http://125.35.101.132:8888/basic
注意: 该接口当前无鉴权，无需 Apifox 令牌；Apifox 令牌只用于 Apifox 平台 API。
真实响应样例见: samples/nofly_list_sample.json

用法:
    python fetch_nofly_list.py                       # 默认第一页 20 条
    python fetch_nofly_list.py --page 1 --page-size 50
    python fetch_nofly_list.py --name 禁飞区 --zone-type 1
    python fetch_nofly_list.py -o nofly.json         # 结果保存为 JSON 文件
"""

import argparse
import json

import requests

BASE_URL = "http://125.35.101.132:8888/basic"  # 测试环境
PATH = "/nofly/list"


def fetch_nofly_list(base_url=BASE_URL, page=1, page_size=20, name=None,
                     control_type=None, zone_type=None, timeout=15):
    """调用分页查询禁飞区列表接口，返回响应 JSON。"""
    params = {"pageNum": page, "pageSize": page_size}
    if name:
        params["name"] = name
    if control_type is not None:
        params["controlType"] = control_type
    if zone_type is not None:
        params["zoneType"] = zone_type

    resp = requests.get(base_url + PATH, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def main():
    parser = argparse.ArgumentParser(description="查询禁飞区列表")
    parser.add_argument("--base-url", default=BASE_URL,
                        help="后端 base URL（默认测试环境）")
    parser.add_argument("--page", type=int, default=1, help="页码（从 1 开始）")
    parser.add_argument("--page-size", type=int, default=20, help="每页条数")
    parser.add_argument("--name", help="名称（模糊匹配）")
    parser.add_argument("--control-type", type=int, help="防控场景")
    parser.add_argument("--zone-type", type=int,
                        help="防护区划设类型 1=圆形 2=多边形")
    parser.add_argument("-o", "--output", help="结果另存为 JSON 文件")
    args = parser.parse_args()

    data = fetch_nofly_list(args.base_url, args.page, args.page_size,
                            args.name, args.control_type, args.zone_type)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("\n已保存到: %s" % args.output)


if __name__ == "__main__":
    main()
