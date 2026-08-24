 # -*- coding: utf-8 -*-
"""
获取设备清单 (equipment 微服务)

后端服务: equipment —— 测试环境地址 http://125.35.101.132:8888/equipment
注意: 该接口当前无鉴权，无需 Apifox 令牌。
真实响应样例见: samples/device_type_latest_*.json

接口说明 (2026-08-24 实测 + Apifox 文档交叉核对):
  - GET /device/all  -> 无需参数, 直接返回全部设备(探测+反制)。
                       实测发现, 未见于 Apifox 文档。
  - GET /device/getType?deviceType=N&subType=M -> 按类型分类查询。
                       Apifox 文档(设备总表查询控制器)确认: deviceType 与
                       subType 均为必填, 缺 subType 返回业务码 400
                       "subType 不能为空"; 文档中 subType 描述为"反制设备
                       类型", 但实测它是细分类型枚举(探测 3/7=摄像头,
                       反制 1=机巢 等), 枚举无官方清单, 需对目标环境探测。
  - 文档 server 为 /ooda 前缀, 但测试环境网关当前返回 10000
    "服务繁忙,请稍后再试"; 实测 /equipment 前缀可用, 故作为默认值,
    可通过 --base-url 覆盖。
  - 文档响应 schema 为分页结构 data:{total, list}, 实测 data 为裸数组;
    记录还包含文档未列的字段(如 hfov), 脚本保留原始响应不做改写。

用法:
    python fetch_device_type.py                          # 默认 all: 抓全部设备
    python fetch_device_type.py --device-type 1 --sub-type 3   # 分类查询: 探测-摄像头
    python fetch_device_type.py -o device_type.json      # 结果保存为 JSON 文件

返回数据格式:
  all 模式 —— /device/all 的原始响应:
  {
    "code": 0,
    "message": "ok",
    "data": [                    # 全部设备 (探测 deviceType=1 + 反制 deviceType=2)
      {
        "id": "8",               # 主键
        "deviceName": "机巢",     # 设备名称
        "deviceType": 2,         # 1=探测设备 2=反制设备
        "lat": 30, "lng": 120,   # 安装位置
        "coverageRadius": 8000,  # 覆盖半径(米)
        "azimuth": 20, "azimuthRange": 323,
        "healthScore": 100,
        "detectionDevice": {...} # 关联探测设备信息 (探测类设备)
        "counterDevice": {...}   # 关联反制设备信息 (反制类设备)
        "droneBase": {...}       # 关联机巢信息 (反制类设备)
        "hangar": {...}          # 关联停机库信息
      }
    ]
  }
  单类型模式 —— /device/getType 的原始响应, 不做任何改写。

说明:
  - 所有模式都保留接口原始响应, 不做扁平化或丢字段。
  - 本机若配置了系统代理(requests 会读 Windows 注册表代理), 访问测试
    环境超时时, 可临时设置 NO_PROXY=125.35.101.132 直连。
"""

import argparse
import json

import requests

BASE_URL = "http://125.35.101.132:8888/equipment"  # 测试环境
PATH_ALL = "/device/all"
PATH_GET_TYPE = "/device/getType"

# deviceType 枚举 → 说明
TYPE_NAMES = {1: "探测设备", 2: "反制设备"}


def fetch_all_devices(base_url=BASE_URL, timeout=15):
    """调用 /device/all 获取全部设备，返回原始响应 JSON。"""
    resp = requests.get(base_url + PATH_ALL, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def fetch_device_type(base_url=BASE_URL, device_type=1, sub_type=1,
                      timeout=15):
    """调用 /device/getType 按类型分类查询，返回该类型的原始响应 JSON。

    deviceType: 1=探测设备 2=反制设备
    subType:    细分类型, 接口必填 (缺省返回业务码 400)
    """
    resp = requests.get(base_url + PATH_GET_TYPE,
                        params={"deviceType": device_type, "subType": sub_type},
                        timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def main():
    parser = argparse.ArgumentParser(description="查询设备清单 (equipment 微服务)")
    parser.add_argument("--base-url", default=BASE_URL,
                        help="后端 base URL（默认测试环境）")
    parser.add_argument("--device-type", choices=["1", "2", "all"],
                        default="all",
                        help="all=全部设备(默认, 走 /device/all); "
                             "1=探测设备 2=反制设备 (走 /device/getType, 需配合 --sub-type)")
    parser.add_argument("--sub-type", type=int,
                        help="细分类型(仅 --device-type 1/2 时有效): "
                             "探测 3/7=摄像头, 反制 1=机巢 等, 接口必填")
    parser.add_argument("-o", "--output", help="结果另存为 JSON 文件")
    args = parser.parse_args()

    if args.device_type == "all":
        data = fetch_all_devices(args.base_url)
    else:
        if args.sub_type is None:
            parser.error("--device-type 1/2 必须配合 --sub-type "
                         "(接口参数 subType 不能为空)")
        data = fetch_device_type(args.base_url, int(args.device_type),
                                 args.sub_type)

    print(json.dumps(data, ensure_ascii=False, indent=2))
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("\n已保存到: %s" % args.output)


if __name__ == "__main__":
    main()
