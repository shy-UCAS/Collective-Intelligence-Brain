# -*- coding: utf-8 -*-
"""
设备清单与空域/禁飞区空间匹配分析

读取 samples/ 下最新的三份样本:
  - device_type_latest_*.json   设备清单 (/device/all)
  - airspace_list_latest_*.json 空域列表 (/airspace/list)
  - nofly_list_latest_*.json    禁飞区列表 (/nofly/list)

空域为圆形 (zoneType=1) 时, 以设施坐标为圆心, 按反制/警戒/预警三级半径判定;
多边形空域 (zoneType=2) 时, 用几何中心近似判定 (geom 字段当前为 null, 无精确多边形)。

用法:
    python match_devices_to_zones.py
"""

import glob
import json
import math
import os

import requests  # noqa: F401  (保持与其它 apitest 脚本一致的依赖)


def latest_sample(pattern):
    """取 samples/ 下最新一份匹配文件。"""
    files = sorted(glob.glob(os.path.join("apitest", "samples", pattern)))
    return json.load(open(files[-1], encoding="utf-8")) if files else None


def haversine(lat1, lng1, lat2, lng2):
    """两地理坐标距离(米)。"""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = (math.sin(dp / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(a))


def classify(dist, radii):
    """按三级半径判定设备处于空域哪一区。radii: (反制, 警戒, 预警)。"""
    counter, alert, warning = radii
    if dist <= counter:
        return "反制区(≤%dm)" % counter
    if dist <= alert:
        return "警戒区(≤%dm)" % alert
    if dist <= warning:
        return "预警区(≤%dm)" % warning
    return "区外(>%dm)" % warning


def main():
    devices = latest_sample("device_type_latest_*.json")
    airspaces = latest_sample("airspace_list_latest_*.json")
    nofly = latest_sample("nofly_list_latest_*.json")

    if not devices:
        print("未找到设备清单样本"); return
    dev_list = devices.get("data") or []
    air_list = ((airspaces or {}).get("data") or {}).get("list") or []
    nofly_list = ((nofly or {}).get("data") or {}).get("list") or []

    print("== 设备 %d 台 | 空域 %d 个 | 禁飞区 %d 个 ==\n"
          % (len(dev_list), len(air_list), len(nofly_list)))

    for rec in dev_list:
        name = rec["deviceName"]
        dt = "探测" if rec["deviceType"] == 1 else "反制"
        lat, lng = rec.get("lat"), rec.get("lng")
        bound = rec.get("airspaceId") and rec["airspaceId"] != "0"
        print("[%s] %s  (%s, %s)" % (dt, name, lat, lng))
        if bound:
            print("    关联空域 airspaceId=%s" % rec["airspaceId"])
        if lat is None or lng is None:
            print("    无坐标, 无法匹配"); continue
        for zone in air_list:
            r1, r2, r3 = (zone.get("countermeasureRadius") or 0,
                          zone.get("alertRadius") or 0,
                          zone.get("warningRadius") or 0)
            # 圆形空域: 以第一个设施为圆心 (列表当前如此)
            fac = (zone.get("facilityList") or [{}])[0]
            if fac.get("lng") is None:
                print("    空域 %s 无设施坐标, 无法判定" % zone.get("name"))
                continue
            d = haversine(lat, lng, fac["lat"], fac["lng"])
            zone_type = "圆形" if zone.get("zoneType") == 1 else "多边形"
            print("    vs 空域[%s]%s 设施[%s](%.6f,%.6f): 距圆心 %6.0fm -> %s"
                  % (zone_type, zone.get("name"), fac.get("name"),
                     fac["lng"], fac["lat"], d,
                     classify(d, (r1, r2, r3))))
        for zone in nofly_list:
            print("    vs 禁飞区[%s]: 见禁飞区明细(当前无数据)"
                  % zone.get("name"))

    if not nofly_list:
        print("\n== 禁飞区列表为空, 无禁飞区与设备匹配 ==")


if __name__ == "__main__":
    main()
