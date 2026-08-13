# -*- coding: utf-8 -*-
"""
空域信息地图可视化 (PyQt5)

数据来源: GET /airspace/list (basic 服务, 测试环境)
功能:
  - 顶部筛选栏: 名称 / 防控模式 / 划设类型 / 是否可用 (下拉菜单)
  - 分页: 页码 / 每页条数
  - 记录选择: 下拉菜单选择某一条空域查看
  - 地图画布: 三级防护圈(预警/警戒/反制) + 禁飞区叠加(可开关) +
    设施点位 + 经纬度网格 + 比例尺
  - 详情面板: 选中记录的完整字段

运行 (study 环境):
    conda run -n study python apitest/airspace_map_viewer.py
自测截图 (无界面环境):
    conda run -n study python apitest/airspace_map_viewer.py --screenshot out.png
"""

import argparse
import json
import math
import os
import re
import sys

from PyQt5.QtCore import QPoint, Qt, QTimer
from PyQt5.QtGui import (QColor, QFont, QFontDatabase, QPainter, QPen,
                         QPolygon, QRegion)
from PyQt5.QtWidgets import (QApplication, QCheckBox, QComboBox, QFormLayout,
                             QHBoxLayout, QLabel, QLineEdit, QMainWindow,
                             QPlainTextEdit, QPushButton, QSpinBox, QVBoxLayout,
                             QWidget)

from fetch_airspace_list import fetch_airspace_list
from fetch_nofly_list import fetch_nofly_list

# ---------- 配色 ----------
COLOR_WARNING = QColor(255, 200, 60)        # 预警圈(最外)
COLOR_ALERT = QColor(255, 140, 30)          # 警戒圈(中间)
COLOR_COUNTER = QColor(230, 60, 50)         # 反制圈(最内)
COLOR_FACILITY = QColor(40, 110, 255)       # 设施点位
COLOR_CENTER = QColor(20, 160, 80)          # 中心点
COLOR_NOFLY = QColor(160, 60, 220)          # 禁飞区 (叠加显示)
COLOR_GRID = QColor(200, 200, 200)
COLOR_GRID_TEXT = QColor(125, 135, 145)
COLOR_TEXT = QColor(60, 60, 60)
COLOR_BG = QColor(248, 250, 252)

ZONE_TYPE_MAP = {1: "圆形", 2: "多边形"}
PREVENTION_MODE_MAP = {1: "平时模式", 2: "战时模式"}


# ---------- 字体 ----------
def configure_application_font(app):
    """为普通窗口和 Qt offscreen 截图注册一个可显示中文的字体。

    部分 Windows/Conda 的 Qt offscreen 插件不会自动读取系统字体，字体库为空时
    所有文字都会消失。正常桌面环境已有字体时不会重复加载。
    """
    preferred = ("Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC",
                 "Noto Sans CJK SC", "Noto Sans CJK", "SimSun", "Arial")
    database = QFontDatabase()
    families = set(database.families())

    if not any(name in families for name in preferred):
        font_files = (
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/simsun.ttc",
            "C:/Windows/Fonts/segoeui.ttf",
            "/System/Library/Fonts/PingFang.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        )
        for font_file in font_files:
            if os.path.isfile(font_file):
                QFontDatabase.addApplicationFont(font_file)
        families = set(QFontDatabase().families())

    family = next((name for name in preferred if name in families), None)
    if family:
        app.setFont(QFont(family, 9))
    return family


# ---------- 几何工具 ----------
_NUMBER_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")


def _as_float(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _as_lng_lat(value):
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    lng, lat = _as_float(value[0]), _as_float(value[1])
    if lng is None or lat is None or not (-180 <= lng <= 180 and -90 <= lat <= 90):
        return None
    return (lng, lat)


def _empty_geometry():
    return {"points": [], "polygons": []}


def _merge_geometry(target, source):
    target["points"].extend(source["points"])
    target["polygons"].extend(source["polygons"])
    return target


def _parse_geojson(obj):
    parsed = _empty_geometry()
    if not isinstance(obj, dict):
        return parsed

    gtype = str(obj.get("type") or "").lower()
    if gtype == "feature":
        return _parse_geojson(obj.get("geometry"))
    if gtype == "featurecollection":
        for feature in obj.get("features") or []:
            _merge_geometry(parsed, _parse_geojson(feature))
        return parsed
    if gtype == "geometrycollection":
        for geometry in obj.get("geometries") or []:
            _merge_geometry(parsed, _parse_geojson(geometry))
        return parsed

    coordinates = obj.get("coordinates")
    if gtype == "point":
        point = _as_lng_lat(coordinates)
        if point:
            parsed["points"].append(point)
    elif gtype == "multipoint":
        parsed["points"].extend(
            point for point in (_as_lng_lat(value) for value in coordinates or [])
            if point)
    elif gtype == "polygon":
        polygon = []
        for values in coordinates or []:
            ring = [point for point in (_as_lng_lat(value) for value in values or [])
                    if point]
            if len(ring) >= 3:
                polygon.append(ring)
        if polygon:
            parsed["polygons"].append(polygon)
    elif gtype == "multipolygon":
        for polygon_values in coordinates or []:
            polygon = []
            for values in polygon_values or []:
                ring = [point for point in (_as_lng_lat(value) for value in values or [])
                        if point]
                if len(ring) >= 3:
                    polygon.append(ring)
            if polygon:
                parsed["polygons"].append(polygon)
    return parsed


def _strip_outer_parentheses(text):
    text = text.strip()
    if len(text) < 2 or text[0] != "(" or text[-1] != ")":
        return None
    depth = 0
    for index, char in enumerate(text):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0 or (depth == 0 and index != len(text) - 1):
                return None
    return text[1:-1] if depth == 0 else None


def _top_level_groups(text):
    groups = []
    depth = 0
    start = None
    for index, char in enumerate(text):
        if char == "(":
            if depth == 0:
                start = index + 1
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0 and start is not None:
                groups.append(text[start:index])
                start = None
            elif depth < 0:
                return []
    return groups if depth == 0 else []


def _wkt_coordinate_list(text):
    points = []
    for item in text.split(","):
        numbers = _NUMBER_RE.findall(item)
        if len(numbers) >= 2:
            point = _as_lng_lat(numbers[:2])
            if point:
                points.append(point)
    return points


def _parse_wkt(text):
    parsed = _empty_geometry()
    text = text.strip()
    if text.upper().startswith("SRID=") and ";" in text:
        text = text.split(";", 1)[1].strip()
    match = re.match(r"^([A-Za-z]+)(?:\s+Z|\s+M|\s+ZM)?\s*(.*)$", text,
                     flags=re.DOTALL)
    if not match:
        return parsed
    gtype, body = match.group(1).upper(), match.group(2).strip()
    if body.upper() == "EMPTY":
        return parsed

    if gtype == "POINT":
        numbers = _NUMBER_RE.findall(body)
        point = _as_lng_lat(numbers[:2]) if len(numbers) >= 2 else None
        if point:
            parsed["points"].append(point)
        return parsed
    if gtype == "MULTIPOINT":
        parsed["points"].extend(_wkt_coordinate_list(body.replace("(", "").replace(")", "")))
        return parsed

    outer = _strip_outer_parentheses(body)
    if outer is None:
        return parsed
    if gtype == "POLYGON":
        ring_groups = _top_level_groups(outer)
        if not ring_groups:
            ring_groups = [outer]
        polygon = [ring for ring in (_wkt_coordinate_list(group)
                                     for group in ring_groups) if len(ring) >= 3]
        if polygon:
            parsed["polygons"].append(polygon)
    elif gtype == "MULTIPOLYGON":
        for polygon_group in _top_level_groups(outer):
            ring_groups = _top_level_groups(polygon_group)
            if not ring_groups:
                ring_groups = [polygon_group]
            polygon = [ring for ring in (_wkt_coordinate_list(group)
                                         for group in ring_groups) if len(ring) >= 3]
            if polygon:
                parsed["polygons"].append(polygon)
    return parsed


def parse_geometry(geom):
    """解析 GeoJSON 字典/字符串或 WKT，统一返回点和多边形集合。"""
    if isinstance(geom, dict):
        return _parse_geojson(geom)
    if not isinstance(geom, str) or not geom.strip():
        return _empty_geometry()
    text = geom.strip()
    if text.startswith(("{", "[")):
        try:
            return _parse_geojson(json.loads(text))
        except (TypeError, ValueError):
            return _empty_geometry()
    try:
        return _parse_wkt(text)
    except (TypeError, ValueError, IndexError):
        return _empty_geometry()


def _ring_centroid(ring):
    """用鞋带公式计算外环质心；退化环回退为顶点均值。"""
    if not ring:
        return None, 0.0
    points = ring[:-1] if len(ring) > 1 and ring[0] == ring[-1] else ring
    if not points:
        return None, 0.0
    cross_sum = cx_sum = cy_sum = 0.0
    for index, point in enumerate(points):
        next_point = points[(index + 1) % len(points)]
        cross = point[0] * next_point[1] - next_point[0] * point[1]
        cross_sum += cross
        cx_sum += (point[0] + next_point[0]) * cross
        cy_sum += (point[1] + next_point[1]) * cross
    if abs(cross_sum) < 1e-12:
        return ((sum(point[0] for point in points) / len(points),
                 sum(point[1] for point in points) / len(points)), 0.0)
    return ((cx_sum / (3.0 * cross_sum), cy_sum / (3.0 * cross_sum)),
            abs(cross_sum))


def _geometry_center(parsed):
    weighted = []
    for polygon in parsed["polygons"]:
        if polygon:
            center, weight = _ring_centroid(polygon[0])
            if center:
                weighted.append((center, weight or 1.0))
    if weighted:
        total = sum(item[1] for item in weighted)
        return (sum(item[0][0] * item[1] for item in weighted) / total,
                sum(item[0][1] * item[1] for item in weighted) / total)
    if parsed["points"]:
        return (sum(point[0] for point in parsed["points"]) / len(parsed["points"]),
                sum(point[1] for point in parsed["points"]) / len(parsed["points"]))
    return None


def _geom_center(geom):
    """从 GeoJSON/WKT 几何提取可靠的参考中心，解析失败返回 None。"""
    return _geometry_center(parse_geometry(geom))


def _facility_locations(record):
    locations = []
    for facility in record.get("facilityList") or []:
        point = _as_lng_lat((facility.get("lng"), facility.get("lat")))
        if point:
            locations.append((facility, point[0], point[1]))
    return locations


def extract_center(record):
    """提取空域可视化的参考中心点。

    返回 (lng, lat, anchor):
      anchor="geom"       来自几何字段
      anchor="facility"   无几何, 取 facilityList 第一个设施的坐标
      anchor="none"       无任何坐标信息

    规则: 三级半径(反制/警戒/预警)的圆心固定为 facilityList 中
    第一个有效坐标的设施位置, 而非设施集合的质心。
    """
    # 最外层几何更适合作为整幅图的参考中心。
    for key in ("warningGeom", "alertGeom", "countermeasureGeom"):
        c = _geom_center(record.get(key))
        if c:
            return (c[0], c[1], "geom")
    pts = [(lng, lat) for _, lng, lat in _facility_locations(record)]
    if pts:
        lng, lat = pts[0]
        return (lng, lat, "facility")
    return (None, None, "none")


class MapCanvas(QWidget):
    """等距局部画布: 绘制三级区域、设施、经纬网格和比例尺。"""

    ZONES = (
        ("warningGeom", "warningRadius", COLOR_WARNING, "预警", 40.0),
        ("alertGeom", "alertRadius", COLOR_ALERT, "警戒", -5.0),
        ("countermeasureGeom", "countermeasureRadius", COLOR_COUNTER, "反制", -45.0),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.record = None
        self.center_lng = None
        self.center_lat = None
        self.center_anchor = "none"
        self.zone_geometries = {}
        self.nofly_zones = []
        self.show_nofly = True
        self.setMinimumSize(480, 360)
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(self.backgroundRole(), COLOR_BG)
        self.setPalette(pal)

    def set_record(self, record):
        self.record = record
        lng, lat, anchor = extract_center(record or {})
        self.center_lng, self.center_lat, self.center_anchor = lng, lat, anchor
        self.zone_geometries = {
            geom_key: parse_geometry((record or {}).get(geom_key))
            for geom_key, _, _, _, _ in self.ZONES
        }
        self.update()

    def set_nofly_records(self, records):
        """设置要在同一张地图上叠加显示的禁飞区列表。"""
        self.nofly_zones = []
        for rec in records or []:
            if not isinstance(rec, dict):
                continue
            zone_type = _as_float(rec.get("zoneType"))
            self.nofly_zones.append({
                "record": rec,
                "zone_type": int(zone_type) if zone_type is not None else None,
                "geometry": parse_geometry(rec.get("geom")),
                "center": _as_lng_lat((rec.get("lng"), rec.get("lat"))),
                "radius": _as_float(rec.get("radius")) or 0.0,
            })
        self.update()

    def set_show_nofly(self, show):
        self.show_nofly = bool(show)
        self.update()

    def _paint_geometry_polygons(self, painter, geometry, color, to_px):
        """填充并描边多边形几何 (每多边形: 首环外环, 其余内环)。"""
        fill = QColor(color)
        fill.setAlpha(45)
        for polygon in geometry["polygons"]:
            qt_rings = []
            for ring in polygon:
                points = []
                for lng, lat in ring:
                    mx, my = self._offset_m(lng, lat)
                    points.append(QPoint(*to_px(mx, my)))
                if len(points) >= 3:
                    qt_rings.append(QPolygon(points))
            if not qt_rings:
                continue
            # 使用整数 QRegion 做奇偶填充，可正确保留 GeoJSON 内环。
            region = QRegion(qt_rings[0])
            for hole in qt_rings[1:]:
                region = region.subtracted(QRegion(hole))
            painter.save()
            painter.setClipRegion(region)
            painter.fillRect(self.rect(), fill)
            painter.restore()
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(color, 2))
            for qt_ring in qt_rings:
                painter.drawPolygon(qt_ring)

    @staticmethod
    def _nice_step(value):
        """把任意距离归整为 1/2/5 * 10^n，适用于网格和比例尺。"""
        if not math.isfinite(value) or value <= 0:
            return 1.0
        magnitude = 10 ** math.floor(math.log10(value))
        fraction = value / magnitude
        if fraction <= 1:
            nice = 1
        elif fraction <= 2:
            nice = 2
        elif fraction <= 5:
            nice = 5
        else:
            nice = 10
        return nice * magnitude

    def _offset_m(self, lng, lat):
        meters_per_lng = 111320.0 * math.cos(math.radians(self.center_lat))
        return ((lng - self.center_lng) * meters_per_lng,
                (lat - self.center_lat) * 110540.0)

    def _zone_type(self):
        value = _as_float((self.record or {}).get("zoneType"))
        return int(value) if value is not None else None

    def _zone_radius(self, radius_key):
        radius = _as_float((self.record or {}).get(radius_key))
        return radius if radius is not None and radius > 0 else 0.0

    def _circle_center(self, geometry):
        return _geometry_center(geometry) or (self.center_lng, self.center_lat)

    def _view_extents(self):
        """分别计算东西、南北半宽，确保非方形画布和多边形都能完整入镜。"""
        x_half = y_half = 0.0
        zone_type = self._zone_type()
        for geom_key, radius_key, _, _, _ in self.ZONES:
            geometry = self.zone_geometries[geom_key]
            for polygon in geometry["polygons"]:
                for ring in polygon:
                    for lng, lat in ring:
                        mx, my = self._offset_m(lng, lat)
                        x_half = max(x_half, abs(mx))
                        y_half = max(y_half, abs(my))
            for lng, lat in geometry["points"]:
                mx, my = self._offset_m(lng, lat)
                x_half = max(x_half, abs(mx))
                y_half = max(y_half, abs(my))

            radius = self._zone_radius(radius_key)
            if radius and not geometry["polygons"] and zone_type != 2:
                circle_lng, circle_lat = self._circle_center(geometry)
                mx, my = self._offset_m(circle_lng, circle_lat)
                x_half = max(x_half, abs(mx) + radius)
                y_half = max(y_half, abs(my) + radius)

        for _, lng, lat in _facility_locations(self.record or {}):
            mx, my = self._offset_m(lng, lat)
            x_half = max(x_half, abs(mx))
            y_half = max(y_half, abs(my))

        if self.show_nofly:
            for zone in self.nofly_zones:
                geometry = zone["geometry"]
                for polygon in geometry["polygons"]:
                    for ring in polygon:
                        for lng, lat in ring:
                            mx, my = self._offset_m(lng, lat)
                            x_half = max(x_half, abs(mx))
                            y_half = max(y_half, abs(my))
                for lng, lat in geometry["points"]:
                    mx, my = self._offset_m(lng, lat)
                    x_half = max(x_half, abs(mx))
                    y_half = max(y_half, abs(my))
                radius = zone["radius"]
                if radius and zone["center"] and zone["zone_type"] != 2:
                    mx, my = self._offset_m(*zone["center"])
                    x_half = max(x_half, abs(mx) + radius)
                    y_half = max(y_half, abs(my) + radius)

        # 单点或零半径数据仍给出可读的 500 m 视野，并留出标签边距。
        return max(x_half * 1.18, 500.0), max(y_half * 1.18, 500.0)

    @staticmethod
    def _format_coord(value, positive, negative):
        return "%.5f°%s" % (abs(value), positive if value >= 0 else negative)

    @staticmethod
    def _format_distance(value):
        if abs(value - round(value)) < 1e-6:
            return "%d m" % round(value)
        return "%.1f m" % value

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if not self.record:
            painter.setPen(COLOR_TEXT)
            painter.drawText(self.rect(), Qt.AlignCenter, "无数据，请先查询")
            painter.end()
            return
        if self.center_lng is None:
            painter.setPen(COLOR_TEXT)
            painter.drawText(self.rect(), Qt.AlignCenter,
                             "该空域无坐标数据 (geom 与设施均为空)")
            painter.end()
            return

        w, h = self.width(), self.height()
        x_half, y_half = self._view_extents()
        # 给四周的坐标文字、比例尺与右侧图例预留空间。
        self.px_per_m = min(max(w - 130, 1) / (2 * x_half),
                            max(h - 90, 1) / (2 * y_half))
        clng, clat = self.center_lng, self.center_lat
        cx, cy = int(w / 2), int(h / 2)
        self.cx, self.cy = cx, cy

        def to_px(mx, my):
            # 返回整数像素坐标。
            # 注意: 本机 PyQt5/Qt5.15 (offscreen) 环境下, 抗锯齿开启时使用
            # 浮点坐标画线/椭圆会触发 Qt fail-fast 崩溃 (0xC0000409),
            # 因此所有绘制几何一律取整。
            # 屏幕 y 轴向下，因此北向(正 my)必须减去像素偏移。
            return int(round(cx + mx * self.px_per_m)), \
                int(round(cy - my * self.px_per_m))

        def draw_text_box(x, y, text, color=COLOR_TEXT):
            metrics = painter.fontMetrics()
            rect = metrics.boundingRect(text).adjusted(-3, -2, 3, 2)
            rect.moveTopLeft(QPoint(int(x), int(y - rect.height() / 2)))
            background = QColor(COLOR_BG)
            background.setAlpha(225)
            painter.fillRect(rect, background)
            painter.setPen(color)
            painter.drawText(rect, Qt.AlignCenter, text)

        # --- 经纬度网格 ---
        painter.setPen(QPen(COLOR_GRID, 1, Qt.DotLine))
        painter.setFont(QFont(self.font().family(), 8))
        visible_x = w / (2 * self.px_per_m)
        visible_y = h / (2 * self.px_per_m)
        # 保证相邻坐标标签至少约 100 px，避免当前截图中标签挤成一串。
        step = self._nice_step(100.0 / self.px_per_m)
        mx = math.ceil(-visible_x / step) * step
        while mx <= visible_x + 1e-6:
            x, _ = to_px(mx, 0)
            painter.drawLine(x, 0, x, h)
            lng = clng + mx / (111320.0 * math.cos(math.radians(clat)))
            label = self._format_coord(lng, "E", "W")
            label_width = painter.fontMetrics().horizontalAdvance(label)
            if 3 <= x <= w - label_width - 5:
                painter.setPen(COLOR_GRID_TEXT)
                painter.drawText(x + 3, h - 6, label)
                painter.setPen(QPen(COLOR_GRID, 1, Qt.DotLine))
            mx += step
        my = math.ceil(-visible_y / step) * step
        while my <= visible_y + 1e-6:
            _, y = to_px(0, my)
            painter.drawLine(0, y, w, y)
            lat = clat + my / 110540.0
            # 底部约 50 px 留给经度标签和比例尺。
            if 55 <= y <= h - 52:
                painter.setPen(COLOR_GRID_TEXT)
                painter.drawText(6, y - 4, self._format_coord(lat, "N", "S"))
                painter.setPen(QPen(COLOR_GRID, 1, Qt.DotLine))
            my += step

        # --- 三级区域 (外→内)。多边形优先画真实 geom，圆形才使用半径。 ---
        zone_type = self._zone_type()
        approximate_circle = False
        missing_polygon = False
        invalid_geometry = False
        missing_nofly_geometry = False
        for geom_key, radius_key, color, label, label_angle in self.ZONES:
            raw_geometry = self.record.get(geom_key)
            geometry = self.zone_geometries[geom_key]
            fill = QColor(color)
            fill.setAlpha(45)
            if raw_geometry and not geometry["points"] and not geometry["polygons"]:
                invalid_geometry = True

            if geometry["polygons"]:
                self._paint_geometry_polygons(painter, geometry, color, to_px)
                continue

            if zone_type == 2:
                missing_polygon = True
                continue
            radius = self._zone_radius(radius_key)
            if not radius:
                continue
            circle_lng, circle_lat = self._circle_center(geometry)
            center_mx, center_my = self._offset_m(circle_lng, circle_lat)
            circle_x, circle_y = to_px(center_mx, center_my)
            r_px = max(1, int(round(radius * self.px_per_m)))
            is_approximate = not geometry["points"] and self.center_anchor == "facility"
            approximate_circle = approximate_circle or is_approximate
            pen_style = Qt.DashLine if is_approximate else Qt.SolidLine
            painter.setBrush(fill)
            painter.setPen(QPen(color, 2, pen_style))
            painter.drawEllipse(circle_x - r_px, circle_y - r_px, 2 * r_px, 2 * r_px)

            angle = math.radians(label_angle)
            label_mx = center_mx + radius * math.cos(angle)
            label_my = center_my + radius * math.sin(angle)
            lx, ly = to_px(label_mx, label_my)
            suffix = " (估算)" if is_approximate else ""
            draw_text_box(lx + 6, ly, "%s %s%s" % (
                label, self._format_distance(radius), suffix), color)

        # --- 禁飞区 (叠加在空域之上) ---
        if self.show_nofly:
            for zone in self.nofly_zones:
                geometry = zone["geometry"]
                if geometry["polygons"]:
                    self._paint_geometry_polygons(painter, geometry,
                                                  COLOR_NOFLY, to_px)
                    continue
                if zone["zone_type"] == 2:
                    missing_nofly_geometry = True
                    continue
                if not zone["center"] or not zone["radius"]:
                    missing_nofly_geometry = True
                    continue
                center_mx, center_my = self._offset_m(*zone["center"])
                circle_x, circle_y = to_px(center_mx, center_my)
                r_px = max(1, int(round(zone["radius"] * self.px_per_m)))
                fill = QColor(COLOR_NOFLY)
                fill.setAlpha(40)
                painter.setBrush(fill)
                painter.setPen(QPen(COLOR_NOFLY, 2))
                painter.drawEllipse(circle_x - r_px, circle_y - r_px,
                                    2 * r_px, 2 * r_px)
                angle = math.radians(25.0)
                label_mx = center_mx + zone["radius"] * math.cos(angle)
                label_my = center_my + zone["radius"] * math.sin(angle)
                lx, ly = to_px(label_mx, label_my)
                draw_text_box(lx + 6, ly, "%s %s" % (
                    zone["record"].get("name") or "禁飞区",
                    self._format_distance(zone["radius"])), COLOR_NOFLY)

        # --- 设施点位 ---
        for facility, flng, flat in _facility_locations(self.record):
            mx, my = self._offset_m(flng, flat)
            fx, fy = to_px(mx, my)
            painter.setPen(QPen(COLOR_FACILITY, 2))
            painter.setBrush(COLOR_FACILITY)
            painter.drawEllipse(fx - 4, fy - 4, 8, 8)
            close_to_center = abs(fx - cx) < 12 and abs(fy - cy) < 12
            label_y = fy + 18 if close_to_center else fy
            draw_text_box(fx + 8, label_y,
                          str(facility.get("name") or "设施"), COLOR_FACILITY)

        # --- 参考中心（最后绘制，避免与同坐标设施点相互遮挡） ---
        cpen = QPen(COLOR_CENTER, 3)
        painter.setPen(cpen)
        painter.setBrush(COLOR_CENTER)
        painter.drawEllipse(cx - 5, cy - 5, 10, 10)
        painter.drawLine(cx - 9, cy, cx + 9, cy)
        painter.drawLine(cx, cy - 9, cx, cy + 9)
        anchor_text = "几何中心" if self.center_anchor == "geom" else "参考中心(首个设施)"
        draw_text_box(cx + 10, cy - 16,
                      "%s (%.5f, %.5f)" % (anchor_text, clng, clat), COLOR_TEXT)

        # --- 数据质量提示 ---
        notices = []
        if approximate_circle:
            notices.append("虚线防护圈：接口缺少空域中心，位置按首个设施坐标估算")
        if missing_polygon:
            notices.append("多边形空域缺少有效 geom，未绘制缺失层级")
        if invalid_geometry:
            notices.append("部分 geom 无法解析，请检查 GeoJSON/WKT")
        if missing_nofly_geometry:
            notices.append("部分禁飞区缺少有效坐标/geom，未绘制")
        notice_y = 15
        for notice in notices:
            draw_text_box(12, notice_y, notice, QColor(175, 75, 20))
            notice_y += painter.fontMetrics().height() + 6

        # --- 比例尺 ---
        bar_m = self._nice_step(110.0 / self.px_per_m)
        bar_px = int(round(bar_m * self.px_per_m))
        bx, by = 20, h - 28
        painter.setPen(QPen(COLOR_TEXT, 2))
        painter.drawLine(bx, by, bx + bar_px, by)
        painter.drawLine(bx, by - 5, bx, by + 5)
        painter.drawLine(bx + bar_px, by - 5, bx + bar_px, by + 5)
        painter.setPen(COLOR_TEXT)
        painter.drawText(bx, by - 8, self._format_distance(bar_m))

        # --- 图例 ---
        lx, ly = w - 110, 14
        painter.setPen(Qt.NoPen)
        for color, label in [(COLOR_COUNTER, "反制区"), (COLOR_ALERT, "警戒区"),
                             (COLOR_WARNING, "预警区"), (COLOR_FACILITY, "设施"),
                             (COLOR_NOFLY, "禁飞区")]:
            painter.setBrush(color)
            painter.drawRect(lx, ly, 12, 12)
            painter.setPen(COLOR_TEXT)
            painter.drawText(lx + 18, ly + 11, label)
            painter.setPen(Qt.NoPen)
            ly += 18

        painter.end()


class AirspaceViewer(QMainWindow):
    """主窗口: 筛选/分页/记录选择 + 地图 + 详情。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("空域信息地图可视化 - Apifox /airspace/list")
        self.records = []
        self.total = 0
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        root = QHBoxLayout(central)

        # ===== 左侧控制面板 =====
        panel = QWidget()
        panel.setFixedWidth(290)
        form = QFormLayout(panel)

        self.name_edit = QLineEdit()
        form.addRow("名称:", self.name_edit)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("全部", None)
        self.mode_combo.addItem("平时模式(1)", 1)
        self.mode_combo.addItem("战时模式(2)", 2)
        form.addRow("防控模式:", self.mode_combo)

        self.zone_combo = QComboBox()
        self.zone_combo.addItem("全部", None)
        self.zone_combo.addItem("圆形(1)", 1)
        self.zone_combo.addItem("多边形(2)", 2)
        form.addRow("划设类型:", self.zone_combo)

        self.enabled_combo = QComboBox()
        self.enabled_combo.addItem("全部", None)
        self.enabled_combo.addItem("可用", True)
        self.enabled_combo.addItem("不可用", False)
        form.addRow("是否可用:", self.enabled_combo)

        page_row = QHBoxLayout()
        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.setValue(1)
        self.page_size_spin = QSpinBox()
        self.page_size_spin.setMinimum(1)
        self.page_size_spin.setMaximum(200)
        self.page_size_spin.setValue(20)
        page_row.addWidget(QLabel("页码:"))
        page_row.addWidget(self.page_spin)
        page_row.addWidget(QLabel("每页:"))
        page_row.addWidget(self.page_size_spin)
        form.addRow(page_row)

        self.query_btn = QPushButton("查询")
        self.query_btn.clicked.connect(self.fetch_data)
        form.addRow(self.query_btn)

        self.nofly_check = QCheckBox("显示禁飞区")
        self.nofly_check.setChecked(True)
        form.addRow(self.nofly_check)

        form.addRow(QLabel("选择记录:"))
        self.record_combo = QComboBox()
        self.record_combo.currentIndexChanged.connect(self.on_record_changed)
        form.addRow(self.record_combo)

        self.status_label = QLabel("未查询")
        self.status_label.setWordWrap(True)
        form.addRow(self.status_label)

        panel.setLayout(form)
        root.addWidget(panel)

        # ===== 右侧: 地图 + 详情 =====
        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.canvas = MapCanvas()
        self.nofly_check.toggled.connect(self.canvas.set_show_nofly)
        right_layout.addWidget(self.canvas, stretch=3)

        self.detail_view = QPlainTextEdit()
        self.detail_view.setReadOnly(True)
        self.detail_view.setMaximumHeight(230)
        # 跟随已注册的应用字体，避免 offscreen 环境指定不存在的 Consolas 后文字消失。
        self.detail_view.setFont(QFont(QApplication.font().family(), 9))
        right_layout.addWidget(self.detail_view, stretch=1)

        root.addWidget(right, stretch=1)
        self.setCentralWidget(central)
        self.resize(1080, 720)

    # ---------- 数据 ----------
    def fetch_data(self):
        """按筛选条件 + 分页拉取数据。"""
        self.status_label.setText("查询中...")
        QApplication.processEvents()
        name = self.name_edit.text().strip() or None
        mode = self.mode_combo.currentData()
        zone = self.zone_combo.currentData()
        enabled = self.enabled_combo.currentData()
        try:
            data = fetch_airspace_list(
                page=self.page_spin.value(),
                page_size=self.page_size_spin.value(),
                name=name, prevention_mode=mode, zone_type=zone,
                enabled=enabled)
        except Exception as e:  # 网络/接口异常
            self.status_label.setText("查询失败: %s" % e)
            return
        if not isinstance(data, dict):
            self.status_label.setText("接口返回异常: 响应不是 JSON 对象")
            return
        if str(data.get("code")) != "0":
            self.status_label.setText("接口返回异常: %s" % data.get("message"))
            return

        body = data.get("data") or {}
        if not isinstance(body, dict) or not isinstance(body.get("list") or [], list):
            self.status_label.setText("接口返回异常: data.list 不是数组")
            return
        self.records = [record for record in (body.get("list") or [])
                        if isinstance(record, dict)]
        total = _as_float(body.get("total"))
        self.total = max(0, int(total)) if total is not None else len(self.records)

        pages = max(1, math.ceil(self.total / self.page_size_spin.value()))
        self.status_label.setText(
            "共 %d 条 / 第 %d 页(共 %d 页)" % (self.total, self.page_spin.value(), pages))

        # 禁飞区列表: 一次拉全量(每页上限 200)叠加到地图上, 失败不阻塞空域展示。
        try:
            nofly_data = fetch_nofly_list(page=1, page_size=200)
        except Exception as e:
            self.status_label.setText(self.status_label.text()
                                      + " | 禁飞区获取失败: %s" % e.__class__.__name__)
            nofly_records = []
        else:
            body = (nofly_data or {}).get("data") or {}
            if not isinstance(nofly_data, dict) or str(nofly_data.get("code")) != "0":
                self.status_label.setText(self.status_label.text() + " | 禁飞区接口异常")
                nofly_records = []
            else:
                nofly_records = [record for record in (body.get("list") or [])
                                 if isinstance(record, dict)]
                self.status_label.setText(self.status_label.text()
                                          + " | 禁飞区 %d 个" % len(nofly_records))
        self.canvas.set_nofly_records(nofly_records)

        self.record_combo.blockSignals(True)
        self.record_combo.clear()
        for i, rec in enumerate(self.records, 1):
            name_ = rec.get("name") or "(无名)"
            self.record_combo.addItem("%d. %s (id:%s)" % (i, name_, rec.get("id")), rec)
        self.record_combo.blockSignals(False)

        if self.records:
            # 注意: clear() 后索引已是 0, setCurrentIndex(0) 不会触发信号,
            # 需手动调用选择回调。
            self.record_combo.setCurrentIndex(0)
            self.on_record_changed(0)
        else:
            self.canvas.set_record(None)
            self.detail_view.clear()
            self.detail_view.setPlainText("无数据")

    def on_record_changed(self, index):
        if index < 0 or index >= len(self.records):
            return
        rec = self.records[index]
        self.canvas.set_record(rec)
        self.detail_view.setPlainText(self._format_detail(rec))

    @staticmethod
    def _format_detail(rec):
        zone_type_value = _as_float(rec.get("zoneType"))
        zone_type_value = int(zone_type_value) if zone_type_value is not None else None
        mode_value = _as_float(rec.get("preventionMode"))
        mode_value = int(mode_value) if mode_value is not None else None
        zone_type = ZONE_TYPE_MAP.get(zone_type_value, rec.get("zoneType"))
        mode = PREVENTION_MODE_MAP.get(mode_value, rec.get("preventionMode"))
        lng, lat, anchor = extract_center(rec)
        if anchor == "geom":
            center_text = "(%.6f, %.6f) [几何中心]" % (lng, lat)
        elif anchor == "facility":
            center_text = "(%.6f, %.6f) [参考中心: 首个设施]" % (lng, lat)
        else:
            center_text = "无坐标数据 (geom 与设施均为空)"
        lines = [
            "名称: %s" % rec.get("name"),
            "ID: %s" % rec.get("id"),
            "场景 scene: %s" % rec.get("scene"),
            "防控级别 controlLevel: %s" % rec.get("controlLevel"),
            "划设类型 zoneType: %s" % zone_type,
            "防控模式 preventionMode: %s" % mode,
            "高度范围: %s ~ %s m" % (rec.get("altitudeMin"), rec.get("altitudeMax")),
            "三级半径: 反制 %s m | 警戒 %s m | 预警 %s m" % (
                rec.get("countermeasureRadius"), rec.get("alertRadius"),
                rec.get("warningRadius")),
            "中心点: %s" % center_text,
        ]
        geometry_states = []
        for key in ("countermeasureGeom", "alertGeom", "warningGeom"):
            if not rec.get(key):
                continue
            parsed = parse_geometry(rec.get(key))
            state = "有效" if parsed["points"] or parsed["polygons"] else "无法解析"
            geometry_states.append("%s=%s" % (key, state))
        if geometry_states:
            lines.append("几何数据: %s" % ", ".join(geometry_states))
        else:
            lines.append("几何数据: 无 (创建空域时未写入 geom)")
        facilities = rec.get("facilityList") or []
        if facilities:
            lines.append("设施 %d 个:" % len(facilities))
            for facility in facilities:
                point = _as_lng_lat((facility.get("lng"), facility.get("lat")))
                if point:
                    location = "%.6f, %.6f" % point
                else:
                    location = "坐标无效"
                lines.append("  - %s (%s)" % (facility.get("name"), location))
        return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="空域信息地图可视化")
    parser.add_argument("--screenshot", help="自测模式: 截图到指定路径后退出")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    configure_application_font(app)
    app.setStyle("Fusion")
    viewer = AirspaceViewer()
    viewer.show()
    viewer.fetch_data()

    if args.screenshot:
        def shot():
            viewer.grab().save(args.screenshot)
            app.quit()
        QTimer.singleShot(2000, shot)

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
